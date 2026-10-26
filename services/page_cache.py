"""匿名访客页面缓存。

只缓存匿名 GET 的 HTML 页面；管理员和提交过评论的访客绕过缓存，
避免把「待审核评论」「后台状态」等个性化内容缓存给其他人。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse

from flask import g, make_response, request, session

from config import CACHE_DIR

PAGE_ROOT = Path(CACHE_DIR) / "pages"

# 不缓存的路径前缀
EXCLUDED_PREFIXES = (
    "/admin", "/api", "/search", "/comment", "/uploads", "/static",
    "/themes", "/share-thumb", "/avatar", "/readme-img", "/favicon.ico",
)


def _url() -> str:
    return request.full_path if request.query_string else request.path


def _ttl(path: str) -> int:
    if path == "/":
        return 300
    if path.startswith("/post/"):
        return 1800
    if path.startswith("/archive/"):
        return 1800
    if path.startswith("/about"):
        return 1800
    if path.startswith("/tag/"):
        return 600
    if path.startswith("/projects"):
        return 600
    if path.startswith("/links"):
        return 600
    if path.startswith("/feed.xml"):
        return 600
    if path.startswith("/status"):
        return 60
    return 300


def _cacheable() -> bool:
    if request.method != "GET":
        return False
    if getattr(g, "_page_cache_skip", False):
        return False
    if session.get("admin_id"):
        return False
    # 评论者需要看到自己的待审核评论，不能读公共缓存
    if request.cookies.get("blog_commenter"):
        return False
    # 有 flash 的页面不缓存，避免把一次性提示存给所有访客
    if session.get("_flashes"):
        g._page_cache_skip = True
        return False
    if request.args.get("preview"):
        return False
    path = request.path
    for prefix in EXCLUDED_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return False
    return True


def _paths(url: str) -> tuple[Path, Path]:
    path = urlparse(url).path or "/"
    segment = path.strip("/").split("/")[0] or "home"
    segment = re.sub(r"[^A-Za-z0-9_-]", "_", segment)[:40] or "home"
    # host 参与 key，避免 www / 裸域互相污染绝对链接
    digest = hashlib.sha1(f"{request.host}|{url}".encode("utf-8")).hexdigest()
    folder = PAGE_ROOT / segment
    return folder / f"{digest}.html", folder / f"{digest}.json"


def load():
    """命中则返回 Flask Response，否则 None。"""
    if not _cacheable():
        return None
    html_path, meta_path = _paths(_url())
    if not html_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        age = time.time() - float(meta.get("created") or 0)
        if age > float(meta.get("ttl") or 600):
            html_path.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
            return None
        html = html_path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None

    response = make_response(html)
    response.headers["Content-Type"] = meta.get("content_type") or "text/html; charset=utf-8"
    response.headers["X-Cache"] = "HIT"
    # 命中页缓存时给浏览器一小段缓存：回访/连点页面直接吃本地副本，
    # 过期后仍允许先展示旧页、后台再校验（stale-while-revalidate）
    response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=120"
    g._page_cache_hit = True
    return response


def store(response) -> None:
    """把匿名 GET 的 200 HTML 写入缓存。"""
    if not _cacheable():
        return
    if getattr(g, "_page_cache_hit", False):
        return
    if response.status_code != 200:
        return
    if response.mimetype not in {"text/html", "application/rss+xml"}:
        return
    if response.headers.get("Set-Cookie"):
        return
    body = response.get_data(as_text=True)
    if not body:
        return

    url = _url()
    html_path, meta_path = _paths(url)
    try:
        html_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = html_path.with_name(html_path.name + ".tmp")
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, html_path)
        meta_path.write_text(
            json.dumps({
                "url": url,
                "created": time.time(),
                "ttl": _ttl(request.path),
                "content_type": response.headers.get("Content-Type") or "text/html; charset=utf-8",
            }),
            encoding="utf-8",
        )
        response.headers["X-Cache"] = "MISS"
    except OSError:
        return


def clear_all() -> None:
    if not PAGE_ROOT.exists():
        return
    for child in PAGE_ROOT.iterdir():
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        except OSError:
            continue


def invalidate_path(path: str) -> None:
    targets = {path, path.rstrip("/"), path + "/"}
    # 同一路径可能带查询串派生多个缓存键（如评论分页 ?cpage=2），按 meta 里的 url 一并清理
    folder = _paths(path)[0].parent
    if folder.is_dir():
        for meta_file in folder.glob("*.json"):
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if urlparse(str(meta.get("url") or "")).path in targets:
                meta_file.unlink(missing_ok=True)
                meta_file.with_suffix(".html").unlink(missing_ok=True)
    for candidate in targets:
        html_path, meta_path = _paths(candidate)
        try:
            html_path.unlink(missing_ok=True)
            meta_path.unlink(missing_ok=True)
        except OSError:
            continue


def stats() -> dict:
    files = list(PAGE_ROOT.rglob("*.html")) if PAGE_ROOT.exists() else []
    size = sum(f.stat().st_size for f in files if f.is_file())
    return {"files": len(files), "size": size}
