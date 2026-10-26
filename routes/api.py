"""JSON API。"""

from __future__ import annotations

from flask import jsonify

from services import status


def api_status():
    expiry, services, generated = status.snapshot()
    response = jsonify({"expiry": expiry, "services": services, "generated_at": generated})
    # 前端每 60 秒轮询，20 秒浏览器缓存足够挡掉重复请求
    response.headers["Cache-Control"] = "public, max-age=20"
    return response


def register(app) -> None:
    app.add_url_rule("/api/status", "api_status", api_status, methods=["GET"])
