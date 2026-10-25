"""头像地址与缓存辅助。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from config import BASE_DIR, UPLOADS_DIR
from services import settings


def default_url() -> str:
    return "/static/images/default-avatar.svg"


def email_hash(email: str | None) -> str:
    email = (email or "").strip().lower()
    return hashlib.md5(email.encode("utf-8")).hexdigest() if email else ""


def qq_from_email(email: str | None) -> str:
    import re

    email = (email or "").strip().lower()
    match = re.fullmatch(r"(\d{5,12})@qq\.com", email)
    return match.group(1) if match else ""


def qq_avatar_size(size: int) -> int:
    if size <= 40:
        return 40
    if size <= 100:
        return 100
    return 640


def urls(email_hash_value: str | None, qq: str = "", size: int = 80) -> tuple[str, str]:
    email_hash_value = email_hash_value or ""
    qq = qq or ""
    if not email_hash_value and not qq:
        return "", ""
    if qq:
        return f"/avatar/q{qq}/{qq_avatar_size(size)}.png", ""
    return f"/avatar/e{email_hash_value}/{max(1, size)}.png", ""


def configured_avatar_exists() -> bool:
    cfg = settings.get_str("avatar", "").strip()
    if not cfg:
        return False
    rel = cfg.lstrip("/")
    return (Path(BASE_DIR) / rel).is_file()


def admin_url(size: int = 40) -> str:
    cfg = settings.get_str("avatar", "").strip()
    if cfg and configured_avatar_exists():
        return cfg
    contact = settings.get_str("contact_email", "").strip().lower()
    if not contact:
        return ""
    return urls(email_hash(contact), qq_from_email(contact), size)[0]
