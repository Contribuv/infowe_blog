"""首页一言解析。"""

from __future__ import annotations


def parse(text: str, limit: int = 100) -> list[dict]:
    """一行一条；文本|出处，出处可省略。空行和 # 注释忽略。"""
    items: list[dict] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            quote_text, source = line.split("|", 1)
        else:
            quote_text, source = line, ""
        quote_text = quote_text.strip()[:300]
        if not quote_text:
            continue
        items.append({"text": quote_text, "src": source.strip()[:80]})
        if len(items) >= limit:
            break
    return items
