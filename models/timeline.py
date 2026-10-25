"""时间线 / 记忆模型。"""

from __future__ import annotations

import db
from models.base import row_to_dict


def load() -> list[dict]:
    rows = db.query("SELECT * FROM timeline ORDER BY sort_order ASC, date DESC, id DESC")
    return [dict(r) for r in rows]


def get(item_id: int) -> dict | None:
    return row_to_dict(db.one("SELECT * FROM timeline WHERE id = ?", (item_id,)))


def save(form: dict, item_id: int | None = None) -> int:
    date = (form.get("date") or "").strip()
    content = (form.get("content") or "").strip()
    sort_order = int(form.get("sort_order") or 0)
    if item_id is not None:
        db.execute(
            "UPDATE timeline SET date=?, content=?, sort_order=? WHERE id=?",
            (date, content, sort_order, item_id),
        )
        return item_id
    return db.insert(
        "INSERT INTO timeline (date, content, sort_order) VALUES (?,?,?)",
        (date, content, sort_order),
    )


def delete(item_id: int) -> None:
    db.execute("DELETE FROM timeline WHERE id = ?", (item_id,))


def bulk(ids: list[int], action: str = "delete") -> int:
    ids = [int(i) for i in ids if int(i) > 0]
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    return db.execute(f"DELETE FROM timeline WHERE id IN ({marks})", ids).rowcount


def load_memories() -> list[dict]:
    rows = db.query("SELECT * FROM memories ORDER BY sort_order ASC, id ASC")
    return [dict(r) for r in rows]


def get_memory(item_id: int) -> dict | None:
    return row_to_dict(db.one("SELECT * FROM memories WHERE id = ?", (item_id,)))


def save_memory(form: dict, item_id: int | None = None) -> int:
    title = (form.get("title") or "").strip()
    text = (form.get("text") or "").strip()
    image = (form.get("image") or "").strip()
    date = (form.get("date") or "").strip()
    sort_order = int(form.get("sort_order") or 0)
    if item_id is not None:
        db.execute(
            "UPDATE memories SET title=?, text=?, image=?, date=?, sort_order=? WHERE id=?",
            (title, text, image, date, sort_order, item_id),
        )
        return item_id
    return db.insert(
        "INSERT INTO memories (title, text, image, date, sort_order) VALUES (?,?,?,?,?)",
        (title, text, image, date, sort_order),
    )


def delete_memory(item_id: int) -> None:
    db.execute("DELETE FROM memories WHERE id = ?", (item_id,))
