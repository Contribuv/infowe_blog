"""内置插件发现、启停与配置。

只加载仓库自带 `plugins/<key>/plugin.json`，不接受后台上传的代码；
插件配置存 `plugins.config`（JSON），升级插件代码不会覆盖配置。
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import db
from config import PLUGINS_DIR


def _root() -> Path:
    return Path(PLUGINS_DIR)


def _read_manifest(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("key"):
        return None
    return data


def discover() -> list[dict]:
    """扫描插件目录，返回 plugin.json 元数据列表。"""
    root = _root()
    if not root.is_dir():
        return []
    result = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        manifest = _read_manifest(child / "plugin.json")
        if not manifest:
            continue
        manifest["_dir"] = str(child)
        result.append(manifest)
    return result


def sync_registry() -> None:
    """把磁盘上的插件同步到数据库；已有记录只更新名称/版本，不动 enabled/config。"""
    for manifest in discover():
        key = str(manifest["key"])
        row = db.one("SELECT key FROM plugins WHERE key = ?", (key,))
        if row is None:
            db.execute(
                "INSERT INTO plugins (key, name, version, enabled, config) VALUES (?,?,?,?,?)",
                (key, str(manifest.get("name") or key), str(manifest.get("version") or ""), 0, "{}"),
            )
        else:
            db.execute(
                "UPDATE plugins SET name=?, version=? WHERE key=?",
                (str(manifest.get("name") or key), str(manifest.get("version") or ""), key),
            )


def all_rows() -> list[dict]:
    rows = db.query("SELECT * FROM plugins ORDER BY key ASC")
    manifests = {m["key"]: m for m in discover()}
    result = []
    for row in rows:
        item = dict(row)
        item["enabled"] = bool(int(item.get("enabled") or 0))
        try:
            item["config"] = json.loads(item.get("config") or "{}")
        except (TypeError, ValueError):
            item["config"] = {}
        item["manifest"] = manifests.get(item["key"], {})
        item["installed"] = item["key"] in manifests
        result.append(item)
    return result


def get(key: str) -> dict | None:
    for item in all_rows():
        if item["key"] == key:
            return item
    return None


def enabled(key: str) -> bool:
    row = db.one("SELECT enabled FROM plugins WHERE key = ?", (key,))
    return bool(row and int(row["enabled"] or 0))


def set_enabled(key: str, value: bool) -> None:
    db.execute(
        "UPDATE plugins SET enabled=?, updated_at=datetime('now','localtime') WHERE key=?",
        (1 if value else 0, key),
    )


def config(key: str) -> dict:
    row = db.one("SELECT config FROM plugins WHERE key = ?", (key,))
    if not row:
        return {}
    try:
        data = json.loads(row["config"] or "{}")
        return data if isinstance(data, dict) else {}
    except (TypeError, ValueError):
        return {}


def save_config(key: str, data: dict) -> None:
    db.execute(
        "UPDATE plugins SET config=?, updated_at=datetime('now','localtime') WHERE key=?",
        (json.dumps(data, ensure_ascii=False), key),
    )


def load_enabled(app) -> None:
    """调用启用插件的 register(app)。插件异常只记录，不影响主站启动。"""
    for item in all_rows():
        if not item["enabled"] or not item["installed"]:
            continue
        manifest = item["manifest"]
        entry = str(manifest.get("entry") or "")
        if ":" not in entry:
            continue
        module_name, func_name = entry.split(":", 1)
        try:
            module = importlib.import_module(module_name)
            getattr(module, func_name)(app)
        except Exception:  # noqa: BLE001
            app.logger.exception("plugin %s failed to load", item["key"])
