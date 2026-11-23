"""评论提交、冷却与渲染。"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from flask import request
from markupsafe import Markup

import db
from config import CACHE_DIR
from services import avatar, comment_identity, ip_location, sensitive, site_url, upload
from services import settings

COOLDOWN = 30
VIEW_COOLDOWN = 60
MAX_IMAGES = 6
_IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
# 与 services.markdown 的图注占位词保持一致：空的 [] 或通用占位词不显示备注
_IMG_ALT_PLACEHOLDERS = {
    "", "null", "none", "undefined", "false", "为空", "为空null", "空",
    "图片", "image", "img", "photo", "picture",
}

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
        # 评论图片走审核中转：未通过审核时返回「审核中」占位图，
        # 通过后才返回原图；同时避免 /uploads/comment 直链绕过审核。
        src = path
        if "/uploads/comment/" in path:
            rel = path.split("/uploads/comment/", 1)[1]
            rel = rel.split("?", 1)[0].split("#", 1)[0]
            src = "/comment-img/comment/" + rel
        # 占位 alt（图片 / image / 空等）清空：评论灯箱只显示用户写的自定义说明
        alt_text = (alt or "").strip()
        if alt_text.lower() in _IMG_ALT_PLACEHOLDERS:
            alt_text = ""
        return f'<img class="cmt-img" src="{src}" alt="{alt_text}" loading="lazy">'

    return Markup(re.sub(
        r"!\[([^\]]*)\]\(((?:/uploads/|/oss-media/uploads/)[^\s()<>\"']+)\)",
        repl, escaped,
    ))


_NICKNAME_URL_RE = re.compile(r"^(?:https?://|www\.)", re.I)


def validate_author(author: str) -> str | None:
    """昵称规则：不能纯数字、不能以网址开头、不能包含违规词。

    违规词与评论正文共用后台「敏感词」词库；昵称是公开展示位，
    即使正文过滤开关关闭，命中词库的昵称也应拒绝。
    """
    value = (author or "").strip()
    if re.fullmatch(r"\d+", value):
        return "昵称不能是纯数字，请换一个"
    if _NICKNAME_URL_RE.match(value):
        return "昵称不能以 http://、https:// 或 www. 开头"
    lowered = value.lower()
    for word in sensitive.words():
        if word and word.lower() in lowered:
            return "昵称包含违规词，请换一个"
    return None


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


COMMENT_IMG_RE = re.compile(
    r"/(?:oss-media/)?uploads/comment/\d{4}/\d{2}/[A-Za-z0-9_.\-]+"
)


def extract_images(content: str) -> list[str]:
    """评论正文里的图片地址（去重）。后台审核、删除评论清图都走这里。"""
    return list(dict.fromkeys(COMMENT_IMG_RE.findall(content or "")))


def tree_ids(comment_id: int) -> list[int]:
    """评论及其全部回复的 id，口径与软删除的级联一致。"""
    ids = [comment_id]
    visited = {comment_id}
    frontier = [comment_id]
    while frontier:
        marks = ",".join("?" * len(frontier))
        rows = db.query(
            f"SELECT id FROM comments WHERE parent_id IN ({marks}) AND deleted_at IS NULL",
            frontier,
        )
        frontier = []
        for row in rows:
            cid = int(row["id"])
            if cid not in visited:
                visited.add(cid)
                frontier.append(cid)
                ids.append(cid)
    return ids


def delete_images(comment_ids: list[int]) -> int:
    """删除这些评论正文里引用的图片（本地 + OSS），返回实际删掉的张数。

    只在「删除评论」时调用：拒绝评论按规则不删图，图片继续留在磁盘上。
    """
    if not comment_ids:
        return 0
    marks = ",".join("?" * len(comment_ids))
    urls: list[str] = []
    for row in db.query(
        f"SELECT content FROM comments WHERE id IN ({marks})", list(comment_ids)
    ):
        urls.extend(extract_images(str(row["content"] or "")))
    removed = 0
    for url in dict.fromkeys(urls):
        if upload.delete_by_url(url):
            removed += 1
    return removed


def merge_images(content: str, raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return content
    urls: list[str] = []
    for line in re.split(r"[\r\n]+", raw):
        url = line.strip()
        if not url or not re.fullmatch(
            r"/(?:uploads|oss-media/uploads)/comment/\d{4}/\d{2}/[A-Za-z0-9_.\-]+", url
        ):
            continue
        if Path(url).suffix.lower() not in _IMG_EXTS:
            continue
        rel = url.replace("/oss-media/uploads/", "", 1).replace("/uploads/", "", 1)
        if upload.resolve(rel) is None:
            continue
        if url not in urls:
            urls.append(url)
        if len(urls) >= MAX_IMAGES:
            break
    if not urls:
        return content
    markers = "\n".join(f"![图片]({url})" for url in urls)
    return (content.rstrip() + "\n" + markers).strip()


def _is_admin() -> bool:
    from services import auth

    return auth.is_admin()


def _blogger_identity() -> tuple[str, set[str]]:
    """博主身份标识：昵称 + 后台配置过的博主邮箱（联系邮箱 / 通知邮箱）。"""
    author = settings.get_str("author", "").strip()
    emails = {
        settings.get_str("contact_email", "").strip().lower(),
        settings.get_str("notify_email", "").strip().lower(),
    }
    emails.discard("")
    return author, emails


def is_blogger_identity(data: dict | None) -> bool:
    """判断「访客记忆」cookie 里存的是否是博主本人资料。

    昵称与博主同名者提交时已被拒绝（见 submit 的占用校验），
    因此 cookie 里的 author 等于站点作者名时，必然是博主自己留下的。
    """
    if not isinstance(data, dict):
        return False
    author, emails = _blogger_identity()
    if author and str(data.get("author") or "").strip() == author:
        return True
    email = str(data.get("email") or "").strip().lower()
    return bool(email and email in emails)


def commenter() -> dict:
    raw = request.cookies.get("blog_commenter", "")
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(value, dict):
        return {}
    # 博主身份不外泄：旧版本以博主身份评论时，会把博主昵称与联系邮箱写进这个 cookie，
    # 退出登录后前台评论表单仍回显博主资料。非管理员身份下直接剔除该身份，
    # 只保留「我发过的评论」记录（待审核时仍能标记为「仅你可见」）。
    if not _is_admin() and is_blogger_identity(value):
        my_comments = value.get("my_comments")
        return {"my_comments": my_comments} if isinstance(my_comments, dict) else {}
    return value


def commenter_hash() -> str:
    """当前浏览者的身份哈希，含被 commenter() 剔除的「博主资料」Cookie。

    commenter() 为了不让博主昵称/邮箱回显到表单，会把这类 Cookie 整条丢掉；
    但身份识别（我的概览 / 站内通知 / 点赞）只读 commenter() 时，
    就会出现「刚以该身份发过评论（仓里还挂着待审核），抽屉却说未识别身份」。
    这里只取邮箱哈希做归集，不返回昵称、邮箱，也不参与表单回显，
    安全边界与 commenter() 一致。
    """
    raw = request.cookies.get("blog_commenter", "")
    if not raw:
        return ""
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return ""
    if not isinstance(value, dict):
        return ""
    stored = str(value.get("email_hash") or "").strip()
    if stored:
        return stored
    email = str(value.get("email") or "").strip()
    if not email:
        return ""
    return avatar.email_hash(normalize_email(email))


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

    from services import auth

    # 博主回复不受 30 秒冷却限制：审核/答疑时经常连续回多条
    is_admin = auth.is_admin()
    if not is_admin and not _cooldown_allowed("comment", ip, COOLDOWN):
        return {"url": back, "error": "评论太频繁，请稍后再试"}
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
    notify_on = str(form.get("notify") or "").strip().lower() in {"1", "on", "true", "yes"}
    if is_admin:
        notify_on = True

    if not author or len(author) > 30:
        return {"url": back, "error": "请填写昵称（30 字以内）"}
    author_error = validate_author(author)
    if author_error:
        return {"url": back, "error": author_error}
    blogger = settings.get_str("author", "").strip()
    if not is_admin and blogger and author == blogger:
        return {"url": back, "error": "该昵称已被占用，请换一个"}
    if not content or len(content) > 2000:
        return {"url": back, "error": "评论内容不能为空且不能超过2000字"}
    # 邮箱必填（实名合规要求）：不填邮箱无法提交评论
    if not email and not is_admin:
        return {"url": back, "error": "请填写邮箱（必填，用于接收回复通知与显示头像）"}

    # 保留过滤前的原文：AI 托管要用它做敏感词硬拦截（过滤后原词已被替换成 *）
    raw_content = content
    content = sensitive.filter_text(content)
    content = merge_images(content, form.get("images", ""))

    email_hash = ""
    qq = ""
    if email:
        email = normalize_email(email)
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return {"url": back, "error": "邮箱格式不正确"}
        email_hash = avatar.email_hash(email)
        qq = avatar.qq_from_email(email)

    # 身份校验：同一邮箱换昵称必须沿用曾用名，或完成邮箱验证码验证。
    # 管理员昵称由后台固定，不参与这套逻辑。
    rename_verified = False
    rename_old_author = ""
    identity_action = ""
    identity_note = ""
    if email and not is_admin:
        identity_row = comment_identity.get_row(email)
        found = comment_identity.conflict(email, author)
        if found:
            if str(form.get("identity_confirmed") or "").strip().lower() in {
                "1", "on", "true", "yes",
            }:
                # 沿用曾用名：服务端直接覆盖，避免前端伪造
                author = found["current_author"]
                identity_action = "keep"
                identity_note = "沿用曾用昵称「%s」" % found["current_author"]
            elif comment_identity.verify_token(
                str(form.get("rename_token") or ""), email, author
            ):
                rename_verified = True
                rename_old_author = found["current_author"]
                identity_action = "rename"
                identity_note = "邮箱验证通过，昵称「%s」→「%s」" % (
                    found["current_author"], author,
                )
            else:
                return {
                    "url": back,
                    "error": (
                        "该邮箱曾使用昵称「%s」，请选择沿用原昵称，"
                        "或完成邮箱验证后再修改" % found["masked_author"]
                    ),
                }
        elif identity_row is None:
            identity_action = "first"
            identity_note = "首次使用该邮箱昵称「%s」" % author

    if website:
        normalized = normalize_website(website)
        if normalized is None:
            return {"url": back, "error": "网址格式不正确（需以 http:// 或 https:// 开头）"}
        website = normalized

    parent_id = None
    parent_row = None
    if parent_raw.isdigit() and int(parent_raw) > 0:
        column = "project_id" if is_project else "post_id"
        import db

        parent_row = db.one(
            f"SELECT id, email_hash, email, notify, is_private FROM comments "
            f"WHERE id = ? AND {column} = ? AND deleted_at IS NULL",
            (int(parent_raw), target_id),
        )
        if parent_row:
            parent_id = int(parent_raw)

    # 只有已登录管理员才自动通过；不再凭表单邮箱是否等于 notify_email 放行
    status = "approved" if is_admin else "pending"

    comment_id = Comment.save(
        None if is_project else target_id,
        author, email, email_hash, website, content,
        parent_id, is_private, qq, ip, status,
        target_id if is_project else None,
        ip_location.of(ip),
        is_owner=is_admin,
        notify=notify_on,
        user_agent=request.headers.get("User-Agent", ""),
        identity_action=identity_action,
        identity_note=identity_note,
    )

    # 站内通知：被回复者收到提醒（与邮件通知独立，不受 comment_notify 开关影响）
    # 待审核评论先不写：被回复者点开也看不到内容；审核通过后由 notify_approved_reply 补写
    if parent_id and status == "approved":
        try:
            from services import comment_notify

            comment_notify.add_reply_for_comment(Comment.get(comment_id))
        except Exception:
            pass

    # 博主通知：评论公开后才写，待审核由后台 pending 实时查询，不复制一份
    if status == "approved":
        try:
            from services import comment_notify as _cn

            _cn.add_admin_comment(Comment.get(comment_id))
        except Exception:
            pass

    if not is_admin:
        _touch_cooldown("comment", ip)
        if rename_verified:
            comment_identity.rename(email, author)
            try:
                from services import hooks

                hooks.emit(
                    "comment.identity.rename",
                    {
                        "comment_id": comment_id,
                        "old_author": rename_old_author,
                        "new_author": author,
                        "email_hash": email_hash,
                        "ip": ip,
                        "user_agent": request.headers.get("User-Agent", ""),
                    },
                )
            except Exception:
                pass
        else:
            comment_identity.remember(email, author)

    # 记住评论者信息（30 天）
    old = commenter()
    data: dict | None = None
    if not is_admin:
        data = {"author": author, "email": email, "website": website, "email_hash": email_hash}
        # 本次提交的值优先，旧记忆只用来补空字段
        # （此前是旧值无条件覆盖新值，用户点「修改」改完资料后永远存不下来）
        for key in ("author", "email", "website"):
            if not data.get(key) and old.get(key):
                data[key] = old[key]
        my_comments = old.get("my_comments") if isinstance(old.get("my_comments"), dict) else {}
        if not is_private:
            my_comments[str(comment_id)] = author
            if len(my_comments) > 20:
                my_comments = dict(list(my_comments.items())[-20:])
        data["my_comments"] = my_comments
        # 记住邮箱通知选择，下次打开表单沿用（默认勾选）
        data["notify"] = "1" if notify_on else "0"
    # 以博主身份评论时不写 cookie：否则博主退出登录后，同一浏览器仍会回显博主昵称与邮箱

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
        hooks.emit("comment.created", {"id": comment_id, "is_admin": is_admin, "raw_content": raw_content})
    except Exception:
        pass

    url = f"{back}#comment-{comment_id}"
    per_page = settings.get_int("comments_per_page", 10)
    if per_page > 0:
        page = Comment.page_of(comment_id, per_page, include_private=is_admin)
        if page > 1:
            url = f"{back}?cpage={page}#comment-{comment_id}"
    return {"url": url, "message": message, "commenter": data}
