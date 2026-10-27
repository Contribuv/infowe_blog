"""多栏布局的侧栏数据：博主、标签、分类、最新评论。"""

from __future__ import annotations

import re

import db
from models import Category, Post
from services import avatar, settings


def _plain(text: str, limit: int = 46) -> str:
    value = str(text or "")
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", value)
    value = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"```.*?```", " ", value, flags=re.S)
    value = re.sub(r"[`*_>#~]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > limit:
        value = value[:limit].rstrip() + "…"
    return value


def _comments(limit: int = 5) -> list[dict]:
    blogger = settings.get_str("author", "").strip()
    where = [
        "c.status = 'approved'",
        "c.is_private = 0",
        "c.is_owner = 0",
        "c.is_ai = 0",
        "(c.post_id IS NOT NULL OR c.project_id IS NOT NULL)",
    ]
    params: list = []
    if blogger:
        where.append("c.author != ?")
        params.append(blogger)
    rows = db.query(
        "SELECT c.id, c.author, c.email_hash, c.qq, c.content, c.created_at, "
        "c.post_id, c.project_id, p.title AS post_title, pj.name AS project_name "
        "FROM comments c "
        "LEFT JOIN posts p ON c.post_id = p.id "
        "LEFT JOIN projects pj ON c.project_id = pj.id "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY c.created_at DESC, c.id DESC LIMIT ?",
        [*params, int(limit)],
    )
    items = []
    for row in rows:
        item = dict(row)
        url, _ = avatar.urls(str(item.get("email_hash") or ""), str(item.get("qq") or ""))
        if item.get("post_id"):
            source_url = f"/post/{item['post_id']}#comment-{item['id']}"
            source_title = item.get("post_title") or "文章"
        else:
            source_url = f"/projects/{item['project_id']}#comment-{item['id']}"
            source_title = item.get("project_name") or "项目"
        items.append(
            {
                "author": item.get("author") or "匿名读者",
                "avatar": url or avatar.default_url(),
                "text": _plain(str(item.get("content") or "")),
                "created_at": item.get("created_at") or "",
                "source_title": source_title,
                "source_url": source_url,
            }
        )
    return items


def data() -> dict:
    cats = [item for item in Category.stats() if int(item.get("post_count") or 0) > 0]
    all_tags = Post.tag_counts(9999)
    post_total = int(db.scalar("SELECT COUNT(*) FROM posts WHERE status = 'published'", (), 0) or 0)
    return {
        "side_tags": all_tags[:12],
        "side_categories": cats,
        "side_comments": _comments(5),
        "side_post_total": post_total,
        "side_tag_total": len(all_tags),
        "side_category_total": len(cats),
    }
