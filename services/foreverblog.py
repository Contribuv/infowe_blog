"""十年之约「今天读什么」挂件：服务端抓取，用本站样式渲染。"""

from __future__ import annotations

import html
import re
import time

import requests

WIDGET_URL = "https://www.foreverblog.cn/widget/today.html?theme=dark"
WORMHOLE_URL = "https://www.foreverblog.cn/go.html"
ABOUT_URL = "https://www.foreverblog.cn/about.html"
UA = "Mozilla/5.0 (compatible; infowe-blog/1.0)"
TTL = 1800

_cache: dict = {"ts": 0.0, "data": None}

_ARTICLE_RE = re.compile(
    r'<a class="article" href="([^"]+)"[^>]*>(.*?)</a>\s*<small>(.*?)</small>',
    re.S,
)
_WORMHOLE_RE = re.compile(r'<a class="wormhole" href="([^"]+)"', re.S)


def _clean(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


def _fetch() -> dict:
    data = {"articles": [], "wormhole": WORMHOLE_URL, "about": ABOUT_URL}
    try:
        resp = requests.get(WIDGET_URL, timeout=4, headers={"User-Agent": UA})
        if resp.status_code >= 400:
            return data
        raw = resp.text
    except Exception:
        return data

    for url, title, source in _ARTICLE_RE.findall(raw):
        title = _clean(title)
        if not title:
            continue
        url = html.unescape(url)
        if not url.lower().startswith(("http://", "https://")):
            continue
        data["articles"].append(
            {
                "url": url,
                "title": title,
                "source": _clean(source),
            }
        )
        if len(data["articles"]) >= 2:
            break

    match = _WORMHOLE_RE.search(raw)
    if match:
        wormhole = html.unescape(match.group(1))
        if wormhole.lower().startswith(("http://", "https://")):
            data["wormhole"] = wormhole
    return data


def widget() -> dict:
    """缓存 30 分钟，抓取失败时返回上一次结果或空列表。"""
    now = time.time()
    cached = _cache.get("data")
    if cached is not None and now - float(_cache.get("ts") or 0) < TTL:
        return cached
    data = _fetch()
    if data["articles"] or cached is None:
        _cache["data"] = data
        _cache["ts"] = now
    return _cache.get("data") or data
