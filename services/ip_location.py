"""IP 归属地：内网识别 + 可选 ip2region xdb + 在线兜底。

服务器上没装 ip2region / 没有 xdb 时，退回 pconline 的公开查询接口，
按 IP 做进程内缓存，避免每条评论都发一次请求。
"""

from __future__ import annotations

import ipaddress
import json
import re
import threading
from pathlib import Path

import requests

from config import DATA_DIR

try:  # 内置 xdb 解析（services/_ip2region），不依赖 pip 包
    from services._ip2region import util as _ip2region_util  # type: ignore
    from services._ip2region.searcher import new_with_file_only  # type: ignore
except Exception:  # pragma: no cover
    _ip2region_util = None
    new_with_file_only = None

_lock = threading.Lock()
_searchers: dict[str, object] = {}
_online_cache: dict[str, str] = {}


def _dedupe(parts) -> list[str]:
    """相邻去重：直辖市在 ip2region/pconline 里省市同名（重庆市|重庆市），
    不处理会显示成「重庆市 重庆市」；只去相邻重复，不误伤正常省+市组合。"""
    out: list[str] = []
    for p in parts:
        if not out or out[-1] != p:
            out.append(p)
    return out


# 展示时丢掉的部分：国家、ISO 代码、运营商、占位值
_IGNORED = {"中国", "cn", "0", "未知", "其他"}
_ISPS = {
    "移动", "联通", "电信", "铁通", "广电", "广电网", "教育网", "长城宽带",
    "鹏博士", "阿里云", "腾讯云", "华为云", "亚马逊", "微软", "cloudflare", "google",
}


def short_location(value: str | None) -> str:
    """把归属地压成「城市」这一级：中国 江西省 九江市 移动 CN -> 九江市。

    库里历史数据有「省 市」和「国家 省 市 运营商 代码」两种写法，统一取最后
    一个有效地名；本地/内网原样保留。
    """
    text = str(value or "").strip()
    if not text:
        return ""
    if text in {"本地", "内网"}:
        return text
    parts = [p for p in re.split(r"[\s|]+", text) if p]
    kept = [
        p for p in parts
        if p.lower() not in _IGNORED and p not in _ISPS
    ]
    return kept[-1] if kept else ""


def migrate_comments(conn) -> int:
    """启动时把历史评论的 ip_location 压成城市级（幂等）。"""
    try:
        rows = conn.execute(
            "SELECT DISTINCT ip_location FROM comments "
            "WHERE ip_location IS NOT NULL AND ip_location != ''"
        ).fetchall()
    except Exception:
        return 0
    changed = 0
    for row in rows:
        old = str(row[0] or "")
        new = short_location(old)
        if new and new != old:
            conn.execute("UPDATE comments SET ip_location = ? WHERE ip_location = ?", (new, old))
            changed += 1
    if changed:
        conn.commit()
        print(f"[数据修复] IP 归属地统一为城市级：{changed} 种写法")
    return changed


def _searcher(version: str):
    if _ip2region_util is None or new_with_file_only is None:
        return None
    path = Path(DATA_DIR) / f"ip2region_v{version}.xdb"
    if not path.is_file() or path.stat().st_size < 1024:
        return None
    with _lock:
        if version not in _searchers:
            try:
                ver = _ip2region_util.IPv4 if version == "4" else _ip2region_util.IPv6
                _searchers[version] = new_with_file_only(ver, str(path))
            except Exception:
                _searchers[version] = None
    return _searchers[version]


def _online(ip: str) -> str:
    cached = _online_cache.get(ip)
    if cached is not None:
        return cached
    location = ""
    try:
        resp = requests.get(
            "https://whois.pconline.com.cn/ipJson.jsp",
            params={"ip": ip, "json": "true"},
            timeout=2.5,
        )
        text = resp.content.decode("gbk", "ignore").strip()
        data = json.loads(text)
        city = str(data.get("city") or "").strip()
        province = str(data.get("pro") or "").strip()
        location = city if city and city not in {"0", "中国"} else (
            province if province and province not in {"0", "中国"} else ""
        )
    except Exception:
        location = ""
    if location:
        _online_cache[ip] = location
    return location


def of(ip: str | None) -> str:
    ip = (ip or "").strip()
    if not ip:
        return ""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ""
    if addr.is_loopback:
        return "本地"
    if addr.is_private:
        return "内网"
    version = "4" if addr.version == 4 else "6"
    searcher = _searcher(version)
    if searcher is None:
        return _online(ip)
    try:
        result = searcher.search(ip)  # type: ignore[attr-defined]
        if not result:
            return _online(ip)
        text = result if isinstance(result, str) else getattr(result, "region", "")
        parts = [p for p in str(text).split("|") if p and p != "0"]
        return short_location(" ".join(_dedupe(parts))) or _online(ip)
    except Exception:
        return _online(ip)


def normalize_display(location: str | None) -> str:
    """展示兜底：历史数据里的「中国 江西省 九江市 移动 CN」压成「九江市」。"""
    return short_location(location)

