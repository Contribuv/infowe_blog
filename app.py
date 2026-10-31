"""Python 博客入口：应用工厂、全局上下文、错误页与 CLI。"""

from __future__ import annotations

import gzip
import os
import re
import secrets
import sys
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, g, redirect, render_template, request, session, url_for
from jinja2 import ChoiceLoader, FileSystemLoader
from werkzeug.middleware.proxy_fix import ProxyFix

import config
from db import init_app as init_db_app, init_db
from services import settings as settings_service
from services import theme as theme_service
from services import quotes as quotes_service
from services.storage import migrate_legacy_storage
from services.settings import get_str

# 走 gzip 的文本类型（图片/字体/视频不在其中）
_GZIP_TYPES = {
    "text/html",
    "text/css",
    "text/plain",
    "text/xml",
    "application/javascript",
    "text/javascript",
    "application/json",
    "application/rss+xml",
    "application/atom+xml",
    "image/svg+xml",
}

# 静态文件压缩结果按「路径 + Last-Modified」缓存，避免每次请求都重新压
_STATIC_GZIP_CACHE: dict[str, bytes] = {}


def _ensure_dirs() -> None:
    for path in (
        config.UPLOADS_DIR, config.BACKUPS_DIR,
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


class _LazyCount:
    """模板里只用到 `all_tags|length`，没必要每个请求都全表扫 posts。

    懒到模板真正取长度时才查一次；不迭代、不取元素，避免误用。
    口径与侧栏一致：只统计已发布文章用到的标签（含草稿/隐藏会让首页与侧栏数字打架）。
    """

    __slots__ = ("_factory", "_value")

    def __init__(self, factory):
        self._factory = factory
        self._value = None

    def __len__(self):
        if self._value is None:
            self._value = len(self._factory())
        return self._value


def create_app(test_config: dict | None = None) -> Flask:
    migrate_legacy_storage()
    _ensure_dirs()
    # 旧的两处主题结构（templates/theme/<key> + themes/<key>/*.css）合并到单目录
    theme_service.migrate_legacy_layout()
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

    # 插件：同步注册表，并把插件模板目录追加到 Jinja loader
    from services import plugins as plugins_service

    with app.app_context():
        plugins_service.sync_registry()
    plugin_loaders = [
        theme_loader,
        FileSystemLoader(str(config.SHARED_TEMPLATE_DIR)),
        FileSystemLoader(str(config.TEMPLATE_DIR)),
    ]
    for manifest in plugins_service.discover():
        plugin_templates = Path(manifest["_dir"]) / "templates"
        if plugin_templates.is_dir():
            plugin_loaders.append(FileSystemLoader(str(plugin_templates)))
    app.jinja_loader = ChoiceLoader(plugin_loaders)

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
    with app.app_context():
        plugins_service.load_all(app)
    if not app.config.get("TESTING"):
        _start_status_scheduler(app)
        from services import feeds as feeds_service
        feeds_service.start_scheduler(app)
    return app


def _register_hooks(app: Flask) -> None:
    @app.before_request
    def _before() -> None:
        admin_prefix = app.config.get("ADMIN_PREFIX", "/admin")
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
            elif session.get("admin_id"):
                # 已登录的后台操作必须带 Origin/Referer；匿名评论（无会话）保持放行，
                # 由评论冷却兜底，避免老客户端/隐私模式误伤。
                return ("缺少来源校验，请从后台页面操作", 403)

        # 强制 HTTPS / www 归一（仅 GET，后台与本地豁免）
        if request.method == "GET" and not request.path.startswith(admin_prefix):
            target = _canonical_redirect()
            if target:
                return redirect(target, code=301)

        # 页面缓存：只命中匿名 GET；写操作标记失效
        from services import page_cache

        if request.method == "POST":
            if request.path == admin_prefix or request.path.startswith(admin_prefix + "/"):
                g._clear_page_cache = True
            match = re.fullmatch(r"/post/(\d+)/comment", request.path)
            if match:
                g._invalidate_pages = [f"/post/{match.group(1)}"]
            match = re.fullmatch(r"/projects/(\d+)/comment", request.path)
            if match:
                g._invalidate_pages = [f"/projects/{match.group(1)}"]
            if request.path == "/links/apply":
                g._invalidate_pages = ["/links"]

        cached = page_cache.load()
        if cached is not None:
            return cached

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

        # 外部链接确认弹窗的白名单：已通过审核的友链站点不再拦截
        from urllib.parse import urlparse

        import db

        friend_hosts: list[str] = []
        for row in db.query("SELECT url FROM links WHERE status = 'approved'"):
            host = urlparse(str(row["url"] or "")).hostname
            if host:
                friend_hosts.append(host.lower())
        friend_hosts = sorted(set(friend_hosts) | {"foreverblog.cn"})

        return {
            "blog_name": conf.get("blog_name", "infowe"),
            "blog_subtitle": conf.get("blog_subtitle", ""),
            "home_title": conf.get("home_title", ""),
            "home_kicker": conf.get("home_kicker", ""),
            "home_quotes": quotes_service.parse(conf.get("home_quotes", "")),
            "home_posts_count": conf.get("home_posts_count", "6"),
            "posts_per_page": conf.get("posts_per_page", "20"),
            "comments_enabled": conf.get("comments_enabled", "1"),
            "comment_notify": conf.get("comment_notify", "0"),
            "comment_image_upload": conf.get("comment_image_upload", "1"),
            "comment_display": conf.get("comment_display", "inline"),
            "fab_shape": conf.get("fab_shape", "capsule"),
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
            # 只算已发布文章的标签，与侧栏/首页「已使用」口径一致（旧的 all_tags 含草稿标签，77≠56）
            "all_tags": _LazyCount(lambda: dict(Post.tag_counts(9999))),
            "nav_on": nav_on,
            "nav_pages": nav_pages,
            "post_layout": conf.get("post_layout", "single"),
            "nav_all": nav_all,
            "friend_hosts": friend_hosts,
            "project_layout": conf.get("project_layout", "three"),
            "version": config.VERSION,
            "static_ver": _static_version(),
            "admin_prefix": app.config.get("ADMIN_PREFIX", "/admin"),
            "theme_css_name": theme_service.css_name(active),
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
            # 侧边栏「留存记录」入口：插件停用时隐藏，避免 url_for 找不到路由
            "retention_enabled": __import__("services.plugins", fromlist=["enabled"]).enabled("retention"),
        }

    @app.after_request
    def _gzip_response(response):
        """gzip 兜底：Nginx 已压缩时响应会带 Content-Encoding，这里直接跳过。

        只压 HTML / CSS / JS / JSON 这类文本；静态文件的结果按
        「路径 + Last-Modified」缓存，避免每次请求都重新压一遍。
        """
        if request.method == "HEAD":
            return response
        if response.headers.get("Content-Encoding"):
            return response
        accept = (request.headers.get("Accept-Encoding") or "").lower()
        if "gzip" not in accept:
            return response
        ctype = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype not in _GZIP_TYPES:
            return response
        if response.direct_passthrough:
            # Flask 的静态文件默认直通发送；只在站内静态目录上关掉直通，
            # 走下面的读文件 + 压缩流程
            if not request.path.startswith(("/static/", "/themes/")):
                return response
            response.direct_passthrough = False

        last_mod = response.headers.get("Last-Modified") or ""
        cache_key = f"{request.path}|{last_mod}" if last_mod else ""
        packed = _STATIC_GZIP_CACHE.get(cache_key) if cache_key else None
        if packed is None:
            try:
                raw = response.get_data()
            except RuntimeError:
                return response
            if len(raw) < 1024:
                return response
            packed = gzip.compress(raw, compresslevel=6)
            if len(packed) >= len(raw) * 0.9:
                return response
            if cache_key:
                if len(_STATIC_GZIP_CACHE) > 200:
                    _STATIC_GZIP_CACHE.clear()
                _STATIC_GZIP_CACHE[cache_key] = packed

        response.set_data(packed)
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = str(len(packed))
        vary = response.headers.get("Vary")
        if vary:
            if "Accept-Encoding" not in vary:
                response.headers["Vary"] = vary + ", Accept-Encoding"
        else:
            response.headers["Vary"] = "Accept-Encoding"
        response.headers.pop("ETag", None)
        return response

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
        # HSTS 由 Nginx 统一输出；只有直连 Flask TLS 且没有代理头时才补
        if request.is_secure and not request.headers.get("X-Forwarded-Proto"):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )

        # 页面缓存：写缓存 / 清理失效页面
        from services import page_cache

        page_cache.store(response)
        if getattr(g, "_clear_page_cache", False):
            page_cache.clear_all()
        elif getattr(g, "_invalidate_pages", None):
            for path in g._invalidate_pages:
                page_cache.invalidate_path(path)
        if response.mimetype in {"text/html", "application/rss+xml"}:
            response.headers.setdefault("Cache-Control", "no-cache")
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
_STATIC_VER_CACHE: dict[str, float] = {"ts": 0.0, "ver": 0.0}


