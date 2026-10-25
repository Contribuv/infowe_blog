"""登录态、密码与会话辅助。"""

from __future__ import annotations

import time
from functools import wraps

from flask import flash, redirect, request, session, url_for

import db
from models import User

LOCK_SECONDS = 300
MAX_FAILS = 5
CAPTCHA_AFTER = 3


def is_admin() -> bool:
    uid = session.get("admin_id")
    if not uid:
        return False
    return User.get(int(uid)) is not None


def current_user() -> dict | None:
    uid = session.get("admin_id")
    return User.get(int(uid)) if uid else None


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_admin():
            target = request.full_path if request.query_string else request.path
            return redirect(url_for("admin_login", next=target))
        return view(*args, **kwargs)

    return wrapped


def _row(ip: str) -> dict:
    row = db.one("SELECT * FROM login_attempts WHERE ip = ?", (ip,))
    return dict(row) if row else {"ip": ip, "fail_count": 0, "last_at": 0, "locked_until": 0}


def check_blocked(ip: str) -> int:
    """返回剩余锁定秒数；0 表示未锁定。"""
    data = _row(ip)
    left = float(data.get("locked_until") or 0) - time.time()
    return max(0, int(left))


def captcha_required(ip: str) -> bool:
    return int(_row(ip).get("fail_count") or 0) >= CAPTCHA_AFTER


def register_failure(ip: str) -> None:
    data = _row(ip)
    fails = int(data.get("fail_count") or 0) + 1
    locked_until = time.time() + LOCK_SECONDS if fails >= MAX_FAILS else 0
    db.execute(
        "INSERT INTO login_attempts (ip, fail_count, last_at, locked_until) VALUES (?,?,?,?) "
        "ON CONFLICT(ip) DO UPDATE SET fail_count=excluded.fail_count, last_at=excluded.last_at, "
        "locked_until=excluded.locked_until",
        (ip, fails, time.time(), locked_until),
    )


def register_success(ip: str) -> None:
    db.execute("DELETE FROM login_attempts WHERE ip = ?", (ip,))


def attempt(username: str, password: str, ip: str) -> tuple[str, str]:
    """返回 (状态, 提示)。状态：ok / otp / error / locked。"""
    left = check_blocked(ip)
    if left:
        return "locked", f"尝试次数过多，请 {left} 秒后再试"
    user = User.verify(username.strip(), password)
    if not user:
        register_failure(ip)
        return "error", "账号或密码错误"
    register_success(ip)

    from services import otp

    if otp.enabled():
        session["otp_pending"] = int(user["id"])
        session["otp_started"] = int(time.time())
        return "otp", ""
    session.clear()
    session["admin_id"] = int(user["id"])
    session.permanent = True
    return "ok", ""


def finish_otp() -> None:
    uid = session.pop("otp_pending", None)
    session.pop("otp_started", None)
    if uid:
        session["admin_id"] = int(uid)
        session.permanent = True


def logout() -> None:
    session.clear()
