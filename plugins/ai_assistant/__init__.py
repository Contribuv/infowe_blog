"""AI 助手插件入口。"""

from __future__ import annotations

from pathlib import Path


def _ensure_schema() -> None:
    from db import get_db

    sql = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    conn = get_db()
    conn.executescript(sql)
    conn.commit()


def register(app) -> None:
    _ensure_schema()
    from services import hooks

    from . import jobs, routes

    routes.register(app)
    jobs.start_scheduler(app)
    hooks.on("comment.created", jobs.on_comment)
    hooks.on("link.applied", jobs.on_link)
