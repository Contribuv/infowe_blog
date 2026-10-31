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
    """只注册路由。

    启动时对所有已安装插件调用，因此后台启用后无需重启即可访问；
    未启用时由 services.plugins 的路由守卫统一返回 404。
    """
    from . import routes

    routes.register(app)


def on_enable(app) -> None:
    """启用时执行：建表、同步身份、启动定时任务、订阅 hooks。"""
    _ensure_schema()
    from services import hooks

    from . import jobs

    try:
        # 兜底把历史 AI 评论的昵称/头像对齐当前配置（幂等，不一致才写库）
        jobs.sync_ai_identity()
    except Exception:
        app.logger.exception("ai identity sync failed")

    jobs.start_scheduler(app)
    hooks.on("comment.created", jobs.on_comment)
    hooks.on("link.applied", jobs.on_link)
