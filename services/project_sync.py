"""项目 GitHub 同步。"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from config import DATA_DIR
from models import Project
from services import github

STATE_FILE = Path(DATA_DIR) / "project_sync.json"
_lock = threading.Lock()
_thread: threading.Thread | None = None


def _read_state() -> dict:
    if STATE_FILE.is_file():
        try:
            value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (ValueError, OSError):
            pass
    return {}


def _write_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def state() -> dict:
    data = _read_state()
    if not data:
        data = {"running": False, "total": 0, "done": 0, "errors": [], "finished_at": 0}
    return data


def sync_one(project: dict) -> dict:
    repo = project.get("github_repo") or github.parse_repo(project.get("url", ""))
    if not repo:
        return {"ok": False, "error": "未配置 GitHub 仓库"}
    payload = github.fetch_and_cache(repo)
    gh = payload.get("gh")
    if not gh:
        return {"ok": False, "error": payload.get("error") or "同步失败"}
    Project.update_github(
        int(project["id"]),
        {
            "stars": gh.get("stars", 0),
            "language": gh.get("language", ""),
            "topics": gh.get("topics", []),
            "languages": gh.get("languages", []),
            "description": gh.get("description", "") if not project.get("description") else project.get("description"),
            "github_repo": repo,
        },
    )
    return {"ok": True, "repo": repo}


def sync_all_background() -> None:
    global _thread
    from flask import current_app

    app = current_app._get_current_object()

    with _lock:
        if _thread and _thread.is_alive():
            return
        state_data = _read_state()
        if state_data.get("running"):
            return
        _thread = threading.Thread(target=_run_all, args=(app,), daemon=True)
        _thread.start()


def sync_one_background(project_id: int) -> bool:
    """单项目同步：在后台线程中带应用上下文执行。"""
    from flask import current_app

    app = current_app._get_current_object()

    def _run() -> None:
        with app.app_context():
            project = Project.get(project_id)
            if project:
                sync_one(project)

    threading.Thread(target=_run, daemon=True).start()
    return True


def _run_all(app) -> None:
    with app.app_context():
        projects = [p for p in Project.load() if p.get("github_repo") or github.parse_repo(p.get("url", ""))]
        errors = []
        done = 0
        started = time.time()
        _write_state(
            {
                "running": True,
                "total": len(projects),
                "done": 0,
                "current": "",
                "errors": [],
                "started_at": started,
                "finished_at": 0,
            }
        )
        try:
            for project in projects:
                _write_state({**_read_state(), "current": project.get("name", "")})
                try:
                    result = sync_one(project)
                except Exception as exc:  # noqa: BLE001
                    result = {"ok": False, "error": str(exc)}
                done += 1
                if not result.get("ok"):
                    errors.append(
                        {"id": project.get("id"), "name": project.get("name"), "error": result.get("error")}
                    )
                _write_state({**_read_state(), "done": done, "errors": errors})
                time.sleep(0.4)
        except Exception as exc:  # noqa: BLE001
            errors.append({"error": str(exc)})
        finally:
            _write_state(
                {
                    "running": False,
                    "total": len(projects),
                    "done": done,
                    "current": "",
                    "errors": errors,
                    "started_at": started,
                    "finished_at": time.time(),
                    "ok": max(0, len(projects) - len([e for e in errors if e.get("id")])),
                    "failed": len([e for e in errors if e.get("id")]),
                    "summary": f"同步完成 {done}/{len(projects)}",
                }
            )


def auto_sync(max_age: int = 86400) -> None:
    """缓存过旧时后台补一次，不阻塞当前请求。"""
    projects = [p for p in Project.load() if p.get("github_repo")]
    if not projects:
        return
    now = time.time()
    stale = False
    for project in projects:
        cached = github.load_cache(project["github_repo"])
        if not cached or now - float(cached.get("ts") or 0) > max_age:
            stale = True
            break
    if stale:
        sync_all_background()
