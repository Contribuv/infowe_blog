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
    # /uploads/xxx 实际落在 var/uploads/xxx（UPLOADS_DIR），
    # 旧实现拼的是 BASE_DIR/uploads/xxx，永远不存在，
    # 结果就是后台上传成功、预览和前台关于页都不显示头像。
    rel = cfg.split("/uploads/", 1)[1] if "/uploads/" in cfg else cfg.lstrip("/")
    rel = rel.split("?", 1)[0]
    parts = rel.split("/")
    if not rel or ".." in parts or rel.startswith("/"):
        return False
    return (Path(UPLOADS_DIR) / rel).is_file()


def admin_url(size: int = 40) -> str:
    cfg = settings.get_str("avatar", "").strip()
    if cfg and configured_avatar_exists():
        return cfg
    contact = settings.get_str("contact_email", "").strip().lower()
    if not contact:
        return ""
    return urls(email_hash(contact), qq_from_email(contact), size)[0]
