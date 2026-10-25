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
) -> tuple[list[dict], int]:
    conditions: list[str] = []
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

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    total = int(db.scalar(f"SELECT COUNT(*) FROM posts {where}", params, 0) or 0)
    page = max(1, int(page or 1))
    per_page = max(1, int(per_page or PAGE_SIZE))
    offset = (page - 1) * per_page
    rows = db.query(
        f"SELECT * FROM posts {where} ORDER BY is_featured DESC, created_at DESC LIMIT ? OFFSET ?",
        [*params, per_page, offset],
    )
    return [hydrate(r) for r in rows], total


def all_years() -> list[str]:
    rows = db.query(
        "SELECT DISTINCT SUBSTR(created_at, 1, 4) AS year FROM posts "
        "WHERE status = 'published' ORDER BY year DESC"
    )
    return [str(r["year"]) for r in rows]


def get(post_id: int) -> dict | None:
    row = db.one("SELECT * FROM posts WHERE id = ?", (post_id,))
    return hydrate(row) if row else None


def get_by_slug(slug: str) -> dict | None:
    row = db.one("SELECT * FROM posts WHERE slug = ?", (slug,))
    return hydrate(row) if row else None


def related(current_id: int, tags: list[str], limit: int = 4) -> list[dict]:
    results: list[dict] = []
    seen: set[int] = set()
    for tag in tags:
        if not tag:
            continue
        escaped = tag.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = db.query(
            "SELECT * FROM posts WHERE status = 'published' AND id != ? AND tags LIKE ? ESCAPE '\\' "
            "ORDER BY created_at DESC LIMIT ?",
            (current_id, f'%"{escaped}"%', limit),
        )
        for row in rows:
            pid = int(row["id"])
            if pid in seen:
                continue
            seen.add(pid)
            results.append(hydrate(row))
            if len(results) >= limit:
                return results
    return results[:limit]


def featured(limit: int = 3) -> list[dict]:
    rows = db.query(
        "SELECT * FROM posts WHERE status = 'published' AND is_featured = 1 "
        "ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    return [hydrate(r) for r in rows]


def home_posts(limit: int = 6, exclude_featured: bool = False) -> list[dict]:
    featured_rows = db.query(
        "SELECT * FROM posts WHERE status = 'published' AND is_featured = 1 ORDER BY created_at DESC"
    )
    featured_ids = [int(r["id"]) for r in featured_rows]
    if exclude_featured:
        if featured_ids:
            marks = ",".join("?" * len(featured_ids))
            rows = db.query(
                f"SELECT * FROM posts WHERE status = 'published' AND id NOT IN ({marks}) "
                "ORDER BY created_at DESC LIMIT ?",
                (*featured_ids, limit),
            )
        else:
            rows = db.query(
                "SELECT * FROM posts WHERE status = 'published' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return [hydrate(r) for r in rows]

    if featured_ids:
        marks = ",".join("?" * len(featured_ids))
        latest = db.query(
            f"SELECT * FROM posts WHERE status = 'published' AND id NOT IN ({marks}) "
            "ORDER BY created_at DESC",
            featured_ids,
        )
    else:
        latest = db.query("SELECT * FROM posts WHERE status = 'published' ORDER BY created_at DESC")
    return [hydrate(r) for r in (featured_rows + latest)][:limit]


def all_tags() -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in db.query("SELECT tags FROM posts"):
        for tag in json_list(row["tags"]):
            tag = str(tag)
            counts[tag] = counts.get(tag, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def stats() -> dict:
    return {
        "total": int(db.scalar("SELECT COUNT(*) FROM posts", (), 0)),
        "published": int(db.scalar("SELECT COUNT(*) FROM posts WHERE status='published'", (), 0)),
        "drafts": int(db.scalar("SELECT COUNT(*) FROM posts WHERE status='draft'", (), 0)),
        "hidden": int(db.scalar("SELECT COUNT(*) FROM posts WHERE status='hidden'", (), 0)),
        "projects": int(db.scalar("SELECT COUNT(*) FROM projects", (), 0)),
        "links": int(db.scalar("SELECT COUNT(*) FROM links WHERE status='approved'", (), 0)),
        "comments": int(db.scalar("SELECT COUNT(*) FROM comments", (), 0)),
        "pending": int(db.scalar("SELECT COUNT(*) FROM comments WHERE status='pending'", (), 0)),
    }


def increment_views(post_id: int) -> None:
    db.execute("UPDATE posts SET views = views + 1 WHERE id = ?", (post_id,))


def slug_exists(slug: str, exclude_id: int | None = None) -> bool:
    if exclude_id is not None:
        return db.one("SELECT 1 FROM posts WHERE slug = ? AND id != ?", (slug, exclude_id)) is not None
    return db.one("SELECT 1 FROM posts WHERE slug = ?", (slug,)) is not None


def save(form: dict, post_id: int | None = None) -> int:
    title = (form.get("title") or "").strip()
    tags = [t.strip() for t in (form.get("tags") or "").split(",") if t.strip()]
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
    if not excerpt and content:
        excerpt = strip_markdown(content)[:200]

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
    db.execute("DELETE FROM posts WHERE id = ?", (post_id,))


def delete_with_uploads(post_id: int) -> int:
    from services import upload

    row = db.one("SELECT title, content, excerpt, tags FROM posts WHERE id = ?", (post_id,))
    gone = upload.extract_urls(
        (row["title"] or "", row["content"] or "", row["excerpt"] or "", row["tags"] or "")
    ) if row else set()
    db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    if not gone:
        return 0
    survivors = upload.referenced_urls()
    removed = 0
    for url in gone:
        if url and url not in survivors and upload.delete_by_url(url):
            removed += 1
    return removed


def bulk_set_status(ids: list[int], status: str) -> int:
    status = normalize_status(status)
    ids = [int(i) for i in ids if int(i) > 0]
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    return db.execute(f"UPDATE posts SET status = ? WHERE id IN ({marks})", (status, *ids)).rowcount


def bulk_delete(ids: list[int]) -> int:
    total = 0
    for pid in [int(i) for i in ids if int(i) > 0]:
        delete_with_uploads(pid)
        total += 1
    return total


def adjacent(created_at: str, earlier: bool) -> dict | None:
    if earlier:
        row = db.one(
            "SELECT id, title FROM posts WHERE status='published' AND created_at < ? "
            "ORDER BY created_at DESC LIMIT 1",
            (created_at,),
        )
    else:
        row = db.one(
            "SELECT id, title FROM posts WHERE status='published' AND created_at > ? "
            "ORDER BY created_at ASC LIMIT 1",
            (created_at,),
        )
    return {"id": int(row["id"]), "title": row["title"]} if row else None
