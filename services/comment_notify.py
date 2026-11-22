"""站内通知：回复 / 审核通过等提醒，按 email_hash 归属。

与邮件通知（services/notify.py）并行，不依赖 SMTP 是否开启。
身份为 email_hash，前端通过「读者登录 Cookie」或「评论 Cookie」拿到同一个哈希。
"""

from __future__ import annotations

import db
from services import avatar

EXCERPT_LIMIT = 120


def _plain(text: str, limit: int = EXCERPT_LIMIT) -> str:
    value = str(text or "")
    value = " ".join(value.split())
    if limit and len(value) > limit:
        return value[:limit].rstrip() + "…"
    return value


def add_reply(
    recipient_email_hash: str,
    comment_id: int,
    parent_id: int,
    post_id: int | None,
    project_id: int | None,
    from_author: str,
    content: str,
) -> int:
    """被回复者收到一条「你的评论被回复」通知。"""
    if not recipient_email_hash:
        return 0
    return db.insert(
        "INSERT INTO comment_notifications "
        "(email_hash, type, comment_id, parent_id, post_id, project_id, from_author, excerpt, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (recipient_email_hash, "reply", comment_id, parent_id, post_id, project_id,
         str(from_author or "")[:30], _plain(content), db.now()),
    )


def add_approved(comment: dict) -> int:
    """评论审核通过后，给评论者一条「评论已通过」通知。"""
    key = str(comment.get("email_hash") or "")
    if not key:
        return 0
    return db.insert(
        "INSERT INTO comment_notifications "
        "(email_hash, type, comment_id, parent_id, post_id, project_id, from_author, excerpt, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (key, "approved", int(comment.get("id") or 0), int(comment.get("parent_id") or 0),
         comment.get("post_id"), comment.get("project_id"), "",
         _plain(str(comment.get("content") or "")), db.now()),
    )


def unread_count(email_hash: str) -> int:
    if not email_hash:
        return 0
    return int(db.scalar(
        "SELECT COUNT(*) FROM comment_notifications WHERE email_hash=? AND is_read=0",
        (email_hash,), 0) or 0)


def list_notifies(email_hash: str, limit: int = 50) -> list[dict]:
    if not email_hash:
        return []
    rows = db.query(
        "SELECT n.id, n.type, n.comment_id, n.parent_id, n.post_id, n.project_id, "
        "n.from_author, n.excerpt, n.is_read, n.created_at, "
        "p.title AS post_title, pj.name AS project_name "
        "FROM comment_notifications n "
        "LEFT JOIN posts p ON n.post_id = p.id "
        "LEFT JOIN projects pj ON n.project_id = pj.id "
        "WHERE n.email_hash = ? ORDER BY n.created_at DESC, n.id DESC LIMIT ?",
        (email_hash, max(1, min(100, int(limit)))),
    )
    results = []
    for row in rows:
        item = dict(row)
        if item.get("post_id"):
            item["label"] = str(item.get("post_title") or "文章")
            item["url"] = f"/post/{item['post_id']}#comment-{item['comment_id']}"
        elif item.get("project_id"):
            item["label"] = str(item.get("project_name") or "项目")
            item["url"] = f"/projects/{item['project_id']}#comment-{item['comment_id']}"
        else:
            item["label"] = ""
            item["url"] = ""
        results.append(item)
    return results


def mark_read(email_hash: str, notify_id: int = 0) -> int:
    """标记已读；notify_id=0 表示全部已读。返回影响行数。"""
    if not email_hash:
        return 0
    if notify_id > 0:
        cur = db.execute(
            "UPDATE comment_notifications SET is_read=1 WHERE id=? AND email_hash=?",
            (notify_id, email_hash),
        )
    else:
        cur = db.execute(
            "UPDATE comment_notifications SET is_read=1 WHERE email_hash=? AND is_read=0",
            (email_hash,),
        )
    return cur.rowcount


def identity_hash_from_cookies(reader_row: dict | None, commenter_cookie: dict, email: str = "") -> str:
    """双身份解析：优先读者登录账号，其次评论 Cookie，最后用当前邮箱现算。"""
    if reader_row:
        return str(reader_row.get("email_hash") or "")
    cookie_hash = str(commenter_cookie.get("email_hash") or "")
    if cookie_hash:
        return cookie_hash
    if email:
        return avatar.email_hash(email)
    return ""


def admin_feed(limit: int = 20) -> list[dict]:
    """博主视角：最近待审核 / 最新评论动态，供后台铃铛展示。"""
    rows = db.query(
        "SELECT c.id, c.author, c.content, c.status, c.created_at, "
        "c.post_id, c.project_id, p.title AS post_title, pj.name AS project_name "
        "FROM comments c "
        "LEFT JOIN posts p ON c.post_id = p.id "
        "LEFT JOIN projects pj ON c.project_id = pj.id "
        "WHERE c.deleted_at IS NULL AND c.is_ai = 0 "
        "ORDER BY (c.status = 'pending') DESC, c.created_at DESC, c.id DESC LIMIT ?",
        (max(1, min(50, int(limit))),),
    )
    items = []
    for row in rows:
        item = dict(row)
        pending = item.get("status") == "pending"
        item["type"] = "pending" if pending else "new"
        item["from_author"] = str(item.get("author") or "匿名")
        item["excerpt"] = _plain(str(item.get("content") or ""))
        item["is_read"] = 0 if pending else 1
        if item.get("post_id"):
            item["label"] = str(item.get("post_title") or "文章")
            item["url"] = "/admin/comments"
        elif item.get("project_id"):
            item["label"] = str(item.get("project_name") or "项目")
            item["url"] = "/admin/comments"
        else:
            item["label"] = ""
            item["url"] = "/admin/comments"
        items.append(item)
    return items


def admin_pending_count() -> int:
    return int(db.scalar(
        "SELECT COUNT(*) FROM comments WHERE status='pending' AND deleted_at IS NULL",
        (), 0) or 0)
