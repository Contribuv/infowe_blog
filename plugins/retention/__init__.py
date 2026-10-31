"""留存记录插件入口：后台操作审计 + AI 审计 + 评论留存的聚合查看与导出。"""

from __future__ import annotations

from pathlib import Path


def _ensure_schema() -> None:
    from db import get_db

    sql = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    conn = get_db()
    conn.executescript(sql)
    # 旧库兼容：插件表不走主 schema 的自动补列，这里手动补 user_agent
    columns = {row[1] for row in conn.execute("PRAGMA table_info(op_logs)")}
    if "user_agent" not in columns:
        conn.execute("ALTER TABLE op_logs ADD COLUMN user_agent TEXT DEFAULT ''")
    conn.commit()


def register(app) -> None:
    """只注册路由，启动时对所有已安装插件调用，启用后无需重启。"""
    from . import routes

    routes.register(app)


def on_enable(app) -> None:
    """启用时执行：建表、启动清理任务、订阅后台操作审计事件。"""
    _ensure_schema()
    from services import hooks

    from . import jobs

    jobs.start_scheduler(app)
    # 订阅后台关键操作审计事件（admin.py/_audit 与 auth.py 登录流程发出）
    hooks.on("admin.action", jobs.on_admin_action)
