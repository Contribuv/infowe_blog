"""留存记录插件入口：后台操作审计 + AI 审计 + 评论留存的聚合查看与导出。"""

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
    # 订阅后台关键操作审计事件（admin.py/_audit 与 auth.py 登录流程发出）
    hooks.on("admin.action", jobs.on_admin_action)
