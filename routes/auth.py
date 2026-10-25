"""后台认证路由：登录、OTP、找回密码。"""

from __future__ import annotations

import random
import time
from datetime import datetime, timedelta

from flask import flash, jsonify, redirect, render_template, request, session, url_for

from models import User
from services import auth, notify, otp, settings
from services.comments import request_ip


def _captcha_question() -> str:
    a, b = random.randint(1, 9), random.randint(1, 9)
    session["captcha_answer"] = a + b
    return f"{a} + {b}"


def admin_index():
    if auth.is_admin():
        return redirect(url_for("admin_dashboard"))
    if session.get("otp_pending"):
        return redirect(url_for("admin_otp"))
    return redirect(url_for("admin_login"))


def admin_login():
    if auth.is_admin():
        return redirect(url_for("admin_dashboard"))
    if session.get("otp_pending"):
        return redirect(url_for("admin_otp"))

    ip = request_ip()
    blocked = auth.check_blocked(ip)
    if blocked:
        return render_template(
            "admin/login.html",
            error=f"尝试次数过多，请 {blocked // 60 + 1} 分钟后再试",
            captcha_required=False,
            captcha_question=None,
        )
    required = auth.captcha_required(ip)
    if required:
        if not session.get("captcha_answer"):
            session["_captcha_q"] = _captcha_question()
        question = session.get("_captcha_q")
    else:
        question = None

    error = None
    if request.method == "POST":
        if required:
            answer = request.form.get("captcha", "").strip()
            if not answer.isdigit() or int(answer) != session.get("captcha_answer"):
                auth.register_failure(ip)
                error = "验证码错误"
                question = _captcha_question()
                session["_captcha_q"] = question
                return render_template(
                    "admin/login.html", error=error, captcha_required=True, captcha_question=question
                )

        username = request.form.get("username", "")
        password = request.form.get("password", "")
        status, message = auth.attempt(username, password, ip)
        if status == "ok":
            session.pop("captcha_answer", None)
            session.pop("_captcha_q", None)
            return redirect(url_for("admin_dashboard"))
        if status == "otp":
            return redirect(url_for("admin_otp"))
        error = message
        if auth.captcha_required(ip):
            required = True
            question = _captcha_question()
            session["_captcha_q"] = question
        if auth.check_blocked(ip):
            error = "尝试次数过多，请 5 分钟后再试"

    if blocked:
        error = error or "尝试次数过多，请 5 分钟后再试"
    return render_template(
        "admin/login.html",
        error=error,
        captcha_required=required,
        captcha_question=question,
    )


def admin_logout():
    auth.logout()
    return redirect(url_for("admin_login"))


def admin_otp():
    if auth.is_admin():
        return redirect(url_for("admin_dashboard"))
    uid = session.get("otp_pending")
    if not uid:
        return redirect(url_for("admin_login"))
    if not otp.enabled():
        auth.finish_otp()
        return redirect(url_for("admin_dashboard"))

    user = User.get(int(uid))
    username = user["username"] if user else "admin"
    error = None
    if request.method == "POST":
        code = (request.form.get("code") or "").strip()
        if not code:
            error = "请输入验证码或恢复码"
        elif otp.consume_recovery(code) or otp.verify(otp.secret(), code):
            auth.finish_otp()
            return redirect(url_for("admin_dashboard"))
        else:
            auth.register_failure(request_ip())
            error = "验证码或恢复码错误"

    return render_template(
        "admin/otp.html",
        error=error,
        user=username,
        recovery_left=otp.recovery_remaining(),
        mail_ok=bool(settings.get_str("smtp_host", "")),
    )


def admin_otp_recover():
    if auth.is_admin():
        return redirect(url_for("admin_dashboard"))
    uid = session.get("otp_pending")
    if not uid:
        return redirect(url_for("admin_login"))
    user = User.get(int(uid))
    username = user["username"] if user else "admin"
    target = settings.get_str("notify_email", "").strip() or settings.get_str("contact_email", "").strip()

    step = "send"
    sent = False
    error = None
    if not settings.get_str("smtp_host", "").strip():
        return render_template(
            "admin/otp_recover.html",
            user=username, step="unavailable", target="", sent=False,
            error="服务器未配置 SMTP，无法邮件找回。可用恢复码登录。",
        )

    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "send":
            if not target:
                error = "管理员未设置联系邮箱，无法接收验证码"
            else:
                last = int(session.get("_otp_mail_ts") or 0)
                if time.time() - last < 60:
                    error = f"发送过于频繁，请 {int(60 - (time.time() - last))} 秒后再试"
                else:
                    code = f"{random.randint(0, 999999):06d}"
                    ok, message = notify.send(
                        target,
                        f"[{settings.get_str('blog_name', 'Blog')}] OTP 找回验证码",
                        f"你的博客后台 OTP 双重验证已丢失，验证码：{code}\n10 分钟内有效。",
                    )
                    if ok:
                        session["_otp_mail_code"] = code
                        session["_otp_mail_ts"] = int(time.time())
                        sent, step = True, "verify"
                    else:
                        error = message
        elif action == "verify":
            step = "verify"
            code = (request.form.get("mail_code") or "").strip()
            issued = str(session.get("_otp_mail_code") or "")
            issued_ts = int(session.get("_otp_mail_ts") or 0)
            if not issued or time.time() - issued_ts > 600:
                error, step = "验证码已过期，请重新发送", "send"
            elif code != issued:
                auth.register_failure(request_ip())
                error = "验证码错误"
            else:
                session.pop("_otp_mail_code", None)
                session.pop("_otp_mail_ts", None)
                otp.reset()
                auth.finish_otp()
                flash("邮箱验证通过，OTP 已临时关闭。", "success")
                return redirect(url_for("admin_settings"))

    def mask(addr: str) -> str:
        if "@" not in addr:
            return ""
        local, domain = addr.split("@", 1)
        return (local[:2] or "**") + "***@" + domain

    return render_template(
        "admin/otp_recover.html",
        user=username, step=step, target=target, masked=mask(target), sent=sent, error=error,
    )


