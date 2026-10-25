"""站点绝对地址。"""

from __future__ import annotations

from flask import request

from services import settings


def base() -> str:
    configured = settings.get_str("site_url", "").strip().rstrip("/")
    if configured:
        return configured
    return request.url_root.rstrip("/")


def absolute(path: str) -> str:
    if not path:
        return base()
    if path.startswith(("http://", "https://")):
        return path
    return base() + ("" if path.startswith("/") else "/") + path
