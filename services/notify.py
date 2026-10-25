"""SMTP 邮件与评论通知。"""

from __future__ import annotations

import smtplib
import threading
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

from services import settings, site_url

_SMTP_PORTS = {25: False, 465: True, 587: False, 994: True}


def send(to: str, subject: str, body: str) -> tuple[bool, str]:
    host = settings.get_str("smtp_host", "").strip()
    user = settings.get_str("smtp_user", "").strip()
    password = settings.get_str("smtp_pass", "")
    sender = settings.get_str("smtp_sender_name", "").strip() or user
    if not host or not user:
        return False, "未配置 SMTP"
    try:
        port = int(settings.get_str("smtp_port", "465") or 465)
    except ValueError:
        port = 465
    use_ssl = _SMTP_PORTS.get(port, port == 465)
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header(sender, "utf-8")), user))
    msg["To"] = to
    timeout = settings.get_int("smtp_timeout", 10)
    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=timeout)
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
            try:
                server.starttls()
            except smtplib.SMTPException:
                pass
        with server:
            if user and password:
                server.login(user, password)
            server.sendmail(user, [to], msg.as_string())
        return True, "发送成功"
    except Exception as exc:  # noqa: BLE001
        return False, f"发送失败：{exc}"


def notify_comment(
    post_id: int | None,
    project_id: int | None,
    title: str,
    author: str,
    content: str,
    parent_id: int | None,
    email: str,
    status: str,
    detail_path: str,
    label: str = "文章",
) -> None:
    admin_to = settings.get_str("notify_email", "").strip()
    if not admin_to:
        return
    details = f"{site_url.base()}{detail_path}"
    review = "待审核" if status == "pending" else "已通过"
    body = (
        f"你的{label}《{title}》收到新评论（{review}）\n\n"
        f"昵称：{author}\n邮箱：{email or '（未填写）'}\n\n"
        f"{content}\n\n查看：{details}\n"
    )
    subject = f"[{settings.get_str('blog_name', '博客')}] {label}《{title}》收到新评论"

    # 在请求上下文内取出被回复者邮箱，线程中不再访问数据库
    reply_to = ""
    if parent_id:
        import db

        parent = db.one("SELECT author, email FROM comments WHERE id = ?", (parent_id,))
        if parent and parent["email"] and parent["email"].lower() != admin_to.lower():
            reply_to = parent["email"]

    from flask import current_app

    app = current_app._get_current_object()

    def _send() -> None:
        # 线程没有请求上下文，必须显式推入应用上下文才能读取 settings
        with app.app_context():
            send(admin_to, subject, body)
            if reply_to:
                reply_body = (
                    f"你在{label}《{title}》的评论收到了回复\n\n"
                    f"{author}：{content}\n\n查看：{details}\n"
                )
                send(reply_to, f"回复通知：{title}", reply_body)

    threading.Thread(target=_send, daemon=True).start()
