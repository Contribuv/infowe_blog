"""settings 表读写。"""

from __future__ import annotations

import json
from typing import Any

from flask import g

import db

DEFAULTS: dict[str, str] = {
    "blog_name": "infowe",
    "blog_subtitle": "Python · Code · Life",
    "home_title": "",
    "home_quotes": "",
    "home_posts_count": "6",
    "posts_per_page": "20",
    "author": "Linus",
    "author_bio": (
        "Python 全栈开发者，热爱开源，沉迷于代码美学与系统架构。\n"
        "相信每一行代码都有它的灵魂，每一个 Bug 都是成长的阶梯。"
    ),
    "about_intro": "infowe 是一个专注于 Python 生态的独立技术博客，使用 Flask 构建，文章以 Markdown 编写。",
    "avatar": "",
    "skills": json.dumps(
        [
            {"name": "Python", "level": 95},
            {"name": "Flask / Django", "level": 90},
            {"name": "JavaScript", "level": 85},
            {"name": "Docker / K8s", "level": 75},
            {"name": "PostgreSQL", "level": 85},
            {"name": "Redis", "level": 80},
            {"name": "Linux", "level": 88},
        ],
        ensure_ascii=False,
    ),
    "github_username": "",
    "social_github": "",
    "github_token": "",
    "contact_email": "",
    "comments_enabled": "1",
    "comment_notify": "1",
    "comment_image_upload": "1",
    "comments_per_page": "10",
    "admin_comments_per_page": "20",
    "sensitive_filter_enabled": "0",
    "sensitive_words": "",
    "smtp_host": "",
    "smtp_port": "465",
    "smtp_sender_name": "",
    "smtp_user": "",
    "smtp_pass": "",
    "notify_email": "",
    "stats_code": "",
    "nav_posts": "1",
    "nav_tags": "1",
    "nav_projects": "1",
    "nav_links": "1",
    "nav_circle": "1",
    "nav_status": "1",
    "nav_about": "1",
    "icp_beian": "",
    "police_beian": "",
    "footer_copyright_owner": "",
    "footer_copyright_year": "",
    "footer_powered_by": "",
    "site_url": "",
    "force_https": "0",
    "unify_www": "0",
    "active_theme": "tech",
    "admin_path": "admin",
    "upload_max_size": "20",
    "upload_image_ext": "jpg,jpeg,png,gif,webp,ico,avif",
    "upload_media_ext": "mp4,webm,mp3,wav,ogg,m4a,flac",
    "upload_file_ext": "pdf,zip,7z,rar,tar,gz,bz2,txt,md,json,csv,yml,yaml,doc,docx,xls,xlsx,ppt,pptx,py,js,css,sql",
    "watermark_enabled": "1",
    "watermark_text": "",
    "watermark_position": "br",
    "watermark_size": "m",
    "monitor_services": "[]",
    "expiry_aliyun": "",
    "expiry_tencent": "",
    "aliyun_access_key": "",
    "aliyun_access_secret": "",
    "aliyun_region": "cn-hangzhou",
    "aliyun_instance_id": "",
    "aliyun_server_type": "",
    "aliyun_expiry_api": "",
    "tencent_secret_id": "",
    "tencent_secret_key": "",
    "tencent_domain": "",
    "tencent_expiry_api": "",
    "otp_enabled": "0",
    "otp_secret": "",
    "otp_emergency_off": "0",
    "otp_recovery_codes": "[]",
    "smtp_timeout": "10",
    "comment_cooldown": "30",
}

BOOL_KEYS = {
    "comments_enabled", "comment_notify", "comment_image_upload",
    "sensitive_filter_enabled", "nav_posts", "nav_tags", "nav_projects",
    "nav_links", "nav_circle", "nav_status", "nav_about", "force_https", "unify_www",
    "watermark_enabled", "otp_enabled",
}


def _cache() -> dict[str, str]:
    if not hasattr(g, "_settings"):
        g._settings = {r["key"]: r["value"] for r in db.query("SELECT key, value FROM settings")}
    return g._settings


def all() -> dict[str, str]:
    data = dict(DEFAULTS)
    data.update(_cache())
    return data


def get(key: str, default: Any = "") -> Any:
    value = _cache().get(key)
    if value is None:
        return DEFAULTS.get(key, default)
    return value


def get_str(key: str, default: str = "") -> str:
    value = get(key, default)
    return "" if value is None else str(value)


def get_int(key: str, default: int = 0) -> int:
    try:
        return int(str(get(key, default)).strip())
    except (TypeError, ValueError):
        return default


def bool_of(key: str, default: bool = False) -> bool:
    value = str(get(key, "1" if default else "0")).strip().lower()
    return value in {"1", "on", "true", "yes"}


def json_list(key: str, default: list | None = None) -> list:
    raw = get_str(key, "")
    if not raw:
        return list(default or [])
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else list(default or [])
    except (ValueError, TypeError):
        return list(default or [])


def set_value(key: str, value: Any) -> None:
    # INSERT OR REPLACE 兼容 SQLite 3.7+（服务器上的 Python 可能链接旧版 SQLite）
    db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, "" if value is None else str(value)),
    )
    if hasattr(g, "_settings"):
        g._settings[key] = "" if value is None else str(value)


def set_many(values: dict[str, Any]) -> None:
    conn = db.get_db()
    conn.executemany(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        [(k, "" if v is None else str(v)) for k, v in values.items()],
    )
    conn.commit()
    if hasattr(g, "_settings"):
        _cache().update({k: "" if v is None else str(v) for k, v in values.items()})


def ensure_defaults() -> None:
    conn = db.get_db()
    existing = {r["key"] for r in conn.execute("SELECT key FROM settings")}
    missing = [(k, v) for k, v in DEFAULTS.items() if k not in existing]
    if missing:
        conn.executemany("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", missing)
        conn.commit()
