"""静态资源、上传文件、头像与分享图路由。"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from flask import abort, redirect, request, send_file, Response

from config import CACHE_DIR, THEMES_DIR
from services import avatar, cachefs, upload


def uploaded_file(filename: str):
    # 评论图片不允许直链：必须走 /comment-img 中转，
    # 未审核 / 已拒绝的图片只返回「审核中」占位图。
    rel = str(filename or "").replace("\\", "/").lstrip("/")
    if rel.lower().startswith("comment/"):
        abort(404)
    path = upload.resolve(filename)
    if path is None or not path.is_file():
        abort(404)
    return send_file(path, conditional=True, max_age=604800)


_THEME_STATIC_EXTS = {
    ".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
    ".json", ".woff", ".woff2", ".ttf", ".otf", ".mp4", ".webm", ".avif",
}


def theme_static(filename: str):
    base = Path(THEMES_DIR).resolve()
    target = (base / filename).resolve()
    try:
        relative = target.relative_to(base)
    except ValueError:
        abort(404)
    # templates/ 是模板源码，绝不通过 /themes/ 公开（Nginx 侧也要同样 deny）
    if "templates" in relative.parts:
        abort(404)
    if target.suffix.lower() not in _THEME_STATIC_EXTS:
        abort(404)
    # 扩展名合法但文件不存在时给 404，而不是让 send_file 抛 500
    if not target.is_file():
        abort(404)
    return send_file(target, conditional=True, max_age=604800)


def share_thumb(filename: str):
    path = upload.share_thumb(filename)
    if path is None:
        abort(404)
    return send_file(path, conditional=True, max_age=86400)


def avatar_proxy(key: str, size: int):
    cache_dir = Path(CACHE_DIR) / "avatars"
    cache_dir.mkdir(parents=True, exist_ok=True)

    if key.startswith("q") and key[1:].isdigit():
        qq = key[1:]
        # 只接受实际用到的三档，避免 /avatar/q1/999999.png 这种无限变体
        if size not in (40, 100, 640):
            abort(404)
        target = size
        sources = [f"https://q{i}.qlogo.cn/g?b=qq&nk={qq}&s={target}" for i in (1, 2, 3, 4)]
    elif key.startswith("e") and len(key) == 33:
        digest = key[1:]
        if not all(c in "0123456789abcdef" for c in digest.lower()):
            abort(404)
        size = max(1, min(size, 640))
        # Gravatar 优先；确认没有时落到 ?qq= 指定的 QQ 头像，最后才是默认图。
        # 这样「自定义 > Gravatar > QQ > 默认」的回退在三端完全一致，
        # 前端不需要再写 onerror 判断。
        path = avatar.gravatar_file(digest, size)
        if path is not None:
            return send_file(path, max_age=604800, mimetype="image/png")
        qq = request.args.get("qq", "").strip()
        if qq.isdigit() and 5 <= len(qq) <= 12:
            return redirect(f"/avatar/q{qq}/{avatar.qq_avatar_size(size)}.png")
        return redirect(avatar.default_url())
    else:
        abort(404)

    cache_file = cache_dir / f"{key}_{size}.png"
    if cache_file.is_file():
        return send_file(cache_file, max_age=604800, mimetype="image/png")

    for url in sources:
        try:
            resp = requests.get(url, timeout=4, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200 and resp.content:
                cache_file.write_bytes(resp.content)
                cachefs.cap(cache_dir, 2000)
                return send_file(cache_file, max_age=604800, mimetype="image/png")
        except requests.RequestException:
            continue
    return redirect(avatar.default_url())


_ALLOWED_README_HOSTS = {
    "raw.githubusercontent.com", "github.com", "user-images.githubusercontent.com",
    "camo.githubusercontent.com", "avatars.githubusercontent.com", "objects.githubusercontent.com",
    "gitee.com", "foruda.gitee.com", "images.gitee.com",
    "img.shields.io", "shields.io", "badgen.net", "img.badgesize.io",
}

# 徽章内容会随上游版本/统计变化，不能像普通图片一样永久缓存。
_BADGE_README_HOSTS = {"img.shields.io", "shields.io", "badgen.net", "img.badgesize.io"}
_BADGE_CACHE_TTL = 300


_README_PLACEHOLDER = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="160" height="48" viewBox="0 0 160 48">'
    b'<rect width="160" height="48" rx="6" fill="#eaeef2"/>'
    b'<text x="80" y="29" font-family="system-ui,sans-serif" font-size="12" fill="#8b949e" '
    b'text-anchor="middle">image unavailable</text></svg>'
)

# 过期图片后台刷新（stale-while-revalidate）：
# 磁盘里已有旧副本时先返回旧图，再起线程回源，访客不再为上游的 3~10 秒买单。
# 同一 key 同时只刷一次，并限制总并发，防止上游抽风时线程暴涨。
_REFRESHING: set[str] = set()
_REFRESH_LOCK = threading.Lock()
_REFRESH_MAX = 8


def _fetch_readme_image(
    raw: str, cache_dir: Path, key: str, suffix: str, timeout: float
) -> Path | None:
    """回源并落盘，返回实际缓存文件；失败返回 None。同步与后台线程共用。"""
    try:
        resp = requests.get(raw, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        final_host = urlparse(resp.url or "").hostname
        if final_host not in _ALLOWED_README_HOSTS:
            # 防止白名单域名 302 到内网/任意地址
            raise requests.RequestException("redirect host not allowed")
        if not (resp.status_code == 200 and resp.content and len(resp.content) <= 8 * 1024 * 1024):
            return None
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if not suffix:
            if "svg" in ctype:
                suffix = ".svg"
            elif "png" in ctype:
                suffix = ".png"
            elif "gif" in ctype:
                suffix = ".gif"
            elif "webp" in ctype:
                suffix = ".webp"
            elif "jpeg" in ctype or "jpg" in ctype:
                suffix = ".jpg"
        path = cache_dir / (key + suffix)
        # 原子替换：后台刷新与 send_file 并发时，绝不能读到写了一半的文件。
        # Windows 下目标被读句柄占用会失败（Linux rename 不受影响），
        # 短暂重试几次；仍失败就保留旧图，等下一轮再刷。
        tmp = path.with_name(path.name + ".tmp")
        try:
            tmp.write_bytes(resp.content)
            for attempt in range(3):
                try:
                    os.replace(tmp, path)
                    break
                except OSError:
                    if attempt == 2:
                        tmp.unlink(missing_ok=True)
                        return None
                    time.sleep(0.2)
        except OSError:
            tmp.unlink(missing_ok=True)
            return None
        # 同一 key 可能留下不同后缀的旧文件（上游 Content-Type 变化），
        # 刷新成功后清掉，避免下次选中陈旧候选
        for stale in cache_dir.glob(key + ".*"):
            if stale != path:
                try:
                    stale.unlink()
                except OSError:
                    continue
        cachefs.cap(cache_dir, 3000)
        return path
    except (requests.RequestException, OSError):
        return None


def _refresh_readme_image_async(
    raw: str, cache_dir: Path, key: str, suffix: str, timeout: float
) -> None:
    with _REFRESH_LOCK:
        if key in _REFRESHING or len(_REFRESHING) >= _REFRESH_MAX:
            return
        _REFRESHING.add(key)

    def run():
        try:
            _fetch_readme_image(raw, cache_dir, key, suffix, timeout)
        finally:
            with _REFRESH_LOCK:
                _REFRESHING.discard(key)

    threading.Thread(target=run, daemon=True, name="readme-image-refresh").start()


def warm_readme_images_from_html(html: str) -> None:
    """页面渲染时顺手预热 README 图片缓存。

    页面 HTML 本身有 10 分钟缓存，但图片是独立子请求。页面刚生成（或刚
    过期）时图片缓存往往也是冷的，这里在后台先抓一遍，等浏览器发出 img
    请求时通常已经落盘，首访不必再为上游的几秒买单。
    """
    if not html or "/readme-img?" not in html:
        return
    import re

    cache_dir = Path(CACHE_DIR) / "readme_images"
    seen: set[str] = set()
    for match in re.finditer(r'/readme-img\?url=([^"\']+)', html):
        raw = unquote(match.group(1))
        if not raw or raw in seen:
            continue
        seen.add(raw)
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in _ALLOWED_README_HOSTS:
            continue
        is_badge = parsed.hostname in _BADGE_README_HOSTS
        ttl = _BADGE_CACHE_TTL if is_badge else 86400
        key = hashlib.sha1(raw.encode()).hexdigest()
        suffix = Path(parsed.path).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".avif"}:
            suffix = ""
        fresh = False
        try:
            mtimes = [p.stat().st_mtime for p in cache_dir.glob(key + ".*")]
            if mtimes:
                fresh = (time.time() - max(mtimes)) < ttl
        except OSError:
            fresh = False
        if fresh:
            continue
        _refresh_readme_image_async(raw, cache_dir, key, suffix, 6 if is_badge else 10)


def readme_image():
    raw = request.args.get("url", "").strip()
    if not raw:
        raw = request.args.get("u", "").strip()
        if raw:
            import base64

            try:
                padded = raw + "=" * (-len(raw) % 4)
                raw = base64.b64decode(padded).decode("utf-8", "replace")
            except Exception:
                abort(404)
    if not raw:
        abort(404)
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in _ALLOWED_README_HOSTS:
        abort(404)

    cache_dir = Path(CACHE_DIR) / "readme_images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(parsed.path).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".avif"}:
        suffix = ""

    key = hashlib.sha1(raw.encode()).hexdigest()
    # glob 顺序不确定；按 mtime 取最新的，避免多后缀残留时选中陈旧文件
    # （.tmp 是原子替换的中间文件，绝不能当成候选）
    candidates = sorted(
        (p for p in cache_dir.glob(key + ".*") if not p.name.endswith(".tmp")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    is_badge = parsed.hostname in _BADGE_README_HOSTS
    ttl = _BADGE_CACHE_TTL if is_badge else 86400
    # 徽标必须快：上游偶尔要 10 秒，超时就当失败，别把访客挂住
    timeout = 6 if is_badge else 10
    fresh = False
    if candidates:
        try:
            fresh = (time.time() - candidates[0].stat().st_mtime) < ttl
        except OSError:
            fresh = False
    if not fresh:
        if candidates:
            # 有旧图就先给旧图，后台再刷新：访客不再等上游
            _refresh_readme_image_async(raw, cache_dir, key, suffix, timeout)
        else:
            # 完全没缓存（首次访问）只能同步回源；失败则给占位图
            stored = _fetch_readme_image(raw, cache_dir, key, suffix, timeout)
            if stored is not None:
                candidates = [stored]
    if not candidates:
        return Response(_README_PLACEHOLDER, mimetype="image/svg+xml", status=200)

    path = candidates[0]
    import mimetypes

    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    response = send_file(
        path,
        mimetype=mime,
        max_age=_BADGE_CACHE_TTL if is_badge else 86400,
        conditional=True,
    )
    if mime == "image/svg+xml":
        # SVG 作为独立文档时禁止脚本，仅允许内联样式（徽章）
        response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    return response



def plugin_asset(plugin_key: str, filename: str):
    """插件静态资源：/plugin-assets/<key>/<path>。"""
    from config import PLUGINS_DIR
    from services import plugins as plugins_service

    if not plugins_service.enabled(plugin_key):
        abort(404)
    base = (Path(PLUGINS_DIR) / plugin_key / "static").resolve()
    target = (base / filename).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        abort(404)
    if not target.is_file():
        abort(404)
    return send_file(target, conditional=True, max_age=60)


def register(app) -> None:
    app.add_url_rule("/uploads/<path:filename>", "uploaded_file", uploaded_file)
    app.add_url_rule("/themes/<path:filename>", "theme_static", theme_static)
    app.add_url_rule("/share-thumb/<path:filename>", "share_thumb", share_thumb)
    app.add_url_rule("/avatar/<key>/<int:size>.png", "avatar_proxy", avatar_proxy)
    app.add_url_rule("/readme-img", "readme_img", readme_image)
    app.add_url_rule("/plugin-assets/<plugin_key>/<path:filename>", "plugin_asset", plugin_asset)
