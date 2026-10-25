"""评论模型（树形组装、审核、批量）。"""

from __future__ import annotations

from typing import Any

import db
from models.base import row_to_dict

ADMIN_PAGE_SIZE = 20


def load(
    post_id: int | None = None,
    project_id: int | None = None,
    include_private: bool = False,
    my_comments: dict[str, str] | None = None,
    page: int = 1,
    per_page: int = 0,
) -> tuple[list[dict], int, dict]:
    """读取评论区。

    返回 (顶层评论, 评论总数, 分页信息)。per_page > 0 时按顶层评论分页，
    楼中楼回复始终跟随所属根评论一起展示。
    """
    from services import avatar, comments as comments_service, settings

    column = "project_id" if project_id is not None else "post_id"
    value = project_id if project_id is not None else post_id
    my_comments = my_comments or {}

    if include_private:
        sql = f"SELECT * FROM comments WHERE {column} = ? AND (status='approved' OR is_private=1)"
        params: list[Any] = [value]
    else:
        sql = f"SELECT * FROM comments WHERE {column} = ? AND status='approved' AND is_private=0"
        params = [value]
        ids = [int(k) for k in my_comments if str(k).isdigit()]
        if ids:
            marks = ",".join("?" * len(ids))
            sql += f" OR (id IN ({marks}) AND {column} = ? AND status != 'rejected')"
            params = [*params, *ids, value]
    sql += " ORDER BY created_at ASC, id ASC"
    rows = [dict(r) for r in db.query(sql, params)]

    if my_comments and not include_private:
        rows = [
            c for c in rows
            if c.get("status") == "approved"
            or (str(c["id"]) in my_comments and my_comments[str(c["id"])] == c.get("author"))
        ]

    author_name = settings.get_str("author", "")
    contact = settings.get_str("contact_email", "").strip().lower()
    contact_hash = avatar.email_hash(contact)
    contact_qq = avatar.qq_from_email(contact)
    avatar_default = avatar.default_url()
    cfg_avatar = settings.get_str("avatar", "").strip()
    cfg_ok = avatar.configured_avatar_exists()

    by_id: dict[int, dict] = {}
    items: list[dict] = []
    for c in rows:
        c["id"] = int(c["id"])
        c["parent_id"] = int(c["parent_id"]) if c.get("parent_id") is not None else None
        c["is_private"] = int(c.get("is_private") or 0)
        c["children"] = []
        c["is_author"] = bool(author_name) and c.get("author") == author_name
        if c["is_author"]:
            if cfg_avatar and cfg_ok:
                c["avatar"], c["avatar_fallback"] = cfg_avatar, ""
            else:
                c["avatar"], c["avatar_fallback"] = avatar.urls(contact_hash, contact_qq)
        else:
            c["avatar"], c["avatar_fallback"] = avatar.urls(
                str(c.get("email_hash") or ""), str(c.get("qq") or "")
            )
        if not c["avatar"]:
            c["avatar"], c["avatar_fallback"] = avatar_default, ""
        c["avatar_default"] = avatar_default
        c["content_html"] = comments_service.render_content(str(c.get("content") or ""))
        c.pop("email", None)
        by_id[c["id"]] = c
        items.append(c)

    roots: list[dict] = []
    for c in items:
        pid = c["parent_id"]
        if pid and pid in by_id:
            c["parent_author"] = by_id[pid].get("author", "")
            by_id[pid]["children"].append(c)
        else:
            c["parent_author"] = ""
            roots.append(c)

    def set_depth(node: dict, depth: int) -> None:
        node["depth"] = depth
        for child in node["children"]:
            set_depth(child, depth + 1)

    for root in roots:
        set_depth(root, 0)

    total_roots = len(roots)
    pager = {"page": 1, "per_page": 0, "total_pages": 1, "total_roots": total_roots}
    if per_page and per_page > 0:
        total_pages = max(1, (total_roots + per_page - 1) // per_page)
        page = min(max(1, int(page or 1)), total_pages)
        start = (page - 1) * per_page
        roots = roots[start:start + per_page]
        pager = {
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_roots": total_roots,
        }
    return roots, len(items), pager


def page_of(comment_id: int, per_page: int, include_private: bool = False) -> int:
    """评论所在的分页页码（按根评论位置计算，供提交后跳转使用）。"""
    if not per_page or per_page <= 0:
        return 1
    row = db.one(
        "SELECT id, parent_id, post_id, project_id, created_at FROM comments WHERE id = ?",
        (int(comment_id),),
    )
    if not row:
        return 1
    root = dict(row)
    guard = 0
    while root.get("parent_id") and guard < 50:
        parent = db.one(
            "SELECT id, parent_id, post_id, project_id, created_at FROM comments WHERE id = ?",
            (int(root["parent_id"]),),
        )
        if not parent:
            break
        root = dict(parent)
        guard += 1

    is_project = root.get("project_id") is not None
    column = "project_id" if is_project else "post_id"
    value = root.get("project_id") if is_project else root.get("post_id")
    visible = (
        "(status = 'approved' OR is_private = 1)"
        if include_private
        else "(status = 'approved' AND is_private = 0)"
    )
    earlier = int(
        db.scalar(
            f"SELECT COUNT(*) FROM comments WHERE {column} = ? AND parent_id IS NULL "
            f"AND {visible} AND (created_at < ? OR (created_at = ? AND id < ?))",
            (value, root.get("created_at"), root.get("created_at"), int(root["id"])),
            0,
        )
        or 0
    )
    return earlier // per_page + 1


def count_pending(nodes: list[dict]) -> int:
    total = 0
    for c in nodes:
        if c.get("status") == "pending":
            total += 1
        total += count_pending(c.get("children") or [])
    return total


def save(
    post_id: int | None,
    author: str,
    email: str,
    email_hash: str,
    website: str,
    content: str,
    parent_id: int | None = None,
    is_private: bool = False,
    qq: str = "",
    ip_text: str = "",
    status: str = "pending",
    project_id: int | None = None,
    ip_location: str = "",
) -> int:
    return db.insert(
        "INSERT INTO comments (post_id, project_id, parent_id, author, email, email_hash, "
        "website, content, status, is_private, qq, ip_text, ip_location, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (post_id, project_id, parent_id, author, email, email_hash, website, content,
         status, 1 if is_private else 0, qq, ip_text, ip_location, db.now()),
    )


