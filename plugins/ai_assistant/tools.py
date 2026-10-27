"""AI 助手可调用的白名单工具。

模型只能通过这些函数操作博客，不能拼 SQL、读文件或执行命令。
写操作由路由层二次确认后再调用 `execute`。
"""

from __future__ import annotations

import json

import db
from models import Category, Comment, Link, Post

READ_TOOLS = {
    "list_posts": "列出文章。参数：limit（默认 10，最大 50）、status（published/draft/hidden/all）、order（latest/oldest）",
    "search_posts": "按关键词搜索文章。参数：q、limit（默认 5）",
    "get_post": "读取一篇文章全文。参数：id",
    "list_comments": "列出评论。参数：limit（默认 10）、status（pending/approved/rejected/all）、email、author、post_id",
    "list_links": "列出友链。参数：limit（默认 10）、status、q（名称或地址关键词）",
    "list_categories": "列出文章分类（id/name/slug）",
    "get_stats": "读取站点统计（文章/评论/友链数量）",
}

WRITE_TOOLS = {
    "create_post": "创建文章。参数：title、content（Markdown）、tags（数组或逗号分隔）、status（published/draft）、category（分类名称）",
    "update_post": "修改文章。参数：id、title、content、status、category（分类名称）",
    "create_category": "新建文章分类。参数：name、slug（可选）",
    "update_category": "修改文章分类。参数：id、name、slug（可选）",
    "approve_comment": "通过一条评论。参数：id",
    "reply_comment": "以 AI 助手身份回复评论。参数：id（被回复评论）、content",
    "add_link": "新增友链。参数：name、url、description、avatar",
    "approve_link": "通过一条友链。参数：id",
}

# 这四类即使开启「写操作自动执行」也必须人工确认
FORCE_CONFIRM = {"create_post", "update_post", "create_category", "update_category"}

ALL_TOOLS = {**READ_TOOLS, **WRITE_TOOLS}

_POST_STATUSES = {"published", "draft", "hidden"}


def _audit(action: str, args: dict, result: dict, ok: bool) -> None:
    try:
        db.execute(
            "INSERT INTO ai_audit (action, args, result, ok, created_at) VALUES (?,?,?,?,datetime('now','localtime'))",
            (action, json.dumps(args, ensure_ascii=False)[:4000], json.dumps(result, ensure_ascii=False)[:4000], 1 if ok else 0),
        )
    except Exception:
        pass


