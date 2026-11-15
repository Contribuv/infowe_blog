"""站点绝对地址。"""

from __future__ import annotations

import os

from flask import has_request_context, request

from services import settings


def base() -> str:
    """返回站点根地址（不带结尾斜杠）。

    优先级：后台「博客设置 → 站点地址」> 环境变量 BLOG_SITE_URL > 当前请求的地址。
    后台线程、定时任务与 CLI 没有请求上下文，此时不能读 request，
    否则会抛 RuntimeError（友链定时审核就卡在这里），直接退回空串由调用方降级处理。
    """
    configured = settings.get_str("site_url", "").strip().rstrip("/")
    if configured:
        return configured
    env = os.environ.get("BLOG_SITE_URL", "").strip().rstrip("/")
    if env:
        return env
    if has_request_context():
        return request.url_root.rstrip("/")
    return ""


def absolute(path: str) -> str:
    if not path:
        return base()
    if path.startswith(("http://", "https://")):
        return path
    return base() + ("" if path.startswith("/") else "/") + path
