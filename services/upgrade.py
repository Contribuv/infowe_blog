"""版本检查与基于 Git 的后台升级。"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

import config

STATE_FILE = Path(config.DATA_DIR) / "upgrade_state.json"
CACHE_FILE = Path(config.DATA_DIR) / "upgrade_check.json"
CACHE_TTL = 600

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_thread: threading.Thread | None = None

GITHUB_REPO = "Contribuv/infowe_blog"
GITEE_REPO = "infowe/infowe_blog"

# 升级源 → 本地 git 远程名。origin 由 clone 时决定（一般指向 GitHub）；
# gitee 远程不存在时由 _ensure_remote 自动补上
SOURCES = {
    "github": {"remote": "origin", "label": "GitHub"},
    "gitee": {"remote": "gitee", "label": "Gitee"},
}
DEFAULT_SOURCE = "github"


def _version_key(value: str) -> tuple[int, ...]:
    parts = [int(x) for x in re.findall(r"\d+", value or "")[:3]]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _clean_version(value: str) -> str:
    return (value or "").strip().lstrip("vV")


def _fetch_github() -> dict | None:
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={"User-Agent": "python-blog-upgrade"},
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return {
            "source": "github",
            "label": "GitHub",
            "tag": _clean_version(data.get("tag_name", "")),
            "url": data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases",
            "notes": (data.get("body") or "")[:4000],
            "published_at": data.get("published_at") or "",
        }
    except (requests.RequestException, ValueError):
        return None


def _fetch_gitee() -> dict | None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://gitee.com/{GITEE_REPO}/releases",
    }
    errors: list[str] = []

    # Gitee 的匿名 API 有时会限流或拦截云服务器 IP。
    # 先试 latest，再试列表接口，最后退到 raw config.py 读取 VERSION。
    endpoints = (
        f"https://gitee.com/api/v5/repos/{GITEE_REPO}/releases/latest",
        f"https://gitee.com/api/v5/repos/{GITEE_REPO}/releases?per_page=1",
    )
    for endpoint in endpoints:
        try:
            resp = requests.get(endpoint, headers=headers, timeout=10)
        except requests.RequestException as exc:
            errors.append(f"{endpoint}: {exc}")
            continue
        if resp.status_code != 200:
            errors.append(f"{endpoint}: HTTP {resp.status_code}")
            continue
        try:
            data = resp.json()
        except ValueError:
            errors.append(f"{endpoint}: invalid JSON")
            continue
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict) or not data.get("tag_name"):
            errors.append(f"{endpoint}: empty release")
            continue
        tag = _clean_version(data.get("tag_name", ""))
        return {
            "source": "gitee",
            "label": "Gitee",
            "tag": tag,
            "url": f"https://gitee.com/{GITEE_REPO}/releases/tag/v{tag}",
            "notes": (data.get("body") or "")[:4000],
            "published_at": data.get("created_at") or "",
        }

    for branch in ("main", "master"):
        try:
            resp = requests.get(
                f"https://gitee.com/{GITEE_REPO}/raw/{branch}/config.py",
                headers=headers,
                timeout=10,
            )
        except requests.RequestException as exc:
            errors.append(f"raw/{branch}: {exc}")
            continue
        if resp.status_code != 200:
            errors.append(f"raw/{branch}: HTTP {resp.status_code}")
            continue
        match = re.search(r'(?m)^\s*VERSION\s*=\s*["\']([^"\']+)', resp.text)
        if not match:
            errors.append(f"raw/{branch}: VERSION not found")
            continue
        tag = _clean_version(match.group(1))
        return {
            "source": "gitee",
            "label": "Gitee",
            "tag": tag,
            "url": f"https://gitee.com/{GITEE_REPO}/releases/tag/v{tag}",
            "notes": "",
            "published_at": "",
        }
    if errors:
        logger.warning("Gitee check failed: %s", " | ".join(errors[-4:]))
    return None


def check(force: bool = False) -> dict:
    """同时查询 GitHub / Gitee 最新 Release，返回模板需要的字段。"""
    now = time.time()
    current = config.VERSION
    if not force and CACHE_FILE.is_file():
        try:
            cached = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            data = cached.get("data") or {}
            fresh = now - float(cached.get("ts") or 0) < CACHE_TTL
            # 旧版本缓存可能没有 upgradable 字段，直接失效重新获取
            complete = isinstance(data, dict) and {
                "ok", "current_version", "latest_version", "upgradable", "sources"
            } <= set(data)
            if fresh and complete and cached.get("version") == current:
                return data
        except (ValueError, OSError, KeyError, TypeError):
            pass

    results = []
    sources = []
    for fetcher in (_fetch_github, _fetch_gitee):
        item = fetcher()
        label = "GitHub" if fetcher is _fetch_github else "Gitee"
        sources.append({"label": label, "ok": bool(item), "checked": now})
        if item:
            results.append(item)

    if not results:
        data = {
            "ok": False,
            "current_version": current,
            "latest_version": "",
            "available": False,
            "source": "",
            "release_url": f"https://github.com/{GITHUB_REPO}/releases",
            "notes": "",
            "message": "GitHub 与 Gitee 均无法获取版本信息（网络受限或 API 限流）",
            "sources": sources,
            "checked": now,
        }
    else:
        latest = max(results, key=lambda r: _version_key(r["tag"]))
        available = _version_key(latest["tag"]) > _version_key(current)
        data = {
            "ok": bool(latest["tag"]),
            "current_version": current,
            "latest_version": latest["tag"],
            "available": available,
            # 模板实际使用的字段名
            "upgradable": available,
            "source": latest["source"],
            "release_url": latest["url"],
            "notes": latest["notes"],
            "body": latest["notes"],
            "published_at": latest.get("published_at", ""),
            "sources": sources,
            "checked": now,
        }

    try:
        CACHE_FILE.write_text(
            json.dumps({"ts": now, "version": current, "data": data}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass
    return data


def _read_state() -> dict:
    if STATE_FILE.is_file():
        try:
            value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return value
        except (ValueError, OSError):
            pass
    return {"state": "idle", "percent": 0, "label": ""}


def _write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def status() -> dict:
    state = {"state": "idle", "percent": 0, "label": "", "summary": "", "cancel_requested": False}
    state.update(_read_state())
    if state.get("state") == "running" and time.time() - float(state.get("started") or 0) > 900:
        state["stale"] = True
    return state


def _normalize_source(source) -> dict:
    """把请求里的源标识收敛到 SOURCES 白名单，非法/缺省回落到默认源。"""
    if isinstance(source, str):
        for key, meta in SOURCES.items():
            if source.strip().lower() == key:
                return {"key": key, **meta}
    return {"key": DEFAULT_SOURCE, **SOURCES[DEFAULT_SOURCE]}


def _ensure_remote(base: Path, name: str) -> subprocess.CompletedProcess | None:
    """gitee 远程名不存在时自动补上（从 GitHub clone 的部署默认没有它）。"""
    probe = subprocess.run(
        ["git", "remote", "get-url", name],
        cwd=str(base), capture_output=True, text=True, timeout=30,
    )
    if probe.returncode == 0:
        return None
    url = f"https://gitee.com/{GITEE_REPO}.git" if name == "gitee" else f"https://github.com/{GITHUB_REPO}.git"
    return subprocess.run(
        ["git", "remote", "add", name, url],
        cwd=str(base), capture_output=True, text=True, timeout=30,
    )


def start(source=None) -> tuple[bool, str]:
    global _thread
    meta = _normalize_source(source)
    with _lock:
        if _read_state().get("state") == "running":
            return False, "已有升级任务正在执行"
        if not (Path(config.BASE_DIR) / ".git").exists():
            return False, "当前目录不是 Git 仓库，无法在线升级；请手动拉取/上传新版本，并保留 data、uploads、backups"
        # 先在锁内写入 running，避免并发请求同时启动两个升级线程
        _write_state({
            "state": "running", "percent": 1, "label": "准备升级",
            "started": time.time(), "source": meta["key"], "source_label": meta["label"],
        })
        _thread = threading.Thread(target=_run, args=(meta,), daemon=True)
        _thread.start()
    return True, "升级任务已启动"


def _run(meta: dict) -> None:
    base = Path(config.BASE_DIR)
    remote = meta["remote"]
    _write_state({
        "state": "running", "percent": 5,
        "label": f"拉取最新代码（{meta['label']}）", "started": time.time(),
        "source": meta["key"], "source_label": meta["label"],
    })
    try:
        ensure = _ensure_remote(base, remote)
        if ensure is not None and ensure.returncode != 0:
            _write_state({
                "state": "failed", "percent": 100, "label": f"配置 {meta['label']} 远程失败",
                "summary": (ensure.stderr or ensure.stdout or "").strip()[:500],
                "finished": time.time(),
            })
            return
        proc = subprocess.run(
            ["git", "pull", "--ff-only", remote],
            cwd=str(base), capture_output=True, text=True, timeout=180,
        )
        if proc.returncode != 0:
            _write_state({
                "state": "failed", "percent": 100, "label": "git pull 失败",
                "summary": (proc.stderr or proc.stdout or "").strip()[:500],
                "finished": time.time(),
            })
            return
        _write_state({"state": "running", "percent": 55, "label": "安装依赖", "started": time.time()})
        venv_pip = base / ".venv" / "bin" / "pip"
        if venv_pip.is_file():
            pip_cmd = [str(venv_pip), "install", "-r", "requirements.txt"]
        else:
            pip_cmd = [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
        proc = subprocess.run(
            pip_cmd,
            cwd=str(base), capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[-1500:]
            _write_state({
                "state": "failed",
                "percent": 100,
                "label": "依赖安装失败（代码已更新）",
                "summary": (
                    "代码已通过 git pull 更新，但依赖安装失败，通常是运行用户无权限写入 Python 环境，或网络无法访问 PyPI。\n\n"
                    f"错误输出：\n{detail}\n\n"
                    "请用 root 手动执行：\n"
                    f"cd {base} && {' '.join(pip_cmd)}"
                ),
                "finished": time.time(),
            })
            return
        _write_state({
            "state": "done", "percent": 100,
            "label": "升级完成，请重启服务",
            "summary": "代码与依赖已更新；请重启 gunicorn/uWSGI 后访问新版本",
            "finished": time.time(),
        })
    except Exception as exc:  # noqa: BLE001
        _write_state({
            "state": "failed", "percent": 100, "label": "升级失败",
            "summary": str(exc)[:500], "finished": time.time(),
        })


def cancel() -> dict:
    state = _read_state()
    state["cancel_requested"] = True
    _write_state(state)
    return {"ok": True}


def reset() -> dict:
    _write_state({"state": "idle", "percent": 0, "label": ""})
    return {"ok": True}
