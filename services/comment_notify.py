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


def add_avatar_review(email_hash: str, approved: bool, reason: str = "") -> int:
    """头像人工审核结果写进读者站内通知（通知抽屉可见）。"""
    if not email_hash:
        return 0
    return db.insert(
        "INSERT INTO comment_notifications "
        "(email_hash, type, excerpt, created_at) VALUES (?,?,?,?)",
        (email_hash, "avatar_approved" if approved else "avatar_rejected",
         _plain(str(reason or ""), 120), db.now()),
    )


def add_reply_for_comment(comment: dict) -> int:
    """按评论记录给被回复者写站内通知，条件不满足则跳过。

    评论提交与审核通过共用同一套判断，避免两处条件写反：
    私密、父级私密、对方关了通知、自己回自己、被回复的是博主 → 不写。
    """
    if not comment:
        return 0
    if int(comment.get("is_private") or 0):
        return 0
    parent_id = int(comment.get("parent_id") or 0)
    if parent_id <= 0:
        return 0
    parent = db.one(
        "SELECT email_hash, is_private, notify, is_owner FROM comments WHERE id = ?",
        (parent_id,),
    )
    if not parent:
        return 0
    recipient = str(parent["email_hash"] or "")
    if not recipient or int(parent["is_private"] or 0) or int(parent["is_owner"] or 0):
        return 0
    if not int(parent["notify"] if parent["notify"] is not None else 1):
        return 0
    if recipient == str(comment.get("email_hash") or ""):
        return 0
    return add_reply(
        recipient, int(comment.get("id") or 0), parent_id,
        comment.get("post_id"), comment.get("project_id"),
        str(comment.get("author") or ""), str(comment.get("content") or ""),
    )


def unread_count(email_hash: str) -> int:
    if not email_hash:
        return 0
    return int(db.scalar(
        "SELECT COUNT(*) FROM comment_notifications WHERE email_hash=? AND is_read=0",
        (email_hash,), 0) or 0)


def _comment_url(post_id: int | None, project_id: int | None, comment_id: int) -> str:
    """通知里的评论链接：按每页评论数算出真实分页，否则目标可能在第 2 页打不开。"""
    base = ""
    if post_id:
        base = f"/post/{int(post_id)}"
    elif project_id:
        base = f"/projects/{int(project_id)}"
    else:
        return ""
    page = 1
    try:
        from models import Comment
        from services import settings

        per_page = settings.get_int("comments_per_page", 10)
        if per_page > 0:
            page = Comment.page_of(int(comment_id), per_page) or 1
    except Exception:
        page = 1
    query = f"?cpage={page}" if page > 1 else ""
    return f"{base}{query}#comment-{int(comment_id)}"


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
        item["label"] = str(item.get("post_title") or item.get("project_name") or "")
        item["url"] = _comment_url(item.get("post_id"), item.get("project_id"), item["comment_id"])
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


def add_admin_comment(comment: dict) -> int:
    """评论公开后给博主写一条通知；待审核不写，审核通过时调这里补写。

    只记录真正需要博主知道的：已通过、非博主本人、非私密。
    同一条评论只写一次，批量通过重复调用不会产生重复行。
    """
    if not comment:
        return 0
    if str(comment.get("status") or "") != "approved":
        return 0
    if int(comment.get("is_owner") or 0) or int(comment.get("is_private") or 0):
        return 0
    comment_id = int(comment.get("id") or 0)
    if comment_id <= 0:
        return 0
    if db.one("SELECT 1 FROM admin_notifications WHERE comment_id = ?", (comment_id,)):
        return 0

    parent_id = int(comment.get("parent_id") or 0)
    kind = "new"
    if parent_id:
        parent = db.one("SELECT is_owner FROM comments WHERE id = ?", (parent_id,))
        if parent and int(parent["is_owner"] or 0):
            kind = "reply"

    return db.insert(
        "INSERT INTO admin_notifications "
        "(type, comment_id, parent_id, post_id, project_id, from_author, excerpt, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (kind, comment_id, parent_id, comment.get("post_id"), comment.get("project_id"),
         str(comment.get("author") or "匿名")[:30], _plain(str(comment.get("content") or "")), db.now()),
    )


