"""服务探活采样。"""

from __future__ import annotations

import time

import db


def add(service_id: str, ok: bool, latency_ms: int = 0, cert_days: int = -1, detail: str = "") -> None:
    db.execute(
        "INSERT INTO service_checks (service_id, checked_at, ok, latency_ms, cert_days, detail) "
        "VALUES (?,?,?,?,?,?)",
        (service_id, time.time(), 1 if ok else 0, int(latency_ms), int(cert_days), detail),
    )


def history(service_id: str, limit: int = 60) -> list[dict]:
    rows = db.query(
        "SELECT * FROM service_checks WHERE service_id = ? ORDER BY checked_at DESC LIMIT ?",
        (service_id, limit),
    )
    return [dict(r) for r in rows]


def latest(service_id: str) -> dict | None:
    row = db.one(
        "SELECT * FROM service_checks WHERE service_id = ? ORDER BY checked_at DESC LIMIT 1",
        (service_id,),
    )
    return dict(row) if row else None


def uptime(service_id: str, hours: int = 24) -> float:
    since = time.time() - hours * 3600
    total = db.scalar(
        "SELECT COUNT(*) FROM service_checks WHERE service_id=? AND checked_at>=?",
        (service_id, since), 0,
    )
    ok = db.scalar(
        "SELECT COUNT(*) FROM service_checks WHERE service_id=? AND checked_at>=? AND ok=1",
        (service_id, since), 0,
    )
    return round((int(ok) / int(total)) * 100, 1) if total else 0.0


def prune(keep: int = 2000) -> None:
    """与 PHP 版一致：每个服务只保留最新 2000 条采样。"""
    service_ids = [r["service_id"] for r in db.query("SELECT DISTINCT service_id FROM service_checks")]
    for service_id in service_ids:
        db.execute(
            "DELETE FROM service_checks WHERE service_id = ? AND id NOT IN "
            "(SELECT id FROM service_checks WHERE service_id = ? ORDER BY id DESC LIMIT ?)",
            (service_id, service_id, keep),
        )
