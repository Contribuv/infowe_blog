"""评论提交、冷却与渲染。"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from flask import request
from markupsafe import Markup

from config import CACHE_DIR
from services import avatar, ip_location, sensitive, site_url, upload
from services import settings

COOLDOWN = 30
VIEW_COOLDOWN = 60
MAX_IMAGES = 6
_IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# 冷却统一走 services.ratelimit（SQLite 表），不再用进程内字典：
# gunicorn 多 worker 下内存字典各自一份，限流等于没有。


def open_comments() -> bool:
    return settings.bool_of("comments_enabled", True)


def image_upload_on() -> bool:
    return settings.bool_of("comment_image_upload", True)


def render_content(content: str) -> Markup:
    import html

    escaped = html.escape(content or "", quote=True)

    def repl(match: re.Match) -> str:
        alt, path = match.group(1), match.group(2)
        ext = Path(urlparse(path).path).suffix.lower()
        if ext not in _IMG_EXTS:
            return match.group(0)
        return f'<img class="cmt-img" src="{path}" alt="{alt}" loading="lazy">'

    return Markup(re.sub(r"!\[([^\]]*)\]\((/uploads/[^\s()<>\"']+)\)", repl, escaped))


def normalize_email(email: str) -> str:
    email = (email or "").strip()
    return email + "@qq.com" if re.fullmatch(r"\d{5,12}", email) else email


def normalize_website(website: str) -> str | None:
    website = (website or "").strip()
    if not website:
        return ""
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", website):
        scheme = website.split("://", 1)[0].lower()
        if scheme not in {"http", "https"}:
            return None
    elif re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:", website):
        scheme = website.split(":", 1)[0]
        if "." not in scheme:
            return None
        website = "https://" + website
    else:
        website = "https://" + website
    if not re.match(r"^https?://\S+$", website, re.I) or len(website) > 200:
        return None
    return website


def merge_images(content: str, raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return content
    urls: list[str] = []
    for line in re.split(r"[\r\n]+", raw):
        url = line.strip()
        if not url or not re.fullmatch(r"/uploads/comment/\d{4}/\d{2}/[A-Za-z0-9_.\-]+", url):
            continue
        if Path(url).suffix.lower() not in _IMG_EXTS:
            continue
        if upload.resolve(url[len("/uploads/"):]) is None:
            continue
        if url not in urls:
            urls.append(url)
        if len(urls) >= MAX_IMAGES:
            break
    if not urls:
        return content
    markers = "\n".join(f"![图片]({url})" for url in urls)
    return (content.rstrip() + "\n" + markers).strip()


def commenter() -> dict:
    raw = request.cookies.get("blog_commenter", "")
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def _cooldown_allowed(bucket: str, key: str, window: int) -> bool:
    from services import ratelimit

    return ratelimit.allow(bucket, key, window, 1)


def _touch_cooldown(bucket: str, key: str) -> None:
    from services import ratelimit

    ratelimit.touch(bucket, key)


def count_view(post_id: int) -> bool:
    ip = request_ip()
    key = f"{ip}:{post_id}"
    if not _cooldown_allowed("view", key, VIEW_COOLDOWN):
        return False
    _touch_cooldown("view", key)
    from models import Post

    Post.increment_views(post_id)
    return True


def request_ip() -> str:
    remote = request.remote_addr or ""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded and _is_private(remote):
        candidate = forwarded.split(",")[0].strip()
        if re.fullmatch(r"[0-9a-fA-F:.]+", candidate or ""):
            return candidate
    return remote


def _is_private(ip: str) -> bool:
    import ipaddress

    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback
    except ValueError:
        return False


def submit(post: dict | None = None, project: dict | None = None, form=None) -> dict:
    """返回 {url, error, commenter}。"""
    from models import Comment

    form = form or request.form
    is_project = project is not None
    target_id = int(project["id"]) if is_project else int(post["id"])
    back = f"/projects/{target_id}" if is_project else f"/post/{target_id}"
    ip = request_ip()

    if not _cooldown_allowed("comment", ip, COOLDOWN):
        return {"url": back, "error": "评论太频繁，请稍后再试"}

    from services import auth

    is_admin = auth.is_admin()
    author = (form.get("author") or "").strip()
    content = (form.get("content") or "").strip()
    email = (form.get("email") or "").strip()
    website = (form.get("website") or "").strip()
    if is_admin:
        author = settings.get_str("author", "") or "博主"
        email = settings.get_str("contact_email", "")
        website = ""

    parent_raw = (form.get("parent_id") or "").strip()
    is_private = str(form.get("is_private") or "").strip().lower() in {"1", "on", "true", "yes"}

    if not author or len(author) > 30:
        return {"url": back, "error": "请填写昵称（30 字以内）"}
    blogger = settings.get_str("author", "").strip()
    if not is_admin and blogger and author == blogger:
        return {"url": back, "error": "该昵称已被占用，请换一个"}
    if not content or len(content) > 2000:
        return {"url": back, "error": "评论内容不能为空且不能超过2000字"}

    content = sensitive.filter_text(content)
    content = merge_images(content, form.get("images", ""))

    email_hash = ""
    qq = ""
    if email:
        email = normalize_email(email)
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return {"url": back, "error": "邮箱格式不正确（选填，仅用于头像）"}
        email_hash = avatar.email_hash(email)
        qq = avatar.qq_from_email(email)
    if website:
        normalized = normalize_website(website)
        if normalized is None:
            return {"url": back, "error": "网址格式不正确（需以 http:// 或 https:// 开头）"}
        website = normalized

    parent_id = None
    if parent_raw.isdigit() and int(parent_raw) > 0:
        column = "project_id" if is_project else "post_id"
        import db

        if db.one(
            f"SELECT id FROM comments WHERE id = ? AND {column} = ?",
            (int(parent_raw), target_id),
        ):
            parent_id = int(parent_raw)

    notify_email = settings.get_str("notify_email", "").strip()
    status = "approved" if is_admin or (
        email and notify_email and email.lower() == notify_email.lower()
    ) else "pending"

    comment_id = Comment.save(
        None if is_project else target_id,
        author, email, email_hash, website, content,
        parent_id, is_private, qq, ip, status,
        target_id if is_project else None,
        ip_location.of(ip),
    )
    _touch_cooldown("comment", ip)

    # 记住评论者信息（30 天）
    data = {"author": author, "email": email, "website": website}
    old = commenter()
    for key in ("author", "email", "website"):
        if old.get(key):
            data[key] = old[key]
    my_comments = old.get("my_comments") if isinstance(old.get("my_comments"), dict) else {}
    if not is_private:
        my_comments[str(comment_id)] = author
        if len(my_comments) > 20:
            my_comments = dict(list(my_comments.items())[-20:])
    data["my_comments"] = my_comments

    # 异步邮件通知（失败静默，不阻塞请求）
    if settings.bool_of("comment_notify", True):
        try:
            from services import notify

            notify.notify_comment(
                post_id=None if is_project else target_id,
                project_id=target_id if is_project else None,
                title=(project or post or {}).get("name") or (post or {}).get("title", ""),
                author=author,
                content=content,
                parent_id=parent_id,
                email=email,
                status=status,
                detail_path=back,
                label="项目" if is_project else "文章",
                comment_id=comment_id,
                is_admin=is_admin,
                is_private=is_private,
            )
        except Exception:
            pass

    if is_private:
        message = "私密评论已提交，仅管理员可见"
    elif status == "approved":
        message = "评论已提交"
    else:
        message = "评论已提交，审核通过后显示"

    # 插件钩子：AI 审核 / 回复等在后台线程处理，不阻塞评论提交
    try:
        from services import hooks
        hooks.emit("comment.created", {"id": comment_id, "is_admin": is_admin})
    except Exception:
        pass

    url = f"{back}#comment-{comment_id}"
    per_page = settings.get_int("comments_per_page", 10)
    if per_page > 0:
        page = Comment.page_of(comment_id, per_page, include_private=is_admin)
        if page > 1:
            url = f"{back}?cpage={page}#comment-{comment_id}"
    return {"url": url, "message": message, "commenter": data}
