"""IP 归属地：内网识别 + 可选 ip2region xdb + 在线兜底。

服务器上没装 ip2region / 没有 xdb 时，退回 pconline 的公开查询接口，
按 IP 做进程内缓存，避免每条评论都发一次请求。
"""

from __future__ import annotations

import ipaddress
import json
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
        parts = [str(data.get("pro") or "").strip(), str(data.get("city") or "").strip()]
        location = " ".join(_dedupe(p for p in parts if p and p not in {"0", "中国"}))
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
        return " ".join(_dedupe(parts)) or _online(ip)
    except Exception:
        return _online(ip)


def normalize_display(location: str | None) -> str:
    """用于模板/后台直接展示库中存储的 ip_location 时做兜底去重"""
    if not location:
        return ""
    text = str(location)
    parts = [p.strip() for p in text.replace("\t", " ").split() if p.strip()]
    parts = _dedupe(parts)
    if len(parts) == 2 and parts[0] == parts[1]:
        parts = [parts[0]]
    if len(parts) >= 2 and parts[0] == parts[1] and (parts[0] in {"北京", "上海", "天津", "重庆", "香港", "澳门"} or parts[0].endswith("市")):
        parts = parts[1:]
    return " ".join(parts)
