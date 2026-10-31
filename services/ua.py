"""User-Agent 轻量解析：仅用于评论/后台展示，不追求完备。

输出尽量短，例如 ``Chrome · Windows``；完整 UA 交给模板 title 展示。
"""

from __future__ import annotations

# 先匹配特殊客户端（它们的 UA 里通常也带 Chrome/Safari，必须排在前面）
_CLIENTS = (
    ("MicroMessenger", "微信"),
    ("QQBrowser", "QQ 浏览器"),
    ("QQ/", "QQ"),
    ("DingTalk", "钉钉"),
    ("AlipayClient", "支付宝"),
    ("Weibo", "微博"),
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("Firefox/", "Firefox"),
    ("CriOS", "Chrome"),
    ("FxiOS", "Firefox"),
    ("Chrome/", "Chrome"),
    ("Safari/", "Safari"),
    ("curl/", "curl"),
    ("python-requests", "requests"),
    ("bot", "Bot"),
    ("spider", "Spider"),
)

_SYSTEMS = (
    ("Windows NT 10", "Windows"),
    ("Windows NT 6.3", "Windows 8.1"),
    ("Windows NT 6.2", "Windows 8"),
    ("Windows NT 6.1", "Windows 7"),
    ("Windows Phone", "Windows Phone"),
    ("Windows", "Windows"),
    ("iPhone", "iOS"),
    ("iPad", "iPadOS"),
    ("Android", "Android"),
    ("Mac OS X", "macOS"),
    ("CrOS", "ChromeOS"),
    ("Linux", "Linux"),
)


def describe(user_agent: str) -> str:
    """把 UA 解析成 ``浏览器 · 系统``；无法识别时返回空串。"""
    ua = str(user_agent or "").strip()
    if not ua:
        return ""
    lowered = ua.lower()
    client = ""
    for needle, label in _CLIENTS:
        if needle.lower() in lowered:
            client = label
            break
    system = ""
    for needle, label in _SYSTEMS:
        if needle.lower() in lowered:
            system = label
            break
    if client and system:
        return f"{client} · {system}"
    return client or system
