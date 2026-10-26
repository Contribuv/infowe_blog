"""主题发现、静态资源版本与旧布局迁移。

主题目录约定（v3.2.16 起）：

    themes/<key>/
    ├── info.json
    ├── preview.png
    ├── templates/        # 前台模板（base.html、index.html ...）
    └── static/           # theme.css / theme.min.css / theme.js 及主题自己的图片字体

旧布局（templates/theme/<key> + themes/<key>/*.css）仍可运行，启动时会自动合并。
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from config import THEMES_DIR, THEME_TEMPLATE_DIR, STATIC_DIR, VERSION

STATIC_NAMES = ("theme.css", "theme.min.css", "theme.js")


def theme_dir(key: str) -> Path:
    return THEMES_DIR / key


def static_dir(key: str) -> Path:
    """新布局 themes/<key>/static；未迁移的旧主题回退到主题根。"""
    new = theme_dir(key) / "static"
    return new if new.is_dir() else theme_dir(key)


def templates_dir(key: str) -> Path:
    """新布局 themes/<key>/templates；未迁移的旧主题回退 templates/theme/<key>。"""
    new = theme_dir(key) / "templates"
    return new if new.is_dir() else THEME_TEMPLATE_DIR / key


def active_key() -> str:
    from services import settings

    try:
        key = settings.get_str("active_theme", "tech").strip() or "tech"
    except RuntimeError:
        # 应用上下文尚未建立（create_app 早期）时用默认主题
        key = "tech"
    if not templates_dir(key).is_dir():
        return "tech"
    return key


def active_template_dir() -> Path:
    return templates_dir(active_key())


def list_themes() -> list[dict]:
    result: list[dict] = []
    if not THEMES_DIR.is_dir():
        return result
    for path in sorted(THEMES_DIR.iterdir(), key=lambda p: p.name):
        if not path.is_dir() or path.name.startswith("."):
            continue
        if not templates_dir(path.name).is_dir():
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
    base = static_dir(active_key())
    for name in STATIC_NAMES:
        path = base / name
        if path.is_file():
            version = max(version, int(path.stat().st_mtime))
    return version


def css_name(key: str | None = None) -> str:
    """优先使用自动压缩的 theme.min.css；源文件更新后自动重建。

    构建失败、目录不可写或缺少 csscompressor 时回退到 theme.css，
    不影响主题正常使用。
    """
    base = static_dir(key or active_key())
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


def has_css(key: str | None = None) -> bool:
    return (static_dir(key or active_key()) / "theme.css").is_file()


def admin_asset_version() -> int:
    version = 0
    for name in ("css/admin.css", "js/admin.js"):
        path = STATIC_DIR / name
        if path.is_file():
            version = max(version, int(path.stat().st_mtime))
    return version


# ── 旧布局迁移 ──────────────────────────────────────────
def _merge_dir(src: Path, dest: Path) -> int:
    """把 src 里的文件并入 dest（不覆盖同名文件），返回移动数量。"""
    moved = 0
    for item in list(src.iterdir()):
        target = dest / item.name
        if not target.exists():
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item), str(target))
            moved += 1
        elif item.is_dir() and target.is_dir():
            moved += _merge_dir(item, target)
    try:
        src.rmdir()
    except OSError:
        pass
    return moved


def migrate_legacy_layout() -> list[str]:
    """把旧的两处主题结构合并到 themes/<key>/{templates,static}。

    - templates/theme/<key>/*  →  themes/<key>/templates/
    - themes/<key>/*.css|js    →  themes/<key>/static/
    幂等、不覆盖已有文件；失败只告警，不影响启动。
    """
    moved: list[str] = []
    try:
        if THEME_TEMPLATE_DIR.is_dir():
            for legacy in sorted(THEME_TEMPLATE_DIR.iterdir()):
                if not legacy.is_dir():
                    continue
                dest = THEMES_DIR / legacy.name / "templates"
                if dest.exists():
                    count = _merge_dir(legacy, dest)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(legacy), str(dest))
                    count = 1
                if count:
                    moved.append(f"{legacy.name}/templates")

        if THEMES_DIR.is_dir():
            for base in sorted(THEMES_DIR.iterdir()):
                if not base.is_dir():
                    continue
                static = base / "static"
                for name in STATIC_NAMES:
                    src = base / name
                    if not src.is_file():
                        continue
                    static.mkdir(exist_ok=True)
                    target = static / name
                    if target.exists():
                        src.unlink()
                    else:
                        shutil.move(str(src), str(target))
                    moved.append(f"{base.name}/static/{name}")

        try:
            THEME_TEMPLATE_DIR.rmdir()
        except OSError:
            pass
    except Exception as exc:  # noqa: BLE001
        print(f"[主题目录] 迁移未完成：{exc}")
    return moved
