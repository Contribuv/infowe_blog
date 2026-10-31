"""静态资源、上传文件、头像与分享图路由。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from flask import abort, redirect, request, send_file, Response

from config import CACHE_DIR, THEMES_DIR
from services import avatar, cachefs, upload


def uploaded_file(filename: str):
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
        sources = [
            f"https://cravatar.cn/avatar/{digest}?s={size}&d=404",
            f"https://weavatar.com/avatar/{digest}?s={size}&d=404",
        ]
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


_README_PLACEHOLDER = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="160" height="48" viewBox="0 0 160 48">'
    b'<rect width="160" height="48" rx="6" fill="#eaeef2"/>'
    b'<text x="80" y="29" font-family="system-ui,sans-serif" font-size="12" fill="#8b949e" '
    b'text-anchor="middle">image unavailable</text></svg>'
)


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

    import hashlib

    key = hashlib.sha1(raw.encode()).hexdigest()
    candidates = list(cache_dir.glob(key + ".*"))
    if not candidates:
        try:
            resp = requests.get(raw, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            final_host = urlparse(resp.url or "").hostname
            if final_host not in _ALLOWED_README_HOSTS:
                # 防止白名单域名 302 到内网/任意地址
                raise requests.RequestException("redirect host not allowed")
            if resp.status_code == 200 and resp.content and len(resp.content) <= 8 * 1024 * 1024:
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
                path.write_bytes(resp.content)
                cachefs.cap(cache_dir, 3000)
                candidates = [path]
        except requests.RequestException:
            candidates = []
    if not candidates:
        return Response(_README_PLACEHOLDER, mimetype="image/svg+xml", status=200)

    path = candidates[0]
    import mimetypes

    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    response = send_file(path, mimetype=mime, max_age=86400, conditional=True)
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
