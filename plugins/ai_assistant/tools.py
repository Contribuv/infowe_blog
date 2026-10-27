"""AI 助手可调用的白名单工具。

模型只能通过这些函数操作博客，不能拼 SQL、读文件或执行命令。
写操作由路由层二次确认后再调用 `execute`。
"""

from __future__ import annotations

import json

import db
from models import Comment, Link, Post

READ_TOOLS = {
    "search_posts": "搜索文章。参数：q（关键词，可空）、limit（默认 5）",
    "get_post": "读取一篇文章。参数：id",
    "list_comments": "列出评论。参数：status（pending/approved/rejected/all）、limit（默认 10）",
    "list_links": "列出友链。参数：status（pending/approved/rejected/all）、limit（默认 10）",
    "list_categories": "列出文章分类",
    "get_stats": "读取站点统计（文章/评论/友链数量）",
}

WRITE_TOOLS = {
    "create_post": "创建文章。参数：title、content（Markdown）、tags（数组或逗号分隔）、status（published/draft）",
    "update_post": "修改文章。参数：id、title/title 可空、content、status",
    "approve_comment": "通过一条评论。参数：id",
    "reply_comment": "以 AI 助手身份回复评论。参数：id（被回复评论）、content",
    "add_link": "新增友链。参数：name、url、description、avatar",
    "approve_link": "通过一条友链。参数：id",
}

ALL_TOOLS = {**READ_TOOLS, **WRITE_TOOLS}


def _audit(action: str, args: dict, result: dict, ok: bool) -> None:
    try:
        db.execute(
            "INSERT INTO ai_audit (action, args, result, ok, created_at) VALUES (?,?,?,?,datetime('now','localtime'))",
            (action, json.dumps(args, ensure_ascii=False)[:4000], json.dumps(result, ensure_ascii=False)[:4000], 1 if ok else 0),
        )
    except Exception:
        pass


def _limit(value, default=5, maximum=20) -> int:
    try:
        return max(1, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


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
    if name == "search_posts":
        posts, total = Post.load("published", None, str(args.get("q") or "").strip() or None, None, 1, _limit(args.get("limit"), 5))
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
        if status == "all":
            rows = db.query("SELECT id, post_id, project_id, author, content, status, is_ai, created_at FROM comments ORDER BY id DESC LIMIT ?", (limit,))
        else:
            rows = db.query("SELECT id, post_id, project_id, author, content, status, is_ai, created_at FROM comments WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit))
        return {"ok": True, "comments": [dict(r) for r in rows]}

    if name == "list_links":
        status = str(args.get("status") or "pending")
        limit = _limit(args.get("limit"), 10)
        if status == "all":
            rows = db.query("SELECT id, name, url, description, status, ai_state, created_at FROM links ORDER BY id DESC LIMIT ?", (limit,))
        else:
            rows = db.query("SELECT id, name, url, description, status, ai_state, created_at FROM links WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit))
        return {"ok": True, "links": [dict(r) for r in rows]}

    if name == "list_categories":
        rows = db.query("SELECT id, name FROM categories ORDER BY sort_order ASC, id ASC")
        return {"ok": True, "categories": [dict(r) for r in rows]}

    if name == "get_stats":
        return {"ok": True, "stats": {
            "posts": int(db.scalar("SELECT COUNT(*) FROM posts", (), 0)),
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
        tags = args.get("tags") or ""
        if isinstance(tags, list):
            tags = ",".join(str(t) for t in tags)
        status = "draft" if str(args.get("status") or "") == "draft" else "published"
        pid = Post.save({"title": title, "content": content, "tags": tags, "status": status})
        return {"ok": True, "id": pid, "message": f"已创建文章《{title}》（{status}）"}

    if name == "update_post":
        pid = int(args.get("id") or 0)
        post = Post.get(pid)
        if not post:
            return {"ok": False, "error": "文章不存在"}
        form = {
            "title": str(args.get("title") or post["title"]),
            "content": str(args.get("content") or post.get("content") or ""),
            "tags": ",".join(post.get("tags") or []),
            "status": str(args.get("status") or post["status"]),
            "excerpt": post.get("excerpt") or "",
            "excerpt_manual": "0",
        }
        Post.save(form, pid)
        return {"ok": True, "id": pid, "message": f"已更新文章《{form['title']}》"}

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
