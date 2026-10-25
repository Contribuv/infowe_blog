"""Python 博客入口：应用工厂、全局上下文、错误页与 CLI。"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, g, redirect, render_template, request, url_for
from jinja2 import ChoiceLoader, FileSystemLoader
from werkzeug.middleware.proxy_fix import ProxyFix

import config
from db import init_app as init_db_app, init_db
from services import settings as settings_service
from services import theme as theme_service
from services.settings import get_str


def _ensure_dirs() -> None:
    for path in (
        config.INSTANCE_DIR, config.UPLOADS_DIR, config.BACKUPS_DIR,
        config.STORAGE_DIR, config.CACHE_DIR, config.DATA_DIR,
        config.THEMES_DIR, config.STATIC_DIR,
    ):
        Path(path).mkdir(parents=True, exist_ok=True)


def _secret_key() -> str:
    _ensure_dirs()
    env_key = os.environ.get("BLOG_SECRET_KEY", "").strip()
    if env_key:
        return env_key
    file = Path(config.SECRET_KEY_FILE)
    if file.is_file():
        value = file.read_text(encoding="utf-8").strip()
        if value:
            return value
    value = secrets.token_hex(32)
    file.write_text(value, encoding="utf-8")
    return value


def create_app(test_config: dict | None = None) -> Flask:
    _ensure_dirs()
    app = Flask(__name__, static_folder=str(config.STATIC_DIR), static_url_path="/static")
    app.config.update(
        SECRET_KEY=_secret_key(),
        DATABASE=str(config.DATABASE),
        MAX_CONTENT_LENGTH=config.MAX_CONTENT_LENGTH,
        SEND_FILE_MAX_AGE_DEFAULT=604800,
        SESSION_COOKIE_NAME=config.SESSION_COOKIE_NAME,
        SESSION_COOKIE_HTTPONLY=config.SESSION_COOKIE_HTTPONLY,
        SESSION_COOKIE_SAMESITE=config.SESSION_COOKIE_SAMESITE,
        PERMANENT_SESSION_LIFETIME=config.PERMANENT_SESSION_LIFETIME,
        JSON_AS_ASCII=False,
    )
    if test_config:
        app.config.update(test_config)

    # 位于 Nginx / 宝塔反向代理之后：信任一层代理的 Host / Proto / IP 头，
    # 否则开启 HTTPS 强制跳转时会因 request.scheme=http 产生循环。
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    # ── 模板加载顺序：当前主题 → 共享片段 → templates 根（含 admin/） ──
    theme_loader = FileSystemLoader(str(theme_service.active_template_dir()))
    app.jinja_loader = ChoiceLoader(
        [
            theme_loader,
            FileSystemLoader(str(config.SHARED_TEMPLATE_DIR)),
            FileSystemLoader(str(config.TEMPLATE_DIR)),
        ]
    )
    app.extensions["theme_loader"] = theme_loader

    init_db_app(app)
    init_db(app)

    # 后台入口前缀（可在后台设置；修改后需重启服务）
    with app.app_context():
        from services.install import seed_initial_data

        seed_initial_data()
        admin_path = str(settings_service.get_str("admin_path", "admin") or "admin").strip().strip("/")
    if (
        not __import__("re").fullmatch(r"[A-Za-z0-9_-]{2,32}", admin_path)
        or (admin_path.lower() in config.ADMIN_PATH_RESERVED and admin_path.lower() != "admin")
    ):
        admin_path = "admin"
    app.config["ADMIN_PREFIX"] = "/" + admin_path

    from routes import admin as admin_routes
    from routes import api as api_routes
    from routes import assets as assets_routes
    from routes import auth as auth_routes
    from routes import front as front_routes

    assets_routes.register(app)
    front_routes.register(app)
    auth_routes.register(app)
    admin_routes.register(app)
    api_routes.register(app)

    _register_hooks(app)
    _register_cli(app)
    return app


def _register_hooks(app: Flask) -> None:
    @app.before_request
    def _before() -> None:
        # 主题可能在后台被切换，每个请求同步模板搜索路径
        loader = app.extensions.get("theme_loader")
        if loader is not None:
            loader.searchpath = [str(theme_service.active_template_dir())]

        # 同源校验：POST/PUT/DELETE 必须来自本站（无 Origin/Referer 的脚本请求放行）
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("Origin", "")
            referer = request.headers.get("Referer", "")
            source = origin or referer
            if source:
                parsed = urlparse(source)
                host_name = request.host.split(":")[0].lower()
                if parsed.hostname and parsed.hostname.lower() != host_name:
                    return ("跨站请求被拒绝", 403)

        # 强制 HTTPS / www 归一（仅 GET，后台与本地豁免）
        if request.method == "GET" and not request.path.startswith("/admin"):
            target = _canonical_redirect()
            if target:
                return redirect(target, code=301)

    @app.context_processor
    def _inject_globals() -> dict:
        from models import Link, Post

        nav_on: dict[str, bool] = {}
        nav_pages: list[dict] = []
        nav_all: list[dict] = []
        for key, label, href in config.NAV_PAGES:
            enabled = settings_service.bool_of(f"nav_{key}", True)
            nav_on[key] = enabled
            nav_all.append({"key": key, "label": label, "enabled": enabled})
            if enabled:
                nav_pages.append({"key": key, "label": label, "href": href})

        conf = settings_service.all()
        active = theme_service.active_key()
        return {
            "blog_name": conf.get("blog_name", "infowe"),
            "blog_subtitle": conf.get("blog_subtitle", ""),
            "home_title": conf.get("home_title", ""),
            "home_posts_count": conf.get("home_posts_count", "6"),
            "posts_per_page": conf.get("posts_per_page", "20"),
            "comments_enabled": conf.get("comments_enabled", "1"),
            "comment_notify": conf.get("comment_notify", "0"),
            "comment_image_upload": conf.get("comment_image_upload", "1"),
            "sensitive_words_json": _sensitive_json(),
            "icp_beian": conf.get("icp_beian", ""),
            "police_beian": conf.get("police_beian", ""),
            "stats_code": _sanitize_stats(conf.get("stats_code", "")),
            "author": conf.get("author", ""),
            "author_bio": conf.get("author_bio", ""),
            "about_intro": conf.get("about_intro", ""),
            "skills": conf.get("skills", ""),
            "social_github": conf.get("social_github", ""),
            "contact_email": conf.get("contact_email", ""),
            "avatar": conf.get("avatar", ""),
            "all_tags": Post.all_tags(),
            "links": Link.load(),
            "nav_on": nav_on,
            "nav_pages": nav_pages,
            "nav_all": nav_all,
            "version": config.VERSION,
            "admin_prefix": app.config.get("ADMIN_PREFIX", "/admin"),
            "theme_asset_ver": theme_service.asset_version(),
            "admin_ver": theme_service.admin_asset_version(),
            "now_year": __import__("datetime").datetime.now().year,
            "config": conf,
            "active_theme": active,
            "themes": theme_service.list_themes(),
            "theme_has_css": theme_service.has_css(active),
            "theme_ver": theme_service.asset_version(),
            "upgrade_check": None,
            "upgrade_available": False,
            "lang_color": _lang_color,
            "icon": icon_svg,
        }

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://hm.baidu.com https://www.google-analytics.com; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob: https: http:; "
            "font-src 'self' data:; "
            "connect-src 'self' https: http:; "
            "media-src 'self' https:; "
            "frame-src 'self' https:; "
            "worker-src 'self' blob:; "
            "frame-ancestors 'self'; base-uri 'self'; form-action 'self'; object-src 'none'",
        )
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    @app.errorhandler(403)
    def _403(err):
        return render_template("403.html"), 403

    @app.errorhandler(404)
    def _404(err):
        try:
            return render_template("404.html"), 404
        except Exception:
            return "404 Not Found", 404

    @app.errorhandler(500)
    def _500(err):
        try:
            return render_template("500.html"), 500
        except Exception:
            return "500 Internal Server Error", 500

    @app.teardown_appcontext
    def _teardown(exc=None):
        g.pop("_settings", None)


def _canonical_redirect() -> str | None:
    if request.host.startswith(("127.0.0.1", "localhost", "0.0.0.0")):
        return None
    target = get_str("site_url", "").strip()
    if not target:
        return None
    parsed = urlparse(target)
    if not parsed.netloc:
        return None
    if settings_service.bool_of("force_https", False) and request.scheme != "https":
        return request.url.replace("http://", "https://", 1)
    if settings_service.bool_of("unify_www", False):
        bare = parsed.netloc.lower().removeprefix("www.")
        if request.host.lower() == bare:
            return request.url.replace(request.host, "www." + bare, 1)
    return None


# ── 模板辅助 ──────────────────────────────────────────────
_ICON_CACHE: dict[str, str] = {}


def icon_svg(name: str, size: int = 20, class_name: str = "") -> str:
    import re

    if not name or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        return ""
    if name not in _ICON_CACHE:
        path = config.STATIC_DIR / "icons" / f"{name}.svg"
        _ICON_CACHE[name] = path.read_text(encoding="utf-8") if path.is_file() else ""
    raw = _ICON_CACHE[name]
    if not raw:
        return ""
    raw = raw.replace('width="24"', f'width="{size}"').replace('height="24"', f'height="{size}"')
    if class_name:
        raw = raw.replace("<svg", f'<svg class="{class_name}"', 1)
    return raw


_LANG_COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "HTML": "#e34c26", "CSS": "#563d7c", "Vue": "#41b883", "Go": "#00ADD8",
    "Rust": "#dea584", "Java": "#b07219", "C": "#555555", "C++": "#f34b7d",
    "C#": "#178600", "PHP": "#4F5D95", "Ruby": "#701516", "Shell": "#89e051",
    "Dockerfile": "#384d54", "Makefile": "#427819", "Swift": "#F05138",
    "Kotlin": "#A97BFF", "Dart": "#00B4AB", "Lua": "#000080", "Perl": "#0298c3",
    "Scala": "#c22d40", "R": "#198CE7", "MATLAB": "#e16737", "SQL": "#e38c00",
}


def _lang_color(name: str) -> str:
    return _LANG_COLORS.get(name or "", "#8b949e")


def _sensitive_json() -> str:
    import json

    if not settings_service.bool_of("sensitive_filter_enabled", False):
        return ""
    words = [
        w.strip()
        for w in settings_service.get_str("sensitive_words", "").replace("\r", "\n").split("\n")
        if w.strip()
    ]
    return json.dumps(words, ensure_ascii=False) if words else ""


def _sanitize_stats(html: str) -> str:
    import re

    if not html:
        return ""
    html = re.sub(r"\son\w+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", "", html, flags=re.I)
    html = re.sub(r"javascript\s*:", "", html, flags=re.I)
    html = re.sub(r"<(?!(script\b|/script>)).*?>", "", html, flags=re.I | re.S)
    return re.sub(r"\n\s*\n+", "\n", html).strip()


def _register_cli(app: Flask) -> None:
    import click

    @app.cli.command("init-db")
    def _cmd_init_db() -> None:
        init_db(app)
        click.echo("数据库已初始化。")

    @app.cli.command("create-admin")
    @click.option("--username", default="admin", help="管理员账号")
    @click.option("--password", default=None, help="密码（留空自动生成）")
    def _cmd_create_admin(username: str, password: str | None) -> None:
        from models import User

        pwd = password or secrets.token_urlsafe(12)
        User.create(username, pwd)
        click.echo(f"管理员已创建：{username} / {pwd}")

    @app.cli.command("reset-password")
    @click.option("--username", default="", help="账号名（留空取唯一管理员）")
    @click.option("--password", default=None, help="新密码（留空自动生成）")
    def _cmd_reset_password(username: str, password: str | None) -> None:
        from models import User

        user = User.get_by_username(username) if username else User.first()
        if not user:
            click.echo("未找到管理员账号")
            return
        pwd = password or secrets.token_urlsafe(12)
        User.update_password(int(user["id"]), pwd)
        click.echo(f"密码已重置：{user['username']} / {pwd}")

    @app.cli.command("run")
    @click.option("--host", default="127.0.0.1")
    @click.option("--port", default=5000, type=int)
    @click.option("--debug/--no-debug", default=False)
    def _cmd_run(host: str, port: int, debug: bool) -> None:
        app.run(host=host, port=port, debug=debug)


app = create_app()


if __name__ == "__main__":
    with app.app_context():
        from models import User

        if User.count() == 0:
            # create_app 已初始化；这里是极端兜底，保持与首次安装一致的默认密码
            User.create("admin", "admin123")
            print("已创建默认管理员：admin / admin123（请登录后立即修改）")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=port, debug=False)
