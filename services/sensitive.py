"""评论敏感词过滤。"""

from __future__ import annotations

import json
import re

from services import settings


def words() -> list[str]:
    raw = settings.get_str("sensitive_words", "")
    seen: list[str] = []
    for line in re.split(r"\r\n|\n|\r", raw):
        word = line.strip()
        if not word or word.startswith("#"):
            continue
        if word not in seen:
            seen.append(word)
    return seen


def enabled() -> bool:
    return settings.bool_of("sensitive_filter_enabled", False) and bool(words())


def filter_text(text: str) -> str:
    if not text or not enabled():
        return text
    items = sorted(words(), key=len, reverse=True)
    if not items:
        return text
    pattern = "(" + "|".join(re.escape(w) for w in items) + ")"
    try:
        return re.sub(pattern, lambda m: "*" * len(m.group(0)), text, flags=re.I)
    except re.error:
        return text


def has(text: str) -> bool:
    if not text or not enabled():
        return False
    return any(w in text for w in words())


def as_json() -> str:
    if not enabled():
        return ""
    return json.dumps(words(), ensure_ascii=False)