def remove_admin_for_comment(comment_ids: list[int]) -> int:
    """删除评论（含回复树）时同步清掉博主通知，避免铃铛指向不存在的评论。"""
    ids = [int(x) for x in (comment_ids or []) if str(x).lstrip("-").isdigit() and int(x) > 0]
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    cur = db.execute(f"DELETE FROM admin_notifications WHERE comment_id IN ({marks})", ids)
    return cur.rowcount


def admin_mark_read(notify_id: int = 0) -> int:
    """标记博主通知已读；notify_id=0 表示全部。待审核项不在这里，处理完自动消失。"""
    if notify_id > 0:
        cur = db.execute(
            "UPDATE admin_notifications SET is_read=1 WHERE id=?", (notify_id,)
        )
    else:
        cur = db.execute("UPDATE admin_notifications SET is_read=1 WHERE is_read=0")
    return cur.rowcount


def admin_feed(limit: int = 20) -> list[dict]:
    """博主通知：新评论 / 被回复。id 是通知 id，不是评论 id。"""
    rows = db.query(
        "SELECT n.id, n.type, n.comment_id, n.parent_id, n.post_id, n.project_id, "
        "n.from_author, n.excerpt, n.is_read, n.created_at, "
        "p.title AS post_title, pj.name AS project_name "
        "FROM admin_notifications n "
        "LEFT JOIN posts p ON n.post_id = p.id "
        "LEFT JOIN projects pj ON n.project_id = pj.id "
        "ORDER BY n.is_read ASC, n.created_at DESC, n.id DESC LIMIT ?",
        (max(1, min(50, int(limit))),),
    )
    items = []
    for row in rows:
        item = dict(row)
        item["label"] = str(item.get("post_title") or item.get("project_name") or "")
        # 已通过的评论在前台可见，直接跳到对应锚点；找不到来源才回后台列表
        item["url"] = _comment_url(item.get("post_id"), item.get("project_id"), item["comment_id"]) or "/admin/comments"
        items.append(item)
    return items


def admin_pending_list(limit: int = 20) -> list[dict]:
    """待审核评论：实时查询，不复制进通知表，避免状态变化后留下一份旧数据。"""
    rows = db.query(
        "SELECT c.id, c.author, c.content, c.created_at, c.post_id, c.project_id, "
        "p.title AS post_title, pj.name AS project_name "
        "FROM comments c "
        "LEFT JOIN posts p ON c.post_id = p.id "
        "LEFT JOIN projects pj ON c.project_id = pj.id "
        "WHERE c.status='pending' AND c.deleted_at IS NULL AND c.is_ai = 0 "
        "ORDER BY c.created_at DESC, c.id DESC LIMIT ?",
        (max(1, min(50, int(limit))),),
    )
    items = []
    for row in rows:
        item = dict(row)
        item["comment_id"] = int(item.pop("id"))
        item["type"] = "pending"
        item["from_author"] = str(item.get("author") or "匿名")
        item["excerpt"] = _plain(str(item.get("content") or ""))
        item["is_read"] = 0
        item["label"] = str(item.get("post_title") or item.get("project_name") or "")
        item["url"] = "/admin/comments"
        items.append(item)
    return items


def admin_unread_count() -> int:
    unread = int(db.scalar(
        "SELECT COUNT(*) FROM admin_notifications WHERE is_read=0", (), 0) or 0)
    return admin_pending_count() + unread


def admin_pending_count() -> int:
    return int(db.scalar(
        "SELECT COUNT(*) FROM comments WHERE status='pending' AND deleted_at IS NULL",
        (), 0) or 0)
