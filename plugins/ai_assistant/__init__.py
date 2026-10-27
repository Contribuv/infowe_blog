"""AI 助手插件入口。"""

from __future__ import annotations

from pathlib import Path


def _ensure_schema() -> None:
    from db import get_db

    sql = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    conn = get_db()
    conn.executescript(sql)
    conn.commit()


def _backfill_ai_avatars() -> None:
    """给历史 AI 评论补头像（旧版本没写 ai_meta.avatar）。"""
    import json

    from db import execute, query

    from . import config

    avatar = config.provider_avatar(config.active_profile())
    rows = query(
        "SELECT id FROM comments WHERE is_ai=1 AND (ai_meta IS NULL OR ai_meta NOT LIKE '%avatar%')"
    )
    for row in rows:
        execute(
            "UPDATE comments SET ai_meta=? WHERE id=?",
            (json.dumps({"avatar": avatar}, ensure_ascii=False), row["id"]),
        )


def register(app) -> None:
    _ensure_schema()
    try:
        _backfill_ai_avatars()
    except Exception:
        app.logger.exception('ai avatar backfill failed')
    from services import hooks

    from . import jobs, routes

    routes.register(app)
    jobs.start_scheduler(app)
    hooks.on("comment.created", jobs.on_comment)
    hooks.on("link.applied", jobs.on_link)
