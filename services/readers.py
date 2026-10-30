"""读者排行与走心评论：只聚合公开评论，不额外维护用户表。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

import db
from services import avatar, settings

RANK_MONTHS = 6
RANK_PER_PAGE = 10


def _blogger() -> str:
    return settings.get_str("author", "").strip()


def _key(row: dict) -> str:
    """同一个读者优先按邮箱哈希聚合；没留邮箱时退回昵称。"""
    return str(row.get("email_hash") or "").strip().lower() or str(row.get("author") or "").strip().lower()


def _plain(text: str, limit: int | None = None) -> str:
    """评论正文转纯文本：去掉图片、链接语法和 Markdown 标记。"""
    value = str(text or "")
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", value)
    value = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"```.*?```", " ", value, flags=re.S)
    value = re.sub(r"[`*_>#~]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    if limit and len(value) > limit:
        value = value[:limit].rstrip() + "…"
    return value


def _site(url: str) -> str:
    value = str(url or "").strip()
    return value if re.match(r"^https?://", value, re.I) else ""


def _avatar(row: dict) -> str:
    url, _ = avatar.urls(str(row.get("email_hash") or ""), str(row.get("qq") or ""))
    return url or avatar.default_url()


def _source(row: dict) -> tuple[str, str]:
    if row.get("post_id"):
        return row.get("post_title") or "文章", f"/post/{row['post_id']}#comment-{row['id']}"
    if row.get("project_id"):
        return row.get("project_name") or "项目", f"/projects/{row['project_id']}#comment-{row['id']}"
    return "", ""


def _rows(where: str, params: list, order: str = "c.created_at DESC, c.id DESC") -> list[dict]:
    sql = (
        "SELECT c.id, c.author, c.email_hash, c.qq, c.website, c.content, c.created_at, "
        "c.post_id, c.project_id, p.title AS post_title, pj.name AS project_name "
        "FROM comments c "
        "LEFT JOIN posts p ON c.post_id = p.id "
        "LEFT JOIN projects pj ON c.project_id = pj.id "
        f"WHERE {where} ORDER BY {order}"
    )
    return [dict(r) for r in db.query(sql, params)]


def _public_filter(months: int | None = RANK_MONTHS) -> tuple[str, list]:
    blogger = _blogger()
    parts = [
        "c.status = 'approved'",
        "c.is_private = 0",
        "c.is_owner = 0",
        "c.is_ai = 0",
        "c.deleted_at IS NULL",
    ]
    params: list = []
    if blogger:
        parts.append("c.author != ?")
        params.append(blogger)
    if months:
        parts.append("c.created_at >= datetime('now', ?)")
        params.append(f"-{int(months)} months")
    return " AND ".join(parts), params


def rank(page: int = 1, per_page: int = RANK_PER_PAGE) -> dict:
    """留言排行：返回当页读者、总人数、分页与统计。"""
    where, params = _public_filter()
    rows = _rows(where, params)

    buckets: dict[str, dict] = {}
    for row in rows:
        key = _key(row)
        if not key:
            continue
        item = buckets.get(key)
        if item is None:
            buckets[key] = {"key": key, "count": 1, "last": row}
        else:
            item["count"] += 1

    ordered = sorted(
        buckets.values(),
        key=lambda item: (-item["count"], _neg_time(item["last"].get("created_at"))),
    )

    total = len(ordered)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(max(1, int(page or 1)), total_pages)
    start = (page - 1) * per_page
    items = []
    for index, bucket in enumerate(ordered[start:start + per_page], start=start + 1):
        row = bucket["last"]
        title, url = _source(row)
        items.append(
            {
                "rank": index,
                "author": row.get("author") or "匿名读者",
                "website": _site(str(row.get("website") or "")),
                "avatar": _avatar(row),
                "count": bucket["count"],
                "last_at": row.get("created_at") or "",
                "last_text": _plain(str(row.get("content") or ""), 60),
                "source_title": title,
                "source_url": url,
            }
        )

    month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    stats = {
        "comments": len(rows),
        "readers": total,
        "recent": sum(1 for row in rows if str(row.get("created_at") or "") >= month_ago),
        "average": round(len(rows) / total, 1) if total else 0,
    }
    return {
        "items": items,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "stats": stats,
    }


def _neg_time(value) -> float:
    """把时间字符串转成可排序负数，让最近留言排在前面。"""
    try:
        return -datetime.fromisoformat(str(value or "").replace("Z", "")).timestamp()
    except ValueError:
        return 0.0