def _limit(value, default=10, maximum=50) -> int:
    try:
        return max(1, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _mask_email(email: str) -> str:
    email = str(email or "").strip()
    if "@" not in email:
        return email
    name, domain = email.split("@", 1)
    if not name:
        return "***@" + domain
    return name[0] + "***@" + domain


def _resolve_category(args: dict) -> tuple[int | None, str]:
    raw_id = args.get("category_id")
    if raw_id:
        try:
            return int(raw_id), ""
        except (TypeError, ValueError):
            pass
    name = str(args.get("category") or "").strip()
    if not name:
        return None, ""
    categories = Category.load()
    for cat in categories:
        if str(cat.get("name")) == name:
            return int(cat["id"]), ""
    names = "、".join(str(c.get("name")) for c in categories)
    return None, f"分类「{name}」不存在，现有分类：{names}"


def _brief_post(row) -> dict:
    item = dict(row)
    return {
        "id": int(item["id"]),
        "title": item.get("title", ""),
        "status": item.get("status", ""),
        "tags": json.loads(item.get("tags") or "[]") if isinstance(item.get("tags"), str) else item.get("tags"),
        "created_at": item.get("created_at", ""),
    }


def execute(name: str, args: dict | None = None, *, audit: bool = True) -> dict:
    args = args or {}
    if name not in ALL_TOOLS:
        return {"ok": False, "error": f"未知工具：{name}"}
    try:
        result = _dispatch(name, args)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": str(exc)[:300]}
    if audit:
        _audit(name, args, result, bool(result.get("ok")))
    return result


def _dispatch(name: str, args: dict) -> dict:
    if name == "list_posts":
        status = str(args.get("status") or "published")
        order = "ASC" if str(args.get("order") or "") == "oldest" else "DESC"
        limit = _limit(args.get("limit"), 10)
        params: list = []
        if status in _POST_STATUSES:
            where = "WHERE status = ?"
            params.append(status)
        else:
            where = ""
        rows = db.query(
            f"SELECT id, title, status, tags, created_at FROM posts {where} "
            f"ORDER BY created_at {order}, id {order} LIMIT ?",
            (*params, limit),
        )
        return {"ok": True, "posts": [_brief_post(r) for r in rows]}

    if name == "search_posts":
        q = str(args.get("q") or "").strip()
        posts, total = Post.load("published", None, q or None, None, 1, _limit(args.get("limit"), 5))
        return {"ok": True, "total": total, "posts": [
            {"id": p["id"], "title": p["title"], "tags": p.get("tags"), "created_at": p["created_at"]}
            for p in posts
        ]}

    if name == "get_post":
        post = Post.get(int(args.get("id") or 0))
        if not post:
            return {"ok": False, "error": "文章不存在"}
        content = str(post.get("content") or "")
        return {"ok": True, "post": {
            "id": post["id"], "title": post["title"], "status": post["status"],
            "tags": post.get("tags"), "excerpt": post.get("excerpt"),
            "content": content[:8000], "truncated": len(content) > 8000,
        }}

    if name == "list_comments":
        status = str(args.get("status") or "pending")
        limit = _limit(args.get("limit"), 10)
        where: list[str] = []
        params: list = []
        if status in {"pending", "approved", "rejected"}:
            where.append("status = ?")
            params.append(status)
        email = str(args.get("email") or "").strip()
        if email:
            where.append("email = ?")
            params.append(email)
        author = str(args.get("author") or "").strip()
        if author:
            where.append("author LIKE ?")
            params.append(f"%{author}%")
        try:
            post_id = int(args.get("post_id") or 0)
        except (TypeError, ValueError):
            post_id = 0
        if post_id:
            where.append("post_id = ?")
            params.append(post_id)
        sql = "SELECT id, post_id, project_id, author, email, content, status, is_ai, created_at FROM comments"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = db.query(sql, tuple(params))
        comments = []
        for row in rows:
            item = dict(row)
            item["email"] = _mask_email(item.get("email"))
            item["content"] = str(item.get("content") or "")[:600]
            comments.append(item)
        return {"ok": True, "count": len(comments), "comments": comments}

    if name == "list_links":
        status = str(args.get("status") or "pending")
        limit = _limit(args.get("limit"), 10)
        where: list[str] = []
        params: list = []
        if status in {"pending", "approved", "rejected"}:
            where.append("status = ?")
            params.append(status)
        q = str(args.get("q") or "").strip()
        if q:
            where.append("(name LIKE ? OR url LIKE ? OR description LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
        sql = "SELECT id, name, url, description, status, ai_state, created_at FROM links"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = db.query(sql, tuple(params))
        return {"ok": True, "links": [dict(r) for r in rows]}

    if name == "list_categories":
        rows = db.query("SELECT id, name, slug FROM categories ORDER BY sort_order ASC, id ASC")
        return {"ok": True, "categories": [dict(r) for r in rows]}

    if name == "get_stats":
        return {"ok": True, "stats": {
            "posts": int(db.scalar("SELECT COUNT(*) FROM posts", (), 0)),
            "published": int(db.scalar("SELECT COUNT(*) FROM posts WHERE status='published'", (), 0)),
            "drafts": int(db.scalar("SELECT COUNT(*) FROM posts WHERE status='draft'", (), 0)),
            "comments": int(db.scalar("SELECT COUNT(*) FROM comments", (), 0)),
            "pending_comments": int(db.scalar("SELECT COUNT(*) FROM comments WHERE status='pending'", (), 0)),
            "links": int(db.scalar("SELECT COUNT(*) FROM links", (), 0)),
            "pending_links": int(db.scalar("SELECT COUNT(*) FROM links WHERE status='pending'", (), 0)),
        }}

    if name == "create_post":
        title = str(args.get("title") or "").strip()
        content = str(args.get("content") or "").strip()
        if not title or not content:
            return {"ok": False, "error": "标题和正文不能为空"}
        category_id, cat_error = _resolve_category(args)
        if cat_error:
            return {"ok": False, "error": cat_error}
        tags = args.get("tags") or ""
        if isinstance(tags, list):
            tags = ",".join(str(t) for t in tags)
        status = "draft" if str(args.get("status") or "") == "draft" else "published"
        pid = Post.save({
            "title": title,
            "content": content,
            "tags": tags,
            "status": status,
            "category_id": str(category_id) if category_id else "",
        })
        return {"ok": True, "id": pid, "message": f"已创建文章《{title}》（{status}）"}

    if name == "update_post":
        pid = int(args.get("id") or 0)
        post = Post.get(pid)
        if not post:
            return {"ok": False, "error": "文章不存在"}
        category_id = post.get("category_id")
        if args.get("category") or args.get("category_id"):
            category_id, cat_error = _resolve_category(args)
            if cat_error:
                return {"ok": False, "error": cat_error}
        form = {
            "title": str(args.get("title") or post["title"]),
            "content": str(args.get("content") or post.get("content") or ""),
            "tags": ",".join(post.get("tags") or []),
            "status": str(args.get("status") or post["status"]),
            "category_id": str(category_id) if category_id else "",
            "excerpt": post.get("excerpt") or "",
            "excerpt_manual": "0",
        }
        Post.save(form, pid)
        return {"ok": True, "id": pid, "message": f"已更新文章《{form['title']}》"}

    if name == "create_category":
        name = str(args.get("name") or "").strip()
        if not name:
            return {"ok": False, "error": "分类名称不能为空"}
        cid = Category.save({"name": name, "slug": str(args.get("slug") or "").strip(), "sort_order": 0})
        return {"ok": True, "id": cid, "message": f"已创建分类：{name}"}

    if name == "update_category":
        cid = int(args.get("id") or 0)
        cat = Category.get(cid)
        if not cat:
            return {"ok": False, "error": "分类不存在"}
        new_name = str(args.get("name") or cat.get("name") or "").strip()
        Category.save({
            "name": new_name,
            "slug": str(args.get("slug") or cat.get("slug") or "").strip(),
            "sort_order": cat.get("sort_order") or 0,
        }, cid)
        return {"ok": True, "id": cid, "message": f"已更新分类：{new_name}"}

    if name == "approve_comment":
        cid = int(args.get("id") or 0)
        if not Comment.get(cid):
            return {"ok": False, "error": "评论不存在"}
        Comment.set_status(cid, "approved")
        return {"ok": True, "message": f"评论 #{cid} 已通过"}

    if name == "reply_comment":
        cid = int(args.get("id") or 0)
        content = str(args.get("content") or "").strip()
        parent = Comment.get(cid)
        if not parent or not content:
            return {"ok": False, "error": "评论不存在或回复为空"}
        new_id = Comment.save(
            parent.get("post_id"), "AI 助手", "", "", "", content,
            cid, 0, "", "", "approved", parent.get("project_id"), "",
            is_ai=1,
        )
        return {"ok": True, "id": new_id, "message": f"已回复评论 #{cid}"}

    if name == "add_link":
        name = str(args.get("name") or "").strip()
        url = str(args.get("url") or "").strip()
        if not name or not url:
            return {"ok": False, "error": "名称和地址不能为空"}
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        lid = Link.save({"name": name, "url": url, "description": str(args.get("description") or ""), "avatar": str(args.get("avatar") or ""), "sort_order": 0}, None, "approved")
        return {"ok": True, "id": lid, "message": f"已添加友链：{name}"}

    if name == "approve_link":
        lid = int(args.get("id") or 0)
        if not Link.get(lid):
            return {"ok": False, "error": "友链不存在"}
        Link.set_status(lid, "approved")
        return {"ok": True, "message": f"友链 #{lid} 已通过"}

    return {"ok": False, "error": "工具未实现"}
