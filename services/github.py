"""GitHub / Gitee 仓库信息与 README 缓存。"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

from config import DATA_DIR
from services import settings

CACHE_DIR = Path(DATA_DIR) / "project_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def parse_repo(url: str) -> str | None:
    """从仓库地址解析 owner/repo。"""
    if not url:
        return None
    match = re.search(r"(?:github\.com|gitee\.com)[/:]([^/\s]+)/([^/\s?#]+)", url)
    if not match:
        return None
    owner, repo = match.group(1), match.group(2)
    repo = re.sub(r"\.git$", "", repo)
    return f"{owner}/{repo}"


def _headers() -> dict:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "python-blog"}
    token = settings.get_str("github_token", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_repo(repo: str, timeout: int = 10) -> dict | None:
    """抓取仓库元信息；GitHub 失败时尝试 Gitee。"""
    owner, _, name = repo.partition("/")
    if not owner or not name:
        return None

    try:
        resp = requests.get(
            f"https://api.github.com/repos/{owner}/{name}",
            headers=_headers(), timeout=timeout,
        )
        if resp.status_code == 200:
            data = resp.json()
            languages = {}
            try:
                lresp = requests.get(
                    f"https://api.github.com/repos/{owner}/{name}/languages",
                    headers=_headers(), timeout=timeout,
                )
                if lresp.status_code == 200:
                    languages = lresp.json()
            except requests.RequestException:
                pass
            return {
                "provider": "github",
                "github_repo": f"{owner}/{name}",
                "name": data.get("name") or name,
                "description": data.get("description") or "",
                "url": data.get("html_url") or f"https://github.com/{owner}/{name}",
                "stars": int(data.get("stargazers_count") or 0),
                "language": data.get("language") or "",
                "topics": data.get("topics") or [],
                "languages": _lang_list(languages),
            }
    except requests.RequestException:
        pass

    try:
        resp = requests.get(
            f"https://gitee.com/api/v5/repos/{owner}/{name}", timeout=timeout,
            headers={"User-Agent": "python-blog"},
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                "provider": "gitee",
                "github_repo": f"{owner}/{name}",
                "name": data.get("name") or name,
                "description": data.get("description") or "",
                "url": data.get("html_url") or f"https://gitee.com/{owner}/{name}",
                "stars": int(data.get("stargazers_count") or 0),
                "language": data.get("language") or "",
                "topics": data.get("topics") or [],
                "languages": [],
            }
    except requests.RequestException:
        pass
    return None


def _lang_list(raw: dict) -> list[dict]:
    total = sum(int(v or 0) for v in raw.values())
    if not total:
        return []
    return [
        {"name": name, "bytes": int(size), "percent": round(int(size) / total * 100, 1)}
        for name, size in sorted(raw.items(), key=lambda kv: -int(kv[1] or 0))
    ]


def fetch_readme(repo: str, timeout: int = 10) -> tuple[str, str]:
    """返回 (markdown 文本, 分支)。"""
    owner, _, name = repo.partition("/")
    headers = _headers()
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{owner}/{name}/readme",
            headers={**headers, "Accept": "application/vnd.github.raw"},
            timeout=timeout,
        )
        if resp.status_code == 200 and resp.text.strip():
            branch = "main"
            try:
                meta = requests.get(
                    f"https://api.github.com/repos/{owner}/{name}",
                    headers=headers, timeout=timeout,
                ).json()
                branch = meta.get("default_branch") or "main"
            except Exception:
                pass
            return resp.text, branch
    except requests.RequestException:
        pass

    try:
        resp = requests.get(
            f"https://gitee.com/api/v5/repos/{owner}/{name}/readme",
            timeout=timeout, headers={"User-Agent": "python-blog"},
        )
        if resp.status_code == 200:
            data = resp.json()
            import base64

            content = base64.b64decode(data.get("content") or "").decode("utf-8", "replace")
            return content, data.get("branch") or "master"
    except (requests.RequestException, ValueError):
        pass
    return "", "main"


def cache_path(repo: str) -> Path:
    return CACHE_DIR / (repo.replace("/", "__") + ".json")


def load_cache(repo: str) -> dict | None:
    path = cache_path(repo)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def save_cache(repo: str, payload: dict) -> None:
    cache_path(repo).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def localize_readme_images(html: str, repo: str, branch: str) -> str:
    """把 README 中的相对图片地址改写成 /readme-img 代理地址。"""
    from urllib.parse import quote

    def repl(match: re.Match) -> str:
        src = match.group(2)
        # 外部绝对地址保持原样（徽章/图床由浏览器直连），只本地化仓库内的相对图片
        if src.startswith(("http://", "https://", "data:", "//")):
            return match.group(0)
        if src.startswith("/"):
            target = f"https://raw.githubusercontent.com/{repo}/{branch}{src}"
        else:
            target = f"https://raw.githubusercontent.com/{repo}/{branch}/{src.lstrip('./')}"
        return f'{match.group(1)}="/readme-img?url={quote(target, safe="")}"'

    return re.sub(r'(<img[^>]*?\bsrc)="([^"]+)"', repl, html, flags=re.I)


def snapshot(repo: str) -> dict | None:
    data = load_cache(repo)
    if not data:
        return None
    return {
        "gh": data.get("gh"),
        "readme": data.get("readme") or "",
        "branch": data.get("branch") or "",
        "ts": float(data.get("ts") or 0),
        "error": data.get("error") or "",
    }


def fetch_and_cache(repo: str) -> dict:
    """抓取并落盘；失败时保留旧缓存。"""
    now = time.time()
    try:
        gh = fetch_repo(repo)
        if not gh:
            raise RuntimeError("仓库信息获取失败")
        markdown_text, branch = fetch_readme(repo)
        from services import markdown

        html = markdown.render_readme(markdown_text, repo, branch) if markdown_text else ""
        html = localize_readme_images(html, repo, branch)
        payload = {"gh": gh, "branch": branch, "ts": now, "readme": html, "error": ""}
        save_cache(repo, payload)
        return payload
    except Exception as exc:  # noqa: BLE001
        old = load_cache(repo) or {}
        old.update({"error": str(exc), "ts": old.get("ts") or now})
        save_cache(repo, old)
        return old
