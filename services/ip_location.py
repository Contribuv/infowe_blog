"""IP 归属地：内网识别 + 可选 ip2region xdb。"""

from __future__ import annotations

import ipaddress
import threading
from pathlib import Path

from config import DATA_DIR

try:  # 可选依赖：安装后支持离线 xdb 查询
    import ip2region.util as _ip2region_util  # type: ignore
except Exception:  # pragma: no cover
    _ip2region_util = None

_lock = threading.Lock()
_searchers: dict[str, object] = {}


def _searcher(version: str):
    if _ip2region_util is None:
        return None
    path = Path(DATA_DIR) / f"ip2region_v{version}.xdb"
    if not path.is_file():
        return None
    with _lock:
        if version not in _searchers:
            try:
                _searchers[version] = _ip2region_util.new_with_file_only("ipv4" if version == "4" else "ipv6", str(path))
            except Exception:
                _searchers[version] = None
    return _searchers[version]


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
        return ""
    try:
        result = searcher.search(ip)  # type: ignore[attr-defined]
        if not result:
            return ""
        text = result if isinstance(result, str) else getattr(result, "region", "")
        parts = [p for p in str(text).split("|") if p and p != "0"]
        return " ".join(parts)
    except Exception:
        return ""
