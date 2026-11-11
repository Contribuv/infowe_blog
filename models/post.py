"""文章模型。"""

from __future__ import annotations

import re
from typing import Any

import db
from models.base import json_dump, json_list, row_to_dict, slugify, strip_markdown, word_count

STATUSES = ("published", "draft", "hidden")
PAGE_SIZE = 10


def normalize_status(status: str) -> str:
    return status if status in STATUSES else "published"


def hydrate(row) -> dict:
    data = row_to_dict(row) or {}
    data["tags"] = json_list(data.get("tags"))
    data["id"] = int(data.get("id") or 0)
    data["views"] = int(data.get("views") or 0)
    data["is_featured"] = int(data.get("is_featured") or 0)
    data["read_time"] = int(data.get("read_time") or 3)
    data["category_id"] = int(data["category_id"]) if data.get("category_id") is not None else None
    data["category_name"] = data.get("category_name") or ""
    return data


def load(
    status: str | None = "published",
    tag: str | None = None,
    search: str | None = None,
    year: str | None = None,
    page: int = 1,
    per_page: int = PAGE_SIZE,
    category_id: int | None = None,
    month: str | None = None,
) -> tuple[list[dict], int]:
    # 回收站（deleted_at 非空）的文章对前台和后台列表都不可见
    conditions: list[str] = ["deleted_at IS NULL"]
    params: list[Any] = []
    if status is not None:
        conditions.append("status = ?")
        params.append(status)
    if tag:
        conditions.append("tags LIKE ? ESCAPE '\\'")
        escaped = tag.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(f'%"{escaped}"%')
    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(
            "(title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\' OR excerpt LIKE ? ESCAPE '\\')"
        )
        like = f"%{escaped}%"
        params.extend([like, like, like])
    if year:
        conditions.append("SUBSTR(created_at, 1, 4) = ?")
        params.append(year)
    if month:
        conditions.append("SUBSTR(created_at, 6, 2) = ?")
        params.append(month)
    if category_id is not None:
        conditions.append("category_id = ?")
        params.append(int(category_id))

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    total = int(db.scalar(f"SELECT COUNT(*) FROM posts {where}", params, 0) or 0)
    page = max(1, int(page or 1))
    per_page = max(1, int(per_page or PAGE_SIZE))
    offset = (page - 1) * per_page
    # 列表一律按时间倒序：精选只影响首页「精选推荐」区，不在归档 / 分类 / 标签 / 搜索 / RSS 里置顶
    rows = db.query(
        f"SELECT * FROM posts {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        [*params, per_page, offset],
    )
    return [hydrate(r) for r in rows], total


def all_years() -> list[str]:
    rows = db.query(
        "SELECT DISTINCT SUBSTR(created_at, 1, 4) AS year FROM posts "
        "WHERE status = 'published' AND deleted_at IS NULL ORDER BY year DESC"
    )
    return [str(r["year"]) for r in rows]


def year_counts() -> dict[str, int]:
    """每年已发布文章数，供归档页年份标题使用。"""
    rows = db.query(
        "SELECT SUBSTR(created_at, 1, 4) AS year, COUNT(*) AS n FROM posts "
        "WHERE status = 'published' AND deleted_at IS NULL GROUP BY year ORDER BY year DESC"
    )
    return {str(r["year"]): int(r["n"]) for r in rows}


def month_counts(year: str) -> dict[str, int]:
    """某年每月已发布文章数，供归档选择器的月份分组使用（仅返回有文章的月份）。"""
    rows = db.query(
        "SELECT SUBSTR(created_at, 6, 2) AS month, COUNT(*) AS n FROM posts "
        "WHERE status = 'published' AND deleted_at IS NULL AND SUBSTR(created_at, 1, 4) = ? "
        "GROUP BY month ORDER BY month DESC",
        (str(year),),
    )
    return {str(int(r["month"])): int(r["n"]) for r in rows}


