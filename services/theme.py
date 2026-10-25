"""主题发现与静态资源版本。"""

from __future__ import annotations

import json
import os
from pathlib import Path

from config import THEMES_DIR, THEME_TEMPLATE_DIR, STATIC_DIR, VERSION


def active_key() -> str:
    from services import settings

    try:
        key = settings.get_str("active_theme", "tech").strip() or "tech"
    except RuntimeError:
        # 应用上下文尚未建立（create_app 早期）时用默认主题
        key = "tech"
    if not (THEME_TEMPLATE_DIR / key).is_dir():
        return "tech"
    return key


def active_template_dir() -> Path:
    return THEME_TEMPLATE_DIR / active_key()


def list_themes() -> list[dict]:
    result: list[dict] = []
    if not THEMES_DIR.is_dir():
        return result
    for path in sorted(THEMES_DIR.iterdir(), key=lambda p: p.name):
        if not path.is_dir() or path.name.startswith("."):
            continue
        if not (THEME_TEMPLATE_DIR / path.name).is_dir():
            continue
        meta: dict = {}
        info = path / "info.json"
        if info.is_file():
            try:
                meta = json.loads(info.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                meta = {}
        result.append(
            {
                "key": path.name,
                "name": meta.get("name", path.name),
                "author": meta.get("author", ""),
                "description": meta.get("description", ""),
                "version": meta.get("version", VERSION),
                "has_preview": (path / "preview.png").is_file(),
            }
        )
    return result


def asset_version() -> int:
    version = 0
    base = THEMES_DIR / active_key()
    for name in ("theme.css", "theme.min.css", "theme.js"):
        path = base / name
        if path.is_file():
            version = max(version, int(path.stat().st_mtime))
    return version


def css_name(key: str | None = None) -> str:
    """优先使用自动压缩的 theme.min.css；源文件更新后自动重建。

    构建失败、目录不可写或缺少 csscompressor 时回退到 theme.css，
    不影响主题正常使用。
    """
    base = THEMES_DIR / (key or active_key())
    src = base / "theme.css"
    dst = base / "theme.min.css"
    if not src.is_file():
        return "theme.css"
    try:
        if not dst.is_file() or src.stat().st_mtime > dst.stat().st_mtime:
            import csscompressor

            text = csscompressor.compress(
                src.read_text(encoding="utf-8"),
                preserve_exclamation_comments=False,
            )
            tmp = dst.with_name(f"{dst.name}.{os.getpid()}.tmp")
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(dst)
    except Exception:
        return "theme.css"
    return "theme.min.css" if dst.is_file() else "theme.css"


def admin_asset_version() -> int:
    version = 0
    for name in ("css/admin.css", "js/admin.js"):
        path = STATIC_DIR / name
        if path.is_file():
            version = max(version, int(path.stat().st_mtime))
    return version


def has_css(key: str | None = None) -> bool:
    return (THEMES_DIR / (key or active_key()) / "theme.css").is_file()
