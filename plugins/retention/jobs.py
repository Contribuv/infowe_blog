"""留存记录插件：审计事件落库 + 定时清理过期记录。"""

from __future__ import annotations

import threading
import time

import db

KEY = "retention"

# 操作审计默认保留天数（176 号令要求网络日志留存 6 个月以上，取 180 天）
KEEP_DAYS = 180

_lock = threading.Lock()
_thread_started = False


def _enabled() -> bool:
    from services import plugins

    return plugins.enabled(KEY)


def on_admin_action(payload) -> None:
    """订阅 hooks 的 admin.action 事件：把后台关键操作写入 op_logs。

    在请求上下文中执行，直接取当前登录管理员与请求 IP；
    单条 INSERT 很快，同步 emit 不影响操作体验。
    """
    if not isinstance(payload, dict):
        return
    from flask import has_request_context, request

    # 先判上下文再查库：hooks 也可能在无请求上下文的地方 emit
    if not has_request_context():
        return
    if not _enabled():
        return
    from services import auth
    from services.comments import request_ip

    user = auth.current_user()
    operator = str(user["username"]) if user else ""
    db.execute(
        "INSERT INTO op_logs (action, target, detail, operator, ip, user_agent) VALUES (?,?,?,?,?,?)",
        (
            str(payload.get("action") or "")[:64],
            str(payload.get("target") or "")[:200],
            str(payload.get("detail") or "")[:500],
            operator[:64],
            request_ip()[:64],
            str(request.headers.get("User-Agent", ""))[:400],
        ),
    )
    db.get_db().commit()


def cleanup(days: int = KEEP_DAYS) -> int:
    """删除超过保留期的操作审计，返回删除条数。"""
    cur = db.execute(
        "DELETE FROM op_logs WHERE created_at < datetime('now','localtime','-%d days')" % int(days)
    )
    db.get_db().commit()
    return int(cur.rowcount or 0)


def start_scheduler(app) -> None:
    """后台线程：启动 60 秒后清理一次，之后每 24 小时一次。

    不依赖 fcntl 文件锁（Windows 跑不了），单进程博客直接清理即可。
    """
    global _thread_started
    with _lock:
        if _thread_started:
            return
        _thread_started = True

    def loop() -> None:
        time.sleep(60)
        while True:
            try:
                if _enabled():
                    with app.app_context():
                        cleanup()
            except Exception:
                app.logger.exception("retention cleanup failed")
            time.sleep(86400)

    threading.Thread(target=loop, daemon=True, name="retention-cleanup").start()