def month_counts_all() -> dict[str, dict[str, int]]:
    """全部年份的逐月文章数：{年: {月: 篇数}}，供归档浮窗切换年份时即时渲染月份。"""
    rows = db.query(
        "SELECT SUBSTR(created_at, 1, 4) AS year, SUBSTR(created_at, 6, 2) AS month, COUNT(*) AS n "
        "FROM posts WHERE status = 'published' AND deleted_at IS NULL "
        "GROUP BY year, month ORDER BY year DESC, month DESC"
    )
    result: dict[str, dict[str, int]] = {}
    for row in rows:
        result.setdefault(str(row["year"]), {})[str(int(row["month"]))] = int(row["n"])
    return result


def tag_counts(limit: int = 12) -> list[tuple[str, int]]:
    """热门标签，供首页/归档页侧栏使用。"""
    rows = db.query("SELECT tags FROM posts WHERE status = 'published' AND deleted_at IS NULL")
    counts: dict[str, int] = {}
    for row in rows:
        for tag in json_list(row["tags"]):
            name = str(tag).strip()
            if name:
                counts[name] = counts.get(name, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ordered[: max(1, int(limit))]


def get(post_id: int) -> dict | None:
    row = db.one("SELECT * FROM posts WHERE id = ? AND deleted_at IS NULL", (post_id,))
    return hydrate(row) if row else None


def get_by_slug(slug: str) -> dict | None:
    row = db.one("SELECT * FROM posts WHERE slug = ? AND deleted_at IS NULL", (slug,))
    return hydrate(row) if row else None


def related(current_id: int, tags: list[str], limit: int = 4) -> list[dict]:
    """一条 SQL 取相关文章：所有 tag 用 OR 拼起来，避免每个 tag 查一次。

    默认取最多 4 条：正文末尾的相关推荐是 2–4 张强调色小卡，
    桌面两列、移动端单列。先按命中 tag 数降序，再按发布时间降序，
    避免时间最新但只沾一个冷门 tag 的文章挤掉真正高相关的。
    """
    tags = [str(t).strip() for t in (tags or []) if str(t).strip()][:6]
    if not tags:
        return []
    escaped = [
        t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        for t in tags
    ]
    conds = " OR ".join(["tags LIKE ? ESCAPE '\\'"] * len(escaped))
    hits = " + ".join(
        ["CASE WHEN tags LIKE ? ESCAPE '\\' THEN 1 ELSE 0 END"] * len(escaped)
    )
    patterns = [f'%"{e}"%' for e in escaped]
    params = [int(current_id), *patterns, *patterns, int(limit)]
    rows = db.query(
        f"SELECT * FROM posts WHERE status = 'published' AND deleted_at IS NULL AND id != ? AND ({conds}) "
        f"ORDER BY ({hits}) DESC, created_at DESC LIMIT ?",
        tuple(params),
    )
    return [hydrate(r) for r in rows]


def featured(limit: int = 3) -> list[dict]:
    rows = db.query(
        "SELECT * FROM posts WHERE status = 'published' AND deleted_at IS NULL AND is_featured = 1 "
        "ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    return [hydrate(r) for r in rows]


def home_posts(limit: int = 6, exclude_featured: bool = False) -> list[dict]:
    featured_rows = db.query(
        "SELECT * FROM posts WHERE status = 'published' AND deleted_at IS NULL AND is_featured = 1 ORDER BY created_at DESC"
    )
    featured_ids = [int(r["id"]) for r in featured_rows]
    if exclude_featured:
        if featured_ids:
            marks = ",".join("?" * len(featured_ids))
            rows = db.query(
                f"SELECT * FROM posts WHERE status = 'published' AND deleted_at IS NULL AND id NOT IN ({marks}) "
                "ORDER BY created_at DESC LIMIT ?",
                (*featured_ids, limit),
            )
        else:
            rows = db.query(
                "SELECT * FROM posts WHERE status = 'published' AND deleted_at IS NULL ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return [hydrate(r) for r in rows]

    if featured_ids:
        marks = ",".join("?" * len(featured_ids))
        latest = db.query(
            f"SELECT * FROM posts WHERE status = 'published' AND deleted_at IS NULL AND id NOT IN ({marks}) "
            "ORDER BY created_at DESC",
            featured_ids,
        )
    else:
        latest = db.query("SELECT * FROM posts WHERE status = 'published' AND deleted_at IS NULL ORDER BY created_at DESC")
    return [hydrate(r) for r in (featured_rows + latest)][:limit]


def all_tags() -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in db.query("SELECT tags FROM posts WHERE deleted_at IS NULL"):
        for tag in json_list(row["tags"]):
            tag = str(tag)
            counts[tag] = counts.get(tag, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def stats() -> dict:
    return {
        "total": int(db.scalar("SELECT COUNT(*) FROM posts WHERE deleted_at IS NULL", (), 0)),
        "published": int(db.scalar("SELECT COUNT(*) FROM posts WHERE status='published' AND deleted_at IS NULL", (), 0)),
        "drafts": int(db.scalar("SELECT COUNT(*) FROM posts WHERE status='draft' AND deleted_at IS NULL", (), 0)),
        "hidden": int(db.scalar("SELECT COUNT(*) FROM posts WHERE status='hidden' AND deleted_at IS NULL", (), 0)),
        "trashed": int(db.scalar("SELECT COUNT(*) FROM posts WHERE deleted_at IS NOT NULL", (), 0)),
        "projects": int(db.scalar("SELECT COUNT(*) FROM projects", (), 0)),
        "links": int(db.scalar("SELECT COUNT(*) FROM links WHERE status='approved'", (), 0)),
        "comments": int(db.scalar("SELECT COUNT(*) FROM comments WHERE deleted_at IS NULL", (), 0)),
        "pending": int(
            db.scalar(
                "SELECT COUNT(*) FROM comments WHERE status='pending' AND deleted_at IS NULL", (), 0
            )
        ),
    }


def increment_views(post_id: int) -> None:
    db.execute("UPDATE posts SET views = views + 1 WHERE id = ?", (post_id,))


def heatmap(weeks: int = 53) -> dict:
    """写作热力图数据：按自然日统计近一年的已发布文章。

    cells 按日期顺序排列，每 7 个为一列（周日起），模板用
    grid-auto-flow: column 填充；months 给出月份标签的起始列与跨度。
    """
    from datetime import date, timedelta

    today = date.today()
    # 以本周六为终点往前推 53 周，保证 start 是周日且窗口包含今天
    end = today + timedelta(days=(5 - today.weekday()) % 7)
    start = end - timedelta(days=weeks * 7 - 1)

    counts = {
        str(row["d"]): int(row["n"])
        for row in db.query(
            "SELECT substr(created_at, 1, 10) AS d, COUNT(*) AS n FROM posts "
            "WHERE status='published' AND deleted_at IS NULL "
            "AND substr(created_at, 1, 10) >= ? GROUP BY d",
            (start.isoformat(),),
        )
    }

    cells: list[dict] = []
    total = 0
    active_days = 0
    longest = 0
    streak = 0
    for index in range(weeks * 7):
        day = start + timedelta(days=index)
        future = day > today
        count = 0 if future else counts.get(day.isoformat(), 0)
        if count:
            total += count
            active_days += 1
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
        if count == 0:
            level = 0
        elif count >= 4:
            level = 4
        else:
            level = count
        cells.append(
            {
                "date": day.isoformat(),
                "count": count,
                "level": level,
                "future": future,
            }
        )

    months: list[dict] = []
    prev_month = 0
    for col in range(weeks):
        day = start + timedelta(days=col * 7)
        if col == 0 or day.month != prev_month:
            months.append({"label": f"{day.month}月", "col": col + 1, "span": 1})
            prev_month = day.month
        else:
            months[-1]["span"] += 1

    return {
        "cells": cells,
        "months": months,
        "total": total,
        "active_days": active_days,
        "longest_streak": longest,
    }


def slug_exists(slug: str, exclude_id: int | None = None) -> bool:
    if exclude_id is not None:
        return db.one("SELECT 1 FROM posts WHERE slug = ? AND id != ?", (slug, exclude_id)) is not None
    return db.one("SELECT 1 FROM posts WHERE slug = ?", (slug,)) is not None


def _auto_excerpt(content: str, limit: int = 200) -> str:
    """自动生成纯文本摘要：剔除代码块/行内代码/图片与 HTML 标签后再截断。

    直接 strip_markdown 会把代码块内容当正文（列表页漏出 `json {"type":...}`），
    `**加粗**` 残留也来自旧逻辑；先删结构块，只留人写的文字。
    """
    text = content or ""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)  # 围栏代码块整体剔除
    text = re.sub(r"`[^`\n]*`", " ", text)  # 行内代码
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)  # 图片：连 URL 一起剔除
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # 链接只留文字
    text = strip_markdown(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def save(form: dict, post_id: int | None = None) -> int:
    title = (form.get("title") or "").strip()
    # 标签去重：大小写不敏感，保留首次出现（前端 change 时也去重，此处兜底防绕过）
    tags, seen = [], set()
    for t in (form.get("tags") or "").split(","):
        t = t.strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            tags.append(t)
    tags_json = json_dump(tags)

    slug = (form.get("slug") or "").strip()
    if not slug:
        slug = slugify(title or "untitled")
    slug = slugify(slug)
    if post_id is not None:
        base, i = slug, 2
        while slug_exists(slug, post_id):
            slug = f"{base}-{i}"
            i += 1
    else:
        base, i = slug, 2
        while slug_exists(slug):
            slug = f"{base}-{i}"
            i += 1

    content = form.get("content") or ""
    content = re.sub(r"<(https?://[^>\s]+)>", r"[\1](\1)", content)
    read_time = max(1, word_count(strip_markdown(content)) // 200) if content else 3
    is_featured = 1 if str(form.get("is_featured", "")) == "1" else 0

    cat_raw = str(form.get("category_id", "")).strip()
    category_id = int(cat_raw) if cat_raw.isdigit() else None

    excerpt = (form.get("excerpt") or "").strip()
    # 默认每次保存都按最新正文重新生成摘要；只有用户手动编辑摘要时才保留
    excerpt_manual = str(form.get("excerpt_manual") or "0") == "1"
    if (not excerpt or not excerpt_manual) and content:
        excerpt = _auto_excerpt(content)

    created_at = (form.get("created_at") or "").strip().replace("T", " ")
    if len(created_at) == 16:
        created_at += ":00"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", created_at or ""):
        created_at = None
    status = normalize_status(str(form.get("status") or "published"))
    cover = (form.get("cover") or "").strip()

    now = db.now()
    if post_id is not None:
        db.execute(
            "UPDATE posts SET title=?, slug=?, content=?, excerpt=?, tags=?, cover=?, "
            "is_featured=?, read_time=?, status=?, category_id=?, "
            "created_at=COALESCE(?, created_at), updated_at=? WHERE id=?",
            (title, slug, content, excerpt, tags_json, cover, is_featured, read_time,
             status, category_id, created_at, now, post_id),
        )
        return post_id

    return db.insert(
        "INSERT INTO posts (title, slug, content, excerpt, tags, cover, is_featured, read_time, "
        "status, category_id, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,COALESCE(?,?),?)",
        (title, slug, content, excerpt, tags_json, cover, is_featured, read_time,
         status, category_id, created_at, now, now),
    )


def delete(post_id: int) -> None:
    """软删除：移入回收站，可恢复；彻底删除请用 purge()。"""
    db.execute(
        "UPDATE posts SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
        (db.now(), post_id),
    )


def trash(post_id: int) -> None:
    """移入回收站（软删单篇）。"""
    delete(post_id)


def trash_many(ids: list[int]) -> int:
    ids = [int(i) for i in ids if int(i) > 0]
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    return db.execute(
        f"UPDATE posts SET deleted_at = ? WHERE deleted_at IS NULL AND id IN ({marks})",
        (db.now(), *ids),
    ).rowcount


def restore(post_id: int) -> None:
    """从回收站恢复。"""
    db.execute("UPDATE posts SET deleted_at = NULL WHERE id = ?", (post_id,))


def restore_many(ids: list[int]) -> int:
    ids = [int(i) for i in ids if int(i) > 0]
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    return db.execute(
        f"UPDATE posts SET deleted_at = NULL WHERE id IN ({marks})", ids
    ).rowcount


def trash_list() -> list[dict]:
    """回收站列表。"""
    rows = db.query(
        "SELECT * FROM posts WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC, id DESC"
    )
    return [hydrate(r) for r in rows]


def trash_count() -> int:
    return int(db.scalar("SELECT COUNT(*) FROM posts WHERE deleted_at IS NOT NULL", (), 0) or 0)


def _purge_rows(rows: list) -> int:
    """物理删除给定文章行并清理不再被引用的上传文件，返回清理文件数。"""
    from services import upload

    gone: set[str] = set()
    for row in rows:
        keys = row.keys() if hasattr(row, "keys") else ()
        # 封面图只在 cover 字段里，正文未必引用；漏掉会导致图残留在 uploads
        cover = row["cover"] if "cover" in keys else ""
        gone |= upload.extract_urls(
            (row["title"] or "", row["content"] or "", row["excerpt"] or "",
             row["tags"] or "", cover or "")
        )
        db.execute("DELETE FROM posts WHERE id = ?", (row["id"],))
    if not gone:
        return 0
    survivors = upload.referenced_urls()
    removed = 0
    for url in gone:
        if url and url not in survivors and upload.delete_by_url(url):
            removed += 1
    return removed


def purge(post_id: int) -> int:
    """彻底删除（回收站里的删除）：物理删行 + 清理不再被引用的上传文件。"""
    row = db.one(
        "SELECT id, title, content, excerpt, tags, cover FROM posts WHERE id = ?", (post_id,)
    )
    return _purge_rows([row]) if row else 0


def purge_many(ids: list[int]) -> int:
    """批量彻底删除。引用扫描只做一次，避免每篇都全表扫（O(n²)）。"""
    ids = [int(i) for i in ids if int(i) > 0]
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    rows = db.query(
        f"SELECT id, title, content, excerpt, tags, cover FROM posts WHERE id IN ({marks})", ids
    )
    _purge_rows(rows)
    return len(rows)


def empty_trash() -> int:
    """清空回收站：真删全部软删文章并清理附件。"""
    rows = db.query(
        "SELECT id, title, content, excerpt, tags, cover FROM posts WHERE deleted_at IS NOT NULL"
    )
    if not rows:
        return 0
    _purge_rows(rows)
    return len(rows)


def bulk_set_status(ids: list[int], status: str) -> int:
    status = normalize_status(status)
    ids = [int(i) for i in ids if int(i) > 0]
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    return db.execute(f"UPDATE posts SET status = ? WHERE id IN ({marks})", (status, *ids)).rowcount


def adjacent(created_at: str, earlier: bool) -> dict | None:
    if earlier:
        row = db.one(
            "SELECT id, title FROM posts WHERE status='published' AND deleted_at IS NULL AND created_at < ? "
            "ORDER BY created_at DESC LIMIT 1",
            (created_at,),
        )
    else:
        row = db.one(
            "SELECT id, title FROM posts WHERE status='published' AND deleted_at IS NULL AND created_at > ? "
            "ORDER BY created_at ASC LIMIT 1",
            (created_at,),
        )
    return {"id": int(row["id"]), "title": row["title"]} if row else None