def _static_version() -> int:
    """static 下 css/js 的最新 mtime，用作 ?t= 缓存戳。

    改了静态文件就自动换 URL，不必每改一次都动版本号；30 秒内复用结果。
    """
    import time as _time

    now = _time.time()
    if now - _STATIC_VER_CACHE["ts"] < 30:
        return int(_STATIC_VER_CACHE["ver"])
    latest = 0
    for path in config.STATIC_DIR.rglob("*"):
        if path.suffix.lower() in {".css", ".js"} and path.is_file():
            latest = max(latest, int(path.stat().st_mtime))
    _STATIC_VER_CACHE.update(ts=now, ver=latest)
    return latest


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


def _start_status_scheduler(app: Flask) -> None:
    """状态页自动探测：每 5 分钟跑一次 probe_all。

    线上 gunicorn 4 个 worker 都会起这个线程，用文件锁保证同一时刻只有一个
    进程真正发请求；没有 fcntl 的平台（本地 Windows）直接不启动。
    """
    import threading
    import time

    def loop() -> None:
        try:
            import fcntl
        except ImportError:
            return
        time.sleep(15)
        while True:
            try:
                with app.app_context():
                    from models import ServiceCheck
                    from services import status as status_service

                    services = status_service.parse_services()
                    if services:
                        latest = 0.0
                        for svc in services:
                            row = ServiceCheck.latest(svc["id"])
                            if row:
                                latest = max(latest, float(row["checked_at"]))
                        if time.time() - latest >= 300:
                            lock_path = Path(config.CACHE_DIR) / "status_probe.lock"
                            lock_path.parent.mkdir(parents=True, exist_ok=True)
                            with open(lock_path, "w") as fh:
                                try:
                                    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                                except OSError:
                                    pass
                                else:
                                    status_service.probe_all(True)
            except Exception:
                app.logger.exception("status probe scheduler failed")
            time.sleep(60)

    threading.Thread(target=loop, daemon=True, name="status-probe").start()


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
