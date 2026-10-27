"""友链模型。"""

from __future__ import annotations

import db
from models.base import row_to_dict

STATUSES = ("approved", "pending", "rejected")


def load(status: str | None = "approved") -> list[dict]:
    if status is None:
        rows = db.query("SELECT * FROM links ORDER BY sort_order ASC, id ASC")
    else:
        rows = db.query(
            "SELECT * FROM links WHERE status = ? ORDER BY sort_order ASC, id ASC", (status,)
        )
    return [dict(r) for r in rows]


def get(link_id: int) -> dict | None:
    return row_to_dict(db.one("SELECT * FROM links WHERE id = ?", (link_id,)))


def save(form: dict, link_id: int | None = None, status: str | None = None) -> int:
    name = (form.get("name") or "").strip()
    url = (form.get("url") or "").strip()
    description = (form.get("description") or "").strip()
    avatar = (form.get("avatar") or "").strip()
    rss = (form.get("rss") or "").strip()
    sort_order = int(form.get("sort_order") or 0)
    if link_id is not None:
        existing = get(link_id)
        # 编辑时未显式传 status 则保留原状态，避免 pending 链接被误通过
        final_status = status or (existing["status"] if existing else "approved")
        if status is None and form.get("status") in STATUSES:
            final_status = str(form["status"])
        db.execute(
            "UPDATE links SET name=?, url=?, description=?, avatar=?, rss=?, sort_order=?, status=? WHERE id=?",
            (name, url, description, avatar, rss, sort_order, final_status, link_id),
        )
        return link_id
    final_status = status or "approved"
    if final_status not in STATUSES:
        final_status = "approved"
    return db.insert(
        "INSERT INTO links (name, url, description, avatar, rss, sort_order, status) VALUES (?,?,?,?,?,?,?)",
        (name, url, description, avatar, rss, sort_order, final_status),
    )


def set_status(link_id: int, status: str) -> None:
    if status in STATUSES:
        db.execute("UPDATE links SET status = ? WHERE id = ?", (status, link_id))


def delete(link_id: int) -> None:
    db.execute("DELETE FROM links WHERE id = ?", (link_id,))


def bulk(ids: list[int], action: str) -> int:
    ids = [int(i) for i in ids if int(i) > 0]
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    if action in {"approve", "approved"}:
        return db.execute(f"UPDATE links SET status='approved' WHERE id IN ({marks})", ids).rowcount
    if action in {"reject", "rejected"}:
        return db.execute(f"UPDATE links SET status='rejected' WHERE id IN ({marks})", ids).rowcount
    if action in {"delete", "remove"}:
        return db.execute(f"DELETE FROM links WHERE id IN ({marks})", ids).rowcount
    return 0


def stats() -> dict:
    return {
        "total": int(db.scalar("SELECT COUNT(*) FROM links", (), 0)),
        "approved": int(db.scalar("SELECT COUNT(*) FROM links WHERE status='approved'", (), 0)),
        "pending": int(db.scalar("SELECT COUNT(*) FROM links WHERE status='pending'", (), 0)),
    }
