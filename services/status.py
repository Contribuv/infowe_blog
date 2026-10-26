"""站点状态探测与云资源到期。"""

from __future__ import annotations

import json
import socket
import ssl
import time
from datetime import date, datetime
from urllib.parse import urlparse

import requests

from models import ServiceCheck
from services import settings


def parse_services() -> list[dict]:
    raw = settings.get_str("monitor_services", "[]")
    try:
        items = json.loads(raw)
    except (ValueError, TypeError):
        return []
    result = []
    for idx, item in enumerate(items if isinstance(items, list) else []):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        name = str(item.get("name") or url)
        # PHP 版历史采样以「服务名称」作为 service_id；新配置可显式带 id
        service_id = str(item.get("id") or name or f"svc{idx + 1}")
        result.append({"id": service_id, "name": name, "url": url})
    return result


def cert_days(hostname: str, port: int = 443, timeout: float = 5) -> int:
    """读对端证书剩余天数。

    优先用 certifi 的根证书建 context：部分服务器（宝塔 / 精简版镜像）
    系统 CA 不全，`ssl.create_default_context()` 会直接报
    `unable to get local issuer certificate`，状态页的 SSL 列就一直是「—」。
    requests 本身就依赖 certifi，所以这里不需要新增依赖。
    """
    if not hostname:
        return -1
    try:
        try:
            import certifi
            context = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            context = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
        expires = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
        return max(0, (expires - datetime.utcnow()).days)
    except Exception:
        return -1


def probe(url: str, timeout: int = 8) -> tuple[bool, int, int, str, float]:
    started = time.time()
    try:
        resp = requests.get(
            url, timeout=timeout, allow_redirects=True,
            headers={"User-Agent": "infowe-status-probe/1.0"},
        )
        elapsed = int((time.time() - started) * 1000)
        ok = resp.status_code < 400
        detail = f"HTTP {resp.status_code}"
        days = -1
        parsed = urlparse(resp.url or url)
        if parsed.scheme == "https" and parsed.hostname:
            days = cert_days(parsed.hostname)
        return ok, elapsed, days, detail, time.time()
    except requests.RequestException as exc:
        elapsed = int((time.time() - started) * 1000)
        return False, elapsed, -1, str(exc)[:200], time.time()


def probe_all(persist: bool = True) -> list[dict]:
    results = []
    for svc in parse_services():
        ok, latency, days, detail, checked_at = probe(svc["url"])
        if persist:
            ServiceCheck.add(svc["id"], ok, latency, days, detail)
        results.append(
            {
                "id": svc["id"],
                "name": svc["name"],
                "url": svc["url"],
                "ok": ok,
                "latency_ms": latency,
                "cert_days": days,
                "detail": detail,
                "checked_at": checked_at,
            }
        )
    if persist:
        ServiceCheck.prune()
    return results


def snapshot() -> tuple[dict, list[dict], float]:
    services = []
    generated = 0.0
    for svc in parse_services():
        latest = ServiceCheck.latest(svc["id"])
        history = ServiceCheck.history(svc["id"], 1)
        if history:
            generated = max(generated, float(history[0]["checked_at"]))
        services.append(
            {
                "id": svc["id"],
                "name": svc["name"],
                "url": svc["url"],
                "ok": None if latest is None else bool(latest["ok"]),
                "latency_ms": None if latest is None else int(latest["latency_ms"] or 0),
                "cert_days": None if latest is None else int(latest["cert_days"] if latest["cert_days"] is not None else -1),
                "detail": "" if latest is None else latest.get("detail", ""),
                "uptime": ServiceCheck.uptime(svc["id"], 24),
                "checked_at": None if latest is None else float(latest["checked_at"]),
            }
        )
    return expiry_info(), services, generated


def parse_date(raw: str) -> date | None:
    raw = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def expiry_info() -> dict:
    today = date.today()
    result: dict[str, dict] = {}
    aliyun_type = settings.get_str("aliyun_server_type", "").strip()
    aliyun_label = f"阿里云 {aliyun_type}" if aliyun_type and not aliyun_type.startswith("阿里云") else (aliyun_type or "阿里云")
    tencent_domain = settings.get_str("tencent_domain", "").strip()
    tencent_label = "腾讯云域名" if tencent_domain else "腾讯云"
    for key, label in (("aliyun", aliyun_label), ("tencent", tencent_label)):
        parsed = parse_date(settings.get_str(f"expiry_{key}", ""))
        if not parsed:
            result[key] = {"label": label, "expiry": "", "status": "none", "days": None}
            continue
        days = (parsed - today).days
        if days < 0:
            status = "expired"
        elif days <= 30:
            status = "warn"
        else:
            status = "ok"
        result[key] = {
            "label": label,
            "expiry": parsed.strftime("%Y-%m-%d"),
            "status": status,
            "days": days,
        }
    return result