def delete(comment_id: int) -> None:
    ids = [comment_id]
    visited = {comment_id}
    frontier = [comment_id]
    while frontier:
        marks = ",".join("?" * len(frontier))
        rows = db.query(f"SELECT id FROM comments WHERE parent_id IN ({marks})", frontier)
        frontier = []
        for row in rows:
            cid = int(row["id"])
            if cid not in visited:
                visited.add(cid)
                frontier.append(cid)
                ids.append(cid)
    marks = ",".join("?" * len(ids))
    db.execute(f"DELETE FROM comments WHERE id IN ({marks})", ids)


def set_status(comment_id: int, status: str) -> None:
    if status in {"pending", "approved", "rejected"}:
        db.execute("UPDATE comments SET status = ? WHERE id = ?", (status, comment_id))


def admin_list(page: int = 1, per_page: int = 0) -> tuple[list[dict], int]:
    """后台评论列表，返回 (当前页数据, 总数)；per_page > 0 时分页。"""
    total = int(db.scalar("SELECT COUNT(*) FROM comments", (), 0))
    sql = (
        "SELECT c.*, p.title AS post_title, p.id AS post_id, pj.name AS project_name, "
        "pa.author AS parent_author FROM comments c "
        "LEFT JOIN posts p ON c.post_id = p.id "
        "LEFT JOIN projects pj ON c.project_id = pj.id "
        "LEFT JOIN comments pa ON c.parent_id = pa.id "
        "ORDER BY (c.status = 'pending') DESC, c.is_private DESC, c.created_at DESC, c.id DESC"
    )
    params: list[Any] = []
    if per_page and per_page > 0:
        page = max(1, int(page or 1))
        sql += " LIMIT ? OFFSET ?"
        params = [per_page, (page - 1) * per_page]
    rows = db.query(sql, params)
    result = []
    for row in rows:
        item = dict(row)
        item["id"] = int(item["id"])
        item["post_id"] = int(item["post_id"]) if item.get("post_id") is not None else None
        item["project_id"] = int(item["project_id"]) if item.get("project_id") is not None else None
        item["is_private"] = int(item.get("is_private") or 0)
        item["parent_author"] = item.get("parent_author") or ""
        result.append(item)
    return result, total


def pending_count() -> int:
    return int(db.scalar("SELECT COUNT(*) FROM comments WHERE status='pending'", (), 0))


def bulk(ids: list[int], action: str) -> int:
    ids = [int(i) for i in ids if int(i) > 0]
    if not ids:
        return 0
    if action in {"approve", "approved"}:
        marks = ",".join("?" * len(ids))
        return db.execute(f"UPDATE comments SET status='approved' WHERE id IN ({marks})", ids).rowcount
    if action in {"delete", "remove"}:
        count = 0
        for cid in ids:
            delete(cid)
            count += 1
        return count
    if action in {"pending"}:
        marks = ",".join("?" * len(ids))
        return db.execute(f"UPDATE comments SET status='pending' WHERE id IN ({marks})", ids).rowcount
    return 0


def get(comment_id: int) -> dict | None:
    return row_to_dict(db.one("SELECT * FROM comments WHERE id = ?", (comment_id,)))