def admin_forgot():
    if auth.is_admin():
        return redirect(url_for("admin_dashboard"))
    target = settings.get_str("notify_email", "").strip() or settings.get_str("contact_email", "").strip()
    sole = User.first()
    if not settings.get_str("smtp_host", "").strip():
        return render_template(
            "admin/forgot.html", step="unavailable", masked="", error="服务器未配置 SMTP，无法通过邮件找回密码。",
        )

    step = "send"
    error = None
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "send":
            if not sole:
                error = "未找到管理员账号，无法找回"
            elif not target:
                error = "管理员未设置联系邮箱，无法接收验证码"
            else:
                last = int(session.get("_fp_ts") or 0)
                if time.time() - last < 60:
                    error = f"发送过于频繁，请 {int(60 - (time.time() - last))} 秒后再试"
                else:
                    code = f"{random.randint(0, 999999):06d}"
                    ok, message = notify.send(
                        target,
                        f"[{settings.get_str('blog_name', 'Blog')}] 后台密码找回验证码",
                        f"重置后台账号「{sole['username']}」密码的验证码：{code}\n10 分钟内有效。",
                    )
                    if ok:
                        session["_fp_code"] = code
                        session["_fp_ts"] = int(time.time())
                        session["_fp_user"] = sole["username"]
                        session.pop("_fp_ok", None)
                        step = "verify"
                    else:
                        error = message
        elif action == "verify":
            step = "verify"
            code = (request.form.get("mail_code") or "").strip()
            issued = str(session.get("_fp_code") or "")
            issued_ts = int(session.get("_fp_ts") or 0)
            if not issued or time.time() - issued_ts > 600:
                error, step = "验证码已过期，请重新发送", "send"
            elif code != issued:
                auth.register_failure(request_ip())
                error = "验证码错误"
            else:
                session["_fp_ok"] = True
                step = "newpass"
        elif action == "newpass":
            session_ok = session.get("_fp_ok") and session.get("_fp_code")
            issued_ts = int(session.get("_fp_ts") or 0)
            if not session_ok or time.time() - issued_ts > 600:
                error, step = "操作已超时，请重新走找回流程", "send"
            else:
                pwd = request.form.get("new_password", "")
                pwd2 = request.form.get("new_password2", "")
                if len(pwd) < 6:
                    error, step = "新密码至少 6 位字符", "newpass"
                elif pwd != pwd2:
                    error, step = "两次输入的密码不一致", "newpass"
                else:
                    user = User.get_by_username(str(session.get("_fp_user") or ""))
                    if not user:
                        error, step = "账号不存在，无法重置", "newpass"
                    else:
                        User.update_password(int(user["id"]), pwd)
                        for key in ("_fp_code", "_fp_ts", "_fp_ok", "_fp_user"):
                            session.pop(key, None)
                        flash("密码已重置，请使用新密码登录", "success")
                        return redirect(url_for("admin_login"))

    def mask(addr: str) -> str:
        if "@" not in addr:
            return ""
        local, domain = addr.split("@", 1)
        return (local[:2] or "**") + "***@" + domain

    return render_template(
        "admin/forgot.html", step=step, masked=mask(target), fp_user=sole["username"] if sole else "", error=error,
    )


def admin_otp_setup():
    if not auth.is_admin():
        return jsonify({"error": "未登录"}), 403
    secret = otp.new_secret()
    user = auth.current_user()
    return jsonify({"secret": secret, "uri": otp.otpauth_uri(secret, user["username"] if user else "admin")})


def admin_otp_clear_emergency():
    if not auth.is_admin():
        return redirect(url_for("admin_login"))
    from config import DATA_DIR

    marker = DATA_DIR / ".otp_disable"
    if marker.is_file():
        marker.unlink(missing_ok=True)
        flash("OTP 紧急禁用标记已清除", "success")
    else:
        flash("标记文件不存在", "error")
    return redirect(url_for("admin_settings"))


def register(app) -> None:
    rules = [
        ("/admin", "admin_index", admin_index, ["GET"]),
        ("/admin/login", "admin_login", admin_login, ["GET", "POST"]),
        ("/admin/logout", "admin_logout", admin_logout, ["GET"]),
        ("/admin/otp", "admin_otp", admin_otp, ["GET", "POST"]),
        ("/admin/otp/recover", "admin_otp_recover", admin_otp_recover, ["GET", "POST"]),
        ("/admin/forgot", "admin_forgot", admin_forgot, ["GET", "POST"]),
        ("/admin/otp/setup", "admin_otp_setup", admin_otp_setup, ["GET"]),
        ("/admin/otp/clear-emergency", "admin_otp_clear_emergency", admin_otp_clear_emergency, ["POST"]),
    ]
    for rule, endpoint, view, methods in rules:
        app.add_url_rule(rule, endpoint=endpoint, view_func=view, methods=methods)
