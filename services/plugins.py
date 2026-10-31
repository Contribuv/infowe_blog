"""内置插件发现、启停与配置。

只加载仓库自带 `plugins/<key>/plugin.json`，不接受后台上传的代码；
插件配置存 `plugins.config`（JSON），升级插件代码不会覆盖配置。
"""

from __future__ import annotations

import importlib
import json
from functools import wraps
from pathlib import Path

from flask import abort

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


def _entry(manifest: dict) -> tuple[str, str] | None:
    entry = str((manifest or {}).get("entry") or "").strip()
    if ":" not in entry:
        return None
    module_name, func_name = entry.split(":", 1)
    module_name, func_name = module_name.strip(), func_name.strip()
    if not module_name or not func_name:
        return None
    return module_name, func_name


def _load_module(manifest: dict):
    parsed = _entry(manifest)
    if parsed is None:
        return None, None
    return importlib.import_module(parsed[0]), parsed[1]


def _guard_endpoints(app, key: str, endpoints: set[str]) -> None:
    """给插件路由包一层启用校验：停用后请求直接 404，无需重启。"""
    for endpoint in endpoints:
        view = app.view_functions.get(endpoint)
        if view is None or getattr(view, "__plugin_guard_key__", None) == key:
            continue

        @wraps(view)
        def guarded(*args, _view=view, _key=key, **kwargs):
            if not enabled(_key):
                abort(404)
            return _view(*args, **kwargs)

        guarded.__plugin_guard_key__ = key
        app.view_functions[endpoint] = guarded


def _register_routes(app, register_func) -> set[str]:
    before = set(app.view_functions)
    register_func(app)
    return set(app.view_functions) - before


# 旧契约插件（没有 on_enable）的路由只能注册一次，避免重复启用时 endpoint 冲突
def _legacy_registered(app) -> set[str]:
    return app.extensions.setdefault("plugin_legacy_registered", set())


def load_all(app) -> None:
    """加载所有已安装插件。

    新契约：插件模块的 ``register(app)`` 只注册路由，``on_enable(app)`` 承担
    建表、启动定时任务、订阅 hooks 等只在启用时需要执行的副作用。

    - ``register`` 始终调用，因此后台启用后无需重启即可访问；
    - 未启用插件的路由由 ``_guard_endpoints`` 拦截为 404；
    - 兼容旧插件：没有 ``on_enable`` 的模块维持原行为（仅启用时完整加载）。
    """
    for item in all_rows():
        if not item["installed"]:
            continue
        key = str(item["key"])
        manifest = item["manifest"]
        try:
            module, func_name = _load_module(manifest)
            if module is None:
                continue
            register_func = getattr(module, func_name)
            on_enable = getattr(module, "on_enable", None)
            if on_enable is None:
                # 旧契约：register 同时负责副作用，只能在启用时整体加载
                legacy = _legacy_registered(app)
                if item["enabled"] and key not in legacy:
                    register_func(app)
                    legacy.add(key)
                continue
            _guard_endpoints(app, key, _register_routes(app, register_func))
            if item["enabled"]:
                on_enable(app)
        except Exception:  # noqa: BLE001
            app.logger.exception("plugin %s failed to load", key)


def load_enabled(app) -> None:
    """向后兼容别名，等同 :func:`load_all`。"""
    load_all(app)


def activate(app, key: str) -> None:
    """运行时启用插件：执行 on_enable，路由已在启动时注册，无需重启。"""
    item = get(key)
    if not item or not item["installed"]:
        return
    module, func_name = _load_module(item["manifest"])
    if module is None:
        return
    on_enable = getattr(module, "on_enable", None)
    if on_enable is not None:
        on_enable(app)
        return
    # 旧插件：没有 on_enable，尝试运行时补注册路由（仅首次）
    legacy = _legacy_registered(app)
    if key in legacy:
        return
    register_func = getattr(module, func_name)
    _guard_endpoints(app, key, _register_routes(app, register_func))
    legacy.add(key)


def deactivate(app, key: str) -> None:
    """运行时停用插件：调用可选的 on_disable，路由守卫会立即拦截请求。"""
    item = get(key)
    if not item:
        return
    try:
        module, _ = _load_module(item["manifest"])
    except Exception:  # noqa: BLE001
        return
    on_disable = getattr(module, "on_disable", None) if module else None
    if on_disable is not None:
        on_disable(app)
