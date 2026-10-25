"""静态资源、上传文件、头像与分享图路由。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from flask import abort, redirect, request, send_file

from config import CACHE_DIR, THEMES_DIR
from services import avatar, upload


def uploaded_file(filename: str):
    path = upload.resolve(filename)
    if path is None or not path.is_file():
        abort(404)
    return send_file(path, conditional=True, max_age=604800)


def theme_static(filename: str):
    base = Path(THEMES_DIR).resolve()
    target = (base / filename).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        abort(404)
    if not target.is_file():
        abort(404)
    return send_file(target, conditional=True, max_age=604800)


def share_thumb(filename: str):
    path = upload.share_thumb(filename)
    if path is None:
        abort(404)
    return send_file(path, conditional=True, max_age=86400, mimetype="image/jpeg")


def avatar_proxy(key: str, size: int):
    cache_dir = Path(CACHE_DIR) / "avatars"
    cache_dir.mkdir(parents=True, exist_ok=True)

    if key.startswith("q") and key[1:].isdigit():
        qq = key[1:]
        target = avatar.qq_avatar_size(size)
        sources = [f"https://q{i}.qlogo.cn/g?b=qq&nk={qq}&s={target}" for i in (1, 2, 3, 4)]
    elif key.startswith("e") and len(key) == 33:
        digest = key[1:]
        if not all(c in "0123456789abcdef" for c in digest.lower()):
            abort(404)
        s = max(1, min(size, 640))
        sources = [
            f"https://cravatar.cn/avatar/{digest}?s={s}&d=404",
            f"https://weavatar.com/avatar/{digest}?s={s}&d=404",
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

    # 徽章/矢量图直接 302 到源站：避免同源 SVG 脚本风险，也省去转换成本
    if parsed.hostname.endswith("shields.io") or parsed.path.lower().endswith(".svg"):
        return redirect(raw, code=302)

    cache_dir = Path(CACHE_DIR) / "readme_images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(parsed.path).suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".avif"}:
        suffix = ""
    path = cache_dir / (hashlib.sha1(raw.encode()).hexdigest() + suffix)
    if not path.is_file():
        try:
            resp = requests.get(raw, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200 or not resp.content:
                return redirect(raw, code=302)
            path.write_bytes(resp.content)
        except requests.RequestException:
            return redirect(raw, code=302)
    return send_file(path, max_age=86400, conditional=True)


def register(app) -> None:
    app.add_url_rule("/uploads/<path:filename>", "uploaded_file", uploaded_file)
    app.add_url_rule("/themes/<path:filename>", "theme_static", theme_static)
    app.add_url_rule("/share-thumb/<path:filename>", "share_thumb", share_thumb)
    app.add_url_rule("/avatar/<key>/<int:size>.png", "avatar_proxy", avatar_proxy)
    app.add_url_rule("/readme-img", "readme_img", readme_image)
