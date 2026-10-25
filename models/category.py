"""分类模型。"""

from __future__ import annotations

import db
from models.base import row_to_dict, slugify


def load() -> list[dict]:
    rows = db.query("SELECT * FROM categories ORDER BY sort_order ASC, id ASC")
    return [dict(r) for r in rows]


def get(cat_id: int) -> dict | None:
    return row_to_dict(db.one("SELECT * FROM categories WHERE id = ?", (cat_id,)))


def name_map() -> dict[int, str]:
    return {int(r["id"]): str(r["name"]) for r in db.query("SELECT id, name FROM categories")}


def save(form: dict, cat_id: int | None = None) -> int:
    name = (form.get("name") or "").strip()
    slug = (form.get("slug") or "").strip() or slugify(name, "category")
    sort_order = int(form.get("sort_order") or 0)
    if cat_id is not None:
        db.execute(
            "UPDATE categories SET name=?, slug=?, sort_order=? WHERE id=?",
            (name, slug, sort_order, cat_id),
        )
        return cat_id
    return db.insert(
        "INSERT INTO categories (name, slug, sort_order) VALUES (?,?,?)",
        (name, slug, sort_order),
    )


def delete(cat_id: int) -> None:
    db.execute("UPDATE posts SET category_id = NULL WHERE category_id = ?", (cat_id,))
    db.execute("DELETE FROM categories WHERE id = ?", (cat_id,))


def bulk_delete(ids: list[int]) -> int:
    count = 0
    for cid in [int(i) for i in ids if int(i) > 0]:
        delete(cid)
        count += 1
    return count


def stats() -> list[dict]:
    rows = db.query(
        "SELECT c.*, COUNT(p.id) AS post_count FROM categories c "
        "LEFT JOIN posts p ON p.category_id = c.id AND p.status = 'published' "
        "GROUP BY c.id ORDER BY c.sort_order ASC, c.id ASC"
    )
    return [dict(r) for r in rows]
