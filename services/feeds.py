"""博客圈：抓取友链 RSS、聚合最新文章。"""

from __future__ import annotations

import html
import ipaddress
import json
import re
import socket
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests

import db
from config import CACHE_DIR

UA = "infowe-circle/1.0 (+blogroll reader)"
MAX_BYTES = 2 * 1024 * 1024
TIMEOUT = 8
PER_PAGE = 20
KEEP_PER_SITE = 15
_scheduler_started = False
_lock = threading.Lock()
ATOM = "{http://www.w3.org/2005/Atom}"


def _safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        infos = socket.getaddrinfo(parsed.hostname, None)
        for info in infos:
            addr = ipaddress.ip_address(info[4][0])
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                return False
        return True
    except Exception:
        return False


def _text(node, tag: str) -> str:
    if node is None:
        return ""
    el = node.find(tag)
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _clean(text: str, limit: int = 220) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    # RSS 摘要常以 [...] / […] 标记原文被截断，透传到卡片里很难看；
    # 去掉后由前端 CSS 做两行省略，只保留一套截断
    text = re.sub(r"\[\s*(?:\.\.\.|…)\s*\]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _ts(value: str) -> float:
    value = (value or "").strip()
    if not value:
        return 0.0
    try:
        return parsedate_to_datetime(value).timestamp()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def parse_feed(raw: bytes, base_url: str) -> list[dict]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []

    result: list[dict] = []
    # RSS 2.0 / RDF
    for item in root.iter("item"):
        link = _text(item, "link") or _text(item, "guid")
        title = _text(item, "title")
        if not link or not title:
            continue
        summary = _text(item, "description")
        if not summary:
            summary = _text(item, "{http://purl.org/rss/1.0/modules/content/}encoded")
        published = _ts(_text(item, "pubDate") or _text(item, "date"))
        result.append({
            "title": _clean(title, 160),
            "url": urljoin(base_url, link),
            "summary": _clean(summary),
            "published": published,
        })

    # Atom
    for entry in root.iter(ATOM + "entry"):
        title = _text(entry, ATOM + "title")
        link = ""
        for node in entry.findall(ATOM + "link"):
            if node.get("rel") in (None, "alternate"):
                link = node.get("href") or ""
                if link:
                    break
        if not title or not link:
            continue
        summary = _text(entry, ATOM + "summary") or _text(entry, ATOM + "content")
        published = _ts(_text(entry, ATOM + "published") or _text(entry, ATOM + "updated"))
        result.append({
            "title": _clean(title, 160),
            "url": urljoin(base_url, link),
            "summary": _clean(summary),
            "published": published,
        })

    result.sort(key=lambda x: x["published"], reverse=True)
    return result


def _mark(link_id: int, ok: bool, error: str = "", count: int = 0) -> None:
    db.execute(
        "UPDATE links SET feed_state=?, feed_error=?, feed_checked_at=?, feed_count=? WHERE id=?",
        ("ok" if ok else "error", error[:300], time.time(), int(count), link_id),
    )


def refresh_link(link: dict) -> bool:
    rss = str(link.get("rss") or "").strip()
    link_id = int(link.get("id") or 0)
    if not rss:
        return False
    if not _safe_url(rss):
        _mark(link_id, False, "RSS 地址不是公网 http/https")
        return False
    try:
        resp = requests.get(rss, timeout=TIMEOUT, stream=True, headers={"User-Agent": UA})
        if resp.status_code >= 400:
            _mark(link_id, False, f"HTTP {resp.status_code}")
            return False
        raw = resp.raw.read(MAX_BYTES, decode_content=True) or b""
    except Exception as exc:  # noqa: BLE001
        _mark(link_id, False, f"请求失败：{exc}")
        return False
    if not raw:
        _mark(link_id, False, "响应为空")
        return False
    items = parse_feed(raw, str(link.get("url") or rss))
    if not items:
        _mark(link_id, False, "未解析到文章（可能不是 RSS/Atom）")
        return False

    now = time.time()
    db.execute("DELETE FROM feed_items WHERE link_id=?", (link_id,))
    saved = items[:KEEP_PER_SITE]
    for item in saved:
        db.execute(
            "INSERT OR REPLACE INTO feed_items (link_id, title, url, summary, published, fetched_at) "
            "VALUES (?,?,?,?,?,?)",
            (link_id, item["title"], item["url"], item["summary"],
             item["published"] or now, now),
        )
    _mark(link_id, True, "", len(saved))
    return True


def sources() -> list[dict]:
    rows = db.query(
        "SELECT id, name, url, rss, status, feed_state, feed_error, feed_checked_at, feed_count "
        "FROM links WHERE rss != '' ORDER BY id ASC"
    )
    return [dict(r) for r in rows]


def refresh_source(link_id: int) -> bool:
    row = db.one("SELECT * FROM links WHERE id=?", (int(link_id),))
    return refresh_link(dict(row)) if row else False


def refresh_all() -> int:
    links = db.query("SELECT * FROM links WHERE status='approved' AND rss != '' ORDER BY id ASC LIMIT 80")
    ok = 0
    for row in links:
        if refresh_link(dict(row)):
            ok += 1
    return ok


def rel_time(ts: float) -> str:
    ts = float(ts or 0)
    if not ts:
        return ""
    diff = time.time() - ts
    if diff < 0:
        diff = 0
    if diff < 3600:
        return f"{max(1, int(diff // 60))} 分钟前"
    if diff < 86400:
        return f"{int(diff // 3600)} 小时前"
    if diff < 86400 * 2:
        return "昨天"
    return datetime.fromtimestamp(ts).strftime("%m-%d")


def aggregate(page: int = 1, per_page: int = PER_PAGE) -> tuple[list[dict], int, dict]:
    page = max(1, int(page or 1))
    total = int(db.scalar(
        "SELECT COUNT(*) FROM feed_items f JOIN links l ON l.id=f.link_id "
        "WHERE l.status='approved' AND l.rss != ''",
        (), 0,
    ) or 0)
    rows = db.query(
        "SELECT f.title, f.url, f.summary, f.published, f.fetched_at, "
        "l.name AS site_name, l.url AS site_url, l.avatar AS site_avatar "
        "FROM feed_items f JOIN links l ON l.id=f.link_id "
        "WHERE l.status='approved' AND l.rss != '' "
        "ORDER BY f.published DESC, f.id DESC LIMIT ? OFFSET ?",
        (per_page, (page - 1) * per_page),
    )
    items = []
    for row in rows:
        item = dict(row)
        # 存量数据入库时还没清洗 [...] 标记，渲染前统一再洗一次，
        # 否则老文章卡片上会一直挂着 RSS 的截断占位符
        item["summary"] = _clean(item.get("summary") or "")
        item["time_text"] = rel_time(item.get("published"))
        items.append(item)

    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day).timestamp()
    week_start = today_start - now.weekday() * 86400
    month_start = datetime(now.year, now.month, 1).timestamp()

    def _count(since: float) -> int:
        return int(db.scalar(
            "SELECT COUNT(*) FROM feed_items f JOIN links l ON l.id=f.link_id "
            "WHERE l.status='approved' AND l.rss != '' AND f.published >= ?",
            (since,), 0,
        ) or 0)

    stats = {
        "sites": int(db.scalar(
            "SELECT COUNT(*) FROM links WHERE status='approved' AND rss != ''", (), 0,
        ) or 0),
        "month": _count(month_start),
        "week": _count(week_start),
        "today": _count(today_start),
    }
    return items, total, stats


def _scheduler(app) -> None:
    try:
        import fcntl
    except ImportError:
        return
    time.sleep(20)
    while True:
        try:
            with app.app_context():
                lock_path = Path(CACHE_DIR) / "circle_refresh.lock"
                lock_path.parent.mkdir(parents=True, exist_ok=True)
                with open(lock_path, "w") as fh:
                    try:
                        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except OSError:
                        pass
                    else:
                        refresh_all()
        except Exception:
            app.logger.exception("circle feed refresh failed")
        time.sleep(1800)


def start_scheduler(app) -> None:
    global _scheduler_started
    with _lock:
        if _scheduler_started:
            return
        _scheduler_started = True
    threading.Thread(target=_scheduler, args=(app,), daemon=True, name="circle-feeds").start()
