"""SMTP 邮件与评论通知。

通知规则（blogger = 博主本人）：
- 博主自己评论 / 回复：不再给自己发「新评论」邮件，只在回复访客时通知对方；
- 访客评论：给博主发一封（待审核的兼作审核提醒）；
- 访客回复访客：给博主发一封；被回复者的「收到回复」邮件等到评论审核通过后再发；
- 同一收件人只发一封，私密评论、回复自己的评论都不发通知。
"""

from __future__ import annotations

import smtplib
import threading

from email.message import EmailMessage
from email.utils import formataddr

import db
from services import mail_template, settings, site_url

_SMTP_PORTS = {25: False, 465: True, 587: False, 994: True}

# 邮件里的评论/回复正文展示真实内容（否则通知邮件失去意义）；
# 仅命中屏蔽词或已被拒绝的评论不外发原文，只提示到后台查看。
_PLACEHOLDER_BAD = "【不当言语】请后台审核"


def _mail_content(content: str, status: str = "") -> str:
    """生成邮件中展示的评论正文：正常内容原样展示，敏感/拒绝内容只放提示。"""
    from services import sensitive

    if (status or "").strip().lower() == "rejected" or sensitive.has(content or ""):
        return _PLACEHOLDER_BAD
    return content or ""


def send(
    to: str,
    subject: str,
    body: str,
    html: str | None = None,
    reply_to: str = "",
) -> tuple[bool, str]:
    """发送邮件；html 不为空时按 multipart/alternative 带上 HTML 版本。"""
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

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((sender, user))
    msg["To"] = to
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body or "")
    if html:
        msg.add_alternative(html, subtype="html")

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


# ── 收件人判定 ──────────────────────────────────────────
def _admin_to() -> str:
    return (
        settings.get_str("notify_email", "").strip()
        or settings.get_str("contact_email", "").strip()
    )


def _blogger_emails() -> set[str]:
    emails = {
        settings.get_str("notify_email", "").strip().lower(),
        settings.get_str("contact_email", "").strip().lower(),
    }
    emails.discard("")
    return emails


def _is_blogger(email: str, author: str = "", is_admin: bool = False) -> bool:
    if is_admin:
        return True
    blogger_name = settings.get_str("author", "").strip()
    if blogger_name and author and author.strip() == blogger_name:
        return True
    return (email or "").strip().lower() in _blogger_emails()


def _detail_url(detail_path: str, comment_id: int | None) -> str:
    base = site_url.base()
    path = detail_path if detail_path.startswith("/") else "/" + detail_path
    anchor = f"#comment-{comment_id}" if comment_id else "#comments"
    return base + path + anchor


def _dispatch(jobs: list[dict]) -> None:
    """邮件放到后台线程发送，失败静默，不阻塞请求。"""
    if not jobs:
        return
    from flask import current_app

    app = current_app._get_current_object()

    def _run() -> None:
        # 线程没有请求上下文，必须显式推入应用上下文才能读取 settings
        with app.app_context():
            for job in jobs:
                send(
                    job["to"],
                    job["subject"],
                    job["text"],
                    job.get("html"),
                    job.get("reply_to", ""),
                )

    threading.Thread(target=_run, daemon=True).start()


def _comment_title(project_id: int | None, post_id: int | None) -> tuple[str, str, str]:
    """返回 (label, title, detail_path)。"""
    import db

    if project_id:
        row = db.one("SELECT name FROM projects WHERE id = ?", (project_id,))
        return "项目", str(row["name"] if row else "项目"), f"/projects/{project_id}"
    row = db.one("SELECT title FROM posts WHERE id = ?", (post_id,))
    return "文章", str(row["title"] if row else "文章"), f"/post/{post_id}"


