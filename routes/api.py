"""JSON API。"""

from __future__ import annotations

from flask import jsonify

from services import status


def api_status():
    expiry, services, generated = status.snapshot()
    return jsonify({"expiry": expiry, "services": services, "generated_at": generated})


def register(app) -> None:
    app.add_url_rule("/api/status", "api_status", api_status, methods=["GET"])
