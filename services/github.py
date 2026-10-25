"""GitHub / Gitee 仓库信息与 README 缓存。"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

from config import DATA_DIR, UPLOADS_DIR
from services import settings
from services.lang import normalize_languages

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
    return normalize_languages([
        {"name": name, "bytes": int(size or 0), "percent": 0}
        for name, size in raw.items()
    ])


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


_README_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".avif"}
_PROXY_IMAGE_HOSTS = {
    "img.shields.io", "shields.io", "badgen.net", "img.badgesize.io",
    "raw.githubusercontent.com", "user-images.githubusercontent.com",
    "camo.githubusercontent.com", "avatars.githubusercontent.com",
}


def _image_ext(url: str) -> str:
    ext = Path(urlparse(url).path).suffix.lower()
    return ext if ext in _README_IMAGE_EXTS else ""


def _download_bytes(url: str, timeout: int = 8) -> bytes | None:
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200 and resp.content and len(resp.content) <= 8 * 1024 * 1024:
            return resp.content
    except requests.RequestException:
        pass
    return None


def _cache_readme_image(url: str, repo: str, ext: str) -> str:
    """与 PHP 版一致：md5(url) 命名，落到 uploads/projects/<slug>/readme/。"""
    name = hashlib.md5(url.encode("utf-8")).hexdigest() + ext
    dest = Path(UPLOADS_DIR) / "projects" / repo / "readme" / name
    if dest.is_file() and dest.stat().st_size > 0:
        return f"/uploads/projects/{repo}/readme/{name}"
    dest.parent.mkdir(parents=True, exist_ok=True)

    site = settings.get_str("site_url", "").strip().rstrip("/")
    candidates = [url]
    if site:
        # 本地网络无法访问 raw.githubusercontent.com 时，从既有 PHP 站回退取图
        candidates.append(f"{site}/uploads/projects/{repo}/readme/{name}")
    for candidate in candidates:
        data = _download_bytes(candidate)
        if data:
            dest.write_bytes(data)
            return f"/uploads/projects/{repo}/readme/{name}"
    return ""


def localize_readme_images(html: str, repo: str, branch: str) -> str:
    """README 图片本地化：
    - GitHub raw / 相对图片 → 下载到 uploads/projects/<repo>/readme（与 PHP 版同路径、同 md5 命名）
    - shields 等徽章 → 站内 /readme-img 代理
    - 其他外链 → 保持原样
    """

    def repl(match: re.Match) -> str:
        attr, src = match.group(1), match.group(2)
        if src.startswith(("data:", "/uploads/", "/readme-img", "#")):
            return match.group(0)
        if src.startswith(("http://", "https://")):
            url = src
        elif src.startswith("//"):
            url = "https:" + src
        elif src.startswith("/"):
            url = f"https://raw.githubusercontent.com/{repo}/{branch}{src}"
        else:
            url = f"https://raw.githubusercontent.com/{repo}/{branch}/{src.lstrip('./')}"

        host = (urlparse(url).hostname or "").lower()
        ext = _image_ext(url)
        is_repo_image = host == "raw.githubusercontent.com" or not src.startswith(("http://", "https://", "//"))
        if is_repo_image and ext:
            local = _cache_readme_image(url, repo, ext)
            if local:
                return f'{attr}="{local}"'
        if host in _PROXY_IMAGE_HOSTS:
            return f'{attr}="/readme-img?url={quote(url, safe="")}"'
        return match.group(0)

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