# ── 评论通知 ────────────────────────────────────────────
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
    comment_id: int | None = None,
    is_admin: bool = False,
    is_private: bool = False,
) -> None:
    """提交评论后的通知：博主提醒 + （已通过时）被回复者提醒。"""
    if not settings.bool_of("comment_notify", True):
        return

    blog = settings.get_str("blog_name", "博客").strip() or "博客"
    site = site_url.base()
    url = _detail_url(detail_path, comment_id)
    when = db.now()
    commenter = (email or "").strip()

    parent_author = ""
    parent_content = ""
    reply_email = ""
    reply_private = False
    reply_notify = True
    if parent_id:
        parent = db.one(
            "SELECT author, email, content, is_private, notify, status FROM comments "
            "WHERE id = ? AND deleted_at IS NULL",
            (parent_id,),
        )
        if parent:
            parent_author = str(parent["author"] or "")
            # 博主提醒邮件里要展示被回复的原评论，与回复正文同一套外发规则
            parent_content = _mail_content(str(parent["content"] or ""), str(parent["status"] or ""))
            reply_email = str(parent["email"] or "").strip()
            reply_private = bool(int(parent["is_private"] or 0))
            # 被回复者提交时取消了「邮箱通知」→ 不再发回复邮件（旧数据默认 1）
            reply_notify = bool(int(parent["notify"] if parent["notify"] is not None else 1))

    jobs: list[dict] = []
    admin_to = _admin_to()
    from_blogger = _is_blogger(commenter, author, is_admin)

    author_avatar = ""
    try:
        from services import avatar
        if email:
            h = avatar.email_hash(email)
            qq = avatar.qq_from_email(email)
            if h or qq:
                a, _ = avatar.urls(h, qq)
                author_avatar = site + a if a and a.startswith('/') else a
    except Exception:
        pass

    # 1) 博主提醒：博主自己发言不再发给自己
    if admin_to and not from_blogger:
        text, page = mail_template.comment_notice(
            blog_name=blog,
            site=site,
            label=label,
            title=title,
            url=url,
            author=author,
            content=_mail_content(content, status),
            when=when,
            status=status,
            parent_author=parent_author,
            parent_content=parent_content,
            author_avatar=author_avatar,
        )
        review = "待审核" if status != "approved" else "已通过"
        jobs.append(
            {
                "to": admin_to,
                "subject": f"[{blog}] {label}《{title}》收到新评论（{review}）",
                "text": text,
                "html": page,
                "reply_to": commenter,
            }
        )

    # 2) 被回复者提醒：仅评论已公开、非私密、对方不是博主本人、也不是自己回自己，
    #    且被回复者提交时保留了「邮箱通知」（notify=0 表示他不要邮件提醒）
    if status == "approved" and reply_email and reply_notify and not reply_private and not is_private:
        reply_lower = reply_email.lower()
        if reply_lower not in _blogger_emails() and reply_lower != commenter.lower():
            text, page = mail_template.reply_notice(
                blog_name=blog,
                site=site,
                label=label,
                title=title,
                url=url,
                author=author,
                content=_mail_content(content, status),
                when=when,
                parent_author=parent_author,
                parent_content=parent_content,
                author_avatar=author_avatar,
            )
            jobs.append(
                {
                    "to": reply_email,
                    "subject": f"[{blog}] 你的评论收到了回复：{title}",
                    "text": text,
                    "html": page,
                }
            )

    _dispatch(jobs)


def notify_approved_reply(comment_id: int) -> None:
    """评论审核通过后，补发「收到回复」邮件给被回复的访客。"""
    if not settings.bool_of("comment_notify", True):
        return

    from models import Comment

    comment = Comment.get(int(comment_id))
    if not comment or comment.get("status") != "approved":
        return
    if int(comment.get("is_private") or 0):
        return
    parent_id = comment.get("parent_id")
    if not parent_id:
        return

    parent = Comment.get(int(parent_id))
    if not parent or int(parent.get("is_private") or 0):
        return
    # 被回复者提交时取消了「邮箱通知」→ 审核通过后也不再补发
    if not int(parent.get("notify") if parent.get("notify") is not None else 1):
        return
    reply_email = str(parent.get("email") or "").strip()
    commenter_email = str(comment.get("email") or "").strip()
    if not reply_email:
        return
    if reply_email.lower() in _blogger_emails():
        return
    if reply_email.lower() == commenter_email.lower():
        return

    blog = settings.get_str("blog_name", "博客").strip() or "博客"
    label, title, detail_path = _comment_title(
        comment.get("project_id"), comment.get("post_id")
    )
    author_avatar = ""
    try:
        from services import avatar
        cemail = str(comment.get("email") or "").strip()
        if cemail:
            h = avatar.email_hash(cemail)
            qq = avatar.qq_from_email(cemail)
            if h or qq:
                a, _ = avatar.urls(h, qq)
                base = site_url.base()
                author_avatar = base + a if a and a.startswith('/') else a
    except Exception:
        pass
    text, page = mail_template.reply_notice(
        blog_name=blog,
        site=site_url.base(),
        label=label,
        title=title,
        url=_detail_url(detail_path, int(comment_id)),
        author=str(comment.get("author") or ""),
        content=_mail_content(str(comment.get("content") or ""), "approved"),
        when=str(comment.get("created_at") or ""),
        parent_author=str(parent.get("author") or ""),
        parent_content=_mail_content(
            str(parent.get("content") or ""), str(parent.get("status") or "")
        ),
        author_avatar=author_avatar,
    )
    _dispatch(
        [
            {
                "to": reply_email,
                "subject": f"[{blog}] 你的评论收到了回复：{title}",
                "text": text,
                "html": page,
            }
        ]
    )
