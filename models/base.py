"""模型基类与通用工具。"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]


def json_list(raw: Any) -> list:
    if isinstance(raw, list):
        return raw
    if not raw:
        return []
    try:
        value = json.loads(str(raw))
        return value if isinstance(value, list) else []
    except (ValueError, TypeError):
        return []


def json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def slugify(text: str, fallback: str = "untitled") -> str:
    slug = re.sub(r"[^a-zA-Z0-9\-]", "-", (text or "").lower())
    slug = re.sub(r"-+", "-", slug).strip("-")[:60].strip("-")
    return slug or fallback


def strip_markdown(text: str) -> str:
    # 文章/项目嵌入语法是块级指令，不该出现在摘要与字数统计里
    plain = re.sub(r"\[\[(?:post|projects?):\s*\d+[^\]]*\]\]", "", text or "", flags=re.I)
    plain = re.sub(r"<[^>]+>", "", plain)
    plain = re.sub(r"[#*`\[\]()!>|~\-]", "", plain)
    plain = re.sub(r"\s+", " ", plain)
    return plain.strip()


def word_count(text: str) -> int:
    return len(re.findall(r"[\w\u4e00-\u9fff]", text or ""))
