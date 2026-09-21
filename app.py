"""
infowe Blog - Python Flask Backend
SQLite 数据库驱动，完整前台 + 后台管理
新增：GitHub 项目页、搜索、分页、友情链接、精选文章
"""

# 应用版本号（后台显示用，修改请同步更新此处）
VERSION = '1.3.56'

import os
import re
import json
import sqlite3
import hashlib
import shutil
import zipfile
import io
import time
import tempfile
import urllib.request
import urllib.error
import ssl

import math
import socket
import base64
import hmac
import struct
import uuid
import threading
import concurrent.futures
import urllib.parse
import smtplib
import email.utils
import ipaddress
from datetime import datetime, timezone, timedelta as _td
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from functools import wraps

import markdown
# Pillow 用于上传图片压缩（可选依赖，缺失时跳过压缩）
try:
    from PIL import Image, ImageOps
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False
# pillow-heif：HEIC/HEIF 解码支持（可选依赖）。优先注册 Pillow 解码器；
# 即使注册失败（如 Pillow 版本兼容问题），仍可用 pillow_heif.open_heif 直接解码。
try:
    import pillow_heif
    _HAS_HEIF = True
    try:
        pillow_heif.register_heif_opener()
    except Exception:
        pass  # 注册失败不影响 open_heif 直解码路径
    _PH_VER = getattr(pillow_heif, '__version__', '?')
    try:
        _LIBHEIF_VER = pillow_heif.libheif_info().get('version', '?')
    except Exception:
        _LIBHEIF_VER = '?'
    print(f'[HEIC] pillow_heif {_PH_VER} (libheif {_LIBHEIF_VER}) / Pillow {getattr(Image, "__version__", "?")}')
except Exception as _heif_err:
    _HAS_HEIF = False
    _PH_VER = '?'
    _LIBHEIF_VER = '?'
    print(f'[HEIC] pillow_heif 导入失败：{_heif_err}')
import werkzeug.security as ws
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from flask import Flask, render_template, abort, request, redirect, url_for, session, flash, jsonify, send_from_directory, send_file, make_response, g, has_request_context
from jinja2 import FileSystemLoader


# ─────────────── 主题系统（v1.3.0）───────────────
# 主题放在 templates/<主题名>/ 下（每个主题一个文件夹，与模板同级）：
#   info.json        （可选）{name, author, description, version}
#   theme.css        （可选）样式覆盖，前台在默认样式之后加载
#   同名模板         （可选）覆盖默认主题的页面结构（如 base.html、index.html）
#   preview.png      （可选）后台主题列表预览图
# 默认主题为 templates/default/（系统内置）。
# 后台「博客设置 → 外观与主题」选择后立即生效（无需重启）。
# 开发新主题：复制 templates/default/ 为模板底稿，放入自定义 theme.css / 模板即可。
# 注意：BASE_DIR 在下方才定义，这里用 __file__ 自行推导模板根目录。
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
DEFAULT_THEME_NAME = 'default'


def _read_theme_info(name):
    """读取主题目录下的 info.json（可选）。缺失/损坏/非对象时返回 {}，由调用方回退默认值。"""
    infof = os.path.join(TEMPLATE_DIR, name, 'info.json')
    if not os.path.isfile(infof):
        return {}
    try:
        with open(infof, encoding='utf-8') as f:
            info = json.load(f)
    except Exception:
        return {}
    return info if isinstance(info, dict) else {}


def list_themes():
    """扫描 templates/ 下的主题文件夹，返回 [{key,name,author,description,version,has_preview}]。

    default 为内置主题（templates/default），固定排首位。
    所有主题（含 default）的展示信息均优先取各自目录下的 info.json，
    字段缺失时回退内置文案——这样 default 也能像其它主题一样用 info.json 自定义元信息。
    """
    fallback_default = {'key': DEFAULT_THEME_NAME, 'name': '系统默认', 'author': 'infowe',
                        'description': '内置样式与模板', 'version': VERSION, 'has_preview': False}
    if not os.path.isdir(TEMPLATE_DIR):
        return [fallback_default]
    # default 固定首位，其余按目录名字典序；跳过隐藏目录与后台专用目录 admin（非主题）
    names = [DEFAULT_THEME_NAME] + sorted(
        n for n in os.listdir(TEMPLATE_DIR)
        if os.path.isdir(os.path.join(TEMPLATE_DIR, n))
        and not n.startswith('.') and n != DEFAULT_THEME_NAME and n != 'admin'
    )
    themes = []
    for name in names:
        d = os.path.join(TEMPLATE_DIR, name)
        info = _read_theme_info(name)
        if name == DEFAULT_THEME_NAME:
            fb = {'name': '系统默认', 'author': 'infowe', 'description': '内置样式与模板', 'version': VERSION}
        else:
            fb = {'name': name, 'author': '', 'description': '', 'version': ''}
        themes.append({
            'key': name,
            'name': info.get('name') or fb['name'],
            'author': info.get('author', fb['author']),
            'description': info.get('description', fb['description']),
            'version': info.get('version', fb['version']),
            'has_preview': os.path.isfile(os.path.join(d, 'preview.png')),
        })
    return themes


def _active_theme_key():
    """当前启用的主题 key（default 表示内置主题）。"""
    return app.config.get('active_theme') or 'default'


def _theme_asset_ver():
    """主题静态资源缓存版本：取当前主题 theme.css / theme.js 的最新 mtime。
    修改样式后 URL 的 ?t= 参数自动变化，强制浏览器重新拉取，避免开发期旧缓存。"""
    ver = 0
    tdir = os.path.join(TEMPLATE_DIR, _active_theme_key())
    for f in ('theme.css', 'theme.js'):
        try:
            ver = max(ver, int(os.path.getmtime(os.path.join(tdir, f))))
        except OSError:
            pass
    return ver or 0


def _admin_asset_ver():
    """后台静态资源缓存版本：admin.css / admin.js 的最新 mtime。
    此前用发布版本号做 ?t= 参数，样式修复未发版时用户浏览器永远命中旧缓存（SMTP
    溢出修复"看似没生效"的根因）。改为 mtime 后，改动即时破缓存。"""
    ver = 0
    for f in ('css/admin.css', 'js/admin.js'):
        try:
            ver = max(ver, int(os.path.getmtime(os.path.join(app.static_folder, f))))
        except OSError:
            pass
    return ver or 0


_LAST_THEME_KEY = [None]


def _sync_theme_cache():
    """主题变化时清空 Jinja 模板缓存，保证同名模板（如 index.html）切换后立即重载。
    任何方式（后台选择、手动改库、导入设置）改变主题都会在下一请求生效。"""
    key = _active_theme_key()
    if _LAST_THEME_KEY[0] != key:
        _LAST_THEME_KEY[0] = key
        try:
            app.jinja_env.cache.clear()
        except Exception:
            pass


def _theme_has_css(key=None):
    """当前启用主题是否提供 theme.css（前台默认样式之后的追加覆盖）。"""
    key = key or _active_theme_key()
    if key == DEFAULT_THEME_NAME:
        return False
    return os.path.isfile(os.path.join(TEMPLATE_DIR, key, 'theme.css'))


class ThemeLoader(FileSystemLoader):
    """主题模板加载器：优先从当前启用主题的文件夹加载同名模板，
    未命中时回退默认主题模板（templates/default），实现“主题可整体覆盖页面结构”。"""

    def __init__(self, flask_app):
        self._flask_app = flask_app
        FileSystemLoader.__init__(self, '')

    def get_source(self, environment, template):
        base = os.path.join(self._flask_app.root_path,
                            self._flask_app.template_folder or 'templates')
        theme = self._flask_app.config.get('active_theme') or 'default'
        paths = []
        tp = os.path.join(base, theme)
        # 活动主题目录优先（default 主题直接命中默认目录，无需重复加入）
        if theme != DEFAULT_THEME_NAME and os.path.isdir(tp):
            paths.append(tp)
        paths.append(os.path.join(base, DEFAULT_THEME_NAME))
        # 根模板目录兜底：后台 admin/ 等全局模板不归属任何主题
        paths.append(base)
        self.searchpath = paths
        return FileSystemLoader.get_source(self, environment, template)


class ThemedFlask(Flask):
    """启用主题模板覆盖的 Flask 应用：模板查找顺序 = 主题模板 → 默认主题模板。
    注：Flask 3.x 通过 jinja_loader property 取得模板加载器（create_jinja_loader
    已不再被调用），因此这里直接覆写该 property。"""

    @property
    def jinja_loader(self):
        return ThemeLoader(self)


def _now():
    """返回本地 CST 时间字符串（YYYY-MM-DD HH:MM:SS）。
    所有 INSERT/UPDATE 统一用这个显式写 DB，不再依赖 SQLite DEFAULT CURRENT_TIMESTAMP（UTC）。"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# 项目根目录与核心路径常量：必须最先定义——下方 secret_key 逻辑（data/.secret_key）就要用 BASE_DIR
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'blog.db')
POSTS_DIR = os.path.join(BASE_DIR, 'posts')
DATA_FILE = os.path.join(BASE_DIR, 'data', 'posts.json')
ICONS_DIR = os.path.join(BASE_DIR, 'static', 'icons')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')          # 上传文件根目录（v1.0.6 起位于项目根）
OLD_UPLOAD_DIR = os.path.join(BASE_DIR, 'static', 'uploads')  # 旧上传目录（v1.0.6 启动时自动迁移）
# 注意：头像上传不使用 .svg，因为 SVG 可内嵌脚本，在同源下会造成存储型 XSS。
ALLOWED_IMAGE_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.heic', '.heif'}
ALLOWED_MEDIA_EXT = {'.mp4', '.webm', '.ogg', '.mov', '.avi'}
ALLOWED_FILE_EXT = {'.zip', '.rar', '.pdf', '.doc', '.docx', '.xls', '.xlsx',
                    '.ppt', '.pptx', '.txt', '.md', '.py', '.js', '.json'}


app = ThemedFlask(__name__)
# 模板按文件 mtime 自动重载：后台切换主题无需重启，生产环境同样生效
app.config['TEMPLATES_AUTO_RELOAD'] = True
# secret_key：优先从环境变量读取（部署时务必设置 BLOG_SECRET_KEY），
# 避免源码中硬编码导致 session 被伪造。未设置时生成随机密钥持久化到文件。
_secret_file = os.path.join(BASE_DIR, 'data', '.secret_key')
if os.environ.get('BLOG_SECRET_KEY'):
    app.secret_key = os.environ['BLOG_SECRET_KEY']
else:
    if os.path.isfile(_secret_file):
        app.secret_key = open(_secret_file, 'r').read().strip()
    else:
        import secrets
        _generated = secrets.token_hex(32)
        os.makedirs(os.path.dirname(_secret_file), exist_ok=True)
        with open(_secret_file, 'w') as _f:
            _f.write(_generated)
        try:
            os.chmod(_secret_file, 0o600)
        except (OSError, NotImplementedError):
            pass  # Windows 不支持 chmod
        app.secret_key = _generated
    print(f'[安全提示] 未设置 BLOG_SECRET_KEY，已生成随机密钥并保存到 data/.secret_key')
# 请求体上限 32MB：上传单文件限制 20MB（见 _save_upload），此处为 Flask 级兜底，
# 防止无 Content-Length 的分块上传或超大附件挤爆临时目录/磁盘；超限自动返回 413。
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024


# 在 Nginx 反代后运行时，让 request.remote_addr 自动还原为真实客户端 IP。
# x_for=1 表示信任来自 1 层可信代理（Nginx）转发过来的 X-Forwarded-For 第一个值。
# 只有经过 Nginx 转发的请求才会被改写，直接访问本机的伪造头无效，避免 IP 欺骗。
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Preload all SVG icons into memory for fast template rendering
_ICON_CACHE = {}
def _load_icons():
    """Load all SVG files from icons directory into memory cache."""
    if not os.path.isdir(ICONS_DIR):
        return
    for fname in os.listdir(ICONS_DIR):
        if fname.endswith('.svg'):
            name = fname[:-4]  # remove .svg extension
            fpath = os.path.join(ICONS_DIR, fname)
            with open(fpath, 'r', encoding='utf-8') as f:
                _ICON_CACHE[name] = f.read().strip()

_load_icons()

def icon_svg(name, size=20, class_name=''):
    """Return inline SVG markup for a named Lucide icon.
    Usage in templates: {{ icon('home', 18, 'nav-icon') | safe }}
    """
    raw = _ICON_CACHE.get(name, '')
    if not raw:
        return ''
    # Replace fixed width/height with dynamic size, add class if provided
    svg = raw.replace('width="24"', f'width="{size}"')
    svg = svg.replace('height="24"', f'height="{size}"')
    if class_name:
        svg = svg.replace('<svg', f'<svg class="{class_name}"', 1)
    return svg

app.jinja_env.globals['icon'] = icon_svg

PAGE_SIZE = 20  # 每页文章数

# ─────────────── 数据库初始化 ───────────────

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    # 不再在此处逐连接执行 PRAGMA journal_mode=WAL：该 PRAGMA 要拿数据库锁，
    # 高并发下新连接执行会撞锁抛 database is locked。WAL 模式已在 init_db 一次性
    # 激活并持久化到库文件，后续连接无需重设。
    # foreign_keys=ON 保留：posts 表存在外键级联删除（L368），依赖此连接级开关。
    conn.execute("PRAGMA foreign_keys=ON")
    # 写锁短暂碰撞时自动等待（最长 ~15s），而非立刻抛 database is locked：
    # 多 gunicorn worker + 监控线程并发写同一 WAL 库时避免偶发 500。
    conn.execute("PRAGMA busy_timeout=15000")
    return conn


def _request_db():
    """请求上下文内复用同一连接（g 缓存，teardown 统一关闭）：
    把每请求多次开 SQLite 连接压成 1 次，减少连接开销与锁争用。
    非请求上下文（模块导入期 load_settings、守护线程等）退回独立连接。"""
    if has_request_context():
        db = getattr(g, '_request_db', None)
        if db is None:
            db = get_db()
            g._request_db = db
        return db
    return get_db()


@app.teardown_appcontext
def _close_request_db(exc=None):
    """请求结束统一关闭 g 缓存的连接，避免连接泄漏。"""
    db = g.pop('_request_db', None)
    if db is not None:
        db.close()


def hash_password(password):
    # 使用 werkzeug 的安全哈希（pbkdf2 + 随机盐 + 多次迭代）
    # 定义放在 init_db 之前，因为 init_db 在模块导入期会被调用，需要此函数已就绪。
    return ws.generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)


def init_db():
    db = get_db()
    # 建库/启动时一次性激活 WAL 模式并持久化（此后所有连接无需重设，见 get_db）
    db.execute("PRAGMA journal_mode=WAL")

    # 基础表
    db.executescript('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            excerpt TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            cover TEXT DEFAULT '',
            read_time INTEGER DEFAULT 3,
            views INTEGER DEFAULT 0,
            status TEXT DEFAULT 'published',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            url TEXT DEFAULT '',
            stars INTEGER DEFAULT 0,
            language TEXT DEFAULT '',
            topics TEXT DEFAULT '[]',
            sort_order INTEGER DEFAULT 0,
            featured INTEGER DEFAULT 0,
            github_repo TEXT DEFAULT '',
            custom_name INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            description TEXT DEFAULT '',
            avatar TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            status TEXT DEFAULT 'approved',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            parent_id INTEGER DEFAULT NULL,
            author TEXT NOT NULL DEFAULT 'Anonymous',
            email_hash TEXT DEFAULT '',
            website TEXT DEFAULT '',
            content TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            is_private INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS timeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            content TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL DEFAULT '',
            image TEXT NOT NULL DEFAULT '',
            date TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS service_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id TEXT NOT NULL,
            checked_at REAL NOT NULL,
            ok INTEGER NOT NULL DEFAULT 0,
            latency_ms INTEGER DEFAULT 0,
            cert_days INTEGER DEFAULT -1,
            detail TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_service_checks ON service_checks (service_id, checked_at);
    ''')

    # 兼容旧数据库：添加新列（如果不存在）
    try:
        db.execute("SELECT is_featured FROM posts LIMIT 1")
    except sqlite3.OperationalError:
        db.execute("ALTER TABLE posts ADD COLUMN is_featured INTEGER DEFAULT 0")
        print('[迁移] 添加列: posts.is_featured')

    try:
        db.execute("SELECT views FROM posts LIMIT 1")
    except sqlite3.OperationalError:
        db.execute("ALTER TABLE posts ADD COLUMN views INTEGER DEFAULT 0")
        print('[迁移] 添加列: posts.views')

    try:
        db.execute("SELECT category_id FROM posts LIMIT 1")
    except sqlite3.OperationalError:
        db.execute("ALTER TABLE posts ADD COLUMN category_id INTEGER DEFAULT NULL")
        print('[迁移] 添加列: posts.category_id')

    try:
        db.execute("SELECT status FROM links LIMIT 1")
    except sqlite3.OperationalError:
        db.execute("ALTER TABLE links ADD COLUMN status TEXT DEFAULT 'approved'")
        print('[迁移] 添加列: links.status')

    try:
        db.execute("SELECT avatar FROM links LIMIT 1")
    except sqlite3.OperationalError:
        db.execute("ALTER TABLE links ADD COLUMN avatar TEXT DEFAULT ''")
        print('[迁移] 添加列: links.avatar')

    # 迁移：projects 表增加 github_repo 列（去重用）
    try:
        db.execute("SELECT github_repo FROM projects LIMIT 1")
    except sqlite3.OperationalError:
        db.execute("ALTER TABLE projects ADD COLUMN github_repo TEXT DEFAULT ''")
        print('[迁移] 添加列: projects.github_repo')

    # 迁移：projects 表增加 custom_name 标记（项目名是否被自定义，同步时不再覆盖）
    try:
        db.execute("SELECT custom_name FROM projects LIMIT 1")
    except sqlite3.OperationalError:
        db.execute("ALTER TABLE projects ADD COLUMN custom_name INTEGER DEFAULT 0")
        print('[迁移] 添加列: projects.custom_name')

    # 迁移：projects 表增加 languages 列（存储语言占比 JSON 列表）
    try:
        db.execute("SELECT languages FROM projects LIMIT 1")
    except sqlite3.OperationalError:
        db.execute("ALTER TABLE projects ADD COLUMN languages TEXT DEFAULT '[]'")
        print('[迁移] 添加列: projects.languages')

    # 默认管理员：仅当 users 表为空时创建（表非空时由下方触发器硬保证不再新增）。
    # 密码随机生成并打印到日志，首次登录后必须在后台修改。
    users_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if users_count == 0:
        import secrets as _secrets
        _default_pwd = _secrets.token_hex(8)
        db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                   ('admin', hash_password(_default_pwd)))
        print(f'[初始化] 默认管理员账号: admin / 密码: {_default_pwd}')
        print(f'[初始化] 请首次登录后立即修改密码！')

    # 默认设置
    defaults = [
        ('blog_name', 'infowe'),
        ('blog_subtitle', 'Python · Code · Life'),
        ('author', 'Linus'),
        ('author_bio', 'Python 全栈开发者，热爱开源，沉迷于代码美学与系统架构。\n相信每一行代码都有它的灵魂，每一个 Bug 都是成长的阶梯。'),
        ('skills', '[{"name":"Python","level":95},{"name":"Flask / Django","level":90},{"name":"JavaScript","level":85},{"name":"Docker / K8s","level":75},{"name":"PostgreSQL","level":85},{"name":"Redis","level":80},{"name":"Linux","level":88}]'),
        ('about_intro', 'infowe 是一个专注于 Python 生态的独立技术博客，使用 Flask 构建，文章以 Markdown 编写。'),
        ('avatar', ''),
        ('github_username', ''),
        ('social_github', ''),
        ('github_token', ''),
        ('contact_email', ''),
        ('home_title', ''),
        ('home_posts_count', '6'),
        ('posts_per_page', '20'),
        ('comments_enabled', '1'),
        # ── 评论邮件通知（SMTP，新评论/新回复时通知博主） ──
        ('comment_notify', '1'),
        ('smtp_host', ''),
        ('smtp_sender_name', ''),
        ('smtp_port', '465'),
        ('smtp_user', ''),
        ('smtp_pass', ''),
        ('notify_email', ''),
        # ── 导航菜单开关（关闭后对应页面返回 404，且 nav/页脚不再显示） ──
        ('nav_posts', '1'),
        ('nav_tags', '1'),
        ('nav_projects', '1'),
        ('nav_links', '1'),
        ('nav_status', '1'),
        ('nav_about', '1'),
        ('icp_beian', ''),
        ('police_beian', ''),
        # ── 服务时效 / Server Status 配置 ──
        ('aliyun_access_key', ''),
        ('aliyun_access_secret', ''),
        ('aliyun_region', 'cn-hangzhou'),
        ('aliyun_instance_id', ''),
        ('tencent_secret_id', ''),
        ('tencent_secret_key', ''),
        ('tencent_domain', ''),
        ('expiry_aliyun', ''),       # 手动兜底：阿里云到期日期 YYYY-MM-DD
        ('expiry_tencent', ''),      # 手动兜底：腾讯云域名到期日期 YYYY-MM-DD
        ('monitor_services', '[]'),  # 监控的 HTTP/HTTPS 服务列表 JSON
        ('watermark_enabled', '1'),      # 图片水印开关
        ('watermark_text', ''),          # 水印文本（空则用「站点名 · 域名」）
        ('watermark_position', 'br'),    # 水印位置 br/bl/tr/tl
        ('watermark_size', 'm'),         # 水印字号档位 s 小 / m 标准 / l 大
    ]
    for k, v in defaults:
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    # ── v1.3.43 自动迁移：DB 时区统一 UTC→CST ──
    # 之前表定义 DEFAULT CURRENT_TIMESTAMP 存 UTC，部分历史数据（导入脚本 datetime.now、
    # Hexo 迁移占位 12:00:00）是本地 CST。schema_version<2 时首次启动自动跑一次。
    try:
        _sv = db.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()
        _ver = int(_sv[0]) if _sv else 0
    except Exception:
        _ver = 0
    if _ver < 2:
        print(f'[时区迁移] schema_version {_ver} → 2，开始 UTC→CST (+8h) 迁移……')

        def _shift_utc(s):
            """UTC 时间字符串 +8h → CST，解析失败原样返回。"""
            if not s:
                return s
            try:
                return (datetime.strptime(s[:19], '%Y-%m-%d %H:%M:%S') +
                        _td(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                return s

        # posts.created_at：纯日期/12:00:00 整点跳过（CST 导入/Hexo 占位），其余 +8h
        for pid, ca, ua in db.execute("SELECT id, created_at, updated_at FROM posts").fetchall():
            new_ca = ca
            if ca and len(ca) >= 19 and ' 12:00:00' not in ca:
                new_ca = _shift_utc(ca)
            new_ua = _shift_utc(ua) if ua else ua
            if new_ca != ca or new_ua != ua:
                db.execute("UPDATE posts SET created_at=?, updated_at=? WHERE id=?", (new_ca, new_ua, pid))

        # 其它表：全 CURRENT_TIMESTAMP UTC → +8h
        for _tbl in ('comments', 'projects', 'timeline', 'links', 'categories', 'memories'):
            try:
                for row in db.execute(f"SELECT rowid, created_at FROM {_tbl} WHERE created_at IS NOT NULL").fetchall():
                    new_v = _shift_utc(row[1])
                    if new_v != row[1]:
                        db.execute(f"UPDATE {_tbl} SET created_at=? WHERE rowid=?", (new_v, row[0]))
            except sqlite3.OperationalError:
                pass  # 表不存在（老版本 DB）

        # projects / timeline 还有 updated_at
        for _tbl in ('projects', 'timeline'):
            try:
                for row in db.execute(f"SELECT rowid, updated_at FROM {_tbl} WHERE updated_at IS NOT NULL").fetchall():
                    new_v = _shift_utc(row[1])
                    if new_v != row[1]:
                        db.execute(f"UPDATE {_tbl} SET updated_at=? WHERE rowid=?", (new_v, row[0]))
            except sqlite3.OperationalError:
                pass

        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('schema_version', '2')")
        print('[时区迁移] 完成，schema_version=2')

    # ── v1.3.51 单管理员迁移：users 表硬保证恰好 1 条 ──
    # 本博客仅支持单个管理员账号。历史库可能残留多余账号（如手工插入的 admin/liuhao 并存），
    # 多账号会让「忘记密码找回」「账号名修改」等功能目标不明。迁移做两件事：
    # 1) 多于 1 条时保留最早创建的账号（id 最小），删除其余；
    # 2) 建触发器拦截一切 INSERT —— 数据库层面硬保证，任何代码 bug / 手工插库都会被拒绝。
    try:
        _sv3 = db.execute("SELECT value FROM settings WHERE key='schema_version'").fetchone()
        _ver3 = int(_sv3[0]) if _sv3 else 0
    except Exception:
        _ver3 = 0
    if _ver3 < 3:
        _users_cnt = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if _users_cnt > 1:
            _keeper = db.execute("SELECT username FROM users ORDER BY id LIMIT 1").fetchone()[0]
            db.execute("DELETE FROM users WHERE username != ?", (_keeper,))
            print(f'[单管理员迁移] 检测到 {_users_cnt} 个账号，保留最早创建的「{_keeper}」，其余已删除')
        db.execute("""
            CREATE TRIGGER IF NOT EXISTS users_single_admin_guard
            BEFORE INSERT ON users
            WHEN (SELECT COUNT(*) FROM users) >= 1
            BEGIN
                SELECT RAISE(ABORT, '博客仅支持单个管理员账号（users 表已有账号，禁止新增）');
            END;""")
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('schema_version', '3')")
        print('[单管理员迁移] 完成，schema_version=3（users 表单账号触发器已就位）')

    db.commit()
    _migrate_comments(db)
    migrate_from_json(db)
    db.close()


def _migrate_comments(db):
    """评论表结构升级（盖楼 + 联系方式 + 审核），幂等可重复执行。
    老库走 ALTER TABLE 补列；新库建表时已含这些列，此处自动跳过。"""
    cols = {r['name'] for r in db.execute("PRAGMA table_info(comments)").fetchall()}
    added = []
    if 'parent_id' not in cols:
        db.execute("ALTER TABLE comments ADD COLUMN parent_id INTEGER DEFAULT NULL")
        added.append('parent_id')
    if 'email_hash' not in cols:
        db.execute("ALTER TABLE comments ADD COLUMN email_hash TEXT DEFAULT ''")
        added.append('email_hash')
    if 'website' not in cols:
        db.execute("ALTER TABLE comments ADD COLUMN website TEXT DEFAULT ''")
        added.append('website')
    if 'status' not in cols:
        # 老评论默认 approved，避免升级后前台评论凭空消失
        db.execute("ALTER TABLE comments ADD COLUMN status TEXT DEFAULT 'approved'")
        added.append('status')
    if 'is_private' not in cols:
        db.execute("ALTER TABLE comments ADD COLUMN is_private INTEGER DEFAULT 0")
        added.append('is_private')
    # 项目详情页评论：comments 支持挂到项目（project_id 与 post_id 二选一）
    if 'project_id' not in cols:
        db.execute("ALTER TABLE comments ADD COLUMN project_id INTEGER DEFAULT NULL")
        added.append('project_id')
    # 评论邮箱通知：存评论者明文邮箱（仅用于发送回复通知，不出现在任何页面）
    if 'email' not in cols:
        db.execute("ALTER TABLE comments ADD COLUMN email TEXT DEFAULT ''")
        added.append('email')
    # 评论 IP 归属地：原始 IP + 归属地（省份），归属地由后台线程查询后回填
    if 'ip_text' not in cols:
        db.execute("ALTER TABLE comments ADD COLUMN ip_text TEXT DEFAULT ''")
        added.append('ip_text')
    if 'ip_location' not in cols:
        db.execute("ALTER TABLE comments ADD COLUMN ip_location TEXT DEFAULT ''")
        added.append('ip_location')
    if 'qq' not in cols:
        db.execute("ALTER TABLE comments ADD COLUMN qq TEXT DEFAULT ''")
        added.append('qq')
    db.execute("UPDATE comments SET status='approved' WHERE status IS NULL OR status=''")
    if added:
        print('[迁移] comments 表新增列：' + ', '.join(added))


def migrate_from_json(db):
    count = db.execute("SELECT COUNT(*) as c FROM posts").fetchone()['c']
    if count > 0:
        return
    if not os.path.exists(DATA_FILE):
        return

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        old_posts = json.load(f)

    migrated = 0
    for p in old_posts:
        slug = p.get('slug', '')
        filename = p.get('filename', '')
        content = ''
        if filename:
            filepath = os.path.join(POSTS_DIR, filename)
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
        try:
            db.execute(
                """INSERT OR IGNORE INTO posts
                   (title, slug, content, excerpt, tags, read_time, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'published', ?, ?)""",
                (p.get('title', ''), slug, content, p.get('excerpt', ''),
                 json.dumps(p.get('tags', []), ensure_ascii=False),
                 p.get('read_time', 3),
                 p.get('date', datetime.now().strftime('%Y-%m-%d')),
                 p.get('date', datetime.now().strftime('%Y-%m-%d')))
            )
            migrated += 1
        except sqlite3.IntegrityError:
            pass
    db.commit()
    print(f'[迁移] 已从 JSON 导入 {migrated} 篇文章')


init_db()


def migrate_uploads():
    """上传目录迁移（v1.0.6+）：static/uploads → 根目录 uploads/。

    1. 移动旧目录文件到新目录（目标已存在时合并，同名跳过）；
    2. 将数据库中所有已存储的 /static/uploads/ URL 批量替换为 /uploads/。
    幂等：旧目录不存在时直接跳过。
    """
    old_dir = OLD_UPLOAD_DIR
    new_dir = UPLOAD_DIR
    if not os.path.isdir(old_dir):
        return  # 全新安装或已迁移
    print('[迁移] 上传目录 static/uploads → uploads')
    # 1. 文件迁移
    if os.path.isdir(new_dir):
        for root, dirs, files in os.walk(old_dir):
            rel = os.path.relpath(root, old_dir)
            target_root = os.path.join(new_dir, rel) if rel != '.' else new_dir
            os.makedirs(target_root, exist_ok=True)
            for fn in files:
                src = os.path.join(root, fn)
                dst = os.path.join(target_root, fn)
                if not os.path.exists(dst):
                    shutil.move(src, dst)
        shutil.rmtree(old_dir, ignore_errors=True)
    else:
        shutil.move(old_dir, new_dir)
    # 2. 数据库 URL 替换：/static/uploads/ → /uploads/
    db = get_db()
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    changed = 0
    old_prefix, new_prefix = '/static/uploads/', '/uploads/'
    for t in tables:
        cols = [r[1] for r in db.execute('PRAGMA table_info("%s")' % t).fetchall()]
        for c in cols:
            cur = db.execute('SELECT "%s" FROM "%s" WHERE instr("%s", ?) > 0' % (c, t, c), (old_prefix,))
            for row in cur.fetchall():
                val = row[0]
                if val and old_prefix in val:
                    db.execute('UPDATE "%s" SET "%s" = ? WHERE "%s" = ?' % (t, c, c),
                               (val.replace(old_prefix, new_prefix), val))
                    changed += 1
    db.commit()
    db.close()
    print(f'[迁移] 已替换 {changed} 处旧上传 URL')


migrate_uploads()

# ─────────────── 工具函数 ───────────────

def load_settings():
    """每请求最早阶段把 settings 表加载进 app.config。
    请求内复用 g 连接（每请求仅开 1 个）；非请求上下文（启动期 L1383、守护线程）走独立连接。"""
    in_request = has_request_context()
    db = _request_db()
    try:
        rows = db.execute("SELECT key, value FROM settings").fetchall()
    finally:
        if not in_request:
            db.close()
    keys = set()
    for row in rows:
        app.config[row['key']] = row['value']
        keys.add(row['key'])
    # 主题设置已从库中移除时回退内置默认主题，避免残留旧值导致无法还原
    if 'active_theme' not in keys:
        app.config.pop('active_theme', None)


# ─────────────── 服务时效 / Server Status ───────────────
# 云资源到期时间查询（阿里云轻量 / 腾讯云域名）+ HTTP(S) 服务可达性监控。
# - 云到期时间：密钥签名调用 OpenAPI，失败自动回退后台手动填写的到期日。
# - 服务监控：守护线程每 5 分钟轮询，结果写入 service_checks 表，前台读聚合。

def _clean_monitor_url(url):
    """清洗监控 URL：去首尾空白与反引号，并禁止内网/回环地址（防 SSRF）。"""
    if not url:
        return ''
    s = str(url).strip()
    if s.startswith('`') and s.endswith('`') and len(s) >= 2:
        s = s[1:-1].strip()
    # 禁止内网/回环地址（防 SSRF）
    try:
        parsed = urllib.parse.urlparse(s)
        hostname = parsed.hostname or ''
        if hostname:
            ip = ipaddress.ip_address(hostname)
            if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
                return ''
    except ValueError:
        pass  # 域名不做 IP 检查，由后续探测决定
    return s


def _parse_monitor_services():
    """解析 settings 中 monitor_services 的 JSON，返回非空 URL 的服务字典列表（URL 已清洗）。"""
    raw = app.config.get('monitor_services', '[]')
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            out = []
            for s in data:
                if isinstance(s, dict):
                    u = _clean_monitor_url(s.get('url') or '')
                    if u:
                        out.append({'name': (s.get('name') or u).strip() or u, 'url': u})
            return out
    except (ValueError, TypeError):
        pass
    return []


def _normalize_expiry(raw):
    """将云 API / 手动输入的到期时间归一为 YYYY-MM-DD，失败返回 None。
    支持：YYYY-MM-DD / YYYY-MM-DD HH:MM:SS / ISO8601（含 Z、+08:00 等时区、
    可带毫秒）/ 纯数字时间戳（秒或毫秒）。"""
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # 纯数字时间戳（秒或毫秒）
    if s.lstrip('-').isdigit():
        ts = int(s)
        if ts > 1e12:
            ts //= 1000
        try:
            return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()
        except Exception:
            return None
    # 带时区 / 毫秒的 ISO8601（含结尾 Z）；保留原时区下的日期，
    # 不转 UTC，避免跨时区日期差一天（Z 值日期与字符串截断行为一致）
    try:
        dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
        return dt.date().isoformat()
    except ValueError:
        pass
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


_NO_PROXY_OPENER = None
_NO_VERIFY_OPENER = None


def _open_url(req, timeout):
    """urlopen 封装：① 禁用系统代理直连（云 API/监控目标为国内直连域名，
    避免系统代理残留导致 WinError 10061）；② 证书校验失败时回退为不校验。

    注意：OpenerDirector.open() 不接受 context 参数，不校验证书须用
    HTTPSHandler(context=...) 单独构造 opener（顶层 urlopen 才有 context）。
    """
    global _NO_PROXY_OPENER, _NO_VERIFY_OPENER
    if _NO_PROXY_OPENER is None:
        _NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        return _NO_PROXY_OPENER.open(req, timeout=timeout)
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLError):
            if _NO_VERIFY_OPENER is None:
                _NO_VERIFY_OPENER = urllib.request.build_opener(
                    urllib.request.ProxyHandler({}),
                    urllib.request.HTTPSHandler(
                        context=ssl._create_unverified_context()))
            return _NO_VERIFY_OPENER.open(req, timeout=timeout)
        raise


def _http_get_json(url, headers=None, timeout=8):
    """GET 请求并解析 JSON；失败抛出异常由调用方兜底。"""
    req = urllib.request.Request(url, headers=headers or {})
    with _open_url(req, timeout) as resp:
        raw = resp.read().decode('utf-8')
    return json.loads(raw) if raw else {}


def _rfc3986(s):
    """阿里云 RPC 签名使用的 RFC3986 编码：字母数字与 -_.~ 不编码，其余百分号大写。"""
    return urllib.parse.quote(str(s), safe='-_.~')


def _aliyun_expiry():
    """查询阿里云轻量应用服务器到期时间（RPC 风格 HMAC-SHA1 签名，ListInstances）。
    返回 (日期 YYYY-MM-DD 或 None, 错误说明或 None)。"""
    ak = (app.config.get('aliyun_access_key') or '').strip()
    sk = (app.config.get('aliyun_access_secret') or '').strip()
    region = (app.config.get('aliyun_region') or 'cn-hangzhou').strip() or 'cn-hangzhou'
    if not ak or not sk:
        return None, '未配置阿里云 AccessKey'

    def _do_request(_params):
        """RPC 签名并发送 GET 请求，返回解析后的 JSON。"""
        canonical = '&'.join('%s=%s' % (k, _rfc3986(_params[k])) for k in sorted(_params))
        string_to_sign = 'GET&%2F&' + _rfc3986(canonical)
        signature = base64.b64encode(
            hmac.new((sk + '&').encode('utf-8'), string_to_sign.encode('utf-8'),
                     hashlib.sha1).digest()).decode('utf-8')
        _params['Signature'] = signature
        # 阿里云 endpoint 为带地域的 {产品}.{region}.aliyuncs.com（swas / ecs 通用）
        url = 'https://%s/?' % (host_fmt % region) + urllib.parse.urlencode(_params)
        return _http_get_json(url)

    params = {
        'AccessKeyId': ak,
        'Format': 'JSON',
        'RegionId': region,
        'SignatureMethod': 'HMAC-SHA1',
        'SignatureNonce': str(uuid.uuid4()),
        'SignatureVersion': '1.0',
        'Timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'PageSize': '100',
    }
    # 服务器类型：swas=轻量应用服务器 / ecs=云服务器 ECS，二者 API 属不同产品
    srv_type = (app.config.get('aliyun_server_type') or 'swas').strip().lower()
    if srv_type == 'ecs':
        # ECS：DescribeInstances，endpoint ecs.{region}.aliyuncs.com，
        # JSON 返回结构为 data.Instances.Instance[]
        params['Action'] = 'DescribeInstances'
        params['Version'] = '2014-05-26'
        host_fmt = 'ecs.%s.aliyuncs.com'
        instances_of = lambda d: (d.get('Instances') or {}).get('Instance') or []
    else:
        # 轻量应用服务器：ListInstances，endpoint swas.{region}.aliyuncs.com
        params['Action'] = 'ListInstances'
        params['Version'] = '2020-06-01'
        host_fmt = 'swas.%s.aliyuncs.com'
        instances_of = lambda d: d.get('Instances') or []
    instance_id = (app.config.get('aliyun_instance_id') or '').strip()
    if instance_id:
        params['InstanceIds'] = json.dumps([instance_id])
    try:
        data = _do_request(params)
    except urllib.error.HTTPError as e:
        return None, 'HTTP %d' % e.code
    except Exception as e:
        return None, '请求阿里云 API 失败（%s）' % str(e)[:100]
    if 'Code' in data:
        return None, '%s: %s' % (data.get('Code'), data.get('Message', ''))
    instances = instances_of(data)
    # 按 InstanceIds 过滤未命中时，去掉过滤条件全量重查一次（可能是实例 ID 填写有误）
    if not instances and instance_id:
        try:
            alt = dict(params)
            alt.pop('InstanceIds', None)
            alt['SignatureNonce'] = str(uuid.uuid4())
            alt['Timestamp'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            data = _do_request(alt)
            if 'Code' not in data:
                instances = instances_of(data)
        except Exception:
            instances = []
    if not instances:
        return None, '当前地域 %s 未查询到%s实例，请检查地域（RegionId）或实例 ID 配置' % (
            region, '轻量' if srv_type != 'ecs' else 'ECS')
    charge = 'PrePaid'
    for inst in instances:
        # ECS 实例计费方式：PrePaid=包年包月 / PostPaid=按量付费
        charge = inst.get('InstanceChargeType') or charge
        expiry = _normalize_expiry(inst.get('ExpiredTime'))
        if expiry:
            return expiry, None
    if srv_type == 'ecs':
        if charge == 'PostPaid':
            return None, '查询到 ECS 实例，但为按量付费（PostPaid）实例，无到期时间；' \
                          '到期提醒仅适用于包年包月实例'
        # 包年包月但解析失败：附带第一个实例的原始到期时间值，便于排查格式问题
        detail = ''
        if instances:
            inst = instances[0]
            detail = '（ExpiredTime 原始值: %r；InstanceId: %s；计费: %s）' % (
                inst.get('ExpiredTime'), inst.get('InstanceId', '?'), charge)
        return None, '实例未返回到期时间（ExpiredTime 字段）' + detail
    return None, '实例未返回到期时间（ExpiredTime 字段）'


def _tencent_expiry():
    """查询腾讯云域名到期时间（TC3-HMAC-SHA256 签名，DescribeDomainBaseInfo）。
    返回 (日期 YYYY-MM-DD 或 None, 错误说明或 None)。"""
    sid = (app.config.get('tencent_secret_id') or '').strip()
    sk = (app.config.get('tencent_secret_key') or '').strip()
    domain = (app.config.get('tencent_domain') or '').strip()
    if not sid or not sk:
        return None, '未配置腾讯云 SecretId/SecretKey'
    if not domain:
        return None, '请在后台填写腾讯云域名（如 example.com）'
    host = 'domain.tencentcloudapi.com'
    service = 'domain'
    ts = int(time.time())
    date = datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%d')
    # GET 请求：业务参数 Domain 放 query 并参与签名；请求体为空串
    canonical_query = 'Domain=%s' % urllib.parse.quote(domain, safe='')
    payload = ''
    hashed_payload = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    canonical_headers = 'content-type:application/x-www-form-urlencoded\nhost:%s\n' % host
    signed_headers = 'content-type;host'
    canonical_request = 'GET\n/\n%s\n%s\n%s\n%s' % (
        canonical_query, canonical_headers, signed_headers, hashed_payload)
    string_to_sign = 'TC3-HMAC-SHA256\n%d\n%s/%s/tc3_request\n%s' % (
        ts, date, service,
        hashlib.sha256(canonical_request.encode('utf-8')).hexdigest())
    # 重要：TC3 第一层签名密钥必须加 'TC3' 前缀（腾讯云官方 SDK 同款算法），
    # 否则真实密钥必报 AuthFailure.SignatureFailure
    secret_date = hmac.new(('TC3' + sk).encode('utf-8'), date.encode('utf-8'),
                           hashlib.sha256).digest()
    secret_service = hmac.new(secret_date, service.encode('utf-8'), hashlib.sha256).digest()
    secret_signing = hmac.new(secret_service, b'tc3_request', hashlib.sha256).digest()
    signature = hmac.new(secret_signing, string_to_sign.encode('utf-8'),
                         hashlib.sha256).hexdigest()
    authorization = ('TC3-HMAC-SHA256 Credential=%s/%s/%s/tc3_request, '
                     'SignedHeaders=%s, Signature=%s') % (
        sid, date, service, signed_headers, signature)
    headers = {
        'Authorization': authorization,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Host': host,
        'X-TC-Action': 'DescribeDomainBaseInfo',
        'X-TC-Timestamp': str(ts),
        'X-TC-Version': '2018-08-08',
    }
    try:
        data = _http_get_json('https://%s/?%s' % (host, canonical_query), headers=headers)
    except urllib.error.HTTPError as e:
        return None, 'HTTP %d' % e.code
    except Exception as e:
        return None, '请求腾讯云 API 失败（%s）' % str(e)[:100]
    if data.get('Response', {}).get('Error'):
        err = data['Response']['Error']
        code = err.get('Code', '')
        msg = err.get('Message', '')
        if code == 'AuthFailure.SignatureFailure':
            return None, '签名校验失败：请确认 SecretId 与 SecretKey 为同一对密钥'
        return None, '%s: %s' % (code, msg)
    info = data.get('Response', {}).get('DomainInfo') or {}
    expiry = _normalize_expiry(info.get('ExpirationDate'))
    if not expiry:
        return None, '未查询到域名到期时间（ExpirationDate 原始值: %r）' % (
            info.get('ExpirationDate'),)
    return expiry, None


# 云 API 到期时间缓存：页面访问（/status、/api/status、后台）只读
# 内存缓存 + 持久化的测试结果，绝不主动请求云 API；仅后台「测试连接」
# 按钮（force=True）才真正调用云 API 并持久化成功结果。
EXPIRY_CACHE = {'ts': 0, 'data': None}
EXPIRY_CACHE_TTL = 3600


def _fmt_ts(ts):
    """unix 秒 -> 'YYYY-MM-DD HH:MM'，用于提示上次「测试连接」的时间。"""
    try:
        return datetime.fromtimestamp(int(ts)).strftime('%Y-%m-%d %H:%M')
    except (ValueError, TypeError, OSError):
        return ts or ''


def get_expiry_info(force=False):
    """聚合云资源到期信息（含持久化的 API 测试结果与手动兜底）。
    页面访问只读内存缓存与持久化结果；仅 force=True（后台「测试连接」）
    才重新查询云 API 并持久化成功结果。"""
    now = time.time()
    if (not force and EXPIRY_CACHE['data'] is not None
            and now - EXPIRY_CACHE['ts'] < EXPIRY_CACHE_TTL):
        return EXPIRY_CACHE['data']
    result = {}
    aliyun_type = (app.config.get('aliyun_server_type') or 'swas').strip().lower()
    fetchers = {'aliyun': _aliyun_expiry, 'tencent': _tencent_expiry}
    for key, label in (
        ('aliyun', '阿里云 ECS 服务器' if aliyun_type == 'ecs' else '阿里云轻量服务器'),
        ('tencent', '腾讯云域名'),
    ):
        expiry, source, note = None, 'manual', '手动填写'
        if force:
            # 仅后台「测试连接」触发时真正调用云 API；失败保留错误提示
            try:
                api_date, err = fetchers[key]()
                if api_date:
                    expiry, source, note = api_date, 'api', 'API 自动同步'
                else:
                    note = err or '未查询到到期时间'
            except Exception as e:
                note = 'API 查询异常：%s' % e
        else:
            # 页面访问：只读上次「测试连接」持久化的结果（进程重启也不丢）
            api_date = _normalize_expiry(app.config.get('%s_expiry_api' % key) or '')
            if api_date:
                expiry, source = api_date, 'api'
                ts_val = (app.config.get('%s_expiry_api_ts' % key) or '').strip()
                note = 'API 同步（测试于 %s）' % _fmt_ts(ts_val) if ts_val else 'API 自动同步'
            if not expiry:
                manual = (app.config.get('expiry_%s' % key) or '').strip()
                if manual and _normalize_expiry(manual):
                    expiry, source, note = _normalize_expiry(manual), 'manual', '手动填写'
                else:
                    note = '未配置'
        days, status = None, 'none'
        if expiry:
            try:
                d = datetime.strptime(expiry, '%Y-%m-%d').date()
                days = (d - datetime.now().date()).days
                status = 'ok' if days > 30 else ('warn' if days > 0 else 'expired')
            except ValueError:
                pass
        result[key] = {
            'label': label, 'expiry': expiry, 'days': days,
            'status': status, 'source': source, 'note': note,
            'server_type': ('云服务器 ECS' if aliyun_type == 'ecs'
                            else '轻量应用服务器') if key == 'aliyun' else None,
        }
    EXPIRY_CACHE['ts'] = now
    EXPIRY_CACHE['data'] = result
    return result


# ── HTTP(S) 服务探测 ──

MONITOR_INTERVAL = 300  # 探测间隔（秒）：5 分钟
MONITOR_LOCK = threading.Lock()


def _is_private_target(hostname):
    """本机/回环/私网/IP 字面量目标判定：这些地址没有 443 可握手取证书，
    跳过避免空等超时（如监控 http://127.0.0.1:5000 时连 :443 直接被拒）。"""
    h = (hostname or '').strip().lower()
    if not h or h == 'localhost' or h == '::1':
        return True
    try:
        ip = ipaddress.ip_address(h)
        return ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved
    except ValueError:
        return False  # 域名，可尝试握手


def _hostname_match(pattern, hn):
    """通配符主机名匹配：pattern 支持 *.example.com 形式。"""
    if pattern == hn:
        return True
    if pattern.startswith('*.'):
        suffix = pattern[1:]
        return bool(hn.endswith(suffix) and hn[:-len(suffix)])
    return False


def _cert_matches_hostname(cert, hostname):
    """校验证书 SAN/CN 是否匹配目标域名（未验证模式下防误取其他站点证书）。"""
    try:
        if not cert:
            return False
        hn = (hostname or '').lower().rstrip('.')
        names = []
        for typ, val in cert.get('subjectAltName', ()) or ():
            if typ == 'DNS':
                names.append(val.lower().rstrip('.'))
        for item in cert.get('subject', ()) or ():
            for k, v in item:
                if k == 'commonName':
                    names.append(v.lower().rstrip('.'))
        return any(_hostname_match(p, hn) for p in names)
    except Exception:
        return False


_SSL_DEFAULT_CTX = None  # 默认校验证书上下文（缓存，自动补齐系统 CA bundle）


def _default_ssl_context():
    """默认校验证书上下文；服务器缺少系统根证书（如精简系统/宝塔编译版 Python）时，
    自动探测常见 CA bundle 路径补齐，使证书校验分支可用（getpeercert() 才能返回完整字典）。"""
    global _SSL_DEFAULT_CTX
    if _SSL_DEFAULT_CTX is not None:
        return _SSL_DEFAULT_CTX
    ctx = ssl.create_default_context()
    try:
        # 已有可信根则直接用；否则逐一尝试常见 CA bundle
        if not ctx.get_ca_certs():
            import os
            for cafile in ('/etc/pki/tls/certs/ca-bundle.crt',
                           '/etc/ssl/certs/ca-certificates.crt',
                           '/etc/ssl/cert.pem',
                           '/etc/ssl/ca-bundle.pem',
                           '/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem',
                           '/usr/local/share/certs/ca-root-nss.crt',
                           '/etc/pki/tls/cacert.pem'):
                if os.path.exists(cafile):
                    try:
                        ctx.load_verify_locations(cafile=cafile)
                        break
                    except Exception:
                        continue
    except Exception:
        pass
    _SSL_DEFAULT_CTX = ctx
    return ctx


def _tlv_next(data, off):
    """读取一个 ASN.1 TLV：返回 (tag, value_bytes, next_off)。
    仅处理短/长长度编码的 BER 结构（证书 DER 内足够）。"""
    tag = data[off]
    p = off + 1
    ln = data[p]
    p += 1
    if ln & 0x80:
        n = ln & 0x7f
        ln = int.from_bytes(data[p:p + n], 'big')
        p += n
    return tag, data[p:p + ln], p + ln


def _der_fields(seq):
    """把 SEQUENCE 内容解析为 [(tag, value), ...] 字段列表。"""
    fields = []
    off = 0
    while off < len(seq):
        tag, val, off = _tlv_next(seq, off)
        fields.append((tag, val))
    return fields


def _der_not_after(der):
    """极简 ASN.1 解析：从证书 DER 提取 notAfter 为 datetime（UTC）。
    仅用于系统无根证书、CERT_NONE 握手时 getpeercert() 返回空 dict 的兜底场景。
    证书结构：Certificate{tbsCertificate{version[0]?, serial, sigalg, issuer,
    validity{notBefore, notAfter}, subject, ...}, sigalg, sig}"""
    try:
        _, cert_val, _ = _tlv_next(der, 0)       # Certificate SEQUENCE
        _, tbs_val, _ = _tlv_next(cert_val, 0)   # tbsCertificate SEQUENCE
        fields = _der_fields(tbs_val)
        idx = 1 if fields and fields[0][0] == 0xa0 else 0
        if len(fields) < idx + 4 or fields[idx + 3][0] != 0x30:
            return None
        times = _der_fields(fields[idx + 3][1])
        if len(times) < 2:
            return None
        tag, raw = times[1]
        s = raw.decode('ascii', 'replace')
        if tag == 0x17 and len(s) >= 12:  # UTCTime: YYMMDDHHMMSSZ（YY>=50 为 19xx）
            yy = int(s[0:2]) + (2000 if int(s[0:2]) < 50 else 1900)
            return datetime(yy, int(s[2:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]), int(s[10:12]), tzinfo=timezone.utc)
        if tag == 0x18 and len(s) >= 14:  # GeneralizedTime: YYYYMMDDHHMMSSZ
            return datetime(int(s[0:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]), int(s[10:12]), int(s[12:14]), tzinfo=timezone.utc)
    except Exception:
        pass
    return None


def _der_cert_names(der):
    """从证书 DER 提取 subject 的 commonName 列表（小写，去尾点）。
    用于未验证 + getpeercert() 空 dict 场景下的域名匹配，防止环回回退误取本机其他站点证书。"""
    try:
        _, cert_val, _ = _tlv_next(der, 0)       # Certificate SEQUENCE
        _, tbs_val, _ = _tlv_next(cert_val, 0)   # tbsCertificate SEQUENCE
        fields = _der_fields(tbs_val)
        idx = 1 if fields and fields[0][0] == 0xa0 else 0
        if len(fields) < idx + 5 or fields[idx + 4][0] != 0x30:
            return []
        names = []
        for tag, rdn_set in _der_fields(fields[idx + 4][1]):
            if tag != 0x31:  # SET OF RDN
                continue
            for _, atv in _der_fields(rdn_set):  # atv 已是 AttributeTypeAndValue 的 SEQUENCE 内容
                oid = None
                value = None
                for ktag, kval in _der_fields(atv):
                    if ktag == 0x06:
                        oid = kval
                    elif ktag in (0x0c, 0x13, 0x14, 0x16, 0x1b, 0x1e):  # 各种字符串类型
                        value = kval.decode('utf-8', 'replace')
                if oid == bytes([0x55, 0x04, 0x03]) and value:  # 2.5.4.3 commonName
                    names.append(value.lower().rstrip('.'))
        return names
    except Exception:
        return []


def _ssl_cert_days(hostname, port=443, timeout=5):
    """直连获取 SSL 证书剩余天数，失败返回 -1 并附原因。
    返回 (cert_days, err)，err 为 None 表示成功。

    服务器实际根因（v1.2.8 detail 定位）：服务器缺少系统 CA 根证书 →
    create_default_context() 校验必然失败（unable to get local issuer certificate）；
    回退 unverified 后 Python 在 CERT_NONE 模式下 getpeercert() 返回空 dict →
    既无 notAfter 也无 SAN，最终 -1。v1.2.9 修复：
    ① 默认上下文自动补齐常见系统 CA bundle，让校验分支可用；
    ② unverified 分支改为从 getpeercert(binary_form=True) 的 DER 极简解析
       notAfter 与 subject CN（不依赖任何私有 API），无根证书也能拿到证书天数。

    反代环境：服务器 https 反代 http://127.0.0.1:5000 并监控自己公网域名时，
    hairpin 自连会被云 VPC 丢弃 → 直连失败后追加 127.0.0.1:port 环回握手，
    TLS SNI 仍用公网域名，由本机 Nginx 按 SNI 返回对应证书；环回结果同样校验
    证书匹配该域名，防误取本机其他站点证书。"""
    if not hostname or _is_private_target(hostname):
        return -1, '私网/IP 目标不可直连取证'
    # 直连公网域名 → 失败后环回取证书（仅在域名目标下追加环回候选）
    candidates = [(hostname, port)]
    if not _is_private_target(hostname):
        candidates.append(('127.0.0.1', port))
    errs = []
    # 默认校验证书（自动补齐 CA bundle）；失败回退为仅取证书信息（不校验证书）
    for target, pp in candidates:
        for ctx in (_default_ssl_context(), ssl._create_unverified_context()):
            try:
                with socket.create_connection((target, pp), timeout=timeout) as sock:
                    with ctx.wrap_socket(sock, server_hostname=hostname) as tls:
                        cert = tls.getpeercert()
                        not_after = cert.get('notAfter') if cert else None
                        der = None
                        # 未验证模式下 getpeercert() 可能返回空 dict → 用 DER 兜底解析
                        if not not_after:
                            der = tls.getpeercert(binary_form=True) or None
                            exp = _der_not_after(der) if der else None
                            if exp is None:
                                errs.append('%s:%s 证书无 notAfter / DER 解析失败' % (target, pp))
                                continue
                        else:
                            # 用 email 标准解析（兼容 GMT 等时区名），避免 strptime %Z 在 3.12+ 解析失败
                            exp = email.utils.parsedate_to_datetime(not_after)
                            if exp is None:
                                errs.append('%s:%s notAfter 解析失败: %s' % (target, pp, not_after))
                                continue
                        # 未验证模式下确认证书确实属于该域名，防误取本机其他站点证书
                        if ctx.verify_mode == ssl.CERT_NONE:
                            if cert:
                                matched = _cert_matches_hostname(cert, hostname)
                            else:
                                matched = any(_hostname_match(n, hostname) for n in (_der_cert_names(der) if der else []))
                            if not matched:
                                errs.append('%s:%s 证书不匹配 %s（未验证回退）' % (target, pp, hostname))
                                continue
                        return (exp - datetime.now(timezone.utc)).days, None
            except Exception as e:
                errs.append('%s:%s %s: %s' % (target, pp, type(e).__name__, str(e)[:80]))
                continue
    # 去重保序，太长截断
    return -1, '; '.join(dict.fromkeys(errs))[:220] or '未知原因'


def probe_url(url, timeout=5):
    """探测单个 URL：返回 (ok, latency_ms, cert_days, detail)。"""
    url = _clean_monitor_url(url)
    if not url.startswith(('http://', 'https://')):
        return False, 0, -1, 'URL 格式错误'
    try:
        p = urllib.parse.urlparse(url)
        hostname = p.hostname
        # 按 URL 实际端口取证书：如 https://nas.infowe.site:5001/ 的证书在 5001，不能默认连 443
        port = p.port or 443
    except Exception:
        return False, 0, -1, 'URL 解析失败'
    start = time.time()
    cert_days = -1
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'infowe-status/1.0'})
        try:
            with _open_url(req, timeout) as resp:
                code = resp.getcode()
        except urllib.error.HTTPError as e:
            code = e.code
        latency = int((time.time() - start) * 1000)
        # http/https 目标统一尝试取证书天数：http 站点通常 301 到 https，443 往往有证书；
        # 取不到时 cert_days=-1，不影响探测结果，原因挂在 detail 上便于排查
        cert_days, cert_err = _ssl_cert_days(hostname, port)
        ok = 200 <= code < 400
        if cert_days < 0 and cert_err:
            return ok, latency, cert_days, 'HTTP %d | SSL:%s' % (code, cert_err)
        return ok, latency, cert_days, 'HTTP %d' % code
    except Exception as e:
        latency = int((time.time() - start) * 1000)
        return False, latency, -1, str(e)[:120]


def probe_all_services(force=False):
    """轮询全部监控服务并写入 service_checks。
    默认按 MONITOR_INTERVAL 窗口去重；force=True 时立即重探。
    探测（单服务网络超时最长 5s）不占写事务；每个服务独立小事务落库，
    避免单事务长占 SQLite 写锁导致其它写请求（后台保存/评论）长时间等待。"""
    services = _parse_monitor_services()
    if not services:
        return {}
    with MONITOR_LOCK:
        now = time.time()
        results = {}
        for svc in services:
            name = (svc.get('name') or svc.get('url') or '').strip()
            url = (svc.get('url') or '').strip()
            if not name or not url:
                continue
            if not force:
                db = get_db()
                try:
                    row = db.execute(
                        "SELECT checked_at FROM service_checks WHERE service_id=? "
                        "ORDER BY checked_at DESC LIMIT 1", (name,)).fetchone()
                finally:
                    db.close()
                if row and now - row['checked_at'] < MONITOR_INTERVAL:
                    continue
            ok, latency, cert_days, detail = probe_url(url)
            db = get_db()
            try:
                db.execute(
                    "INSERT INTO service_checks (service_id, checked_at, ok, latency_ms, cert_days, detail) "
                    "VALUES (?,?,?,?,?,?)",
                    (name, now, 1 if ok else 0, latency, cert_days, detail))
                db.commit()
            finally:
                db.close()
            results[name] = {
                'name': name, 'url': url, 'ok': ok,
                'latency_ms': latency, 'cert_days': cert_days, 'detail': detail,
            }
        # 超量记录清理（独立小事务，不长期占用写锁）
        for name in results:
            db = get_db()
            try:
                db.execute(
                    "DELETE FROM service_checks WHERE service_id=? AND id NOT IN "
                    "(SELECT id FROM service_checks WHERE service_id=? ORDER BY id DESC LIMIT 2000)",
                    (name, name))
                db.commit()
            finally:
                db.close()
    return results


def get_services_status():
    """读取各服务最新探测结果 + 近 24h 可用率，供前台 /api/status 使用。"""
    services = _parse_monitor_services()
    if not services:
        return []
    db = get_db()
    items = []
    day_ago = time.time() - 86400
    for svc in services:
        name = (svc.get('name') or svc.get('url') or '').strip()
        url = (svc.get('url') or '').strip()
        if not name or not url:
            continue
        row = db.execute(
            "SELECT ok, latency_ms, cert_days, detail, checked_at FROM service_checks "
            "WHERE service_id=? ORDER BY checked_at DESC LIMIT 1", (name,)).fetchone()
        stat = db.execute(
            "SELECT COUNT(*) AS total, SUM(ok) AS ok_count FROM service_checks "
            "WHERE service_id=? AND checked_at>=?", (name, day_ago)).fetchone()
        total = stat['total'] or 0
        ok_count = stat['ok_count'] or 0
        uptime = round(ok_count * 100.0 / total, 1) if total else None
        if row:
            items.append({
                'name': name, 'url': url,
                'ok': bool(row['ok']), 'latency_ms': row['latency_ms'],
                'cert_days': row['cert_days'], 'detail': row['detail'],
                'checked_at': row['checked_at'], 'uptime': uptime,
            })
        else:
            items.append({
                'name': name, 'url': url, 'ok': None,
                'latency_ms': None, 'cert_days': None, 'detail': '尚未探测',
                'checked_at': None, 'uptime': uptime,
            })
    db.close()
    return items


def _monitor_loop():
    """守护线程主循环：每 MONITOR_INTERVAL 秒轮询一次。"""
    while True:
        try:
            probe_all_services()
        except Exception as e:
            print('[Status] 探测线程异常：%s' % e)
        time.sleep(MONITOR_INTERVAL)


def _start_monitor_thread():
    t = threading.Thread(target=_monitor_loop, name='status-monitor', daemon=True)
    t.start()
    print('[Status] 服务监控线程已启动（每 %d 秒轮询）' % MONITOR_INTERVAL)


# 仅在真正的服务进程启动探测线程（gunicorn worker / flask 非 reloader 主进程），
# 避免 debug reloader 下主进程与子进程重复启动。
if os.environ.get('WERKZEUG_RUN_MAIN') or not app.debug:
    _start_monitor_thread()


def save_setting(key, value):
    db = get_db()
    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    db.commit()
    db.close()
    app.config[key] = value


def _parse_json_list(raw, default=None):
    """将 settings 中的 JSON 字符串解析为 Python 列表，解析失败返回 default 或空列表。"""
    if default is None:
        default = []
    if not raw:
        return default
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else default
    except (ValueError, TypeError):
        return default


load_settings()


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            # 账号密码已通过、尚在 OTP 验证中间态时，强制回到 OTP 页，避免绕过
            if session.get('_otp_user'):
                return redirect(url_for('admin_otp'))
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


def verify_password(stored_hash, password):
    # 兼容旧版 SHA-256(secret_key 拼接) 哈希，验证成功后由调用方懒迁移
    if stored_hash.startswith(('pbkdf2:', 'scrypt:', 'bcrypt:')):
        return ws.check_password_hash(stored_hash, password)
    # 旧格式：sha256((password + secret_key))
    legacy = hashlib.sha256((password + app.secret_key).encode()).hexdigest()
    return legacy == stored_hash


# ─────────────── 登录防爆破（基于 IP 的内存计数） ───────────────
# 个人博客场景足够：进程重启清零。如需持久可改存数据库/Redis。
import time
import random
_LOGIN_ATTEMPTS = {}          # ip -> {'fails': int, 'lock_until': float}
_LOGIN_MAX_FAILS = 5          # 连续失败上限
_LOGIN_LOCK_SECONDS = 15 * 60 # 锁定时长（15 分钟）
_LOGIN_BASE_DELAY = 0.5       # 基础失败延迟（秒）
_LOGIN_CAPTCHA_FAILS = 3      # 连续失败达到该次数后要求验证码


def _captcha_required(ip):
    rec = _LOGIN_ATTEMPTS.get(ip)
    return bool(rec) and rec.get('fails', 0) >= _LOGIN_CAPTCHA_FAILS


def _gen_captcha():
    # 算术验证码：生成 a + b = ?，答案与题目均存入 session（零依赖，无需图片库）
    a, b = random.randint(1, 9), random.randint(1, 9)
    session['captcha_answer'] = a + b
    session['_captcha_q'] = '%d + %d' % (a, b)
    return session['_captcha_q']


def _client_ip():
    # 经 ProxyFix 处理后，request.remote_addr 已是真实客户端 IP（取自 X-Forwarded-For 首个值）。
    # 无需再手动解析头部，避免伪造 XFF 头欺骗；直接访问本机时即为其真实连接 IP。
    return request.remote_addr or 'unknown'


# ── 评论显示 IP 归属地（省份）──
_IP_LOC_CACHE = {}
_IP_LOC_CACHE_MAX = 2000  # 缓存上限：超过后淘汰最早条目，防长期运行内存无限增长


def _fmt_loc(loc):
    """去掉行政区划后缀：重庆市→重庆、四川省→四川、广西壮族自治区→广西。"""
    if not loc:
        return ''
    for suf in ('壮族自治区', '维吾尔自治区', '回族自治区', '自治区', '特别行政区', '省', '市'):
        loc = loc.replace(suf, '')
    return loc.strip()


def _ip_location(ip):
    """在线查 IP 归属地并缓存；查不到返回 ''（前台不展示，不打扰）。"""
    if not ip or ip == 'unknown':
        return ''
    # 回环/私网 IP 不查询归属地（避免无效请求）
    try:
        _ip_obj = ipaddress.ip_address(ip)
        if _ip_obj.is_loopback or _ip_obj.is_private or _ip_obj.is_link_local:
            return ''
    except ValueError:
        pass
    if ip in _IP_LOC_CACHE:
        return _IP_LOC_CACHE[ip]
    loc = ''
    prov = city = ''
    for url in ('https://ip.useragentinfo.com/json?ip=%s' % ip,
                'https://api.vore.top/api/IPdata?ip=%s' % ip,
                'http://ip-api.com/json/%s?lang=zh-CN&fields=status,regionName,city' % ip):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0',
                                                       'Referer': 'https://ip.useragentinfo.com/'})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode('utf-8'))
            if 'province' in data:  # ip.useragentinfo.com
                prov = (data.get('province') or '').strip()
                city = (data.get('city') or '').strip()
            elif (data.get('data') or {}).get('province') is not None:  # api.vore.top
                d = data.get('data') or {}
                prov = (d.get('province') or '').strip()
                city = (d.get('city') or '').strip()
            elif data.get('status') == 'success':  # ip-api.com（备用，仅 IPv4）
                prov = (data.get('regionName') or '').strip()
                city = (data.get('city') or '').strip()
            prov = _fmt_loc(prov)
            city = _fmt_loc(city)
            if prov:
                loc = prov if (prov == city or not city) else ('%s %s' % (prov, city))
                break
        except Exception:
            continue
    # 容量上限控制：dict 保持插入序，超限时淘汰最早一条（dict.popitem(last=False)）
    if len(_IP_LOC_CACHE) >= _IP_LOC_CACHE_MAX:
        try:
            _IP_LOC_CACHE.popitem(last=False)
        except (KeyError, StopIteration):
            pass
    _IP_LOC_CACHE[ip] = loc
    return loc


def _fill_ip_location(cid, ip):
    """后台线程：查询归属地后回填评论；失败静默（前台不展示归属地即可）。"""
    try:
        loc = _ip_location(ip)
        if not loc:
            return
        db = get_db()
        db.execute("UPDATE comments SET ip_location=? WHERE id=?", (loc, cid))
        db.commit()
        db.close()
    except Exception:
        pass


def _login_blocked(ip):
    rec = _LOGIN_ATTEMPTS.get(ip)
    if not rec:
        return False
    if rec.get('lock_until', 0) > time.time():
        return True
    return False


def _prune_login_attempts():
    """清理过期的登录失败记录，防止内存被爆破日志撑爆。
    逻辑：解锁已超过 1 天的记录直接删除；总量超过上限（异常 flood）时整表重置。"""
    now = time.time()
    stale = [k for k, rec in _LOGIN_ATTEMPTS.items()
             if rec.get('lock_until', 0) < now - 86400]
    for k in stale:
        _LOGIN_ATTEMPTS.pop(k, None)
    if len(_LOGIN_ATTEMPTS) > 2000:
        _LOGIN_ATTEMPTS.clear()


def _register_fail(ip):
    _prune_login_attempts()  # 写入前先清理，控制无界增长
    rec = _LOGIN_ATTEMPTS.get(ip) or {'fails': 0, 'lock_until': 0}
    rec['fails'] += 1
    # 递增失败延迟：0.5s, 1s, 2s, 4s ...
    delay = _LOGIN_BASE_DELAY * (2 ** min(rec['fails'] - 1, 5))
    if rec['fails'] >= _LOGIN_MAX_FAILS:
        rec['lock_until'] = time.time() + _LOGIN_LOCK_SECONDS
    _LOGIN_ATTEMPTS[ip] = rec
    time.sleep(min(delay, 16))  # 每次失败都延迟，拖慢爆破


def _register_success(ip):
    _LOGIN_ATTEMPTS.pop(ip, None)


# ─────────────── OTP 双重验证（TOTP，RFC 6238，零外部依赖）───────────────
# 标准 TOTP：HMAC-SHA1 + 6 位 + 30 秒步长，与 Google Authenticator / 1Password / Authy 等通用。
# 密钥以无填充的 base32 存 settings 表（与 smtp_pass / github_token 同策略）；恢复码只存哈希。
_OTP_STEP = 30              # 30 秒一个时间窗口
_OTP_DIGITS = 6             # 6 位验证码
_OTP_WINDOW = 1             # 前后各容差 1 步，抗设备时钟漂移
_OTP_RECOVERY_N = 10        # 启用 OTP 时生成的恢复码数量
_OTP_RECOVERY_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # 去掉易混淆的 0/O/1/I
_OTP_EMERGENCY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', '.otp_disable')


def _b32_pad(raw):
    """base32 密钥存储时不带 '=' 填充，读取时按需补齐。"""
    raw = (raw or '').strip().upper()
    return raw + '=' * ((8 - len(raw) % 8) % 8)


def _otp_secret():
    return (app.config.get('otp_secret') or '').strip()


def _otp_emergency_off():
    """是否存在 OTP 紧急禁用标记文件。部署者可在服务器上执行 `touch data/.otp_disable`
    临时跳过 OTP 验证（兜底自救），登录后到设置页「清除标记」恢复。"""
    return os.path.isfile(_OTP_EMERGENCY_FILE)


def _otp_configured():
    """用户是否在设置中打开了 OTP 开关。"""
    return (app.config.get('otp_enabled', '0') or '').strip() in ('1', 'on', 'true', 'yes')


def _otp_enabled():
    """OTP 是否实际生效：开关打开、已绑定密钥，且不存在紧急禁用标记。"""
    if _otp_emergency_off():
        return False
    return _otp_configured() and bool(_otp_secret())


def _totp_code(secret_b32, t=None):
    """RFC 6238 TOTP 计算：HMAC-SHA1(counter) 动态截断出 6 位码。"""
    key = base64.b32decode(_b32_pad(secret_b32))
    now = int(time.time()) if t is None else int(t)
    counter = struct.pack('>Q', now // _OTP_STEP)
    mac = hmac.new(key, counter, hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack('>I', mac[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** _OTP_DIGITS)
    return '%0*d' % (_OTP_DIGITS, code)


def _totp_verify(secret_b32, code):
    """校验用户输入的 6 位验证码，允许前后各 _OTP_WINDOW 步的时间窗口。"""
    code = (code or '').strip().replace(' ', '')
    if not (code.isdigit() and len(code) == _OTP_DIGITS):
        return False
    now = int(time.time())
    for i in range(-_OTP_WINDOW, _OTP_WINDOW + 1):
        if hmac.compare_digest(_totp_code(secret_b32, now + i * _OTP_STEP), code):
            return True
    return False


def _otpauth_uri(secret_b32, username):
    """生成 otpauth:// URI，供验证器扫码绑定。"""
    issuer = (app.config.get('blog_name') or 'infowe').strip()
    acct = username or 'admin'
    return ('otpauth://totp/%s:%s?secret=%s&issuer=%s&algorithm=SHA1&digits=%d&period=%d'
            % (urllib.parse.quote(issuer), urllib.parse.quote(acct), secret_b32,
               urllib.parse.quote(issuer), _OTP_DIGITS, _OTP_STEP))


def _gen_recovery_codes(n=_OTP_RECOVERY_N):
    """生成 n 个 8 位恢复码，返回 (明文列表, sha256 哈希列表)。
    明文仅生成时展示这一次，数据库只存哈希，用于校验时一次性消费。"""
    rng = random.SystemRandom()
    seen = set()
    while len(seen) < n:
        seen.add(''.join(rng.choice(_OTP_RECOVERY_ALPHABET) for _ in range(8)))
    codes = list(seen)
    hashes = [hashlib.sha256(c.encode()).hexdigest() for c in codes]
    return codes, hashes


def _norm_recovery(code):
    """恢复码归一化：去分隔符/空白并转大写（兼容 XXXX-XXXX / XXXXXXXX / 夹空格三种输入）。"""
    return (code or '').strip().upper().replace('-', '').replace(' ', '')


def _otp_recovery_remaining():
    """当前剩余未使用的恢复码数量。"""
    cur = app.config.get('otp_recovery_codes') or ''
    try:
        lst = json.loads(cur) if cur else []
    except (ValueError, TypeError):
        lst = []
    return len(lst) if isinstance(lst, list) else 0


def _consume_recovery(code):
    """校验并一次性消费一个恢复码；成功返回 True。哈希比对通过后从库中移除。"""
    norm = _norm_recovery(code)
    if len(norm) != 8:
        return False
    digest = hashlib.sha256(norm.encode()).hexdigest()
    cur = app.config.get('otp_recovery_codes') or ''
    try:
        hashes = json.loads(cur) if cur else []
    except (ValueError, TypeError):
        hashes = []
    if not isinstance(hashes, list) or digest not in hashes:
        return False
    hashes = [h for h in hashes if h != digest]
    payload = json.dumps(hashes)
    db = get_db()
    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ('otp_recovery_codes', payload))
    db.commit()
    db.close()
    app.config['otp_recovery_codes'] = payload
    return True


def _otp_new_secret():
    """生成新的 base32 密钥（160bit，标准字符集 A-Z2-7，无填充）。"""
    return base64.b32encode(os.urandom(20)).decode().rstrip('=')




def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows):
    return [dict(r) for r in rows]


# ─────────────── 文章数据层 ───────────────

def db_load_posts(status='published', tag=None, search=None, year=None, page=1, per_page=PAGE_SIZE):
    db = get_db()
    conditions = []
    params = []

    if status:
        conditions.append("status=?")
        params.append(status)
    if tag:
        conditions.append("tags LIKE ?")
        params.append(f'%"{tag}"%')
    if search:
        conditions.append("(title LIKE ? OR content LIKE ? OR excerpt LIKE ?)")
        s = f'%{search}%'
        params.extend([s, s, s])
    if year:
        conditions.append("substr(created_at, 1, 4) = ?")
        params.append(year)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    # 总数
    count_row = db.execute(f"SELECT COUNT(*) as c FROM posts {where}", params).fetchone()
    total = count_row['c'] if count_row else 0

    # 分页
    offset = (page - 1) * per_page
    rows = db.execute(
        f"SELECT * FROM posts {where} ORDER BY is_featured DESC, created_at DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    posts = []
    for r in rows:
        p = dict(r)
        p['tags'] = json.loads(p['tags'])
        posts.append(p)

    db.close()
    return posts, total


def db_get_all_years():
    """获取所有已发布文章的年份集合（降序）"""
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT substr(created_at, 1, 4) as year "
        "FROM posts WHERE status='published' ORDER BY year DESC"
    ).fetchall()
    db.close()
    return [r['year'] for r in rows]


def db_get_post(slug):
    db = get_db()
    row = db.execute("SELECT * FROM posts WHERE slug=?", (slug,)).fetchone()
    db.close()
    if row:
        p = dict(row)
        p['tags'] = json.loads(p['tags'])
        return p
    return None


def db_get_post_by_id(post_id):
    db = get_db()
    row = db.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    db.close()
    if row:
        p = dict(row)
        p['tags'] = json.loads(p['tags'])
        return p
    return None


def db_get_related_posts(current_id, tags, limit=3):
    """获取相关文章"""
    db = get_db()
    results = []
    for tag in tags:
        rows = db.execute(
            "SELECT * FROM posts WHERE status='published' AND id!=? AND tags LIKE ? ORDER BY created_at DESC LIMIT ?",
            (current_id, f'%"{tag}"%', limit)
        ).fetchall()
        for r in rows:
            p = dict(r)
            p['tags'] = json.loads(p['tags'])
            if p['id'] not in [x['id'] for x in results]:
                results.append(p)
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
    db.close()
    return results[:limit]


def db_get_featured_posts(limit=3):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM posts WHERE status='published' AND is_featured=1 ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    posts = []
    for r in rows:
        p = dict(r)
        p['tags'] = json.loads(p['tags'])
        posts.append(p)
    db.close()
    return posts


def db_load_home_posts(limit=6, exclude_featured=False):
    """首页文章：默认精选置顶其次最新；exclude_featured=True 时仅取普通文章（精选改由独立区展示）"""
    db = get_db()
    featured_rows = db.execute(
        "SELECT * FROM posts WHERE status='published' AND is_featured=1 ORDER BY created_at DESC"
    ).fetchall()
    featured_ids = [r['id'] for r in featured_rows]
    if exclude_featured:
        # 主列表仅普通文章：首页 featured 已独立卡展示，避免同一篇重复出现
        if featured_ids:
            placeholders = ','.join('?' * len(featured_ids))
            latest_rows = db.execute(
                f"SELECT * FROM posts WHERE status='published' AND id NOT IN ({placeholders}) ORDER BY created_at DESC LIMIT ?",
                featured_ids + [limit]
            ).fetchall()
        else:
            latest_rows = db.execute(
                "SELECT * FROM posts WHERE status='published' ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        rows = latest_rows
    else:
        if featured_ids:
            placeholders = ','.join('?' * len(featured_ids))
            latest_rows = db.execute(
                f"SELECT * FROM posts WHERE status='published' AND id NOT IN ({placeholders}) ORDER BY created_at DESC",
                featured_ids
            ).fetchall()
        else:
            latest_rows = db.execute(
                "SELECT * FROM posts WHERE status='published' ORDER BY created_at DESC"
            ).fetchall()
        rows = list(featured_rows) + list(latest_rows)
    db.close()
    posts = []
    for r in rows[:limit]:
        p = dict(r)
        p['tags'] = json.loads(p['tags'])
        posts.append(p)
    return posts


def db_get_all_tags():
    """获取所有文章的标签集合（含草稿，去重，按频率排序）。
    请求内复用 g 连接（每请求 1 个连接），非请求上下文走独立连接。"""
    in_request = has_request_context()
    db = _request_db()
    try:
        rows = db.execute("SELECT tags FROM posts").fetchall()
    finally:
        if not in_request:
            db.close()
    tag_counts = {}
    for r in rows:
        for tag in json.loads(r['tags']):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    return dict(sorted(tag_counts.items(), key=lambda x: x[1], reverse=True))


def db_get_stats():
    db = get_db()
    total = db.execute("SELECT COUNT(*) as c FROM posts").fetchone()['c']
    published = db.execute("SELECT COUNT(*) as c FROM posts WHERE status='published'").fetchone()['c']
    drafts = db.execute("SELECT COUNT(*) as c FROM posts WHERE status='draft'").fetchone()['c']
    project_count = db.execute("SELECT COUNT(*) as c FROM projects").fetchone()['c']
    link_count = db.execute("SELECT COUNT(*) as c FROM links WHERE status='approved'").fetchone()['c']
    db.close()
    return {
        'total': total, 'published': published, 'drafts': drafts,
        'projects': project_count, 'links': link_count
    }


def _toc_slugify(value, separator):
    """自定义 slugify：保留中文，用于生成与 Markdown 锚点链接一致的标题 ID。"""
    value = value.lower().strip()
    value = re.sub(r'[^\w\u4e00-\u9fff]+', separator, value)
    return re.sub(r'-+', separator, value).strip(separator)


def normalize_auto_links(content):
    """把 Markdown 自动链接 <https://...> 规范化为标准链接 [URL](URL)。
    Vditor 编辑往返会丢弃 <URL> 写法，标准链接则稳定不丢。"""
    return re.sub(r'<(https?://[^>\s]+)>', r'[\1](\1)', content)


def render_post_content(content):
    """渲染 Markdown，返回 (html, toc_html)。toc 为空字符串表示无目录。"""
    if not content:
        return '', ''
    content = re.sub(r'^---.*?---\s*', '', content, flags=re.DOTALL)
    # 兜底：历史数据中的自动链接 <URL> 规范化为标准链接（避免 Vditor 编辑往返丢失）
    content = normalize_auto_links(content)
    # Markdown 任务列表 [ ] / [x] -> 带样式的勾选符号
    content = content.replace('[x]', '<i class="ck ck-done">☑</i> ').replace('[ ]', '<i class="ck ck-todo">☐</i> ')
    md = markdown.Markdown(
        extensions=['fenced_code', 'tables', 'nl2br', 'sane_lists', 'toc', 'footnotes', 'attr_list', 'def_list', 'admonition', 'md_in_html'],
        extension_configs={'toc': {'slugify': _toc_slugify, 'toc_depth': '2-6'}},
        output_format='html'
    )
    html = md.convert(content)
    toc = md.toc
    if '<li>' not in toc:
        toc = ''
    # 图片性能优化：懒加载 + 异步解码 + 自动填充空 alt（消除 CLS）
    # 首图特殊处理：微信等分享爬虫从页面首张 <img> 取卡片图，
    # 注入真实 width/height（无尺寸图可能被跳过）且禁用 lazy，避免爬虫抓不到
    _img_seen = [False]

    def _img_repl(m):
        tag = m.group(0)
        if 'loading=' in tag:
            return tag
        src = re.search(r'src="([^"]+)"', tag)
        alt = re.search(r'alt="([^"]*)"', tag)
        # 优先保留 markdown 写的 alt 描述，空 alt 时用文件名兜底
        if alt and alt.group(1):
            alt_text = alt.group(1)
        else:
            alt_text = os.path.basename(src.group(1)) if src else ''
        # 移除已有 alt 属性（避免重复 alt="x" alt=""）
        tag = re.sub(r'\s+alt="[^"]*"', '', tag)
        is_first = not _img_seen[0]
        _img_seen[0] = True
        if is_first:
            extra = ' decoding="async"'
            if src and src.group(1).startswith('/uploads/'):
                dims = _upload_image_dims(urllib.parse.unquote(src.group(1)))
                if dims:
                    extra += f' width="{dims[0]}" height="{dims[1]}"'
        else:
            extra = ' loading="lazy" decoding="async"'
        return tag.replace('<img', f'<img{extra} alt="{alt_text}"', 1)
    html = re.sub(r'<img\b[^>]*>', _img_repl, html)
    # 超链接新窗口打开，但页内锚点（href 以 # 开头）除外，过滤 javascript: 协议
    def _a_repl(m):
        tag = m.group(0)
        if re.search(r'href="#', tag):
            return tag  # 页内定位锚点，当前窗口跳转
        if re.search(r'href\s*=\s*["\']\s*javascript:', tag, re.I):
            # 危险伪协议：href 整体置为 #，彻底移除可执行内容（仅加 rel 挡不住 XSS）
            return re.sub(r'href\s*=\s*["\'][^"\']*["\']', 'href="#"', tag, count=1)
        if 'target=' in tag:
            return tag
        return tag.replace('<a', '<a target="_blank" rel="noopener noreferrer"', 1)
    html = re.sub(r'<a\b[^>]*>', _a_repl, html)
    return html, toc


def db_save_post(form_data, post_id=None):
    db = get_db()
    tags = json.dumps([t.strip() for t in form_data.get('tags', '').split(',') if t.strip()], ensure_ascii=False)
    slug = form_data.get('slug', '').strip()
    if not slug:
        # 仅保留 ASCII 字母数字和连字符，剔除中文等非 ASCII 字符
        slug = re.sub(r'[^a-zA-Z0-9\-]', '-', form_data.get('title', 'untitled').lower())[:60]
    slug = re.sub(r'-+', '-', slug).strip('-') or 'untitled'

    content = form_data.get('content', '')
    # 自动链接 <https://...> 规范化为标准链接 [URL](URL)，避免 Vditor 编辑往返时丢失
    content = normalize_auto_links(content)
    read_time = max(1, len(content.split()) // 200) if content else 3
    is_featured = 1 if form_data.get('is_featured') == '1' else 0
    category_id_raw = form_data.get('category_id', '') or ''
    category_id = int(category_id_raw) if str(category_id_raw).strip().isdigit() else None

    # 摘要：留空则从正文自动截取前 200 字符（去除 HTML/Markdown 标记）
    excerpt = (form_data.get('excerpt', '') or '').strip()
    if not excerpt and content:
        plain = re.sub(r'<[^>]+>', '', content)      # 去 HTML 标签
        plain = re.sub(r'[#*`\[\]()!>|~-]', '', plain)  # 去 Markdown 符号
        plain = re.sub(r'\s+', ' ', plain).strip()
        excerpt = plain[:200] if len(plain) > 200 else plain

    # 发布日期：datetime-local 表单值（YYYY-MM-DDTHH:MM）归一化为 DB 格式；留空则新建时用当前时间、编辑时保持不变
    created_at = (form_data.get('created_at', '') or '').strip().replace('T', ' ')
    if created_at and len(created_at) == 16:
        created_at += ':00'
    created_at = created_at or None

    # slug 唯一化：新建时若冲突则追加 -2/-3... 直到唯一
    if not post_id:
        base = slug
        i = 2
        while db.execute("SELECT 1 FROM posts WHERE slug=?", (slug,)).fetchone():
            slug = f"{base}-{i}"
            i += 1

    if post_id:
        db.execute(
            """UPDATE posts SET title=?, slug=?, content=?, excerpt=?, tags=?,
               is_featured=?, read_time=?, status=?, category_id=?,
               created_at=COALESCE(?, created_at), updated_at=? WHERE id=?""",
            (form_data.get('title', ''), slug, content, excerpt,
             tags, is_featured, read_time, form_data.get('status', 'published'), category_id,
             created_at, _now(), post_id)
        )
    else:
        db.execute(
            """INSERT INTO posts (title, slug, content, excerpt, tags, is_featured, read_time, status, category_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, ?), ?)""",
            (form_data.get('title', ''), slug, content, excerpt,
             tags, is_featured, read_time, form_data.get('status', 'published'), category_id,
             created_at, _now(), _now())
        )
    db.commit()
    db.close()


def db_delete_post(post_id):
    db = get_db()
    # 删除前先收集本文引用的上传文件 URL，供删除后做清理判定
    row = db.execute("SELECT title, content, excerpt, tags FROM posts WHERE id=?", (post_id,)).fetchone()
    gone_urls = _extract_upload_urls(*tuple(row)) if row else set()
    db.execute("DELETE FROM posts WHERE id=?", (post_id,))
    db.commit()
    removed = []
    if gone_urls:
        # 共享引用保护：删除后仍被其他文章引用的文件一律保留。
        # 剩余文章的正文可能存百分号编码 URL，须同样归一为解码 URL 集合再比对。
        rows = db.execute("SELECT title, content, excerpt, tags FROM posts").fetchall()
        survivor_urls = set()
        for r in rows:
            survivor_urls |= _extract_upload_urls(*tuple(r))
        for url in sorted(gone_urls):
            if url and url not in survivor_urls:
                if _delete_upload_file(url):
                    removed.append(url)
    db.close()
    return removed


# ─────────────── 文章分类数据层 ───────────────

def db_load_categories():
    db = get_db()
    rows = db.execute(
        "SELECT c.*, (SELECT COUNT(*) FROM posts p WHERE p.category_id=c.id) as post_count "
        "FROM categories c ORDER BY c.sort_order ASC, c.id ASC"
    ).fetchall()
    db.close()
    return rows_to_list(rows)


def db_get_category(cat_id):
    db = get_db()
    row = db.execute("SELECT * FROM categories WHERE id=?", (cat_id,)).fetchone()
    db.close()
    return dict(row) if row else None


def db_save_category(form_data, cat_id=None):
    db = get_db()
    name = form_data.get('name', '').strip()
    slug = form_data.get('slug', '').strip()
    if not slug:
        slug = re.sub(r'[^\w\-]', '-', name.lower())[:40] or 'category'
    # 确保 slug 唯一
    if cat_id:
        exists = db.execute("SELECT id FROM categories WHERE slug=? AND id!=?", (slug, cat_id)).fetchone()
    else:
        exists = db.execute("SELECT id FROM categories WHERE slug=?", (slug,)).fetchone()
    if exists:
        slug = f"{slug}-{cat_id if cat_id else int(datetime.now().timestamp())}"
    sort_order = int(form_data.get('sort_order', 0) or 0)
    if cat_id:
        db.execute("UPDATE categories SET name=?, slug=?, sort_order=? WHERE id=?",
                   (name, slug, sort_order, cat_id))
    else:
        db.execute("INSERT INTO categories (name, slug, sort_order) VALUES (?,?,?)",
                   (name, slug, sort_order))
    db.commit()
    db.close()


def db_delete_category(cat_id):
    db = get_db()
    # 解除该分类下文章的分类绑定
    db.execute("UPDATE posts SET category_id=NULL WHERE category_id=?", (cat_id,))
    db.execute("DELETE FROM categories WHERE id=?", (cat_id,))
    db.commit()
    db.close()

# ─────────────── GitHub 项目数据层 ───────────────

def parse_github_repo(url):
    """从 GitHub 地址中解析 owner/repo，失败返回 None。"""
    if not url:
        return None
    m = re.search(r'github\.com[:/]([^/\s]+)/([^/\s#?]+)', url.strip())
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    repo = repo.replace('.git', '')
    return f"{owner}/{repo}"


# 记录最近一次 GitHub API 失败原因，供同步路由给出精确提示
last_gh_error = ''


_GITHUB_SSL_CTX = None  # GitHub API SSL 上下文（模块级缓存，避免每次请求重建 CA bundle）


def _github_ssl_context():
    """构造用于访问 GitHub API 的 SSL 上下文（首次创建后缓存复用）。

    优先使用 certifi 提供的 CA 证书包（跨平台稳定，避免服务器缺少
    系统 CA 时出现的 CERTIFICATE_VERIFY_FAILED）；certifi 不可用时
    回退到系统默认证书。
    """
    global _GITHUB_SSL_CTX
    if _GITHUB_SSL_CTX is not None:
        return _GITHUB_SSL_CTX
    try:
        import certifi
        _GITHUB_SSL_CTX = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        _GITHUB_SSL_CTX = ssl.create_default_context()
    return _GITHUB_SSL_CTX


def fetch_github_repo(url):
    """拉取 GitHub 仓库实时数据，返回 dict 或 None（失败回退）。

    若 settings 中配置了 github_token，则带 Bearer 认证头调用 API，
    可访问私有仓库且将速率限额从匿名 60/小时 提升到 5000/小时。
    """
    global last_gh_error
    last_gh_error = ''
    slug = parse_github_repo(url)
    if not slug:
        last_gh_error = '地址无效：不是合法的 GitHub 仓库地址'
        return None
    api = f"https://api.github.com/repos/{slug}"
    headers = {'User-Agent': 'infowe-Blog', 'Accept': 'application/vnd.github+json'}
    token = (app.config.get('github_token') or '').strip()
    if token:
        headers['Authorization'] = f'Bearer {token}'
    try:
        data = json.loads(_http_get_text_auto(api, headers))
    except urllib.error.HTTPError as e:
        code = getattr(e, 'code', 0)
        if code == 403:
            last_gh_error = ('GitHub API 请求被拒绝（403）：多为未配置 Token 导致匿名限额(60/小时)耗尽，'
                             '或仓库为私有且无权限。请在「设置」中填入 GitHub Token。')
        elif code == 404:
            last_gh_error = '仓库不存在或无访问权限（404）：请检查地址，或仓库为私有需在「设置」配置 Token。'
        elif code == 401:
            last_gh_error = ('GitHub 拒绝访问（401）：Token 无效且匿名重试仍被拒（可能为私有仓库），'
                             '请在「设置」中更新 GitHub Token。')
        else:
            last_gh_error = f'GitHub API 返回错误码 {code}'
        return None
    except (urllib.error.URLError, ValueError, OSError) as e:
        last_gh_error = f'网络请求失败：{e}'
        return None
    if not isinstance(data, dict) or 'full_name' not in data:
        last_gh_error = 'GitHub 返回数据异常'
        return None
    # 抓取全部语言占比（主接口只返回占比最高的单种语言）
    languages = []
    try:
        lang_headers = {'User-Agent': 'infowe-Blog', 'Accept': 'application/vnd.github+json'}
        if token:
            lang_headers['Authorization'] = f'Bearer {token}'
        lang_data = json.loads(_http_get_text_auto(
            f"https://api.github.com/repos/{slug}/languages", lang_headers))
        if isinstance(lang_data, dict) and lang_data:
            total = sum(lang_data.values())
            # 按字节数降序，存储 [(语言名, 百分比), ...]
            languages = sorted(
                [(name, round(val * 100 / total, 1)) for name, val in lang_data.items()],
                key=lambda x: x[1], reverse=True)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError):
        languages = []
    return {
        'name': data.get('name') or slug.split('/')[-1],
        'description': data.get('description') or '',
        'url': data.get('html_url') or url,
        'stars': int(data.get('stargazers_count') or 0),
        'language': data.get('language') or (languages[0][0] if languages else ''),
        'languages': languages,  # [(name, pct), ...]
        'topics': data.get('topics') or [],
        'default_branch': data.get('default_branch') or 'main',
    }


# ─────────────── GitHub README 拉取与缓存（项目详情页） ───────────────

# 内存缓存：{repo_slug: {'ts', 'gh', 'readme', 'branch', 'error'}}
# 详情页访问时按 TTL 检查，过期即重取，从而跟随 GitHub 上 README 的更新
_PROJECT_GH_CACHE = {}
_PROJECT_GH_LOCK = threading.Lock()
# README 候选文件名（覆盖常见大小写与 .markdown 后缀写法）
_README_FILENAMES = ('README.md', 'readme.md', 'Readme.md', 'README.markdown')


# ── 项目同步后台任务 ──
# 同步会拉取 README 并本地化图片，单项目可能耗时 1-2 分钟、一键同步全部更久，
# 远超 nginx 默认 60s 上游超时。因此 POST 后立即返回，由 daemon 线程执行，
# 页面用 /admin/projects/sync-status 轮询进度，完成后再刷新查看结果。
#
# 同步状态落盘（data/project_sync_state.json）：gunicorn 多 worker 部署下各进程
# 内存彼此独立，提交与轮询可能打到不同 worker，只有磁盘状态才是跨 worker 一致
# 的——同步线程每更新一次即写盘，读取以内存（本 worker 正在跑）为优先、否则回退
# 磁盘（其他 worker 提交的任务）。
_PROJECT_SYNC_STATE_DEFAULT = {
    'running': False, 'finished': False,
    'total': 0, 'done': 0, 'ok': 0, 'failed': 0,
    'current': '', 'summary': '', 'saved_at': 0,
}
SYNC_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               'data', 'project_sync_state.json')


def _load_sync_state():
    """启动/首访时从磁盘加载同步状态（多 worker / 重启后状态不丢）。"""
    try:
        with open(SYNC_STATE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            st = dict(_PROJECT_SYNC_STATE_DEFAULT)
            for k in st:
                if k in data:
                    st[k] = data[k]
            # 不残留陈旧的「完成」提示：完成超过 10 分钟即视为空闲，
            # 避免重启/换 worker 后页面一直挂着上次的「同步完成」条。
            if st['finished'] and time.time() - st.get('saved_at', 0) > 600:
                st['finished'] = False
                st['summary'] = ''
            return st
    except (OSError, ValueError, TypeError):
        pass
    return dict(_PROJECT_SYNC_STATE_DEFAULT)


def _save_sync_state():
    """原子写入同步状态（tmp + os.replace），供其他 worker 读取。"""
    try:
        tmp = SYNC_STATE_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(_PROJECT_SYNC_STATE, f, ensure_ascii=False)
        os.replace(tmp, SYNC_STATE_FILE)
    except OSError:
        pass


_PROJECT_SYNC_STATE = _load_sync_state()
_PROJECT_SYNC_LOCK = threading.Lock()
# 磁盘读取 mtime 快照：[上次比对键, 上次文件键, 上次解析数据]
_SYNC_STATE_SNAP = [None, None, dict(_PROJECT_SYNC_STATE_DEFAULT)]


def project_sync_state():
    """读取跨 worker 一致的同步状态（只读不写）。
    本 worker 正在跑任务则以内存为准；否则回退磁盘（可能是其他 worker 提交的）。
    带 mtime+size 快照，避免每个轮询请求都做 IO + JSON 解析。"""
    mem = _PROJECT_SYNC_STATE
    if mem.get('running'):
        return dict(mem)
    try:
        st = os.stat(SYNC_STATE_FILE)
        key = (st.st_mtime_ns, st.st_size)
        if _SYNC_STATE_SNAP[0] != key:
            if key != _SYNC_STATE_SNAP[1]:
                with open(SYNC_STATE_FILE, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                data = raw if isinstance(raw, dict) else {}
                _SYNC_STATE_SNAP[1] = key
            else:
                data = _SYNC_STATE_SNAP[2]
            _SYNC_STATE_SNAP[0] = key
            _SYNC_STATE_SNAP[2] = data
        else:
            data = _SYNC_STATE_SNAP[2]
    except (OSError, ValueError, TypeError):
        data = {}
    st_out = dict(_PROJECT_SYNC_STATE_DEFAULT)
    for k in st_out:
        if k in data:
            st_out[k] = data[k]
    return st_out


def _sync_projects_background(projects, single_id=None):
    """后台线程批量同步项目（GitHub 实时数据 + README 本地化），状态写入
    _PROJECT_SYNC_STATE 并立即落盘（供多 worker 读取）。
    projects: 全部项目行；single_id: 仅同步该 id（其余忽略）；None 表示同步全部。"""
    with _PROJECT_SYNC_LOCK:
        # 兜底防重：磁盘显示已有任务（本 worker 或他 worker）则不再启动
        if project_sync_state()['running']:
            return
        _PROJECT_SYNC_STATE.update(running=True, finished=False,
                                   total=0, done=0, ok=0, failed=0,
                                   current='', summary='', saved_at=time.time())
        _save_sync_state()
    targets = [p for p in projects if single_id is None or p['id'] == single_id]
    _PROJECT_SYNC_STATE['total'] = len(targets)
    _save_sync_state()
    seen = set()
    try:
        for p in targets:
            slug = parse_github_repo(p.get('url') or '') or ''
            _PROJECT_SYNC_STATE['current'] = (p.get('name') or p.get('title') or p.get('url') or '').strip() or slug
            if not slug or slug in seen:
                _PROJECT_SYNC_STATE['done'] += 1
                _save_sync_state()
                continue
            seen.add(slug)
            try:
                gh = fetch_github_repo(p['url'])
                if not gh:
                    _PROJECT_SYNC_STATE['failed'] += 1
                else:
                    # 拉 README 并本地化图片（写磁盘缓存）
                    fetch_project_github(p['url'])
                    db_save_project({
                        'url': gh['url'],
                        'sort_order': p.get('sort_order') or 0,
                        'featured': '1' if p.get('featured') else '',
                    }, p['id'], keep_name=True)
                    _PROJECT_SYNC_STATE['ok'] += 1
            except Exception:
                _PROJECT_SYNC_STATE['failed'] += 1
            _PROJECT_SYNC_STATE['done'] += 1
            _save_sync_state()
        _PROJECT_SYNC_STATE['summary'] = '同步完成：成功 %d 个，失败 %d 个' % (
            _PROJECT_SYNC_STATE['ok'], _PROJECT_SYNC_STATE['failed'])
    finally:
        _PROJECT_SYNC_STATE['running'] = False
        _PROJECT_SYNC_STATE['finished'] = True
        _PROJECT_SYNC_STATE['saved_at'] = time.time()
        _save_sync_state()


def _start_project_sync(projects, single_id=None):
    """以 daemon 线程启动后台同步（本 worker 或磁盘显示已在同步则返回 False）。
    真正的 running 标记由后台线程设置并立即落盘，启动前只做只读检查。"""
    with _PROJECT_SYNC_LOCK:
        if project_sync_state()['running']:
            return False
    t = threading.Thread(target=_sync_projects_background,
                         args=(list(projects), single_id), daemon=True)
    t.start()
    return True


def _github_headers(json_accept=True):
    """构造 GitHub 请求头（配置了 Token 则带认证，提升限额并可访问私有仓库）。"""
    headers = {'User-Agent': 'infowe-Blog'}
    if json_accept:
        headers['Accept'] = 'application/vnd.github+json'
    token = (app.config.get('github_token') or '').strip()
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers


def _http_get_text(url, headers, timeout=8):
    """GET 并解码为文本，失败抛异常交调用方处理。"""
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=_github_ssl_context()) as resp:
        return resp.read().decode('utf-8', 'replace')


def _http_get_text_auto(url, headers, timeout=8):
    """带认证的 GET；若 Token 无效被拒（401），自动去掉 Authorization 匿名重试一次。

    公开仓库即使配置了失效的 Token 也能正常读取；匿名重试仍失败则抛最终异常。
    """
    try:
        return _http_get_text(url, headers, timeout)
    except urllib.error.HTTPError as e:
        if e.code == 401 and headers.get('Authorization'):
            h2 = dict(headers)
            h2.pop('Authorization', None)
            return _http_get_text(url, h2, timeout)
        raise


def fetch_github_readme(slug, branch=None):
    """拉取仓库 README 原文（Markdown 文本），返回 (文本, 错误信息)，失败时文本为 None。

    优先请求 raw.githubusercontent.com —— 该域名不计入 GitHub API 匿名配额（60 次/小时），
    因此详情页频繁刷新 README 也不会耗尽限额；常见文件名都取不到时，回退 readme API 兜底
    （可覆盖 README 使用自定义路径的情况）。
    """
    owner, _, repo = (slug or '').partition('/')
    if not (owner and repo):
        return None, '仓库地址无效'
    if not branch:
        # 未提供默认分支时查一次仓库 API；失败不阻断，用 main/master 试探
        try:
            data = json.loads(_http_get_text_auto(f'https://api.github.com/repos/{slug}', _github_headers()))
            branch = data.get('default_branch') or ''
        except Exception:
            branch = ''
    branches = list(dict.fromkeys([b for b in (branch, 'main', 'master') if b]))
    net_err = ''
    for br in branches:
        for fn in _README_FILENAMES:
            try:
                text = _http_get_text_auto(
                    f'https://raw.githubusercontent.com/{slug}/{br}/{fn}', _github_headers(json_accept=False))
            except urllib.error.HTTPError:
                continue          # 该文件名不存在，试下一个
            except (urllib.error.URLError, OSError, ValueError):
                # raw 域名网络不通：记下错误，改走 readme API 兜底（api 域名可能可达）
                net_err = last_gh_error or '网络请求失败，无法访问 GitHub'
                break
            if text.strip():
                return text, ''
        if net_err:
            break
    # 回退：readme API（占 1 次 API 配额，可拿到自定义路径的 README；Token 失效会自动匿名重试）
    try:
        data = json.loads(_http_get_text_auto(f'https://api.github.com/repos/{slug}/readme', _github_headers()))
        content = base64.b64decode(data.get('content') or '').decode('utf-8', 'replace')
        if content.strip():
            return content, ''
    except Exception:
        pass
    return None, net_err or '仓库中未找到 README 文件'


def _absolutize_readme_urls(html, slug, branch):
    """把 README 中的相对链接/图片补成 GitHub 绝对地址，避免图片与跳转失效。"""
    base_blob = f'https://github.com/{slug}/blob/{branch}/'
    base_raw = f'https://raw.githubusercontent.com/{slug}/{branch}/'

    def _fix(m):
        attr, url = m.group(1), m.group(2)
        # 已是绝对地址、协议相对或页内锚点则原样保留
        if re.match(r'^(?:[a-z][a-z0-9+.-]*:|//|#)', url, re.I):
            return m.group(0)
        target = base_raw if attr == 'src' else base_blob
        return '%s="%s%s"' % (attr, target, url.lstrip('/'))

    return re.sub(r'\b(src|href)="([^"]*)"', _fix, html)


def render_readme_html(md, slug, branch):
    """README Markdown → 消毒后的 HTML（含相对链接修正）。转换异常时返回 None。"""
    if not md:
        return None
    try:
        html = markdown.markdown(
            md, extensions=['fenced_code', 'tables', 'nl2br', 'sane_lists'])
    except Exception:
        return None
    html = _absolutize_readme_urls(html, slug, branch or 'main')
    return _sanitize_html(html)


# ── README 图片本地化：同步时把 GitHub raw 图片下载到本地上传目录 ──
# 存储位置 uploads/projects/<slug>/readme/（与上传附件同体系，URL 走 /uploads/ 路由，
# 不入 static/ 避免参与版本指纹扫描）；文件名为 URL 的 MD5 + 扩展名，内容不变则文件复用。
_README_IMG_ROOT = os.path.join(UPLOAD_DIR, 'projects')
_README_IMG_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp', '.ico')
_README_IMG_MAX = 8 * 1024 * 1024  # 单图上限 8MB，防超大图拖慢同步/占满磁盘


def _fetch_bin(url, timeout, accept=None, auth=False):
    """下载二进制内容（带 UA/可选 Accept/Bearer）；失败或超限返回 None。"""
    headers = {'User-Agent': 'infowe-Blog'}
    if accept:
        headers['Accept'] = accept
    if auth:
        token = (app.config.get('github_token') or '').strip()
        if token:
            headers['Authorization'] = 'Bearer ' + token
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout, context=_github_ssl_context()) as resp:
            return resp.read(_README_IMG_MAX + 1)
    except Exception:
        return None


def _raw_url_to_api(url, slug):
    """raw.githubusercontent.com/{slug}/{branch}/{path} → api.github.com 下载地址。

    raw 域名在部分网络下极慢，回退到 api.github.com（一般快得多）仍能取到原图字节。
    """
    m = re.match(r'https://raw\.githubusercontent\.com/' + re.escape(slug) + r'/([^/]+)/(.+)', url)
    if not m:
        return None
    branch, path = m.group(1), m.group(2)
    # 路径可能含中文/空格等非 ASCII 字符，必须 percent-encode（保留 / 与已有编码）
    path_q = urllib.parse.quote(path, safe='/%')
    return (f'https://api.github.com/repos/{slug}/contents/{path_q}?ref={branch}')


def _guess_image_ext(data, url):
    """扩展名：URL 后缀优先，其次按文件魔数识别，均无法识别则留空。"""
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    if ext in _README_IMG_EXT:
        return ext
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return '.png'
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return '.gif'
    if data[:2] == b'\xff\xd8':
        return '.jpg'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return '.webp'
    if data[:5] in (b'<svg ', b'<?xml'):
        return '.svg'
    return ''


def _download_readme_image(url, slug):
    """下载单个 README 图片到本地，返回 'projects/<slug>/readme/<name>'；失败返回 None。"""
    data = _fetch_bin(url, 15)
    if data is None:
        # raw 域名网络不通时回退 GitHub API 下载（计入 API 配额，Token 下配额充足）
        alt = _raw_url_to_api(url, slug)
        if alt:
            data = _fetch_bin(alt, 15, accept='application/vnd.github.raw', auth=True)
    if not data or len(data) > _README_IMG_MAX:
        return None
    name = hashlib.md5(url.encode('utf-8')).hexdigest() + _guess_image_ext(data, url)
    directory = os.path.join(_README_IMG_ROOT, slug, 'readme')
    try:
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, name), 'wb') as f:
            f.write(data)
    except OSError:
        return None
    return 'projects/%s/readme/%s' % (slug, name)


def _prune_readme_images(slug, new_html):
    """清理 readme 图片目录中已不被新 HTML 引用的旧文件（防止多次同步后膨胀）。"""
    directory = os.path.join(_README_IMG_ROOT, slug, 'readme')
    if not os.path.isdir(directory):
        return
    kept = set(re.findall(r'/uploads/projects/%s/readme/([A-Za-z0-9._-]+)' % re.escape(slug),
                          new_html))
    try:
        for name in os.listdir(directory):
            p = os.path.join(directory, name)
            if os.path.isfile(p) and name not in kept:
                try:
                    os.remove(p)
                except OSError:
                    pass
    except OSError:
        pass


def _localize_readme_images(html, slug):
    """把 README 中指向同仓库 raw.githubusercontent.com 的图片下载到本地并替换 src。

    仅管理员同步时调用（前台零 GitHub 请求）。下载失败的图片保留原 GitHub 地址，
    不影响 README 展示。多张图并发下载（该域名在部分网络下较慢，串行会拖死同步）。
    返回替换后的 HTML。
    """
    if not html or not slug:
        return html
    pattern = re.compile(
        r'(<img\b[^>]*\bsrc=")(https://raw\.githubusercontent\.com/' + re.escape(slug) + r'/[^"]*)(")',
        re.I)
    urls = [m.group(2) for m in pattern.finditer(html)]
    if not urls:
        return html
    # 子线程只负责下载并返回文件名（不调用 url_for，避免线程外无 app context）；URL 组装回主线程
    filename_map = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_download_readme_image, u, slug): u for u in dict.fromkeys(urls)}
        for f in concurrent.futures.as_completed(futs):
            try:
                fn = f.result()
            except Exception:
                fn = None
            if fn:
                filename_map[futs[f]] = fn

    def _replace(m):
        fn = filename_map.get(m.group(2))
        if not fn:
            return m.group(0)
        # 直接拼 /uploads/ 相对路径（与 /uploads 路由一致），避免依赖请求上下文
        return m.group(1) + '/uploads/' + fn + m.group(3)

    new_html = pattern.sub(_replace, html)
    if new_html != html:
        _prune_readme_images(slug, new_html)
    return new_html


# 磁盘持久化缓存文件：拉取结果存盘，服务重启后仍可秒开已拉取过的项目
_PROJECT_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   'data', 'project_gh_cache.json')

# 磁盘缓存读取快照：[最近一次命中 (mtime_ns,size), 已解析 key, 解析出的 dict]
# 供 project_cache_snapshot 多进程回退时避免每个请求都读文件 + JSON 解析
_PERSIST_CACHE_SNAP = [None, None, {}]


def _persist_project_cache():
    """把内存缓存写盘（data/project_gh_cache.json），失败静默。"""
    try:
        with open(_PROJECT_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(_PROJECT_GH_CACHE, f, ensure_ascii=False)
    except (OSError, TypeError, ValueError):
        pass


def _load_project_cache():
    """启动时把磁盘缓存载入内存（结构校验，坏数据忽略）。"""
    try:
        with open(_PROJECT_CACHE_FILE, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for k, v in raw.items():
                if isinstance(v, dict) and isinstance(v.get('ts'), (int, float)):
                    _PROJECT_GH_CACHE[k] = v
    except (OSError, ValueError, TypeError):
        pass


_load_project_cache()


def project_cache_snapshot(slug):
    """只读缓存快照（绝不触发网络请求）；无缓存返回 None。

    多进程部署（gunicorn/uwsgi 多 worker）下，各进程的内存缓存可能不一致：
    管理员在某 worker 上同步后，其他 worker 内存里没有结果，导致「一会儿能
    读到文档、一会儿提示未同步」。因此这里始终以磁盘缓存文件为权威：
    内存 miss 时回退读磁盘；磁盘条目的 ts 比内存新时也取磁盘。磁盘文件小
    （几个项目、几 KB），带 mtime 快照避免每个请求都做 IO + JSON 解析。
    """
    best = _PROJECT_GH_CACHE.get(slug)
    # 读磁盘缓存（mtime+size 不变则复用上次解析结果，零开销）
    try:
        st = os.stat(_PROJECT_CACHE_FILE)
        key = (st.st_mtime_ns, st.st_size)
        if _PERSIST_CACHE_SNAP[0] != key:
            if key != _PERSIST_CACHE_SNAP[1]:
                with open(_PROJECT_CACHE_FILE, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                data = raw if isinstance(raw, dict) else {}
                _PERSIST_CACHE_SNAP[1] = key
            else:
                data = _PERSIST_CACHE_SNAP[2]
            _PERSIST_CACHE_SNAP[0] = key
            _PERSIST_CACHE_SNAP[2] = data
        else:
            data = _PERSIST_CACHE_SNAP[2]
    except (OSError, ValueError, TypeError):
        data = {}
    disk_entry = data.get(slug)
    if not isinstance(disk_entry, dict):
        disk_entry = None
    if best and disk_entry:
        best = best if (best.get('ts') or 0) >= (disk_entry.get('ts') or 0) else disk_entry
    elif disk_entry:
        best = disk_entry
    return dict(best) if best else None


def fetch_project_github(project_url):
    """拉取项目在 GitHub 上的实时元数据与 README，写入内存缓存并持久化（磁盘）。

    仅在管理员后台「新增项目 / 同步 / 一键同步全部」时被调用（手动触发），
    前台页面绝不发起任何 GitHub 请求 —— 匿名 API 限额（60/小时）只被低频的
    管理员操作消耗，前台永远秒开。返回 {'gh','readme','branch','ts','error'}。
    """
    slug = parse_github_repo(project_url)
    if not slug:
        return {'gh': None, 'readme': None, 'branch': '', 'ts': 0,
                'error': '该项目未关联 GitHub 仓库'}
    now = time.time()
    gh = fetch_github_repo(project_url)
    branch = (gh or {}).get('default_branch') or ''
    md, err = fetch_github_readme(slug, branch)
    html = render_readme_html(md, slug, branch)
    if html:
        # 图片本地化：同仓库 raw 图片下载到 uploads/projects/<slug>/readme/，前台零 GitHub 请求
        html = _localize_readme_images(html, slug)
    entry = {
        'ts': now,
        'gh': gh,
        'branch': branch or 'main',
        'readme': html,
        'error': '' if md else (err or '未找到 README 文件'),
    }
    with _PROJECT_GH_LOCK:
        _PROJECT_GH_CACHE[slug] = entry
    _persist_project_cache()
    return dict(entry)


def db_repo_exists(slug, exclude_id=None):
    """判断该 GitHub 仓库（owner/repo）是否已存在于 projects 表，去重用。"""
    if not slug:
        return False
    db = get_db()
    if exclude_id:
        row = db.execute("SELECT id FROM projects WHERE github_repo=? AND id!=?", (slug, exclude_id)).fetchone()
    else:
        row = db.execute("SELECT id FROM projects WHERE github_repo=?", (slug,)).fetchone()
    db.close()
    return row is not None


def db_load_projects():
    db = get_db()
    rows = db.execute("SELECT * FROM projects ORDER BY sort_order ASC, created_at DESC").fetchall()
    projects = []
    for r in rows:
        p = dict(r)
        p['topics'] = json.loads(p['topics'])
        projects.append(p)
    db.close()
    return projects


def db_save_project(form_data, project_id=None, keep_name=False):
    db = get_db()
    # 仅提交 GitHub URL 时，自动从 GitHub 拉取实时数据（stars/语言/标签/描述）
    custom_name = form_data.get('name', '').strip()
    gh = fetch_github_repo(form_data.get('url', ''))
    if gh:
        # 自定义项目名优先，留空才用 GitHub 仓库名
        gh_name = gh['name']
        description = gh['description']
        url = gh['url']
        stars = gh['stars']
        language = gh['language']
        languages = json.dumps(gh['languages'], ensure_ascii=False)
        topics = json.dumps(gh['topics'], ensure_ascii=False)
        github_repo = parse_github_repo(form_data.get('url', ''))
    else:
        # 拉取失败：保留表单手填值（兼容旧数据或非 GitHub 地址）
        gh_name = None
        description = form_data.get('description', '')
        url = form_data.get('url', '')
        stars = int(form_data.get('stars', 0) or 0)
        language = form_data.get('language', '')
        languages = ''
        topics = json.dumps([t.strip() for t in form_data.get('topics', '').split(',') if t.strip()], ensure_ascii=False)
        github_repo = parse_github_repo(url)

    # 项目名处理：用户手动填写且与 GitHub 仓库名不同（或拉取失败但填了名）视为自定义
    if keep_name:
        # 同步模式：尊重已有的自定义名，不覆盖
        existing = db.execute(
            "SELECT name, custom_name FROM projects WHERE id=?", (project_id,)
        ).fetchone()
        name = existing['name'] if existing else (custom_name or gh_name)
        is_custom = existing['custom_name'] if existing else 0
    else:
        if custom_name and custom_name != gh_name:
            name = custom_name
            is_custom = 1
        else:
            name = custom_name or gh_name
            is_custom = 0

    if project_id:
        db.execute(
            "UPDATE projects SET name=?, description=?, url=?, stars=?, language=?, languages=?, topics=?, sort_order=?, featured=?, github_repo=?, custom_name=?, updated_at=? WHERE id=?",
            (name, description, url, stars, language, languages, topics,
             int(form_data.get('sort_order', 0) or 0), 1 if form_data.get('featured') == '1' else 0, github_repo or '', is_custom, _now(), project_id)
        )
    else:
        db.execute(
            "INSERT INTO projects (name, description, url, stars, language, languages, topics, sort_order, featured, github_repo, custom_name, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (name, description, url, stars, language, languages, topics,
             int(form_data.get('sort_order', 0) or 0), 1 if form_data.get('featured') == '1' else 0, github_repo or '', is_custom)
        )
    db.commit()
    db.close()


def db_delete_project(project_id):
    db = get_db()
    db.execute("DELETE FROM projects WHERE id=?", (project_id,))
    # 项目删除后其评论失去归属，一并清理（post_id 与 project_id 二选一的载体）
    db.execute("DELETE FROM comments WHERE project_id=?", (project_id,))
    db.commit()
    db.close()


def db_get_project(project_id):
    """按 id 取单个项目（topics 解析为列表），不存在返回 None。"""
    db = get_db()
    row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    db.close()
    if not row:
        return None
    p = dict(row)
    try:
        p['topics'] = json.loads(p['topics']) if p['topics'] else []
    except (ValueError, TypeError):
        p['topics'] = []
    return p


# ─────────────── 友情链接数据层 ───────────────

def db_load_links(status=None):
    in_request = has_request_context()
    db = _request_db()
    try:
        if status:
            rows = db.execute(
                "SELECT * FROM links WHERE status=? ORDER BY sort_order ASC, created_at DESC",
                (status,)).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM links ORDER BY sort_order ASC, created_at DESC").fetchall()
    finally:
        if not in_request:
            db.close()
    return rows_to_list(rows)


def db_save_link(form_data, link_id=None, status=None):
    db = get_db()
    if link_id:
        db.execute("UPDATE links SET name=?, url=?, description=?, avatar=?, sort_order=? WHERE id=?",
                   (form_data.get('name', ''), form_data.get('url', ''),
                    form_data.get('description', ''), (form_data.get('avatar') or '').strip(),
                    int(form_data.get('sort_order', 0)), link_id))
    else:
        db.execute("INSERT INTO links (name, url, description, avatar, sort_order, status) VALUES (?,?,?,?,?,?)",
                   (form_data.get('name', ''), form_data.get('url', ''),
                    form_data.get('description', ''), (form_data.get('avatar') or '').strip(),
                    int(form_data.get('sort_order', 0)),
                    status or 'approved'))
    db.commit()
    db.close()


def db_set_link_status(link_id, status):
    db = get_db()
    db.execute("UPDATE links SET status=? WHERE id=?", (status, link_id))
    db.commit()
    db.close()


def db_delete_link(link_id):
    db = get_db()
    db.execute("DELETE FROM links WHERE id=?", (link_id,))
    db.commit()
    db.close()


# ─────────────── 评论数据层 ───────────────

def _avatar_url(email_hash, size=80):
    """后台头像：经站内代理 /avatar/e/<md5>/<size>.png（后端 Cravatar → WeAvatar 轮换）。"""
    if not email_hash:
        return ''
    return url_for('avatar_proxy', key='e' + email_hash, size=max(1, size), _external=True)


_QQ_RE = re.compile(r'^(\d{5,12})@(?:qq\.com|foxmail\.com|vip\.qq\.com|qq\.com\.cn)$')


def _qq_avatar_size(size):
    """q1.qlogo.cn 只接受 40 / 100 / 640 三档，其它尺寸一律返回 400（2026-09-06 实测）。"""
    return 40 if size <= 40 else (100 if size <= 100 else 640)


def _avatar_urls(email_hash, qq='', size=80):
    """返回 (主头像URL, 备用头像URL)。统一指向站内代理 /avatar/<key>/<size>.png：
    外部图源（qlogo 多域名 / Cravatar / WeAvatar）在服务端轮换并落盘缓存，
    浏览器不再直连任何外部域名，规避 qlogo 400/403、图源挂起、防盗链等问题。
    备用源由代理内部兜底，故不再返回第二 URL。"""
    if not email_hash and not qq:
        return '', ''
    if qq:
        return url_for('avatar_proxy', key='q' + qq, size=_qq_avatar_size(size), _external=True), ''
    return url_for('avatar_proxy', key='e' + email_hash, size=max(1, size), _external=True), ''


# ─────────────── 头像代理：评论/博主头像统一经站内中转 ───────────────
# 背景：评论头像此前直连外部图源。q1.qlogo.cn 对非 40/100/640 档的 s 参数返回 400，
#   部分出口 IP / 域名被风控返回 403，个别请求 TCP 挂起 → 头像不可用。
# 方案：浏览器只请求本站 /avatar/<key>/<size>.png，后端按源优先级轮换抓取并落盘缓存；
#   全部外部源失败时返回 404，由前端本地 default-avatar.svg 兜底。
_AVATAR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'cache', 'avatars')
_AVATAR_MAX_AGE = 15 * 24 * 3600      # 缓存 15 天，过期自动重新抓取
_AVATAR_TIMEOUT = 8                    # 单源超时（秒），超时换下一个源
_AVATAR_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
_AVATAR_MAGIC = ((b'\x89PNG', 'image/png'), (b'\xff\xd8\xff', 'image/jpeg'),
                 (b'GIF8', 'image/gif'), (b'<svg', 'image/svg+xml'))


def _fetch_image_bytes(url):
    """抓取并校验图片格式；任何失败返回 (None, None)。
    服务器缺系统根证书时（精简环境/宝塔编译版 Python），校验证书分支会抛
    SSLError 导致全部头像源失败 → 代理 404。头像为非敏感公开数据，
    先按校验证书抓，SSLError 时降级为不校验证书重试一次。"""
    req = urllib.request.Request(url, headers={'User-Agent': _AVATAR_UA})
    for ctx, label in ((_default_ssl_context(), 'verify'),
                       (ssl._create_unverified_context(), 'noverify')):
        try:
            with urllib.request.urlopen(req, timeout=_AVATAR_TIMEOUT, context=ctx) as r:
                data = r.read(2 * 1024 * 1024)
                ctype = (r.headers.get('Content-Type') or '').lower()
            break
        except ssl.SSLError:
            continue
        except Exception:
            return None, None
    else:
        return None, None
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return data, 'image/webp'
    for magic, mime in _AVATAR_MAGIC:
        if data[:len(magic)].lower() == magic:
            return data, mime
    if data and 'image/' in ctype:
        return data, ctype
    return None, None


@app.route('/avatar/<key>/<int:size>.png')
def avatar_proxy(key, size):
    """站内头像代理：键 q<QQ号> / e<md5>，按源优先级轮换抓取并缓存到磁盘。"""
    if key.startswith('q') and key[1:].isdigit():
        qq, s = key[1:], _qq_avatar_size(size)
        sources = ['https://q%d.qlogo.cn/g?b=qq&nk=%s&s=%d' % (i, qq, s) for i in (1, 2, 3, 4)]
    elif key.startswith('e') and re.fullmatch(r'[0-9a-f]{32}', key[1:]):
        md5, s = key[1:], max(1, min(size, 640))
        # d=404：Cravatar/WeAvatar 未注册该邮箱时返回 404，而非黑色占位剪影，
        # 由代理 404 + 前端 onerror 兜底显示博客默认头像。
        sources = ['https://cravatar.cn/avatar/%s?s=%d&d=404' % (md5, s),
                   'https://weavatar.com/avatar/%s?s=%d&d=404' % (md5, s)]
    else:
        abort(404)
    fname = '%s_%d.png' % (key, s)
    path = os.path.join(_AVATAR_DIR, fname)
    try:
        if os.path.exists(path) and time.time() - os.path.getmtime(path) < _AVATAR_MAX_AGE:
            return send_from_directory(_AVATAR_DIR, fname, max_age=_AVATAR_MAX_AGE)
    except OSError:
        pass
    data, mime = None, None
    for url in sources:
        data, mime = _fetch_image_bytes(url)
        if data:
            break
    if not data:
        abort(404)
    try:
        os.makedirs(_AVATAR_DIR, exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, path)          # 原子落盘，并发请求互不干扰
    except OSError:
        pass
    resp = make_response(data)
    resp.headers['Content-Type'] = mime
    resp.headers['Cache-Control'] = 'public, max-age=%d' % _AVATAR_MAX_AGE
    resp.headers['X-Avatar-Source'] = 'fetch'
    return resp


def db_load_comments(post_id=None, project_id=None, include_private=False, my_comments=None):
    """加载评论并组装为树（一次查询，内存组装，避免 N+1）。
    普通访客：仅已通过且非私密 + 本人待审核的非私密评论（my_comments 为 {评论id: 昵称} 映射，校验昵称防伪造）；
    管理员：已通过 + 全部私密（含待审核）。
    post_id / project_id 二选一：写评论归属的载体（文章或项目）。
    返回 (根评论列表, 评论总数)。每条评论附带 avatar / depth / parent_author。"""
    db = get_db()
    if project_id is not None:
        target_col, target_val = 'project_id', project_id
    else:
        target_col, target_val = 'post_id', post_id
    if include_private:
        sql = "SELECT * FROM comments WHERE %s=? AND (status='approved' OR is_private=1)" % target_col
        params = [target_val]
    else:
        sql = "SELECT * FROM comments WHERE %s=? AND (status='approved' AND is_private=0)" % target_col
        params = [target_val]
        if my_comments:
            ids = [i for i in my_comments if str(i).isdigit()]
            if ids:
                sql += " OR id IN (%s)" % ','.join('?' * len(ids))
                params += ids
    sql += " ORDER BY created_at ASC, id ASC"
    rows = db.execute(sql, params).fetchall()
    db.close()
    comments = rows_to_list(rows)
    # 本人待审核评论：校验昵称与 cookie 记录一致，防止伪造 id 偷看他人待审核评论
    if my_comments and not include_private:
        comments = [c for c in comments
                    if c['status'] == 'approved'
                    or (str(c['id']) in my_comments and my_comments[str(c['id'])] == c['author'])]
    author_name = app.config.get('author', '')
    # 博主头像固定用后台「联系邮箱」生成 Cravatar，与评论者邮箱无关
    contact = (app.config.get('contact_email') or '').strip().lower()
    contact_hash = hashlib.md5(contact.encode('utf-8')).hexdigest() if contact else ''
    _cm = _QQ_RE.match(contact)
    contact_qq = _cm.group(1) if _cm else ''
    by_id = {c['id']: c for c in comments}
    roots = []
    # 本地默认头像：外部头像源不可达（失败/挂起）时由前端兜底显示，避免空白
    avatar_default = url_for('static', filename='images/default-avatar.svg', _external=True)
    for c in comments:
        c['children'] = []
        c['is_author'] = bool(author_name) and c['author'] == author_name
        # 博主头像单独判断：优先用后台「设置」上传的头像（管理员自行控制），
        # 配置为空或文件已被删除时回退到 Cravatar（后台联系邮箱生成）
        if c['is_author']:
            cfg_avatar = app.config.get('avatar', '')
            if cfg_avatar and _avatar_file_exists():
                c['avatar'] = cfg_avatar
                c['avatar_fallback'] = ''
            else:
                c['avatar'], c['avatar_fallback'] = _avatar_urls(contact_hash, contact_qq)
        else:
            c['avatar'], c['avatar_fallback'] = _avatar_urls(c.get('email_hash', ''), c.get('qq', ''))
        # 评论未留邮箱：_avatar_urls 返回空 → 直接显示博客默认头像（不渲染首字母）
        if not c['avatar']:
            c['avatar'], c['avatar_fallback'] = avatar_default, ''
        c['avatar_default'] = avatar_default
        # 明文邮箱仅用于回复通知，不出现在任何渲染上下文
        c.pop('email', None)
        pid = c.get('parent_id')
        if pid and pid in by_id:
            c['parent_author'] = by_id[pid]['author']
            by_id[pid]['children'].append(c)
        else:
            c['parent_author'] = ''
            roots.append(c)

    def set_depth(node, d):
        node['depth'] = d
        for ch in node['children']:
            set_depth(ch, d + 1)

    for r in roots:
        set_depth(r, 0)
    return roots, len(comments)


def _count_pending(nodes):
    """递归统计评论树中 status='pending' 的条数。
    仅用于「你的评论正在审核中」提示：普通访客的树里只会含本人待审核评论。"""
    n = 0
    for c in nodes or []:
        if c.get('status') == 'pending':
            n += 1
        n += _count_pending(c.get('children'))
    return n


def db_save_comment(post_id, author, email, email_hash, website, content, parent_id=None, is_private=False, qq='', ip_text='', status='pending', project_id=None):
    """新评论默认 pending，审核通过后才在前台展示。
    私密评论同样 pending：仅管理员可见（含待审核），普通访客始终不可见。
    email 为评论者明文邮箱（仅用于发送回复通知，不展示）；ip_text 为原始 IP。
    status 由调用方指定：博主本人（邮箱 == notify_email）在路由层传 approved 免审核。
    project_id 与 post_id 二选一：项目详情页评论传 project_id（文章评论保持传 post_id）。"""
    db = get_db()
    cur = db.execute(
        "INSERT INTO comments (post_id, project_id, parent_id, author, email, email_hash, website, content, status, is_private, qq, ip_text, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (post_id, project_id, parent_id, author, email, email_hash, website, content, status, 1 if is_private else 0, qq, ip_text, _now())
    )
    db.commit()
    db.close()
    return cur.lastrowid


def db_delete_comment(comment_id):
    """删除评论及其全部子回复（整棵子树）。"""
    db = get_db()
    # 循环收集子树 id（避免依赖 SQLite 递归 CTE）
    ids = [comment_id]
    frontier = [comment_id]
    while frontier:
        rows = db.execute(
            "SELECT id FROM comments WHERE parent_id IN (%s)" % ','.join('?' * len(frontier)),
            frontier
        ).fetchall()
        frontier = [r['id'] for r in rows]
        ids.extend(frontier)
    db.execute("DELETE FROM comments WHERE id IN (%s)" % ','.join('?' * len(ids)), ids)
    db.commit()
    db.close()


# ─────────────── 全局上下文 ───────────────

def _preview_thumb(source):
    """主题预览图缩略：cover 裁切为 480x300，缓存于主题目录（preview.thumb.png）。
    主题目录只读或 PIL 不可用时回退原图（后台仍显示完整图，不报错）。"""
    cache = os.path.join(os.path.dirname(source), 'preview.thumb.png')
    if not os.path.isfile(cache):
        try:
            from PIL import Image
            with Image.open(source) as im:
                im = im.convert('RGB')
                tw, th = 480, 300
                scale = max(tw / im.width, th / im.height)
                nw, nh = max(tw, round(im.width * scale)), max(th, round(im.height * scale))
                im = im.resize((nw, nh))
                im = im.crop(((nw - tw) // 2, (nh - th) // 2,
                              (nw - tw) // 2 + tw, (nh - th) // 2 + th))
                im.save(cache, 'PNG', optimize=True)
        except Exception:
            return source
    return cache


@app.route('/themes/<path:filename>')
def theme_static(filename):
    """主题静态资源（theme.css、preview.png 等），从 templates/ 主题文件夹发送。
    仅允许静态资源扩展名；default 内置主题仅放行 preview.png（供后台预览）。
    preview.png 请求自动改发服务端缩略图（480x300），避免后台列表加载完整大图。"""
    if filename.startswith(DEFAULT_THEME_NAME + '/') and filename != DEFAULT_THEME_NAME + '/preview.png':
        abort(404)
    if not filename.lower().endswith(('.css', '.js', '.png', '.jpg', '.jpeg', '.gif',
                                      '.webp', '.svg', '.ico', '.woff', '.woff2',
                                      '.ttf', '.otf')):
        abort(404)
    if filename.endswith('/preview.png'):
        source = os.path.join(TEMPLATE_DIR, filename)
        if os.path.isfile(source):
            # ponytail: 缩略图尺寸 480x300 匹配预览容器 16:10；换更大卡片时同步调大
            return send_file(_preview_thumb(source), mimetype='image/png', max_age=86400)
    return send_from_directory(TEMPLATE_DIR, filename)


@app.before_request
def _before_theme_sync():
    """每次请求最早阶段：加载最新设置并同步主题变化的模板缓存。
    放在 before_request 是因为 context_processor 在模板加载之后才执行，
    那时清缓存已来不及（本请求会命中旧主题的模板）。"""
    load_settings()
    _sync_theme_cache()


@app.after_request
def _security_headers(response):
    """统一设置安全响应头，防止 XSS、点击劫持、MIME 嗅探等。"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # CSP 说明：本站为无构建管线的 SSR 博客，前台/后台模板大量内联 <script>，
    # 后台「统计代码」功能需注入外域脚本（百度统计/GA 等均为 https）——
    # 因此 script-src 必须含 'unsafe-inline' 与 https:，否则全站交互脚本被浏览器拦截（v1.3.56 首版教训）。
    # 保留的实质防护：object-src 'none'（禁 object/embed）、base-uri 'self'（防 base 劫持）、
    # frame-ancestors 'none'（禁被嵌套，与 X-Frame-Options 双保险）。
    csp = ("default-src 'self'; script-src 'self' 'unsafe-inline' https:; "
           "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
           "font-src 'self' data:; connect-src 'self' https:; "
           "object-src 'none'; base-uri 'self'; frame-ancestors 'none';")
    response.headers['Content-Security-Policy'] = csp
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


# ─── 会话安全配置 ───────────────────────────────────────────
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
if os.environ.get('FLASK_DEBUG', '0') != '1':
    app.config['SESSION_COOKIE_SECURE'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 3600


# ─── 导航菜单开关 ───
# (配置 key 后缀, 显示名, 链接)；首页、写作入口为固定导航，不参与开关
NAV_PAGES = [
    ('posts', '文章', '/posts'),
    ('tags', '标签', '/tags'),
    ('projects', '项目', '/projects'),
    ('links', '友链', '/links'),
    ('about', '关于', '/about'),
    ('status', '状态', '/status'),
]


def nav_enabled(key):
    """判断某个导航页面是否启用（默认启用）"""
    return str(app.config.get('nav_' + key, '1')).strip().lower() in ('1', 'on', 'true', 'yes')


@app.context_processor
def inject_globals():
    load_settings()
    # 仅读取缓存结果，绝不主动发起网络请求（避免后台页面因 GitHub 检测卡住）
    _upgrade_info = UPGRADE_CACHE.get('info') if request.path.startswith('/admin') else None
    return {
        'blog_name': app.config.get('blog_name', 'infowe'),
        'blog_subtitle': app.config.get('blog_subtitle', ''),
        'home_title': app.config.get('home_title', ''),
        'home_posts_count': app.config.get('home_posts_count', '6'),
        'posts_per_page': app.config.get('posts_per_page', '20'),
        'comments_enabled': app.config.get('comments_enabled', '1'),
        'icp_beian': app.config.get('icp_beian', ''),
        'police_beian': app.config.get('police_beian', ''),
        # 统计代码：消毒后注入前台 </body> 前（仅管理员可配置）
        'stats_code': _sanitize_stats_code(app.config.get('stats_code', '')),
        'author': app.config.get('author', ''),
        'author_bio': app.config.get('author_bio', ''),
        'about_intro': app.config.get('about_intro', ''),
        'skills': app.config.get('skills', ''),
        'social_github': app.config.get('social_github', ''),
        'contact_email': app.config.get('contact_email', ''),
        'avatar': app.config.get('avatar', ''),
        'all_tags': db_get_all_tags(),
        'links': db_load_links(),
        # 导航开关：nav_on 供页脚条件渲染，nav_pages 供导航栏循环（仅启用项），
        # nav_all 供后台设置页循环渲染开关
        'nav_on': {k: nav_enabled(k) for k, _, _ in NAV_PAGES},
        'nav_pages': [{'key': k, 'label': label, 'href': href}
                      for k, label, href in NAV_PAGES if nav_enabled(k)],
        'nav_all': [{'key': k, 'label': label, 'enabled': nav_enabled(k)}
                    for k, label, _ in NAV_PAGES],
        'version': VERSION,
        'now_year': datetime.now().year,
        # 主题系统：当前启用主题 + 全部可选主题 + 当前主题是否带 theme.css
        'active_theme': _active_theme_key(),
        'themes': list_themes(),
        'theme_has_css': _theme_has_css(),
        # 主题静态资源缓存版本：随 theme.css/theme.js 的 mtime 变化，改样式即可强制浏览器换新
        'theme_ver': _theme_asset_ver(),
        # 后台静态资源缓存版本：同机制，admin.css / admin.js 改动即破缓存
        'admin_ver': _admin_asset_ver(),
        # 后台页面才检测更新（有缓存，前台不受网络影响）
        'upgrade_check': _upgrade_info,
        'upgrade_available': bool(_upgrade_info and _upgrade_info['version'] > parse_version(VERSION)),
    }


# ─────────────── 前台路由 ───────────────

@app.route('/')
def index():
    tag = request.args.get('tag', '')
    search = request.args.get('q', '')

    home_count = int(app.config.get('home_posts_count', '6') or 6)
    if tag or search:
        posts, total = db_load_posts(tag=tag if tag else None, search=search if search else None, page=1)
        featured = []
    else:
        # 首页：精选区独立展示（最多 3 条），主列表为最新普通文章，二者不重复不跳号
        featured = db_get_featured_posts(3)
        posts = db_load_home_posts(home_count, exclude_featured=True)
        _, total = db_load_posts(page=1)

    # 附加分类名称
    categories = {c['id']: c['name'] for c in db_load_categories()}
    for p in posts + featured:
        cid = p.get('category_id')
        p['category_name'] = categories.get(cid, '') if cid else ''

    # 首页友链圈（仅正常首页展示）
    home_links = []
    if not tag and not search:
        home_links = db_load_links(status='approved')

    return render_template('index.html',
                           posts=posts, current_tag=tag, search_query=search,
                           page=1, total_pages=1, total=total,
                           featured=featured,
                           links=home_links,
                           total_categories=len(categories))


@app.route('/posts')
def posts_page():
    if not nav_enabled('posts'):
        abort(404)
    tag_filter = request.args.get('tag', '').strip() or None
    year_filter = request.args.get('year', '').strip() or None
    per_page = int(app.config.get('posts_per_page', '20') or 20)
    # 附加分类名称（供列表展示）
    categories = {c['id']: c['name'] for c in db_load_categories()}
    all_tags = db_get_all_tags()
    all_years = db_get_all_years()

    # 归档模式：无任何筛选时，按「置顶 → 年份」分组展示（leelaa 归档质感），同样分页
    if not tag_filter and not year_filter:
        page = request.args.get('page', 1, type=int)
        _, total = db_load_posts(status='published', page=1, per_page=per_page)
        total_pages = max(1, math.ceil(total / per_page))
        page = max(1, min(page, total_pages))
        posts, _ = db_load_posts(status='published', page=page, per_page=per_page)
        for p in posts:
            cid = p.get('category_id')
            p['category_name'] = categories.get(cid, '') if cid else ''
        pinned = [p for p in posts if p['is_featured']]
        regular = [p for p in posts if not p['is_featured']]
        groups = []
        if pinned:
            groups.append({'label': '置顶', 'items': pinned})
        for y in all_years:
            items = [p for p in regular if (p['created_at'] or '').startswith(y)]
            if items:
                groups.append({'label': y, 'items': items})
        return render_template('posts.html', posts=posts, groups=groups, total=total,
                               page=page, total_pages=total_pages, filtered=False,
                               all_tags=all_tags, all_years=all_years,
                               active_tag='', active_year='')

    # 筛选模式：标签 / 年份过滤 + 分页
    page = request.args.get('page', 1, type=int)
    _, total = db_load_posts(status='published', tag=tag_filter, year=year_filter,
                              page=1, per_page=per_page)
    total_pages = max(1, math.ceil(total / per_page))
    page = max(1, min(page, total_pages))
    posts, _ = db_load_posts(status='published', tag=tag_filter, year=year_filter,
                              page=page, per_page=per_page)
    for p in posts:
        cid = p.get('category_id')
        p['category_name'] = categories.get(cid, '') if cid else ''
    return render_template('posts.html', posts=posts, groups=None, total=total,
                           page=page, total_pages=total_pages, filtered=True,
                           all_tags=all_tags, all_years=all_years,
                           active_tag=tag_filter or '', active_year=year_filter or '')


@app.route('/post/<int:post_id>')
def post_detail(post_id):
    post = db_get_post_by_id(post_id)
    if not post:
        abort(404)
    # 附加分类名称
    cid = post.get('category_id')
    if cid:
        cat = db_get_category(cid)
        post['category_name'] = cat['name'] if cat else ''
    else:
        post['category_name'] = ''
    content_html, toc_html = render_post_content(post['content'])
    # 分享卡片图（og:image / twitter:image）：封面 > 正文首图（4:3 缩略图）> 默认站图。
    # 微信等爬虫不执行 JS，直接读 SSR 的 meta 与首张 img；原图经 /share-thumb/ 转 4:3 轻量图
    share_src = (post.get('cover') or '').strip()
    if not share_src:
        share_src = _first_upload_url(post.get('content'))
    if share_src.startswith('/uploads/'):
        og_image_path = '/share-thumb/' + urllib.parse.quote(share_src.split('/uploads/', 1)[1])
    elif share_src:
        og_image_path = share_src  # 封面为外链等非 uploads 图时原样使用
    else:
        og_image_path = url_for('static', filename='images/og-image.png')
    # 字数统计（去空白，供 "共 x 字 / 约 x 分钟" 元信息）
    post['word_count'] = len(re.sub(r'\s', '', post['content']))
    related = db_get_related_posts(post['id'], post['tags'])
    comments_enabled = str(app.config.get('comments_enabled', '1')) in ('1', 'on', 'true', 'yes')
    is_admin = bool(session.get('admin_logged_in'))
    # 读取记住的评论者信息（昵称/邮箱/网址），用于表单预填；my_comments 用于展示本人待审核评论
    commenter = {}
    raw = request.cookies.get('blog_commenter')
    if raw:
        try:
            commenter = json.loads(raw)
        except (ValueError, TypeError):
            commenter = {}
    my_comments = commenter.get('my_comments') if isinstance(commenter, dict) else None
    comments, comment_total = db_load_comments(post['id'], include_private=is_admin,
                                               my_comments=my_comments) if comments_enabled else ([], 0)
    # 本人待审核评论数（管理员视角下 pending 全部可见，无需再提示）
    my_pending = 0 if is_admin else _count_pending(comments)

    # 上一篇 / 下一篇（按 created_at 排序）
    db = get_db()
    # 更早发布的是"上一篇"，更晚的是"下一篇"
    prev_row = db.execute(
        "SELECT id, title FROM posts WHERE created_at < ? ORDER BY created_at DESC LIMIT 1",
        (post['created_at'],)
    ).fetchone()
    next_row = db.execute(
        "SELECT id, title FROM posts WHERE created_at > ? ORDER BY created_at ASC LIMIT 1",
        (post['created_at'],)
    ).fetchone()
    db.close()
    prev_post = dict(prev_row) if prev_row else None
    next_post = dict(next_row) if next_row else None

    # 三栏阅读：左栏展示最近文章索引（用于高亮当前篇）
    side_posts, _ = db_load_posts(status='published', page=1, per_page=12)

    # 博主身份条头像：后台「联系邮箱」——QQ 邮箱走 qlogo，其余走 Cravatar
    admin_avatar = ''
    if is_admin:
        contact = (app.config.get('contact_email') or '').strip().lower()
        if contact:
            _cm = _QQ_RE.match(contact)
            if _cm:
                admin_avatar = url_for('avatar_proxy', key='q' + _cm.group(1), size=40, _external=True)
            else:
                admin_avatar = _avatar_url(hashlib.md5(contact.encode('utf-8')).hexdigest(), 40)

    return render_template('post.html', post=post, content=content_html, toc=toc_html,
                           related=related, comments=comments, comment_total=comment_total,
                           prev_post=prev_post, next_post=next_post,
                           comments_enabled=comments_enabled,
                           og_image_path=og_image_path,
                           commenter=commenter, is_admin=is_admin,
                           admin_avatar=admin_avatar,
                           my_pending=my_pending,
                           side_posts=side_posts)


# 浏览计数去重：同一 IP 对同一文章在窗口期内只计一次（兜底防刷新/多端刷次数）
_VIEW_COOLDOWN = {}
_VIEW_COOLDOWN_WINDOW = 60  # 秒
_VIEW_MAX_ENTRIES = 10000  # 防止内存无限增长


def _prune_cooldown(cooldown_dict, window):
    """清理过期的冷却记录，防止内存无限增长。"""
    now = time.time()
    stale = [k for k, v in cooldown_dict.items() if now - v >= window]
    for k in stale:
        cooldown_dict.pop(k, None)


@app.route('/post/<int:post_id>/view', methods=['POST'])
def post_view(post_id):
    """浏览计数：由前端在页面停留满阈值后上报（sendBeacon），秒开秒关不计数。"""
    ip = request.remote_addr
    key = (ip, post_id)
    now = time.time()
    _prune_cooldown(_VIEW_COOLDOWN, _VIEW_COOLDOWN_WINDOW)
    last = _VIEW_COOLDOWN.get(key, 0)
    if now - last < _VIEW_COOLDOWN_WINDOW:
        return ('', 204)
    _VIEW_COOLDOWN[key] = now
    # 条目数超限时强制清理
    if len(_VIEW_COOLDOWN) > _VIEW_MAX_ENTRIES:
        _prune_cooldown(_VIEW_COOLDOWN, 0)  # 清理全部过期条目
    db = get_db()
    db.execute("UPDATE posts SET views = views + 1 WHERE id = ?", (post_id,))
    db.commit()
    db.close()
    return ('', 204)


# 评论限流：同一 IP 在窗口期内只允许提交一条（防脚本刷评）
_COMMENT_COOLDOWN = {}
_COMMENT_COOLDOWN_WINDOW = 30  # 秒
_COMMENT_MAX_ENTRIES = 5000


def _comments_open():
    """评论总开关。"""
    return str(app.config.get('comments_enabled', '1')) in ('1', 'on', 'true', 'yes')


def _handle_new_comment(post=None, project=None):
    """评论提交的公共逻辑（文章 / 项目详情页共用）。

    post / project 二选一：post 不为空走文章评论（post_id），否则走项目评论（project_id）；
    均不允许同时为空。校验/保存/通知/记忆与文章评论完全一致。
    """
    is_project = project is not None
    target_id = project['id'] if is_project else post['id']
    title = project['name'] if is_project else post['title']
    back = url_for('project_detail', project_id=target_id) if is_project else url_for('post_detail', post_id=target_id)

    # 限流：同一 IP 30 秒内只能发一条（定期清理过期条目防内存泄漏）
    ip = _client_ip()
    now = time.time()
    _prune_cooldown(_COMMENT_COOLDOWN, _COMMENT_COOLDOWN_WINDOW)
    if now - _COMMENT_COOLDOWN.get(ip, 0) < _COMMENT_COOLDOWN_WINDOW:
        flash('评论太频繁，请稍后再试', 'error')
        return redirect(back)

    is_admin = bool(session.get('admin_logged_in'))
    author = request.form.get('author', '').strip()
    content = request.form.get('content', '').strip()
    email = request.form.get('email', '').strip()
    website = request.form.get('website', '').strip()
    # 博主登录后以博主身份评论：昵称/邮箱固定取后台设置，忽略表单
    if is_admin:
        author = app.config.get('author', '') or '博主'
        email = app.config.get('contact_email', '') or ''
        website = ''
    parent_id = request.form.get('parent_id', '').strip()
    is_private = request.form.get('is_private', '') in ('1', 'on', 'true', 'yes')

    # 昵称必填（盖楼需要身份标识）
    if not author or len(author) > 30:
        flash('请填写昵称（30 字以内）', 'error')
        return redirect(back)
    # 昵称保留：博主昵称仅限后台登录态使用，防访客冒充（展示时 is_author 按昵称判定）
    blogger_name = (app.config.get('author') or '').strip()
    if not is_admin and blogger_name and author == blogger_name:
        flash('该昵称已被占用，请换一个', 'error')
        return redirect(back)
    if not content or len(content) > 2000:
        flash('评论内容不能为空且不能超过2000字', 'error')
        return redirect(back)

    # 邮箱选填：仅用于生成 Cravatar 头像，不存明文
    email_hash = ''
    qq = ''
    if email:
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            flash('邮箱格式不正确（选填，仅用于头像）', 'error')
            return redirect(back)
        email_hash = hashlib.md5(email.lower().encode('utf-8')).hexdigest()
        _qm = _QQ_RE.match(email.strip().lower())
        if _qm:
            qq = _qm.group(1)

    # 网址选填：仅允许 http/https，防 javascript: 等伪协议
    if website:
        if not re.match(r'^https?://[^\s]+$', website) or len(website) > 200:
            flash('网址格式不正确（需以 http:// 或 https:// 开头）', 'error')
            return redirect(back)

    # 父级校验：必须是同一载体（文章/项目）下已存在的评论，防跨载体伪造
    pid = None
    parent_author = ''
    if parent_id:
        try:
            pid = int(parent_id)
        except (TypeError, ValueError):
            pid = None
        if pid:
            col = 'project_id' if is_project else 'post_id'
            db = get_db()
            row = db.execute(
                "SELECT id, author FROM comments WHERE id=? AND %s=?" % col, (pid, target_id)
            ).fetchone()
            db.close()
            if not row:
                pid = None
            else:
                parent_author = row['author']

    admin_email = (app.config.get('notify_email') or '').strip()
    status = 'approved' if (email and admin_email and email.lower() == admin_email.lower()) else 'pending'
    cid = db_save_comment(
        None if is_project else target_id, author, email, email_hash, website, content,
        pid, is_private, qq, ip, status=status,
        project_id=target_id if is_project else None)
    _COMMENT_COOLDOWN[ip] = now
    # 条目数超限时强制清理
    if len(_COMMENT_COOLDOWN) > _COMMENT_MAX_ENTRIES:
        _prune_cooldown(_COMMENT_COOLDOWN, 0)
    # 评论邮件通知：配置了 SMTP 时后台线程发送（通知博主 + 被回复者），不阻塞提交、失败静默
    detail_path = ('/projects/%d#comments' if is_project else '/post/%d#comments') % target_id
    if str(app.config.get('comment_notify', '0')) in ('1', 'on', 'true', 'yes'):
        threading.Thread(
            target=_send_comment_notify,
            args=(None if is_project else target_id, title, request.host_url.rstrip('/'),
                  author, content, pid, email, status),
            kwargs={'detail_path': detail_path, 'label': '项目' if is_project else '文章'},
            daemon=True).start()
    # IP 归属地：后台线程查询并回填，未查到则评论不显示归属地（静默）
    if ip and ip != 'unknown':
        threading.Thread(target=_fill_ip_location, args=(cid, ip), daemon=True).start()
    # 记住评论者信息（昵称/邮箱/网址），下次免填；仅存非敏感字段
    # my_comments 记录本人待审核评论 {id: 昵称}，用于前台展示"待审核"徽标
    commenter_data = {'author': author, 'email': email, 'website': website}
    my_comments = {}
    raw = request.cookies.get('blog_commenter')
    if raw:
        try:
            old = json.loads(raw)
            if isinstance(old, dict):
                for k in ('author', 'email', 'website'):
                    if old.get(k):
                        commenter_data[k] = old[k]
                if isinstance(old.get('my_comments'), dict):
                    my_comments = old['my_comments']
        except (ValueError, TypeError):
            pass
    if not is_private:
        my_comments[str(cid)] = author
        # 限制数量防 cookie 膨胀，保留最新 20 条
        if len(my_comments) > 20:
            my_comments = dict(list(my_comments.items())[-20:])
    commenter_data['my_comments'] = my_comments
    resp = make_response(redirect(back + '#comments'))
    resp.set_cookie('blog_commenter',
                    json.dumps(commenter_data, ensure_ascii=False),
                    max_age=30 * 24 * 3600, httponly=True, samesite='Lax')
    flash('私密评论已提交，仅管理员可见' if is_private else ('博主评论已直接显示' if status == 'approved' else '评论已提交，审核通过后显示'), 'success')
    return resp


@app.route('/post/<int:post_id>/comment', methods=['POST'])
def post_comment(post_id):
    # 评论开关关闭时，直接拦截上传
    if not _comments_open():
        abort(403)
    post = db_get_post_by_id(post_id)
    if not post:
        abort(404)
    return _handle_new_comment(post=post)


@app.route('/projects/<int:project_id>/comment', methods=['POST'])
def project_comment(project_id):
    """项目详情页评论提交：与文章评论同一套校验/审核/通知，归属 project_id。"""
    if not _comments_open():
        abort(403)
    project = db_get_project(project_id)
    if not project:
        abort(404)
    return _handle_new_comment(project=project)


def _smtp_send(to_addr, subject, html, overrides=None):
    """发送 HTML 邮件；SMTP 配置缺漏或连接失败时抛异常，由调用方决定吞还是报。
    overrides：测试邮件用——以表单临时配置试发，不落库不改全局配置。"""
    cfg = overrides if overrides is not None else app.config
    host = (cfg.get('smtp_host') or '').strip()
    if not host or not to_addr:
        raise ValueError('SMTP 未配置')
    port = int(cfg.get('smtp_port') or 465)
    user = (cfg.get('smtp_user') or '').strip()
    pwd = cfg.get('smtp_pass') or ''
    sender = (cfg.get('smtp_sender_name') or '').strip() or app.config.get('blog_name') or 'Blog'
    msg = MIMEText(html, 'html', 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = formataddr((sender, user or to_addr))
    msg['To'] = to_addr
    msg['Date'] = email.utils.formatdate(localtime=True)
    if port == 465:
        s = smtplib.SMTP_SSL(host, port, timeout=15)
    else:
        s = smtplib.SMTP(host, port, timeout=15)
        s.ehlo()
        s.starttls()
        s.ehlo()
    if user:
        s.login(user, pwd)
    s.sendmail(user or to_addr, [to_addr], msg.as_string())
    s.quit()


_NOTIFY_CSS = ('body{margin:0;padding:0;background:#eef0f4;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",Arial,sans-serif}'
               '.wrap{max-width:580px;margin:0 auto;padding:28px 16px}.brand{font-size:12px;font-weight:600;color:#98a1b3;letter-spacing:1.5px;margin:0 6px 10px}'
               '.card{background:#fff;border:1px solid #e4e7ee;border-radius:14px;overflow:hidden;box-shadow:0 4px 18px rgba(31,45,80,.06)}'
               '.head{background:linear-gradient(135deg,#5b6cf5,#7c5cf5);color:#fff;padding:18px 22px;font-size:17px;font-weight:700}.head-sub{display:block;font-size:12px;font-weight:400;opacity:.92;margin-top:4px}'
               '.body{padding:20px 22px}.meta{font-size:13px;color:#57606a;margin:6px 0;line-height:1.6}.link a{color:#0969da;text-decoration:none}'
               '.cta-wrap{margin-top:14px}'
               '.cta{display:inline-block;background:#5b6cf5;color:#fff!important;text-decoration:none;font-size:13px;font-weight:600;padding:9px 18px;border-radius:8px}'
               '.quote{margin-top:18px;background:#f6f8fa;border:1px solid #eef0f4;border-left:4px solid #5b6cf5;border-radius:8px;padding:12px 14px}'
               '.q-author{font-size:13px;font-weight:700;color:#24292f;margin-bottom:6px}.q-avatar{display:inline-block;width:26px;height:26px;line-height:26px;text-align:center;border-radius:50%;background:#5b6cf5;color:#fff;font-size:13px;font-weight:700;margin-right:8px}'
               '.q-content{font-size:14px;color:#3a4152;line-height:1.75;white-space:pre-wrap}'
               '.foot{margin:16px 6px 0;font-size:12px;color:#98a1b3;line-height:1.6;text-align:center}')


def _notify_html(head, post_title, post_url, author, content, label='文章'):
    """评论通知邮件 HTML（内嵌样式，兼容主流邮箱客户端）。
    label 为归属载体名称：文章评论传「文章」，项目详情页评论传「项目」。"""
    blog_name = app.config.get('blog_name') or 'Blog'
    av = (author or '匿')[0].upper()
    return (
        '<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head><body>'
        '<div class="wrap">'
        '<div class="brand">%s</div>'
        '<div class="card">'
        '<div class="head">%s<span class="head-sub">%s《%s》</span></div>'
        '<div class="body">'
        '<div class="cta-wrap"><a class="cta" href="%s">查看详情</a></div>'
        '<div class="quote">'
        '<div class="q-author"><span class="q-avatar">%s</span>%s</div>'
        '<div class="q-content">%s</div>'
        '</div></div></div>'
        '<div class="foot">本邮件由 %s 自动发送，请勿直接回复。</div>'
        '</div></body></html>'
    ) % (_NOTIFY_CSS, blog_name, head, label, post_title, post_url,
         av, author or '匿名', content, blog_name)


def _send_comment_notify(post_id, post_title, base_url, author, content, parent_id, commenter_email, status='pending', detail_path=None, label='文章'):
    """后台线程：新评论通知博主；若评论已通过（博主免审核），同时通知被回复者。
    待审核评论的被回复者通知延迟到审核通过后（见 _notify_reply_recipient），
    避免对方点进链接却看不到待审核的回复。SMTP 未配置或发送失败均静默。
    detail_path 为详情页路径：文章评论传 /post/<id>#comments，项目评论传 /projects/<id>#comments；
    不传时按文章规则拼 URL（兼容既有调用）。"""
    try:
        post_url = '%s%s' % (base_url.rstrip('/'), detail_path or ('/post/%d#comments' % post_id))
        notify_email = (app.config.get('notify_email') or '').strip()
        contact_email = (app.config.get('contact_email') or '').strip()
        blogger = notify_email or contact_email
        # 博主身份邮箱集合：notify_email 与 contact_email 任一命中即视为博主
        blogger_emails = {e.lower() for e in (notify_email, contact_email) if e}
        reply = bool(parent_id)
        # 1) 通知博主（博主自己评论/回复时不打扰，仅访客互动才通知）
        if blogger and (not commenter_email or commenter_email.lower() not in blogger_emails):
            kind = '回复通知' if reply else '新评论通知'
            _smtp_send(
                blogger,
                '[%s] %s%s《%s》' % (app.config.get('blog_name') or 'Blog', kind, label, post_title),
                _notify_html(kind, post_title, post_url, author, content, label))
        # 2) 通知被回复者（仅已通过评论；待审核的由审核通过后补发）
        if reply and status == 'approved':
            db = get_db()
            row = db.execute("SELECT author, email FROM comments WHERE id=?", (parent_id,)).fetchone()
            db.close()
            if row and row['email'] and row['email'].lower() not in blogger_emails and row['email'].lower() != (commenter_email or '').lower():
                _smtp_send(
                    row['email'],
                    '[%s] 你的评论收到新回复%s《%s》' % (app.config.get('blog_name') or 'Blog', label, post_title),
                    _notify_html('你的评论收到一条新回复', post_title, post_url, author, content, label))
    except Exception as e:
        print('[评论通知] 邮件发送失败：%s' % e)


def _notify_reply_recipient(comment_id, base_url):
    """审核通过后补发：通知被回复者（若其评论填过邮箱且不是博主本人、也不是评论者自己）。
    同时兼容文章评论与项目详情页评论。后台线程调用，失败静默。"""
    try:
        db = get_db()
        row = db.execute(
            "SELECT c.post_id, c.project_id, c.author, c.content, c.parent_id, c.email AS commenter_email, "
            "p.title AS post_title, pj.name AS project_name "
            "FROM comments c LEFT JOIN posts p ON p.id = c.post_id "
            "LEFT JOIN projects pj ON pj.id = c.project_id WHERE c.id = ?",
            (comment_id,)).fetchone()
        if not row or not row['parent_id']:
            db.close()
            return
        parent = db.execute(
            "SELECT author, email FROM comments WHERE id = ?", (row['parent_id'],)).fetchone()
        db.close()
        if not parent or not parent['email']:
            return
        notify_email = (app.config.get('notify_email') or '').strip()
        contact_email = (app.config.get('contact_email') or '').strip()
        blogger_emails = {e.lower() for e in (notify_email, contact_email) if e}
        if parent['email'].lower() in blogger_emails:
            return
        if parent['email'].lower() == (row['commenter_email'] or '').lower():
            return
        # 归属载体不同，详情页地址与文案随之变化
        if row['project_id']:
            label = '项目'
            title = row['project_name'] or '项目'
            detail_path = '/projects/%d#comments' % row['project_id']
        else:
            label = '文章'
            title = row['post_title'] or ''
            detail_path = '/post/%d#comments' % row['post_id']
        post_url = '%s%s' % (base_url.rstrip('/'), detail_path)
        _smtp_send(
            parent['email'],
            '[%s] 你的评论收到新回复%s《%s》' % (app.config.get('blog_name') or 'Blog', label, title),
            _notify_html('你的评论收到一条新回复', title, post_url, row['author'], row['content'], label))
    except Exception as e:
        print('[评论通知] 回复通知发送失败：%s' % e)


@app.route('/tags')
def tags():
    """标签页：标签云 + 按标签分组的文章列表（对齐 leelaa 标签页结构）。"""
    if not nav_enabled('tags'):
        abort(404)
    posts, total = db_load_posts(status='published', page=1, per_page=99999)
    categories = {c['id']: c['name'] for c in db_load_categories()}
    buckets = {}
    for p in posts:
        cid = p.get('category_id')
        p['category_name'] = categories.get(cid, '') if cid else ''
        for t in p['tags']:
            buckets.setdefault(t, []).append(p)
    # 按文章数降序，再按标签名字母序
    ordered = sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return render_template('tags.html', tag_groups=ordered, post_total=total)


@app.route('/about')
def about():
    if not nav_enabled('about'):
        abort(404)
    skills_str = app.config.get('skills', '[]')
    try:
        skills = json.loads(skills_str)
    except json.JSONDecodeError:
        skills = []
    about_intro = app.config.get('about_intro', '')
    author = app.config.get('author', '')
    github = app.config.get('github_username', '') or app.config.get('social_github', '')
    # 关于页 Hero 统计（与首页口径一致：仅统计已发布文章）
    _, post_total = db_load_posts(status='published', page=1, per_page=1)
    category_total = len(db_load_categories())
    db = get_db()
    timeline_rows = db.execute(
        "SELECT id, date, content FROM timeline ORDER BY sort_order ASC, date DESC"
    ).fetchall()
    db.close()
    timeline = [dict(r) for r in timeline_rows]
    return render_template('about.html', skills=skills, about_intro=about_intro,
                           author=author, github=github, timeline=timeline,
                           post_total=post_total, category_total=category_total)


@app.route('/status')
def status_page():
    """前台服务状态页（Sever Status）。SSR 首批数据 + JS 轮询 /api/status。"""
    if not nav_enabled('status'):
        abort(404)
    return render_template('status.html', expiry=get_expiry_info(),
                           services=get_services_status())


@app.route('/api/status')
def api_status():
    """公开 JSON：云资源到期信息 + 各服务最新探测与可用率（不含任何密钥）。"""
    return jsonify({
        'expiry': get_expiry_info(),
        'services': get_services_status(),
        'generated_at': int(time.time()),
    })


# GitHub 语言调色板（名称 -> 颜色），未知语言回退灰色
LANGUAGE_COLORS = {
    'JavaScript': '#f1e05a', 'TypeScript': '#3178c6', 'Python': '#3572A5',
    'Go': '#00ADD8', 'Rust': '#dea584', 'Java': '#b07219', 'C': '#555555',
    'C++': '#f34b7d', 'C#': '#178600', 'HTML': '#e34c26', 'CSS': '#563d7c',
    'Shell': '#89e051', 'PowerShell': '#012A60', 'Vue': '#41b883', 'Ruby': '#701516',
    'PHP': '#4F5D95', 'Swift': '#F05138', 'Kotlin': '#A97BFF', 'Dart': '#00B4AB',
    'Lua': '#000080', 'Dockerfile': '#384d54', 'Makefile': '#427819', 'R': '#198CE7',
    'Objective-C': '#438eff', 'Scala': '#c22d40', 'Perl': '#0298c3', 'Haskell': '#5e5086',
    'Elixir': '#6e4a7e', 'Clojure': '#db5855', 'Racket': '#3c5caa', 'Assembly': '#6E4C13',
    'Zig': '#ec915c', 'Nix': '#7e7eff', 'YAML': '#cb171e', 'JSON': '#292929',
}


def lang_color(name):
    return LANGUAGE_COLORS.get(name, '#8b949e')


@app.route('/projects')
def projects_page():
    if not nav_enabled('projects'):
        abort(404)
    projects = db_load_projects()
    # 按语言统计（支持多语言，从 languages JSON 列表聚合）
    languages = {}
    for p in projects:
        try:
            langs = json.loads(p['languages']) if p['languages'] else []
        except (ValueError, TypeError):
            langs = []
        # 兼容旧数据：未迁移的语言列表为空但 language 字段有值时，当作单语言
        if not langs and p['language']:
            langs = [[p['language'], 100]]
        # 注入颜色字段： [[name, pct], ...] -> [[name, pct, color], ...]
        p['lang_list'] = [[name, pct, lang_color(name)] for name, pct in langs]
        p['lang_names'] = ','.join([name for name, _, _ in p['lang_list']])
        for item in langs:
            lang = item[0] if isinstance(item, (list, tuple)) else item
            languages[lang] = languages.get(lang, 0) + 1
    return render_template('projects.html', projects=projects, languages=languages)


@app.route('/projects/<int:project_id>')
def project_detail(project_id):
    """项目详情页：顶部项目卡片（访问 GitHub 入口）+ 中部 README 区 + 底部评论区。"""
    if not nav_enabled('projects'):
        abort(404)
    project = db_get_project(project_id)
    if not project:
        abort(404)
    # 语言徽章配色（与列表页一致）：[[name, pct, color], ...]
    try:
        langs = json.loads(project['languages']) if project['languages'] else []
    except (ValueError, TypeError):
        langs = []
    if not langs and project['language']:
        langs = [[project['language'], 100]]
    project['lang_list'] = [[n, pct, lang_color(n)] for n, pct in langs]
    project['lang_names'] = ','.join(n for n, _, _ in project['lang_list'])

    # GitHub 实时数据 + README（内存缓存 + 磁盘持久化）。
    # 前台零 GitHub 请求：缓存只在管理员后台「新增/同步/一键同步全部」时写入；
    # 详情页直接读快照，无缓存则显示「未同步」提示（管理员可在后台点同步拉取）。
    slug = (project.get('github_repo') or '').strip() or parse_github_repo(project.get('url') or '')
    cached = project_cache_snapshot(slug) if slug else None
    if cached:
        gh = dict(cached)
        gh['cached'] = True
    else:
        gh = {'gh': None, 'readme': None, 'branch': '', 'ts': 0, 'error': '', 'cached': False}
    # README 抓取时间 → 「更新于 X 前」文案：分钟超过阈值自动切换为小时/天/月/年，
    # 避免出现「760 分钟前」这种长串数字。30 天按月，365 天按年取整数。
    if gh['ts']:
        diff = max(0, time.time() - gh['ts'])
        if diff < 60:
            gh['age_text'] = '刚刚'
        elif diff < 3600:
            gh['age_text'] = '%d 分钟前' % int(diff / 60)
        elif diff < 86400:
            gh['age_text'] = '%d 小时前' % int(diff / 3600)
        elif diff < 86400 * 30:
            gh['age_text'] = '%d 天前' % int(diff / 86400)
        elif diff < 86400 * 365:
            gh['age_text'] = '%d 个月前' % int(diff / (86400 * 30))
        else:
            gh['age_text'] = '%d 年前' % int(diff / (86400 * 365))
    else:
        gh['age_text'] = ''

    comments_enabled = _comments_open()
    is_admin = bool(session.get('admin_logged_in'))
    # 读取记住的评论者信息（昵称/邮箱/网址），用于表单预填；my_comments 用于展示本人待审核评论
    commenter = {}
    raw = request.cookies.get('blog_commenter')
    if raw:
        try:
            commenter = json.loads(raw)
        except (ValueError, TypeError):
            commenter = {}
    my_comments = commenter.get('my_comments') if isinstance(commenter, dict) else None
    comments, comment_total = (db_load_comments(project_id=project_id, include_private=is_admin,
                                                my_comments=my_comments)
                               if comments_enabled else ([], 0))
    # 本人待审核评论数（管理员视角下 pending 全部可见，无需再提示）
    my_pending = 0 if is_admin else _count_pending(comments)
    # 博主身份条头像（与文章页一致）
    admin_avatar = ''
    if is_admin:
        contact = (app.config.get('contact_email') or '').strip().lower()
        if contact:
            _cm = _QQ_RE.match(contact)
            if _cm:
                admin_avatar = url_for('avatar_proxy', key='q' + _cm.group(1), size=40, _external=True)
            else:
                admin_avatar = _avatar_url(hashlib.md5(contact.encode('utf-8')).hexdigest(), 40)

    return render_template('project_detail.html', project=project, gh=gh,
                           comments=comments, comment_total=comment_total,
                           comments_enabled=comments_enabled,
                           commenter=commenter, is_admin=is_admin,
                           admin_avatar=admin_avatar, my_pending=my_pending)


@app.route('/links')
def links_page():
    links = db_load_links(status='approved')
    return render_template('links.html', links=links)


@app.route('/links/apply', methods=['GET', 'POST'])
def links_apply():
    if not nav_enabled('links'):
        abort(404)
    if request.method == 'POST':
        form = request.form
        name = (form.get('name') or '').strip()
        url = (form.get('url') or '').strip()
        description = (form.get('description') or '').strip()
        avatar = (form.get('avatar') or '').strip()
        if not name or not url:
            flash('请填写名称和网址', 'error')
            return render_template('links_apply.html', form=form)
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        db_save_link({'name': name, 'url': url, 'description': description, 'avatar': avatar, 'sort_order': 0},
                     status='pending')
        flash('申请已提交，等待管理员审核', 'success')
        return redirect(url_for('links_page'))
    return render_template('links_apply.html', form=None)


@app.route('/search')
def search():
    q = request.args.get('q', '')
    if not q:
        return redirect(url_for('index'))
    return redirect(url_for('index', q=q))


@app.route('/feed.xml')
def rss_feed():
    """RSS 订阅"""
    posts, _ = db_load_posts(page=1, per_page=20)
    from xml.etree.ElementTree import Element, SubElement, tostring
    from xml.dom import minidom

    rss = Element('rss', version='2.0')
    channel = SubElement(rss, 'channel')
    blog_name = app.config.get('blog_name', 'infowe')
    SubElement(channel, 'title').text = blog_name
    SubElement(channel, 'link').text = request.url_root
    SubElement(channel, 'description').text = app.config.get('blog_subtitle', '')
    SubElement(channel, 'language').text = 'zh-CN'

    for p in posts:
        item = SubElement(channel, 'item')
        SubElement(item, 'title').text = p['title']
        SubElement(item, 'link').text = request.url_root + 'post/' + str(p['id'])
        SubElement(item, 'description').text = p['excerpt'] or ''
        # RSS pubDate 必须是 RFC822 格式且带时区；DB 存的是中国时区(CST)，
        # 把字符串当本地时间替换 +08:00 timezone 后格式化输出。
        try:
            _cst_tz = timezone(_td(hours=8))
            dt = datetime.strptime(p['created_at'][:19], '%Y-%m-%d %H:%M:%S').replace(tzinfo=_cst_tz)
            pub = email.utils.format_datetime(dt)
        except Exception:
            pub = p['created_at']  # 解析失败时降级为原值，避免 RSS 整体 500
        SubElement(item, 'pubDate').text = pub
        SubElement(item, 'guid').text = request.url_root + 'post/' + str(p['id'])

    xml_str = minidom.parseString(tostring(rss, 'utf-8')).toprettyxml(indent='  ')
    return app.response_class(xml_str, mimetype='application/rss+xml')


@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(e):
    # 生产环境统一返回站内风格的错误页，避免泄露调试信息
    if getattr(app, 'debug', False):
        raise e  # 开发模式下仍显示原始异常，便于排查
    return render_template('500.html'), 500


# ─────────────── 后台: 登录 ───────────────

@app.route('/admin')
def admin_index():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    # 账号密码已通过、OTP 尚未验证时直达 /admin → 直接进 OTP 验证页
    if session.get('_otp_user'):
        return redirect(url_for('admin_otp'))
    return redirect(url_for('admin_login'))


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    # 账号密码已通过、正等 OTP 时若回到登录页，转去 OTP 验证
    if session.get('_otp_user'):
        return redirect(url_for('admin_otp'))
    ip = _client_ip()
    error = None
    if _login_blocked(ip):
        error = '尝试次数过多，请 %d 分钟后再试' % (_LOGIN_LOCK_SECONDS // 60)
        return render_template('admin/login.html', error=error)

    captcha_required = _captcha_required(ip)
    # 仅在需要验证码、且 session 尚未持有题目时才生成（避免 POST 覆盖正确答案）
    if captcha_required and 'captcha_answer' not in session:
        _gen_captcha()
    captcha_question = session.get('_captcha_q') if captcha_required else None

    if request.method == 'POST':
        # 验证码校验（仅当已触发要求时）
        if captcha_required:
            try:
                user_ans = int(request.form.get('captcha', '').strip())
            except (ValueError, TypeError):
                user_ans = None
            if user_ans != session.get('captcha_answer'):
                _register_fail(ip)
                error = '验证码错误'
                captcha_question = _gen_captcha()  # 刷新验证码
                return render_template('admin/login.html', error=error,
                                       captcha_required=True, captcha_question=captcha_question)
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        db.close()
        if user and verify_password(user['password_hash'], password):
            # 懒迁移：旧格式哈希验证通过则升级为新格式
            if not user['password_hash'].startswith(('pbkdf2:', 'scrypt:', 'bcrypt:')):
                db = get_db()
                db.execute("UPDATE users SET password_hash=? WHERE username=?",
                           (hash_password(password), username))
                db.commit()
                db.close()
            _register_success(ip)
            session.pop('captcha_answer', None)
            if _otp_emergency_off():
                # 服务器上存在紧急禁用标记：临时跳过 OTP（登录后设置页会提示处理）
                session['admin_logged_in'] = True
                session['admin_username'] = username
                flash('检测到 OTP 紧急禁用标记（data/.otp_disable），本次登录已跳过 OTP 验证，请尽快到设置页处理', 'error')
                return redirect(url_for('admin_settings'))
            if _otp_enabled():
                # OTP 已开启：先进入第二因子验证页，验证通过才真正登录
                session['_otp_user'] = username
                return redirect(url_for('admin_otp'))
            session['admin_logged_in'] = True
            session['admin_username'] = username
            return redirect(url_for('admin_dashboard'))
        else:
            _register_fail(ip)
            rec = _LOGIN_ATTEMPTS.get(ip)
            remaining = _LOGIN_MAX_FAILS - (rec['fails'] if rec else 0)
            # 失败达到阈值后下一次需验证码
            if _captcha_required(ip):
                captcha_question = _gen_captcha()
                captcha_required = True
            if rec and rec.get('lock_until', 0) > time.time():
                error = '尝试次数过多，请 %d 分钟后再试' % (_LOGIN_LOCK_SECONDS // 60)
            else:
                error = '用户名或密码错误' + ('（还可尝试 %d 次）' % max(remaining, 0) if remaining > 0 else '')
    return render_template('admin/login.html', error=error,
                           captcha_required=captcha_required, captcha_question=captcha_question,
                           now_year=time.strftime('%Y'))


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))


# ─────────────── 后台: OTP 双重验证 ───────────────

@app.route('/admin/otp', methods=['GET', 'POST'])
def admin_otp():
    """OTP 第二因子验证页：账号密码通过后进入，输入 6 位验证码或 8 位恢复码。"""
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    username = session.get('_otp_user')
    if not username:
        return redirect(url_for('admin_login'))
    if not _otp_enabled():
        # OTP 中途被关闭/重置（如邮箱找回）时直接放行，并清掉中间态
        session.pop('_otp_user', None)
        session['admin_logged_in'] = True
        session['admin_username'] = username
        return redirect(url_for('admin_dashboard'))

    error = None
    mail_ok = bool((app.config.get('smtp_host') or '').strip())
    if request.method == 'POST':
        code = (request.form.get('code') or '').strip()
        if not code:
            error = '请输入验证码或恢复码'
        elif _otp_emergency_off():
            # 管理员已在服务器放了紧急标记：本次验证直接放行
            session.pop('_otp_user', None)
            session['admin_logged_in'] = True
            session['admin_username'] = username
            flash('检测到 OTP 紧急禁用标记（data/.otp_disable），本次登录已跳过 OTP 验证，请尽快到设置页处理', 'error')
            return redirect(url_for('admin_settings'))
        elif _consume_recovery(code):
            session.pop('_otp_user', None)
            session['admin_logged_in'] = True
            session['admin_username'] = username
            return redirect(url_for('admin_dashboard'))
        elif _totp_verify(_otp_secret(), code):
            session.pop('_otp_user', None)
            session['admin_logged_in'] = True
            session['admin_username'] = username
            return redirect(url_for('admin_dashboard'))
        else:
            _register_fail(_client_ip())  # 复用登录防爆破：失败延迟 + 锁定，拖慢爆破
            error = '验证码或恢复码错误'

    return render_template('admin/otp.html',
                           error=error,
                           user=username,
                           recovery_left=_otp_recovery_remaining(),
                           mail_ok=mail_ok,
                           now_year=time.strftime('%Y'))


@app.route('/admin/otp/recover', methods=['GET', 'POST'])
def admin_otp_recover():
    """OTP 丢失找回：向绑定邮箱发 6 位一次性验证码，验证通过后重置 OTP（需重新绑定）。"""
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    username = session.get('_otp_user')
    if not username:
        return redirect(url_for('admin_login'))

    target = (app.config.get('notify_email') or '').strip() or (app.config.get('contact_email') or '').strip()
    if not (app.config.get('smtp_host') or '').strip():
        return render_template('admin/otp_recover.html', user=username, step='unavailable', target='',
                               sent=False, error='服务器未配置 SMTP，无法邮件找回。可用恢复码登录，'
                                                 '或由服务器管理员执行 touch data/.otp_disable 临时跳过。',
                               now_year=time.strftime('%Y'))

    error = None
    sent = False
    step = 'send'
    if request.method == 'POST':
        action = request.form.get('action', '')
        if action == 'send':
            if not target:
                error = '管理员未设置联系邮箱（notify_email / contact_email），无法接收验证码'
            else:
                last = session.get('_otp_mail_ts') or 0
                if time.time() - last < 60:
                    error = '发送过于频繁，请 %d 秒后再试' % int(60 - (time.time() - last))
                else:
                    mail_code = '%06d' % random.randint(0, 999999)
                    try:
                        _smtp_send(
                            target,
                            '[%s] OTP 找回验证码' % (app.config.get('blog_name') or 'Blog'),
                            ('<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head><body>'
                             '<div class="wrap"><div class="card">'
                             '<div class="head">OTP 找回验证码</div>'
                             '<div class="meta">你的博客后台 OTP 双重验证已丢失，请使用以下验证码重置：</div>'
                             '<div class="code" style="font-size:28px;letter-spacing:4px;font-weight:bold;margin:12px 0;">%s</div>'
                             '<div class="meta">10 分钟内有效。验证通过后 OTP 会被关闭，请重新登录并绑定新密钥。</div>'
                             '</div></div></body></html>') % (_NOTIFY_CSS, mail_code))
                        session['_otp_mail_code'] = mail_code
                        session['_otp_mail_ts'] = int(time.time())
                        sent = True
                        step = 'verify'
                    except Exception as e:
                        session.pop('_otp_mail_code', None)
                        error = '邮件发送失败：%s' % e
        elif action == 'verify':
            step = 'verify'
            code = (request.form.get('mail_code') or '').strip()
            issued = session.get('_otp_mail_code')
            issued_ts = session.get('_otp_mail_ts') or 0
            if not issued or time.time() - issued_ts > 600:
                error = '验证码已过期，请重新发送'
                step = 'send'
            elif not code or not hmac.compare_digest(issued, code):
                _register_fail(_client_ip())
                error = '验证码错误'
            else:
                # 通过：重置 OTP（关闭开关 + 清空密钥/恢复码），随后进入后台引导重新绑定
                session.pop('_otp_mail_code', None)
                session.pop('_otp_mail_ts', None)
                session.pop('_otp_user', None)
                db = get_db()
                for k in ('otp_enabled', 'otp_secret', 'otp_recovery_codes'):
                    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, '')", (k,))
                db.commit()
                db.close()
                for k in ('otp_enabled', 'otp_secret', 'otp_recovery_codes'):
                    app.config[k] = ''
                session['admin_logged_in'] = True
                session['admin_username'] = username
                flash('邮箱验证通过，OTP 已临时关闭。已为你打开重新绑定流程，扫码确认即可重新开启；'
                      '如暂不使用 OTP 保持现状即可', 'success')
                # 直接定位到设置页「安全验证」卡片并自动展开绑定流程（otp_rebind=1 触发前端钩子）
                return redirect(url_for('admin_settings', _anchor='otp-card', otp_rebind='1'))
    # 邮箱仅掩码展示（ow***@example.com），防验证页泄露完整绑定邮箱
    return render_template('admin/otp_recover.html', user=username, step=step, target=target,
                           masked=_mask_email(target), sent=sent, error=error,
                           now_year=time.strftime('%Y'))


def _mask_email(addr):
    """邮箱掩码：ab***@domain.com（本地部分保留前 2 位）。空/无效地址返回空串，由模板走未设置分支。"""
    addr = (addr or '').strip()
    if not addr or '@' not in addr:
        return ''
    local, domain = addr.split('@', 1)
    return (local[:2] if local else '**') + '***@' + domain


@app.route('/admin/forgot', methods=['GET', 'POST'])
def admin_forgot():
    """忘记密码找回：向绑定邮箱发 6 位一次性验证码，验证通过后设置新密码（无需登录）。"""
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    target = (app.config.get('notify_email') or '').strip() or (app.config.get('contact_email') or '').strip()
    if not (app.config.get('smtp_host') or '').strip():
        return render_template('admin/forgot.html', step='unavailable', masked='',
                               error='服务器未配置 SMTP，无法通过邮件找回密码。'
                                     '请由服务器管理员在数据库中重置，或联系部署者处理。',
                               now_year=time.strftime('%Y'))

    error = None
    step = 'send'
    if request.method == 'POST':
        action = request.form.get('action', '')
        if action == 'send':
            # 单管理员（users 表由触发器硬保证恰好 1 条）：重置目标即唯一账号
            db = get_db()
            row = db.execute("SELECT username FROM users LIMIT 1").fetchone()
            db.close()
            if not row:
                error = '未找到管理员账号，无法找回'
            elif not target:
                error = '管理员未设置联系邮箱（notify_email / contact_email），无法接收验证码'
            else:
                last = session.get('_fp_ts') or 0
                if time.time() - last < 60:
                    error = '发送过于频繁，请 %d 秒后再试' % int(60 - (time.time() - last))
                else:
                    fp_user = row['username']
                    mail_code = '%06d' % random.randint(0, 999999)
                    try:
                        _smtp_send(
                            target,
                            '[%s] 后台密码找回验证码' % (app.config.get('blog_name') or 'Blog'),
                            ('<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head><body>'
                             '<div class="wrap"><div class="card">'
                             '<div class="head">后台密码找回验证码</div>'
                             '<div class="meta">收到本邮件说明有人请求重置博客后台账号「%s」的登录密码。验证码：</div>'
                             '<div class="code" style="font-size:28px;letter-spacing:4px;font-weight:bold;margin:12px 0;">%s</div>'
                             '<div class="meta">10 分钟内有效。若非本人操作，请忽略本邮件并检查后台安全设置。</div>'
                             '</div></div></body></html>') % (_NOTIFY_CSS, fp_user, mail_code))
                        session['_fp_code'] = mail_code
                        session['_fp_ts'] = int(time.time())
                        session['_fp_user'] = fp_user   # 重置目标锁定到该账号
                        session.pop('_fp_ok', None)     # 新码作废旧的验证通过态
                        step = 'verify'
                    except Exception as e:
                        session.pop('_fp_code', None)
                        error = '邮件发送失败：%s' % e
        elif action == 'verify':
            step = 'verify'
            code = (request.form.get('mail_code') or '').strip()
            issued = session.get('_fp_code')
            issued_ts = session.get('_fp_ts') or 0
            if not issued or time.time() - issued_ts > 600:
                error = '验证码已过期，请重新发送'
                step = 'send'
            elif not code or not hmac.compare_digest(issued, code):
                _register_fail(_client_ip())
                error = '验证码错误'
            else:
                # 码正确：进入设置新密码步骤（10 分钟内完成）
                session['_fp_ok'] = True
                step = 'newpass'
        elif action == 'newpass':
            fp_user = session.get('_fp_user') or ''
            issued_ts = session.get('_fp_ts') or 0
            if not session.get('_fp_ok') or not session.get('_fp_code') or time.time() - issued_ts > 600:
                error = '操作已超时，请重新走找回流程'
                step = 'send'
            else:
                new_password = request.form.get('new_password') or ''
                new_password2 = request.form.get('new_password2') or ''
                if len(new_password) < 6:
                    error = '新密码至少 6 位字符'
                    step = 'newpass'
                elif new_password != new_password2:
                    error = '两次输入的密码不一致'
                    step = 'newpass'
                else:
                    # 重置精确锁定到发码时校验过的账号
                    db = get_db()
                    row = db.execute("SELECT username FROM users WHERE username=?", (fp_user,)).fetchone()
                    if not row:
                        error = '账号不存在，无法重置'
                        step = 'newpass'
                    else:
                        db.execute("UPDATE users SET password_hash=? WHERE username=?",
                                   (hash_password(new_password), fp_user))
                        db.commit()
                        db.close()
                        for k in ('_fp_code', '_fp_ts', '_fp_ok', '_fp_user'):
                            session.pop(k, None)
                        flash('密码已重置，请使用新密码登录', 'success')
                        return redirect(url_for('admin_login'))
    masked = _mask_email(target)
    # 展示用唯一账号名（模板只读显示）
    db = get_db()
    _row = db.execute("SELECT username FROM users LIMIT 1").fetchone()
    db.close()
    fp_user_display = _row['username'] if _row else ''
    return render_template('admin/forgot.html', step=step, masked=masked, fp_user=fp_user_display,
                           error=error, now_year=time.strftime('%Y'))


@app.route('/admin/otp/setup')
@admin_required
def admin_otp_setup():
    """设置页「生成二维码」：返回全新 base32 密钥与 otpauth URI（JSON）。"""
    secret = _otp_new_secret()
    username = session.get('admin_username', 'admin')
    return jsonify(secret=secret, uri=_otpauth_uri(secret, username))


@app.route('/admin/otp/clear-emergency', methods=['POST'])
@admin_required
def admin_otp_clear_emergency():
    """清除 OTP 紧急禁用标记文件，恢复双重验证。"""
    try:
        os.remove(_OTP_EMERGENCY_FILE)
        flash('OTP 紧急禁用标记已清除，双重验证已恢复', 'success')
    except OSError:
        flash('标记文件不存在或无法删除', 'error')
    return redirect(url_for('admin_settings'))


# ─────────────── 后台: 仪表盘 ───────────────

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    stats = db_get_stats()
    posts, _ = db_load_posts(status=None, per_page=5)
    recent = sorted(posts, key=lambda x: x['updated_at'], reverse=True)[:5]
    return render_template('admin/dashboard.html', stats=stats, recent=recent)


# ─────────────── 后台: 文章分类管理 ───────────────

@app.route('/admin/categories')
@admin_required
def admin_categories():
    categories = db_load_categories()
    return render_template('admin/categories.html', categories=categories)


@app.route('/admin/categories/new', methods=['GET', 'POST'])
@admin_required
def admin_category_new():
    if request.method == 'POST':
        db_save_category(request.form)
        flash('分类已创建', 'success')
        return redirect(url_for('admin_categories'))
    return render_template('admin/category_edit.html', category=None)


@app.route('/admin/categories/<int:cat_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_category_edit(cat_id):
    category = db_get_category(cat_id)
    if not category:
        abort(404)
    if request.method == 'POST':
        db_save_category(request.form, cat_id)
        flash('分类已更新', 'success')
        return redirect(url_for('admin_categories'))
    return render_template('admin/category_edit.html', category=category)


@app.route('/admin/categories/<int:cat_id>/delete', methods=['POST'])
@admin_required
def admin_category_delete(cat_id):
    db_delete_category(cat_id)
    flash('分类已删除', 'success')
    return redirect(url_for('admin_categories'))


@app.route('/admin/categories/bulk', methods=['POST'])
@admin_required
def admin_categories_bulk():
    """分类批量删除：解绑该分类下所有文章为未分类，再删除。"""
    action = request.form.get('action')
    ids = request.form.getlist('cat_ids')
    if action != 'delete':
        flash('无效的批量操作', 'error')
        return redirect(url_for('admin_categories'))
    if not ids:
        flash('未选择任何分类', 'error')
        return redirect(url_for('admin_categories'))
    for cid in ids:
        db_delete_category(int(cid))
    flash('已删除 %d 个分类（该分类下文章已变为未分类）' % len(ids), 'success')
    return redirect(url_for('admin_categories'))


# ─────────────── 后台: 文章管理 ───────────────

@app.route('/admin/posts')
@admin_required
def admin_posts():
    status_filter = request.args.get('status', 'all')
    search = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)

    if status_filter == 'all':
        posts, total = db_load_posts(status=None, search=search if search else None, page=page)
    else:
        posts, total = db_load_posts(status=status_filter, search=search if search else None, page=page)

    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    return render_template('admin/posts.html', posts=posts, status_filter=status_filter,
                           search_query=search, page=page, total_pages=total_pages, total=total)


@app.route('/admin/posts/bulk', methods=['POST'])
@admin_required
def admin_posts_bulk():
    """文章批量操作：publish 批量发布 / unpublish 批量下线 / delete 批量删除。"""
    action = request.form.get('action')
    ids = request.form.getlist('post_ids')
    if action not in ('publish', 'unpublish', 'delete'):
        flash('无效的批量操作', 'error')
        return redirect(url_for('admin_posts'))
    if not ids:
        flash('未选择任何文章', 'error')
        return redirect(url_for('admin_posts'))
    db = get_db()
    if action == 'delete':
        db.close()
        for pid in ids:
            db_delete_post(int(pid))
        flash('已删除 %d 篇文章' % len(ids), 'success')
    else:
        new_status = 'published' if action == 'publish' else 'draft'
        db.execute("UPDATE posts SET status=? WHERE id IN (%s)"
                   % ','.join('?' * len(ids)), [new_status] + ids)
        db.commit()
        db.close()
        flash('已将 %d 篇文章设为「%s」' % (len(ids), '已发布' if action == 'publish' else '草稿'), 'success')
    return redirect(url_for('admin_posts'))


@app.route('/admin/posts/new', methods=['GET', 'POST'])
@admin_required
def admin_post_new():
    categories = db_load_categories()
    render_kwargs = {'post': None, 'categories': categories, 'all_tags': db_get_all_tags()}
    if request.method == 'POST':
        # 新建文章必须选择分类
        category_id_raw = (request.form.get('category_id') or '').strip()
        if not category_id_raw.isdigit():
            flash('请选择文章分类', 'error')
            return render_template('admin/post_edit.html', **render_kwargs)
        db_save_post(request.form)
        flash('文章已创建', 'success')
        return redirect(url_for('admin_posts'))
    return render_template('admin/post_edit.html', **render_kwargs)


@app.route('/admin/posts/<int:post_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_post_edit(post_id):
    post = db_get_post_by_id(post_id)
    if not post:
        flash('文章不存在', 'error')
        return redirect(url_for('admin_posts'))
    if request.method == 'POST':
        db_save_post(request.form, post_id)
        flash('文章已更新', 'success')
        return redirect(url_for('admin_posts'))
    categories = db_load_categories()
    # 加载编辑页时把自动链接 <URL> 规范化为标准链接，避免 Vditor 往返丢弃
    if post and post.get('content'):
        post['content'] = normalize_auto_links(post['content'])
    return render_template('admin/post_edit.html', post=post, categories=categories,
                           all_tags=db_get_all_tags())


@app.route('/admin/posts/<int:post_id>/delete', methods=['POST'])
@admin_required
def admin_post_delete(post_id):
    removed = db_delete_post(post_id)
    if removed:
        flash('文章已删除，并清理 %d 个不再被引用的上传文件' % len(removed), 'success')
    else:
        flash('文章已删除（引用的上传文件仍被其他内容使用，已保留）', 'success')
    return redirect(url_for('admin_posts'))


@app.route('/admin/posts/<int:post_id>/preview')
@admin_required
def admin_post_preview(post_id):
    post = db_get_post_by_id(post_id)
    if not post:
        return jsonify({'html': ''})
    html, _ = render_post_content(post['content'])
    return jsonify({'html': html})


@app.route('/admin/posts/preview-content', methods=['POST'])
@admin_required
def admin_preview_content():
    content = request.form.get('content', '')
    html, _ = render_post_content(content)
    return jsonify({'html': html})


# ─────────────── 后台: 项目管理 ───────────────

@app.route('/admin/projects')
@admin_required
def admin_projects():
    projects = db_load_projects()
    for p in projects:
        try:
            raw = json.loads(p['languages']) if p['languages'] else []
        except (ValueError, TypeError):
            raw = []
        if not raw and p['language']:
            raw = [[p['language'], 100]]
        p['lang_list'] = [[name, pct, lang_color(name)] for name, pct in raw]
    return render_template('admin/projects.html', projects=projects)


@app.route('/admin/projects/new', methods=['GET', 'POST'])
@admin_required
def admin_project_new():
    if request.method == 'POST':
        slug = parse_github_repo(request.form.get('url', ''))
        if slug and db_repo_exists(slug):
            flash('该项目已存在，不能重复添加（' + slug + '）', 'error')
            return render_template('admin/project_edit.html', project=None)
        db_save_project(request.form)
        # 同时同步 README 入缓存（管理员手动触发，前台零 GitHub 请求）
        if slug:
            fetch_project_github(request.form.get('url', ''))
        flash('项目已添加（已从 GitHub 同步实时数据）', 'success')
        return redirect(url_for('admin_projects'))
    return render_template('admin/project_edit.html', project=None)


@app.route('/admin/projects/<int:project_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_project_edit(project_id):
    db = get_db()
    row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        db.close()
        flash('项目不存在', 'error')
        return redirect(url_for('admin_projects'))
    project = dict(row)
    project['topics'] = json.loads(project['topics'])
    db.close()
    if request.method == 'POST':
        db_save_project(request.form, project_id)
        flash('项目已更新', 'success')
        return redirect(url_for('admin_projects'))
    return render_template('admin/project_edit.html', project=project)


@app.route('/admin/projects/<int:project_id>/delete', methods=['POST'])
@admin_required
def admin_project_delete(project_id):
    db_delete_project(project_id)
    flash('项目已删除', 'success')
    return redirect(url_for('admin_projects'))


@app.route('/admin/projects/bulk', methods=['POST'])
@admin_required
def admin_projects_bulk():
    """项目批量操作：delete 批量删除。"""
    action = request.form.get('action')
    ids = request.form.getlist('project_ids')
    if action != 'delete':
        flash('无效的批量操作', 'error')
        return redirect(url_for('admin_projects'))
    if not ids:
        flash('未选择任何项目', 'error')
        return redirect(url_for('admin_projects'))
    for pid in ids:
        db_delete_project(int(pid))
    flash('已删除 %d 个项目' % len(ids), 'success')
    return redirect(url_for('admin_projects'))


@app.route('/admin/projects/<int:project_id>/sync', methods=['POST'])
@admin_required
def admin_project_sync(project_id):
    """同步单个项目：转入后台线程执行（含 README 图片本地化，可能耗时 1-2 分钟，
    同步执行会超 nginx 60s 上游超时）。前端 AJAX 提交，立即返回 JSON（不再 302
    跳转，避免页面闪跳），进度经 /admin/projects/sync-status 原地轮询。"""
    projects = db_load_projects()
    if not any(p['id'] == project_id for p in projects):
        return jsonify({'started': False, 'error': '项目不存在'})
    if not _start_project_sync(projects, single_id=project_id):
        return jsonify({'started': False, 'error': '已有同步任务正在后台执行，请等待完成'})
    return jsonify({'started': True, 'total': 1})


@app.route('/admin/projects/sync-all', methods=['POST'])
@admin_required
def admin_projects_sync_all():
    """批量同步全部项目（后台线程执行，按 GitHub 仓库去重，不重复请求）。
    返回 JSON 供前端原地轮询进度。"""
    projects = db_load_projects()
    if not projects:
        return jsonify({'started': False, 'error': '没有可同步的项目'})
    if not _start_project_sync(projects, single_id=None):
        return jsonify({'started': False, 'error': '已有同步任务正在后台执行，请等待完成'})
    return jsonify({'started': True, 'total': len(projects)})


@app.route('/admin/projects/sync-status')
@admin_required
def admin_projects_sync_status():
    """后台同步进度接口（前台轮询）：running/total/done/current/summary。
    返回跨 worker 一致的状态（本 worker 内存优先，否则回退磁盘）。
    ?consume=1：页面自动刷新前调用，把已完成的提示消费掉（清空 finished/summary
    及进度数字），避免下次进入 /admin/projects 时仍挂「同步完成」条；运行中不可消费。"""
    st = project_sync_state()
    if request.args.get('consume') == '1' and st.get('finished') and not st.get('running'):
        with _PROJECT_SYNC_LOCK:
            _PROJECT_SYNC_STATE.update(finished=False, summary='', current='',
                                       done=0, total=0, ok=0, failed=0)
            _save_sync_state()
        st['finished'] = False
        st['summary'] = ''
        st['current'] = ''
        st['done'] = st['total'] = st['ok'] = st['failed'] = 0
    return jsonify(st)


# ─────────────── 后台: 友情链接管理 ───────────────

@app.route('/admin/links')
@admin_required
def admin_links():
    links = db_load_links(status='approved')
    pending = db_load_links(status='pending')
    return render_template('admin/links.html', links=links, pending=pending)


@app.route('/admin/links/<int:link_id>/approve', methods=['POST'])
@admin_required
def admin_link_approve(link_id):
    db_set_link_status(link_id, 'approved')
    flash('友链已通过审核', 'success')
    return redirect(url_for('admin_links'))


@app.route('/admin/links/<int:link_id>/reject', methods=['POST'])
@admin_required
def admin_link_reject(link_id):
    db_set_link_status(link_id, 'rejected')
    flash('友链已拒绝', 'success')
    return redirect(url_for('admin_links'))


@app.route('/admin/links/new', methods=['GET', 'POST'])
@admin_required
def admin_link_new():
    if request.method == 'POST':
        db_save_link(request.form)
        flash('链接已添加', 'success')
        return redirect(url_for('admin_links'))
    return render_template('admin/link_edit.html', link=None)


@app.route('/admin/links/<int:link_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_link_edit(link_id):
    db = get_db()
    row = db.execute("SELECT * FROM links WHERE id=?", (link_id,)).fetchone()
    if not row:
        db.close()
        flash('链接不存在', 'error')
        return redirect(url_for('admin_links'))
    link = dict(row)
    db.close()
    if request.method == 'POST':
        db_save_link(request.form, link_id)
        flash('链接已更新', 'success')
        return redirect(url_for('admin_links'))
    return render_template('admin/link_edit.html', link=link)


@app.route('/admin/links/<int:link_id>/delete', methods=['POST'])
@admin_required
def admin_link_delete(link_id):
    db_delete_link(link_id)
    flash('链接已删除', 'success')
    return redirect(url_for('admin_links'))


@app.route('/admin/links/bulk', methods=['POST'])
@admin_required
def admin_links_bulk():
    """友链批量操作：approve 通过 / reject 拒绝 / delete 删除。"""
    action = request.form.get('action')
    ids = request.form.getlist('link_ids')
    if action not in ('approve', 'reject', 'delete'):
        flash('无效的批量操作', 'error')
        return redirect(url_for('admin_links'))
    if not ids:
        flash('未选择任何链接', 'error')
        return redirect(url_for('admin_links'))
    if action == 'delete':
        for lid in ids:
            db_delete_link(int(lid))
        flash('已删除 %d 条链接' % len(ids), 'success')
    else:
        status = 'approved' if action == 'approve' else 'rejected'
        for lid in ids:
            db_set_link_status(int(lid), status)
        flash('已将 %d 条链接设为「%s」' % (len(ids), '已通过' if action == 'approve' else '已拒绝'), 'success')
    return redirect(url_for('admin_links'))


# ─────────────── 后台: 博客历程（时间线）管理 ───────────────

@app.route('/admin/timeline')
@admin_required
def admin_timeline():
    db = get_db()
    rows = db.execute(
        "SELECT id, date, content, sort_order FROM timeline ORDER BY sort_order ASC, date DESC"
    ).fetchall()
    db.close()
    items = [dict(r) for r in rows]
    return render_template('admin/timeline.html', items=items)


@app.route('/admin/timeline/new', methods=['GET', 'POST'])
@admin_required
def admin_timeline_new():
    if request.method == 'POST':
        date = request.form.get('date', '').strip()
        content = request.form.get('content', '').strip()
        sort_order = int(request.form.get('sort_order', 0) or 0)
        if not date or not content:
            flash('日期和内容不能为空', 'error')
            return render_template('admin/timeline_edit.html', item=None)
        db = get_db()
        db.execute(
            "INSERT INTO timeline (date, content, sort_order, created_at) VALUES (?, ?, ?, ?)",
            (date, content, sort_order),
        )
        db.commit()
        db.close()
        flash('历程已添加', 'success')
        return redirect(url_for('admin_timeline'))
    return render_template('admin/timeline_edit.html', item=None)


@app.route('/admin/timeline/<int:item_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_timeline_edit(item_id):
    db = get_db()
    item = db.execute(
        "SELECT id, date, content, sort_order FROM timeline WHERE id=?", (item_id,)
    ).fetchone()
    db.close()
    if item is None:
        flash('历程不存在', 'error')
        return redirect(url_for('admin_timeline'))
    if request.method == 'POST':
        date = request.form.get('date', '').strip()
        content = request.form.get('content', '').strip()
        sort_order = int(request.form.get('sort_order', 0) or 0)
        if not date or not content:
            flash('日期和内容不能为空', 'error')
            return render_template('admin/timeline_edit.html', item=dict(item))
        db = get_db()
        db.execute(
            "UPDATE timeline SET date=?, content=?, sort_order=? WHERE id=?",
            (date, content, sort_order, item_id),
        )
        db.commit()
        db.close()
        flash('历程已更新', 'success')
        return redirect(url_for('admin_timeline'))
    return render_template('admin/timeline_edit.html', item=dict(item))


@app.route('/admin/timeline/<int:item_id>/delete', methods=['POST'])
@admin_required
def admin_timeline_delete(item_id):
    db = get_db()
    db.execute("DELETE FROM timeline WHERE id=?", (item_id,))
    db.commit()
    db.close()
    flash('历程已删除', 'success')
    return redirect(url_for('admin_timeline'))


@app.route('/admin/timeline/bulk', methods=['POST'])
@admin_required
def admin_timeline_bulk():
    """博客历程批量操作：delete 批量删除。"""
    action = request.form.get('action')
    ids = request.form.getlist('timeline_ids')
    if action != 'delete':
        flash('无效的批量操作', 'error')
        return redirect(url_for('admin_timeline'))
    if not ids:
        flash('未选择任何历程', 'error')
        return redirect(url_for('admin_timeline'))
    db = get_db()
    db.execute("DELETE FROM timeline WHERE id IN (%s)" % ','.join('?' * len(ids)), ids)
    db.commit()
    db.close()
    flash('已删除 %d 条历程' % len(ids), 'success')
    return redirect(url_for('admin_timeline'))


# ─────────────── 后台: 评论管理 ───────────────

@app.route('/admin/comments')
@admin_required
def admin_comments():
    db = get_db()
    rows = db.execute(
        "SELECT c.*, p.title as post_title, p.id as post_id, "
        "pj.name as project_name, "
        "pa.author as parent_author "
        "FROM comments c "
        "LEFT JOIN posts p ON c.post_id=p.id "
        "LEFT JOIN projects pj ON c.project_id=pj.id "
        "LEFT JOIN comments pa ON c.parent_id=pa.id "
        "ORDER BY (c.status='pending') DESC, c.is_private DESC, c.created_at DESC"
    ).fetchall()
    db.close()
    comments = rows_to_list(rows)
    # 后台头像：复用站内代理生成（qq 优先，其次 Cravatar），与前台同源
    # 后台评论区默认头像（邮箱为空 / Cravatar 未注册时代理 404，前端 onerror 兜底到此）
    admin_default_avatar = url_for('static', filename='images/default-avatar.svg', _external=True)
    for c in comments:
        is_author = bool(app.config.get('author')) and c.get('author') == app.config.get('author')
        if is_author and app.config.get('avatar') and _avatar_file_exists():
            c['admin_avatar'] = app.config.get('avatar')
        else:
            c['admin_avatar'], _ = _avatar_urls(c.get('email_hash', ''), c.get('qq', ''))
        # 无任何头像来源（无邮箱无 QQ）→ 直接给博客默认头像，不再显示空位
        if not c['admin_avatar']:
            c['admin_avatar'] = admin_default_avatar
        c['admin_avatar_default'] = admin_default_avatar
    return render_template('admin/comments.html', comments=comments)


@app.route('/admin/comments/<int:comment_id>/approve', methods=['POST'])
@admin_required
def admin_comment_approve(comment_id):
    db = get_db()
    db.execute("UPDATE comments SET status='approved' WHERE id=?", (comment_id,))
    db.commit()
    db.close()
    # 审核通过后补发被回复者通知（若适用），后台线程发送不阻塞
    if str(app.config.get('comment_notify', '0')) in ('1', 'on', 'true', 'yes'):
        threading.Thread(
            target=_notify_reply_recipient,
            args=(comment_id, request.host_url.rstrip('/')),
            daemon=True).start()
    flash('评论已通过', 'success')
    return redirect(url_for('admin_comments'))


@app.route('/admin/comments/<int:comment_id>/delete', methods=['POST'])
@admin_required
def admin_comment_delete(comment_id):
    db_delete_comment(comment_id)
    flash('评论及其回复已删除', 'success')
    return redirect(url_for('admin_comments'))


@app.route('/admin/comments/bulk', methods=['POST'])
@admin_required
def admin_comments_bulk():
    """批量操作：approve 批量通过 / delete 批量删除（含全部回复）。"""
    action = request.form.get('action')
    ids = request.form.getlist('comment_ids')
    if action not in ('approve', 'delete'):
        flash('无效的批量操作', 'error')
        return redirect(url_for('admin_comments'))
    if not ids:
        flash('未选择任何评论', 'error')
        return redirect(url_for('admin_comments'))
    if action == 'approve':
        db = get_db()
        db.execute(
            "UPDATE comments SET status='approved' WHERE id IN (%s)"
            % ','.join('?' * len(ids)), ids)
        db.commit()
        db.close()
        # 批量通过后逐条补发被回复者通知
        if str(app.config.get('comment_notify', '0')) in ('1', 'on', 'true', 'yes'):
            for cid in ids:
                threading.Thread(
                    target=_notify_reply_recipient,
                    args=(int(cid), request.host_url.rstrip('/')),
                    daemon=True).start()
        flash('已通过 %d 条评论' % len(ids), 'success')
    else:
        for cid in ids:
            db_delete_comment(int(cid))
        flash('已删除 %d 条评论及其回复' % len(ids), 'success')
    return redirect(url_for('admin_comments'))


# ─────────────── 附件上传（MD 编辑器集成） ───────────────

def _optimize_heic(stream):
    """HEIC/HEIF 专用转换：用 pillow_heif.open_heif 直接解码（不依赖 Pillow 插件注册），
    统一压缩为 JPEG。返回 (data, '.jpg')；失败返回 (None, 错误信息)。"""
    if not _HAS_HEIF:
        return None, '服务器缺少 HEIC 解码支持（需安装 pillow-heif）'
    try:
        stream.seek(0)
        heif = pillow_heif.open_heif(stream)
        img = heif.to_pillow()
        if img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')
        # iPhone 等拍摄的照片常带 EXIF 方向信息，解码后按方向修正，避免横竖颠倒
        img = ImageOps.exif_transpose(img)
        max_side = 1920
        if max(img.size) > max_side:
            ratio = max_side / max(img.size)
            img = img.resize((int(img.size[0] * ratio), int(img.size[1] * ratio)),
                             Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, 'JPEG', quality=82, optimize=True, progressive=True)
        return out.getvalue(), '.jpg'
    except Exception as e:
        pv = getattr(Image, '__version__', '?')
        return None, f'HEIC 解码失败：{e}（pillow_heif {_PH_VER} / libheif {_LIBHEIF_VER} / Pillow {pv}，可尝试升级：pip install -U pillow-heif Pillow）'


def _optimize_image(stream, ext):
    """上传图片压缩：最长边 1920px，JPEG quality 82。
    返回 (data, new_ext, err)；data 为 None 时 err 为失败原因（非 HEIC 图片恒为 None）。"""
    if not _HAS_PIL:
        return None, None, None
    if ext in ('.heic', '.heif'):
        data, err = _optimize_heic(stream)
        return data, '.jpg' if data else None, err
    try:
        img = Image.open(stream)
        img = img.convert('RGB') if img.mode in ('RGBA', 'P', 'LA') else img
        max_side = 1920
        if max(img.size) > max_side:
            ratio = max_side / max(img.size)
            img = img.resize((int(img.size[0] * ratio), int(img.size[1] * ratio)),
                             Image.LANCZOS)
        out = io.BytesIO()
        if ext in ('.png', '.bmp') and img.mode == 'RGBA':
            img.save(out, 'PNG', optimize=True)
            return out.getvalue(), ext, None
        img.save(out, 'JPEG', quality=82, optimize=True, progressive=True)
        return out.getvalue(), '.jpg', None
    except Exception:
        return None, None, None


# ─────────────── 图片水印（正文/灯箱展示带水印，.originals 保留无痕原图） ───────────────

# 水印字体发现，三级策略：
#   1) 仓库自带 fonts/wqy-microhei.ttc（文泉驿微米黑，Apache-2.0，随代码部署）——首选，
#      跨平台一致且杜绝「服务器命中西文字体导致中文方块」（DejaVu 几乎所有发行版都预装）
#   2) 已知候选路径（Win 中文字体 / 各发行版常见包路径），命中即用
#   3) 动态扫描系统字体目录，仅接受 CJK 命名的字体（纯西文字体对中文水印无意义）
_APP_ROOT = os.path.dirname(os.path.abspath(__file__))
_WM_FONT_CANDIDATES = [
    os.path.join(_APP_ROOT, 'fonts', 'wqy-microhei.ttc'),  # 仓库自带，跨平台保底
    'C:/Windows/Fonts/msyh.ttc',                    # 微软雅黑
    'C:/Windows/Fonts/simhei.ttf',                  # 黑体
    'C:/Windows/Fonts/simsun.ttc',                  # 宋体
    '/System/Library/Fonts/PingFang.ttc',           # macOS 苹方
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
]
_WM_FONT_SCAN_DIRS = [
    '/usr/share/fonts', '/usr/local/share/fonts',
    os.path.expanduser('~/.local/share/fonts'), os.path.expanduser('~/.fonts'),
    '/Library/Fonts', '/System/Library/Fonts',
    'C:/Windows/Fonts',
]
# 文件名命中这些关键字的优先当 CJK 字体（排序靠前）
_WM_CJK_HINTS = ('notosanscjk', 'notoserifcjk', 'sourcehan', 'wqy', 'microhei',
                 'zenhei', 'msyh', 'simhei', 'simsun', 'pingfang', 'hiragino',
                 'droidsansfallback', 'uming', 'ukai', 'cjk')


def _find_watermark_font():
    """返回可用字体文件路径；三级策略全部落空时返回 None。"""
    from PIL import ImageFont

    def _usable(p):
        try:
            ImageFont.truetype(p, 16)
            return True
        except Exception:
            return False

    for p in _WM_FONT_CANDIDATES:
        if os.path.exists(p) and _usable(p):
            return p
    found = []
    for d in _WM_FONT_SCAN_DIRS:
        if d and os.path.isdir(d):
            for root, _dirs, files in os.walk(d):
                for fn in files:
                    if fn.lower().endswith(('.ttf', '.ttc', '.otf')):
                        found.append(os.path.join(root, fn))

    def _rank(p):
        n = os.path.basename(p).lower()
        for i, hint in enumerate(_WM_CJK_HINTS):
            if hint in n:
                return i
        return len(_WM_CJK_HINTS)

    # 扫描只收 CJK 命名命中者：不含中文的字体（如 DejaVu）只会把水印画成方块
    for p in sorted(found, key=_rank):
        if _rank(p) < len(_WM_CJK_HINTS) and _usable(p):
            return p
    return None


_WM_FONT_PATH = _find_watermark_font()
_WM_FONT = None
if _WM_FONT_PATH:
    try:
        from PIL import ImageFont
        _WM_FONT = ImageFont.truetype(_WM_FONT_PATH, 16)
    except Exception:
        _WM_FONT = None


# 水印字号档位：按图宽比例缩放，min/max 为像素上下限。
# s 小（沿用旧值）/ m 标准（默认，修正旧版偏小）/ l 大（强防盗场景）
_WM_SIZE_LEVELS = {
    's': {'ratio': 0.02, 'min': 14, 'max': 28},
    'm': {'ratio': 0.03, 'min': 18, 'max': 52},
    'l': {'ratio': 0.04, 'min': 24, 'max': 76},
}


def _apply_watermark(img, text, position='br', size='m'):
    """给 img 指定角落画「站点名 · 域名」半透明水印（文字单枚）。
    绘制失败或文字为空时返回原图，不阻断上传。"""
    if not text or not _HAS_PIL:
        return img
    try:
        from PIL import ImageDraw, ImageFont
        w, h = img.size
        lv = _WM_SIZE_LEVELS.get(size, _WM_SIZE_LEVELS['m'])
        font_size = max(lv['min'], min(lv['max'], int(w * lv['ratio'])))
        font = None
        try:
            if _WM_FONT_PATH:
                font = ImageFont.truetype(_WM_FONT_PATH, font_size)
            else:
                # Pillow 10.1+ 的 load_default 支持 size，按档位缩放；
                # 旧版不接受参数，退回固定字号（英文仍可正常显示）
                try:
                    font = ImageFont.load_default(font_size)
                except TypeError:
                    font = ImageFont.load_default()
        except Exception:
            try:
                font = ImageFont.load_default(font_size)
            except TypeError:
                font = ImageFont.load_default()
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        # 先量文字尺寸：ImageDraw.textbbox 是 Pillow 8+ 的标准接口
        try:
            bbox = d.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except Exception:
            tw, th = font.getsize(text)
        pad = max(10, int(font_size * 0.45))
        # 角落坐标：br 右下 / bl 左下 / tr 右上 / tl 左上 / bc 底部居中
        pos = {
            'br': (w - tw - pad, h - th - pad),
            'bl': (pad, h - th - pad),
            'tr': (w - tw - pad, pad),
            'tl': (pad, pad),
            'bc': ((w - tw) // 2, h - th - pad),
        }
        x, y = pos.get(position, pos['br'])
        # 深色阴影 + 半透明白字，深浅图片上都可读
        d.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0, 150))
        d.text((x, y), text, font=font, fill=(255, 255, 255, 180))
        if img.mode == 'RGBA':
            return Image.alpha_composite(img, overlay)
        base = img.convert('RGBA')
        return Image.alpha_composite(base, overlay).convert(img.mode or 'RGB')
    except Exception:
        return img


def _watermark_text():
    """水印文案：优先取后台自定义文本，空则回退「站点名 · 域名」。"""
    custom = (app.config.get('watermark_text') or '').strip()
    if custom:
        return custom
    blog_name = app.config.get('blog_name') or ''
    host = request.host if request and hasattr(request, 'host') else ''
    return (blog_name + ' · ' + host).strip(' ·') if (blog_name or host) else ''


def _watermark_position():
    """水印位置：br 右下 / bl 左下 / tr 右上 / tl 左上 / bc 底部居中（默认右下）。"""
    p = (app.config.get('watermark_position') or '').strip()
    return p if p in ('br', 'bl', 'tr', 'tl', 'bc') else 'br'


def _watermark_size():
    """水印字号档位：s 小 / m 标准（默认）/ l 大。"""
    s = (app.config.get('watermark_size') or '').strip().lower()
    return s if s in ('s', 'm', 'l') else 'm'


def _safe_stem(name):
    """宽松安全化文件名主干：保留中文等可读字符，剔除路径分隔与控制字符。

    相对 werkzeug.secure_filename（非 ASCII 一律丢弃，产生 docx.docx 式结果），
    这里保留中文/字母/数字/中划线/点，仅把其余符号折叠为下划线：
    '微信图片_2020-01-29_114456.jpg' -> '微信图片_2020-01-29_114456'
    '我的毕业设计.docx'               -> '我的毕业设计'
    """
    stem = os.path.splitext(name or '')[0]
    stem = re.sub(r'[^\w\u4e00-\u9fff.-]', '_', stem, flags=re.UNICODE)
    stem = re.sub(r'_+', '_', stem)
    stem = re.sub(r'\.{2,}', '_', stem)  # 连续点折叠，避免 ../ 类路径穿越被误拒或误判
    stem = stem.strip('_. ')
    # Windows 保留设备名兜底，避免写入失败
    if stem.upper() in ('CON', 'PRN', 'AUX', 'NUL',
                        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
                        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'):
        stem = '_' + stem
    return stem[:80] or 'file'


# 文章正文对上传文件的引用形如 /uploads/2026/09/xxx.jpg，据此提取用于清理判定。
# 命名保留中文后，正文里可能是原始中文 URL，也可能是 url_for 生成的百分号编码 URL
# （含 % 字符），正则须同时兼容中文(\w)与 %，否则编码 URL 会被 % 截断漏判。
_UPLOAD_URL_RE = re.compile(r'/uploads/[/\w%.\-]+')


def _extract_upload_urls(*texts):

    """从一段或多段文本中提取所有 /uploads/ 相对 URL（去重，并按 URL 解码归一）。

    磁盘文件名是中文原始字符，而 url_for 生成的 URL 是百分号编码，
    必须 unquote 归一后两者才能互相匹配。
    """
    urls = set()
    for t in texts:
        if not t:
            continue
        for m in _UPLOAD_URL_RE.finditer(str(t)):
            urls.add(urllib.parse.unquote(m.group(0)))
    return urls


def _first_upload_url(*texts):
    """按正文出现顺序返回第一个 /uploads/ 相对 URL（保序，供分享卡片图取首图）。

    与 _extract_upload_urls（集合去重、无序）不同，这里只取正则命中的第一处。"""
    for t in texts:
        if not t:
            continue
        m = _UPLOAD_URL_RE.search(str(t))
        if m:
            return urllib.parse.unquote(m.group(0))
    return ''


def _load_referenced_urls():
    """收集全库文章文本中引用的 /uploads/ URL 集合（孤儿清理判定基准）。"""
    db = get_db()
    rows = db.execute("SELECT title, content, excerpt, tags FROM posts").fetchall()
    db.close()
    urls = set()
    for r in rows:
        urls |= _extract_upload_urls(*tuple(r))
    return urls


def _prune_empty_dirs(start):
    """自底向上删除空目录（不越过 UPLOAD_DIR）。"""
    d = start
    while d and d != UPLOAD_DIR and os.path.abspath(d).startswith(os.path.abspath(UPLOAD_DIR)):
        try:
            os.rmdir(d)
        except OSError:
            break
        d = os.path.dirname(d)


def _delete_upload_file(url):
    """按 /uploads/ 相对 URL 删除正式文件与其 .originals 无痕原图，并清理空目录。

    入参可能是百分号编码 URL（正文引用即编码形式），先解码归一为磁盘路径。
    拒绝 avatar / projects / 隐藏路径等非文章上传目录，防误删。
    返回是否真的删除了文件。
    """
    rel = urllib.parse.unquote(url.split('/uploads/', 1)[-1])
    segs = rel.split('/')
    if (not rel or '..' in rel or rel.startswith('.') or not segs[0]
            or segs[0].startswith('.') or segs[0] in ('avatar', 'projects')):
        return False
    abs_path = os.path.join(UPLOAD_DIR, *segs)
    if not os.path.isfile(abs_path):
        return False
    try:
        os.remove(abs_path)
        orig = os.path.join(UPLOAD_DIR, '.originals', *segs)
        if os.path.isfile(orig):
            os.remove(orig)
        _prune_empty_dirs(os.path.dirname(abs_path))
        return True
    except OSError:
        return False


def _fmt_size(n):
    """字节数转人类可读尺寸。"""
    n = float(n or 0)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return ('%d B' % n) if unit == 'B' else ('%.1f %s' % (n, unit))
        n /= 1024.0
    return '%.1f TB' % n


def _save_upload(file, allowed_ext):
    if not file or not file.filename:
        return None, '未选择文件'
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        return None, '不支持的文件类型: ' + ext
    if file.content_length and file.content_length > 20 * 1024 * 1024:
        return None, '文件过大（上限 20MB）'
    # 按 年/月 分子目录，避免所有文件堆在 uploads 根目录
    now = datetime.now()
    sub = now.strftime('%Y/%m')
    target_dir = os.path.join(UPLOAD_DIR, sub)
    os.makedirs(target_dir, exist_ok=True)
    # 避免重名覆盖（保留中文等可读文件名）
    base = _safe_stem(file.filename)
    filename = base + ext
    counter = 1
    while os.path.exists(os.path.join(target_dir, filename)):
        filename = f'{base}_{counter}{ext}'
        counter += 1
    # 压缩：位图类在保存前压缩（gif 不压缩以保留动画）
    if ext in ('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.heic', '.heif'):
        data, new_ext, err = _optimize_image(file.stream, ext)
        if data:
            if new_ext != ext:
                filename = base + new_ext
                while os.path.exists(os.path.join(target_dir, filename)):
                    filename = f'{base}_{counter}{new_ext}'
                    counter += 1
            # 无痕原图（压缩后、加水印前）备份到 .originals，公网不可达；
            # 展示层一律用带水印版本（后台可自定义文本/位置，未启用则纯无痕）
            orig_abs = os.path.join(UPLOAD_DIR, '.originals', sub, filename)
            if new_ext in ('.jpg', '.jpeg', '.png', '.webp', '.bmp'):
                _write_file(orig_abs, data)
                if app.config.get('watermark_enabled', '1') in ('1', 'on', 'true', 'yes'):
                    data = _watermark_bytes(data, new_ext, _watermark_text(),
                                            _watermark_position(), _watermark_size())
            _write_file(os.path.join(target_dir, filename), data)
        elif ext in ('.heic', '.heif'):
            # err 由 _optimize_heic 提供（含真实异常信息）
            return None, err or 'HEIC 图片解码失败'
        else:
            file.stream.seek(0)
            file.save(os.path.join(target_dir, filename))
    else:
        file.save(os.path.join(target_dir, filename))
    url = url_for('uploaded_file', filename=sub + '/' + filename)
    return url, None


def _write_file(path, data):
    """带父目录创建的写文件。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def _watermark_bytes(data, ext, text, position='br', size='m'):
    """字节级水印：data(压缩后)→ 加角落水印 → 新 bytes。失败返回原 data。"""
    if not text or not _HAS_PIL:
        return data
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        wm = _apply_watermark(img, text, position, size)
        out = io.BytesIO()
        if ext == '.png':
            wm.save(out, 'PNG', optimize=True)
        else:
            wm.save(out, 'JPEG', quality=82, optimize=True, progressive=True)
        return out.getvalue()
    except Exception:
        return data


# ---------------------------------------------------------------------------
# 历史图片水印批量重做（后台保存设置后自动触发 + 手动 CLI 共用同一份逻辑）
# ---------------------------------------------------------------------------
# 后台线程调度锁与运行标记：避免重复启动刷新线程（仅进程内有效，多 worker 并发重做幂等无害）
_WM_RUN_LOCK = threading.Lock()
_WM_REF_DONE = threading.Event()          # 置位=空闲可接收新任务；开始刷新时清除
_WM_REF_DONE.set()                        # 进程启动即处于空闲态
_WM_REFRESH_STATE = {'state': 'idle', 'time': '', 'done': 0, 'errs': 0}

# 与 watermark_backfill.py 保持一致：可处理的位图扩展名
WM_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')


def wm_refresh_state():
    """返回最近一次历史图刷新的状态(dict)，供设置页展示。"""
    return dict(_WM_REFRESH_STATE)


def _wm_redo_all(text, position='br', size='m', force=True):
    """遍历 uploads 全部位图重做水印（自动刷新 / backfill 共用核心）。

    某图已有 .originals 无痕原图 → 从原图重新叠当前水印写回正式路径(force)。
    从未处理过 → 先把正式文件备份为无痕原图，再叠水印写回。
    avatar / projects / 隐藏目录一律跳过。
    返回 (完成数, 跳过数, 失败数)。
    """
    global _WM_REF_DONE
    started = time.time()
    count = skipped = errs = 0
    state = {'state': 'running', 'time': datetime.now().strftime('%H:%M:%S'), 'done': 0, 'errs': 0}
    _WM_REFRESH_STATE.update(state)
    try:
        for root, dirs, files in os.walk(UPLOAD_DIR):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('projects', 'avatar')]
            for fn in sorted(files):
                ext = os.path.splitext(fn)[1].lower()
                src = os.path.join(root, fn)
                if ext not in WM_EXT or not os.path.isfile(src):
                    continue
                sub = os.path.relpath(root, UPLOAD_DIR).replace('\\', '/')
                orig = os.path.join(UPLOAD_DIR, '.originals', sub, fn)
                if os.path.exists(orig):
                    if not force:
                        skipped += 1
                        continue
                    try:
                        with open(orig, 'rb') as f:
                            data = f.read()
                    except Exception as e:
                        errs += 1
                        print(' ! 读取无痕原图失败:', sub + '/' + fn, e)
                        continue
                else:
                    # 首次处理：把当前文件备份为无痕原图
                    try:
                        with open(src, 'rb') as f:
                            data = f.read()
                        os.makedirs(os.path.dirname(orig), exist_ok=True)
                        with open(orig, 'wb') as f:
                            f.write(data)
                    except Exception as e:
                        errs += 1
                        print(' ! 备份无痕原图失败:', sub + '/' + fn, e)
                        continue
                try:
                    with open(src, 'wb') as f:
                        f.write(_watermark_bytes(data, ext, text, position, size))
                    count += 1
                except Exception as e:
                    errs += 1
                    print(' ! 重做失败:', sub + '/' + fn, e)
        _WM_REFRESH_STATE.update({
            'state': 'done',
            'time': datetime.now().strftime('%H:%M:%S'),
            'done': count, 'errs': errs, 'seconds': int(time.time() - started),
        })
    finally:
        _WM_REF_DONE.set()
    print('水印批量刷新完成：%d 张，失败 %d，耗时 %ds' % (count, errs, int(time.time() - started)))
    return count, skipped, errs


def _start_wm_refresh(text, position='br', size='m'):
    """后台线程启动历史图水印重做；已有刷新在跑则跳过本次（下次保存设置仍会触发）。"""
    global _WM_REF_DONE
    with _WM_RUN_LOCK:
        if not _WM_REF_DONE.is_set():
            return False
        _WM_REF_DONE.clear()
    threading.Thread(target=_wm_redo_all, args=(text, position, size),
                     kwargs={'force': True}, daemon=True).start()
    return True


# 根目录 /uploads 静态文件服务（v1.0.6 起上传目录移至项目根）
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    # 点开头的隐藏目录（如 .originals 无痕原图）一律不可达，防公网取原图
    if filename.startswith('.') or '/.' in filename:
        abort(404)
    return send_from_directory(UPLOAD_DIR, filename)


# ─────────────── 分享卡片缩略图（4:3，微信朋友圈 / Twitter 卡片图）───────────────
# 需求背景：微信等分享爬虫不执行 JS，卡片图来自 og:image 或页面首张 <img>；
# 原图多为手机直出（3~8MB、比例不一），直接喂给卡片加载慢且显示差。
# /share-thumb/2026/09/xxx.jpg -> uploads 同路径图片的 4:3 居中裁切缩略图，
# 首次访问懒生成 + 磁盘缓存（data/share_thumbs/，不在 uploads/ 下以避开孤儿清理）。
_THUMB_DIR = os.path.join(BASE_DIR, 'data', 'share_thumbs')
_THUMB_SIZE = (800, 600)   # 4:3，对微信卡片与 Twitter summary 卡均友好
_IMG_DIMS_CACHE = {}       # 首图尺寸注入缓存: {相对路径: (mtime, w, h)}


def _upload_image_dims(rel_url):
    """读取 uploads 图片真实尺寸（供首图 width/height 注入），按 mtime 缓存。"""
    rel = rel_url.split('/uploads/', 1)[-1]
    src = os.path.normpath(os.path.join(UPLOAD_DIR, rel))
    if not os.path.abspath(src).startswith(os.path.abspath(UPLOAD_DIR) + os.sep) \
            or not os.path.isfile(src):
        return None
    try:
        mtime = os.path.getmtime(src)
    except OSError:
        return None
    cached = _IMG_DIMS_CACHE.get(rel)
    if cached and cached[0] == mtime:
        return cached[1:]
    try:
        with Image.open(src) as im:
            dims = im.size
    except Exception:
        return None
    _IMG_DIMS_CACHE[rel] = (mtime,) + dims
    return dims


@app.route('/share-thumb/<path:filename>')
def share_thumb(filename):
    # 与 /uploads 同级安全策略：点开头的隐藏目录（.originals 无痕原图）不可达
    if filename.startswith('.') or '/.' in filename:
        abort(404)
    src = os.path.normpath(os.path.join(UPLOAD_DIR, filename))
    if not os.path.abspath(src).startswith(os.path.abspath(UPLOAD_DIR) + os.sep) \
            or not os.path.isfile(src):
        abort(404)
    if os.path.splitext(src)[1].lower() not in ALLOWED_IMAGE_EXT:
        abort(404)
    cache_path = os.path.splitext(os.path.join(_THUMB_DIR, filename))[0] + '.jpg'
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    # 缓存失效：源图更新（重新上传/水印重刷）后自动重新生成
    if not (os.path.isfile(cache_path)
            and os.path.getmtime(cache_path) >= os.path.getmtime(src)):
        try:
            with Image.open(src) as im:
                im = im.convert('RGB')  # PNG 透明通道 / GIF 动图取首帧
                tw, th = _THUMB_SIZE
                target = tw / th
                w, h = im.size
                if w and h:
                    if w / h > target:      # 过宽：左右居中裁切
                        nw = max(1, int(h * target))
                        box = ((w - nw) // 2, 0, (w + nw) // 2, h)
                    else:                   # 过窄（竖图）：上下居中裁切
                        nh = max(1, int(w / target))
                        box = (0, (h - nh) // 2, w, (h + nh) // 2)
                    im = im.crop(box).resize(_THUMB_SIZE, Image.LANCZOS)
                im.save(cache_path, 'JPEG', quality=85, optimize=True)
        except Exception:
            # 生成失败（源图损坏等）退回原图，保证分享图不至 404
            return send_from_directory(UPLOAD_DIR, filename)
    # 缓存文件与 filename 同构（正斜杠相对路径）——werkzeug safe_join 拒绝反斜杠路径
    resp = send_from_directory(_THUMB_DIR, os.path.splitext(filename)[0] + '.jpg')
    resp.headers['Cache-Control'] = 'public, max-age=86400'
    return resp


@app.route('/admin/upload/image', methods=['POST'])
@admin_required
def admin_upload_image():
    # EasyMDE 图片上传钩子（字段名 image）
    f = request.files.get('image')
    url, err = _save_upload(f, ALLOWED_IMAGE_EXT)
    if err:
        return jsonify({'error': err}), 400
    return jsonify({'url': url})


@app.route('/admin/upload/media', methods=['POST'])
@admin_required
def admin_upload_media():
    # 视频/音频
    f = request.files.get('file') or request.files.get('media')
    url, err = _save_upload(f, ALLOWED_MEDIA_EXT)
    if err:
        return jsonify({'error': err}), 400
    return jsonify({'url': url, 'name': os.path.basename(url)})


@app.route('/admin/upload/file', methods=['POST'])
@admin_required
def admin_upload_file():
    # 附件
    f = request.files.get('file')
    url, err = _save_upload(f, ALLOWED_FILE_EXT)
    if err:
        return jsonify({'error': err}), 400
    return jsonify({'url': url, 'name': os.path.basename(url)})


# ─────────────── 后台: 孤儿文件清理 ───────────────

@app.route('/admin/orphans', methods=['GET', 'POST'])
@admin_required
def admin_orphans():
    """粘贴上传但从未（或不再）被任何文章引用的文件清理。

    判定基准：全库文章的 title/content/excerpt/tags 文本中是否出现过该文件的
    /uploads/ 相对 URL。avatar / projects / 隐藏目录（如 .originals 无痕原图）
    不属于文章上传目录，一律不列出、不可清理。
    """
    if request.method == 'POST':
        selected = request.form.getlist('path')
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        deleted = failed = 0
        results = []  # AJAX：逐项结果，供前端移除成功行 / 标记失败行
        for raw in selected:
            rel = urllib.parse.unquote(raw.replace('\\', '/'))
            segs = rel.split('/')
            if (not rel or rel.startswith('.') or rel.startswith('/') or '..' in rel
                    or not segs[0] or segs[0].startswith('.')
                    or segs[0] in ('avatar', 'projects')):
                if is_ajax:
                    results.append({'rel': rel, 'ok': False, 'reason': '非法路径'})
                continue
            abs_path = os.path.join(UPLOAD_DIR, *segs)
            if not os.path.isfile(abs_path):
                if is_ajax:
                    results.append({'rel': rel, 'ok': False, 'reason': '文件不存在'})
                continue
            try:
                os.remove(abs_path)
                orig = os.path.join(UPLOAD_DIR, '.originals', *segs)
                if os.path.isfile(orig):
                    os.remove(orig)
                _prune_empty_dirs(os.path.dirname(abs_path))
                deleted += 1
                if is_ajax:
                    results.append({'rel': rel, 'ok': True})
            except OSError:
                failed += 1
                if is_ajax:
                    results.append({'rel': rel, 'ok': False, 'reason': '删除失败'})
        if is_ajax:
            return jsonify({'deleted': deleted, 'failed': failed, 'results': results})
        if deleted and not failed:
            flash('已清理 %d 个孤儿文件' % deleted, 'success')
        elif deleted and failed:
            flash('已清理 %d 个孤儿文件，%d 个删除失败' % (deleted, failed), 'error')
        elif failed:
            flash('%d 个文件删除失败' % failed, 'error')
        else:
            flash('没有可清理的文件', 'success')
        return redirect(url_for('admin_orphans'))

    refs = _load_referenced_urls()
    orphans = []
    for root, dirs, files in os.walk(UPLOAD_DIR):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('avatar', 'projects')]
        if root == UPLOAD_DIR:
            continue
        for fn in sorted(files):
            rel = os.path.relpath(os.path.join(root, fn), UPLOAD_DIR).replace('\\', '/')
            if ('/uploads/' + rel) in refs:
                continue
            p = os.path.join(root, fn)
            try:
                size = os.path.getsize(p)
                mtime = datetime.fromtimestamp(os.path.getmtime(p)).strftime('%Y-%m-%d %H:%M')
            except OSError:
                continue
            ext = os.path.splitext(fn)[1].lstrip('.').lower()
            orphans.append({'rel': rel, 'url': '/uploads/' + rel,
                            'size': _fmt_size(size), 'size_bytes': size,
                            'ext': ext, 'mtime': mtime,
                            'has_origin': os.path.isfile(os.path.join(UPLOAD_DIR, '.originals', rel))})
    orphans.sort(key=lambda x: x['mtime'], reverse=True)
    total_size = sum(os.path.getsize(os.path.join(UPLOAD_DIR, o['rel'])) for o in orphans
                     if os.path.isfile(os.path.join(UPLOAD_DIR, o['rel'])))
    return render_template('admin/orphans.html', orphans=orphans,
                           total_size=_fmt_size(total_size))


# ─────────────── 后台: 设置 ───────────────

def _avatar_file_exists():
    """判断 config 中 avatar 指向的文件是否真实存在，避免显示已删除的图。"""
    avatar = app.config.get('avatar', '')
    if not avatar:
        return False
    # 兼容两种 URL 前缀：v1.0.6 起 /uploads/...（新上传目录），旧版 /static/uploads/...（旧目录已自动迁移）
    if '/uploads/' in avatar:
        rel = avatar.split('/uploads/', 1)[-1]
        base = UPLOAD_DIR
    elif '/static/' in avatar:
        rel = avatar.split('/static/', 1)[-1]
        base = os.path.join(BASE_DIR, 'static')
    else:
        return False
    if not rel:
        return False
    return os.path.exists(os.path.join(base, rel))


@app.route('/admin/status', methods=['GET', 'POST'])
@admin_required
def admin_status():
    """后台「服务时效」：云资源到期配置 + HTTP(S) 服务监控列表管理。"""
    if request.method == 'POST':
        save_setting('aliyun_access_key', request.form.get('aliyun_access_key', '').strip())
        save_setting('aliyun_server_type', request.form.get('aliyun_server_type', '').strip() or 'swas')
        save_setting('aliyun_access_secret', request.form.get('aliyun_access_secret', '').strip())
        save_setting('aliyun_region', request.form.get('aliyun_region', '').strip() or 'cn-hangzhou')
        save_setting('aliyun_instance_id', request.form.get('aliyun_instance_id', '').strip())
        save_setting('tencent_secret_id', request.form.get('tencent_secret_id', '').strip())
        save_setting('tencent_secret_key', request.form.get('tencent_secret_key', '').strip())
        save_setting('tencent_domain', request.form.get('tencent_domain', '').strip())
        save_setting('expiry_aliyun', request.form.get('expiry_aliyun', '').strip())
        save_setting('expiry_tencent', request.form.get('expiry_tencent', '').strip())
        # 云 API 同步结果（仅当后台点过「同步」且未手动修改时才带入，非空才持久化）
        for key in ('aliyun', 'tencent'):
            api_val = request.form.get('%s_expiry_api' % key, '').strip()
            if api_val:
                save_setting('%s_expiry_api' % key, api_val)
                save_setting('%s_expiry_api_ts' % key, str(int(time.time())))
        # 监控服务列表：name[] / url[] 同名数组，按顺序配对
        names = request.form.getlist('svc_name')
        urls = request.form.getlist('svc_url')
        services = []
        for n, u in zip(names, urls):
            n = (n or '').strip()
            u = _clean_monitor_url(u)
            if n and u:
                services.append({'name': n, 'url': u})
        save_setting('monitor_services', json.dumps(services, ensure_ascii=False))
        # 保存后立即探测一次，避免前台要等下一次 5 分钟轮询才有数据
        try:
            probe_all_services(force=True)
        except Exception:
            pass
        flash('服务时效配置已保存', 'success')
        return redirect(url_for('admin_status'))
    return render_template('admin/status.html',
                           expiry=get_expiry_info(),
                           services=_parse_monitor_services(),
                           status_items=get_services_status())


@app.route('/admin/status/probe', methods=['POST'])
@admin_required
def admin_status_probe():
    """立即重探全部监控服务，返回最新结果 JSON（后台「立即探测」）。"""
    probe_all_services(force=True)
    return jsonify({'ok': True, 'services': get_services_status()})


@app.route('/admin/status/test-cloud', methods=['POST'])
@admin_required
def admin_status_test_cloud():
    """同步云 API 到期时间：强制重新查询，结果仅返回页面预览，不落库。
    页面访问（/status、/api/status、后台页面）只读持久化结果，
    不会主动请求云 API；只有点击「同步」才调用，点「保存全部配置」后持久化。"""
    result = get_expiry_info(force=True)
    return jsonify({'ok': True, 'expiry': result})


@app.route('/admin/themes', methods=['GET', 'POST'])
@admin_required
def admin_themes():
    """外观与主题：独立页面展示全部主题，卡片选择后保存即切换（v1.3.0）。
    独立成页而非塞进设置页，是为了放几十个主题时能有更大的卡片网格。"""
    if request.method == 'POST':
        new_theme = request.form.get('active_theme', '')
        valid_keys = {t['key'] for t in list_themes()}
        if new_theme in valid_keys:
            save_setting('active_theme', new_theme)
            app.config['active_theme'] = new_theme
            _LAST_THEME_KEY[0] = new_theme  # 主动同步标记，避免下个请求再清一次缓存
            try:
                app.jinja_env.cache.clear()
            except Exception:
                pass
            flash('主题已切换为：' + new_theme, 'success')
        else:
            flash('无效的主题：' + new_theme, 'error')
        return redirect(url_for('admin_themes'))
    return render_template('admin/themes.html',
                           themes=list_themes(),
                           active_theme=_active_theme_key())


@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    if request.method == 'POST':
        for key in ['blog_name', 'blog_subtitle', 'author', 'author_bio',
                     'about_intro', 'skills', 'avatar', 'github_username',
                     'social_github', 'github_token', 'contact_email', 'home_title', 'icp_beian', 'police_beian',
                     'home_posts_count', 'posts_per_page',
                     'smtp_host', 'smtp_sender_name', 'smtp_port', 'smtp_user', 'smtp_pass', 'notify_email',
                     'footer_copyright_year', 'footer_copyright_owner', 'footer_powered_by',
                     'stats_code']:
            if key in request.form:
                val = request.form[key]
                if key == 'stats_code':
                    val = _sanitize_stats_code(val)
                save_setting(key, val)
                app.config[key] = val
        # 图片水印设置（开关为复选框，未勾选即为关闭）
        wm_on = '1' if request.form.get('watermark_enabled') else '0'
        # 先记录旧配置，用于判断“文本/位置/字号/开关”是否变化（变化才触发历史图后台刷新）
        wm_old_on = (app.config.get('watermark_enabled', '1') or '').strip() in ('1', 'on', 'true', 'yes')
        wm_old_text = _watermark_text()
        wm_old_pos = _watermark_position()
        wm_old_size = _watermark_size()
        save_setting('watermark_enabled', wm_on)
        app.config['watermark_enabled'] = wm_on
        for key in ('watermark_text', 'watermark_position', 'watermark_size'):
            if key in request.form:
                save_setting(key, request.form[key])
                app.config[key] = request.form[key]
        # 水印开关/文本/位置/字号任一变化 → 后台线程自动重做全部历史图（无需手动跑脚本）；
        # 首次启用或换文本/位置/字号，历史图都要按最新配置重画
        wm_new_on = wm_on in ('1', 'on', 'true', 'yes')
        wm_new_text = _watermark_text()
        wm_new_pos = _watermark_position()
        wm_new_size = _watermark_size()
        if (wm_new_on and wm_new_text
                and (wm_new_on != wm_old_on or wm_new_text != wm_old_text
                     or wm_new_pos != wm_old_pos or wm_new_size != wm_old_size)):
            if _start_wm_refresh(wm_new_text, wm_new_pos, wm_new_size):
                flash('水印配置已变化，历史图片正在后台自动刷新…', 'success')
            else:
                flash('水印配置已保存（上一轮刷新仍在进行，完成后即按新配置生效）', 'success')
        # 复选框未勾选时不会随表单提交，需单独处理为关闭态
        comments_on = '1' if request.form.get('comments_enabled') else '0'
        save_setting('comments_enabled', comments_on)
        app.config['comments_enabled'] = comments_on
        # 评论邮件通知开关（同上，未勾选即为关闭）
        notify_on = '1' if request.form.get('comment_notify') else '0'
        save_setting('comment_notify', notify_on)
        app.config['comment_notify'] = notify_on
        # 发送 SMTP 测试邮件（SMTP 配置已在上方保存循环中入库，这里直接验证）
        if request.form.get('test_email'):
            tgt = (request.form.get('notify_email') or '').strip() or (request.form.get('contact_email') or '').strip()
            try:
                _smtp_send(
                    tgt,
                    '[%s] SMTP 测试邮件' % (app.config.get('blog_name') or 'Blog'),
                    ('<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head><body>'
                     '<div class="wrap"><div class="card">'
                     '<div class="head">SMTP 配置测试</div>'
                     '<div class="meta">服务器：%s:%s</div>'
                     '<div class="meta">发件账号：%s</div>'
                     '<div class="meta">收件人：%s</div>'
                     '<div class="foot">收到本邮件说明 SMTP 配置可用，评论互动通知可正常送达。</div>'
                     '</div></div></body></html>')
                    % (_NOTIFY_CSS, request.form.get('smtp_host'), request.form.get('smtp_port'),
                       request.form.get('smtp_user'), tgt))
                flash('测试邮件已发送（%s），请查收收件箱/垃圾箱' % tgt, 'success')
            except Exception as e:
                flash('测试邮件发送失败：%s' % e, 'error')
        # 导航菜单开关（同上，未勾选即为关闭）
        for nav_key, _, _ in NAV_PAGES:
            nav_on = '1' if request.form.get('nav_' + nav_key) == '1' else '0'
            save_setting('nav_' + nav_key, nav_on)
            app.config['nav_' + nav_key] = nav_on

        db = get_db()
        cur_user = session.get('admin_username', 'admin')
        # 修改管理员账号名（校验：非空、仅含安全字符、长度限制）
        new_username = request.form.get('admin_username', '').strip()
        if new_username and new_username != cur_user:
            if not re.match(r'^[a-zA-Z0-9_\u4e00-\u9fff-]{2,30}$', new_username):
                flash('账号名格式不合法（仅支持中英文、数字、下划线、连字符，2-30 字符）', 'error')
            else:
                exist = db.execute("SELECT id FROM users WHERE username=?", (new_username,)).fetchone()
                if exist:
                    flash('账号名已存在，未修改', 'error')
                else:
                    db.execute("UPDATE users SET username=? WHERE username=?", (new_username, cur_user))
                    session['admin_username'] = new_username
                    flash('管理员账号名已修改为：' + new_username, 'success')
        # 修改密码：需验证旧密码
        new_pwd = request.form.get('new_password', '')
        if new_pwd and len(new_pwd) >= 6:
            old_pwd = request.form.get('old_password', '')
            if old_pwd:
                cur_hash = db.execute("SELECT password_hash FROM users WHERE username=?",
                                      (session.get('admin_username', 'admin'),)).fetchone()
                if cur_hash and verify_password(cur_hash['password_hash'], old_pwd):
                    db.execute("UPDATE users SET password_hash=? WHERE username=?",
                               (hash_password(new_pwd), session.get('admin_username', 'admin')))
                    flash('密码已修改', 'success')
                else:
                    flash('旧密码错误，密码未修改', 'error')
            else:
                flash('请先输入旧密码', 'error')
        # 头像上传 -> 固定存到 uploads/avatar/（项目根）
        avatar_file = request.files.get('avatar_file') if 'avatar_file' in request.files else None
        if avatar_file and avatar_file.filename:
            ext = os.path.splitext(avatar_file.filename)[1].lower()
            if ext not in ALLOWED_IMAGE_EXT:
                flash('头像格式不支持（仅 png/jpg/jpeg/gif/webp/heic）', 'error')
            elif ext in ('.heic', '.heif') and not (_HAS_HEIF and _HAS_PIL):
                flash('服务器缺少 HEIC 解码支持，无法处理 HEIC 头像', 'error')
            else:
                avatar_dir = os.path.join(UPLOAD_DIR, 'avatar')
                os.makedirs(avatar_dir, exist_ok=True)
                # 头像固定压缩为 144px 正方形 JPEG（显示仅 72px，体积几十 KB）
                saved_ext = '.jpg'
                filename = 'avatar' + saved_ext
                save_path = os.path.join(avatar_dir, filename)
                if _HAS_PIL:
                    if ext in ('.heic', '.heif'):
                        # HEIC 用 open_heif 直接解码（不依赖 Pillow 插件注册）
                        img = pillow_heif.open_heif(avatar_file.stream).to_pillow().convert('RGB')
                    else:
                        img = Image.open(avatar_file.stream).convert('RGB')
                    # 居中裁剪为正方形
                    w, h = img.size
                    s = min(w, h)
                    img = img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
                    img = img.resize((144, 144), Image.LANCZOS)
                    img.save(save_path, 'JPEG', quality=85, optimize=True, progressive=True)
                else:
                    avatar_file.save(save_path)
                avatar_url = url_for('uploaded_file', filename='avatar/' + filename)
                save_setting('avatar', avatar_url)
                app.config['avatar'] = avatar_url
                flash('头像已更新', 'success')
        # ── OTP 双重验证：开关 / 绑定 / 重绑 / 关闭（开关即绑定）──
        want_otp = '1' if request.form.get('otp_enabled') else '0'
        cur_otp = _otp_enabled()
        new_secret = (request.form.get('otp_secret') or '').strip().upper()
        confirm_code = (request.form.get('otp_confirm_code') or '').strip()
        if want_otp and not cur_otp:
            # 启用：必须扫码并输入正确验证码才落库生效，同时生成一次性恢复码
            if new_secret and _totp_verify(new_secret, confirm_code):
                codes, hashes = _gen_recovery_codes()
                for k, v in (('otp_enabled', '1'), ('otp_secret', new_secret),
                             ('otp_recovery_codes', json.dumps(hashes))):
                    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, v))
                    app.config[k] = v
                session['_otp_new_codes'] = codes  # 仅本次 GET 展示
                flash('OTP 双重验证已启用，请立即保存恢复码', 'success')
            else:
                flash('OTP 启用失败：请先点击「生成二维码」扫码，再输入验证码确认绑定', 'error')
        elif not want_otp and _otp_configured():
            # 关闭：清空密钥与恢复码，下次启用走全新绑定
            for k in ('otp_enabled', 'otp_secret', 'otp_recovery_codes'):
                db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, '')", (k,))
                app.config[k] = ''
            flash('OTP 双重验证已关闭', 'success')
        elif want_otp and cur_otp and request.form.get('otp_rotate') and new_secret:
            # 已启用状态下重新绑定（换新密钥 + 新恢复码）
            if _totp_verify(new_secret, confirm_code):
                codes, hashes = _gen_recovery_codes()
                for k, v in (('otp_secret', new_secret), ('otp_recovery_codes', json.dumps(hashes))):
                    db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, v))
                    app.config[k] = v
                session['_otp_new_codes'] = codes
                flash('OTP 已重新绑定，恢复码已更新，请保存新恢复码', 'success')
            else:
                flash('重新绑定失败：请用新二维码扫码并输入对应验证码', 'error')
        db.commit()
        db.close()
        flash('设置已保存', 'success')
        return redirect(url_for('admin_settings'))
    otp_new_codes = session.pop('_otp_new_codes', None)
    return render_template('admin/settings.html',
                           admin_username=session.get('admin_username', 'admin'),
                           admin_avatar=app.config.get('avatar', ''),
                           avatar_exists=_avatar_file_exists(),
                           smtp_host=app.config.get('smtp_host', ''),
                           smtp_port=app.config.get('smtp_port', '465'),
                           smtp_user=app.config.get('smtp_user', ''),
                           smtp_pass=app.config.get('smtp_pass', ''),
                           notify_email=app.config.get('notify_email', ''),
                           smtp_sender_name=app.config.get('smtp_sender_name', ''),
                           comment_notify=app.config.get('comment_notify', '0'),
                           watermark_enabled=app.config.get('watermark_enabled', '1'),
                           watermark_text=app.config.get('watermark_text', ''),
                           watermark_position=app.config.get('watermark_position', 'br'),
                           watermark_size=app.config.get('watermark_size', 'm'),
                           wm_refresh=wm_refresh_state(),
                           otp_enabled=_otp_configured(),
                           otp_secret_set=bool(_otp_secret()),
                           otp_emergency=_otp_emergency_off(),
                           otp_recovery_left=_otp_recovery_remaining(),
                           otp_new_codes=otp_new_codes,
                           otp_mail_ok=bool((app.config.get('smtp_host') or '').strip()))


@app.route('/admin/settings/test-email', methods=['POST'])
@admin_required
def admin_settings_test_email():
    """SMTP 连通性测试：以表单当前配置试发，不落库；返回 JSON，前端卡片内反馈（不刷新页面）。"""
    tgt = (request.form.get('notify_email') or '').strip() or (request.form.get('contact_email') or '').strip()
    cfg = {
        'smtp_host': (request.form.get('smtp_host') or '').strip(),
        'smtp_port': (request.form.get('smtp_port') or '').strip(),
        'smtp_user': (request.form.get('smtp_user') or '').strip(),
        'smtp_pass': request.form.get('smtp_pass') or '',
        'smtp_sender_name': (request.form.get('smtp_sender_name') or '').strip(),
    }
    try:
        _smtp_send(
            tgt,
            '[%s] SMTP 测试邮件' % (app.config.get('blog_name') or 'Blog'),
            ('<!doctype html><html><head><meta charset="utf-8"><style>%s</style></head><body>'
             '<div class="wrap"><div class="card">'
             '<div class="head">SMTP 配置测试</div>'
             '<div class="meta">服务器：%s:%s</div>'
             '<div class="meta">发件账号：%s</div>'
             '<div class="meta">收件人：%s</div>'
             '<div class="foot">收到本邮件说明 SMTP 配置可用，评论互动通知可正常送达。</div>'
             '</div></div></body></html>')
            % (_NOTIFY_CSS, cfg['smtp_host'], cfg['smtp_port'],
               cfg['smtp_user'], tgt),
            overrides=cfg)
        return jsonify({'ok': True, 'msg': '测试邮件已发送（%s），请查收收件箱/垃圾箱' % tgt})
    except Exception as e:
        return jsonify({'ok': False, 'msg': '发送失败：%s' % e})


# ─────────────── 数据导出与备份 ───────────────

BACKUP_DIR = os.path.join(BASE_DIR, 'backups')

@app.route('/admin/export')
@admin_required
def admin_export():
    """数据导出与备份管理页面"""
    backups = []
    os.makedirs(BACKUP_DIR, exist_ok=True)
    for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
        fp = os.path.join(BACKUP_DIR, f)
        if os.path.isfile(fp):
            size = os.path.getsize(fp)
            size_str = f'{size / 1024:.1f} KB' if size < 1024 * 1024 else f'{size / 1024 / 1024:.1f} MB'
            backups.append({
                'filename': f,
                'size': size_str,
                'mtime': datetime.fromtimestamp(os.path.getmtime(fp)).strftime('%Y-%m-%d %H:%M')
            })
    # 数据库统计
    db = get_db()
    stats = {}
    for t in ['posts', 'projects', 'links', 'comments', 'timeline', 'categories']:
        stats[t] = db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
    stats['settings'] = db.execute('SELECT COUNT(*) FROM settings').fetchone()[0]
    db.close()
    return render_template('admin/export.html',
                           backups=backups,
                           stats=stats,
                           blog_db=os.path.basename(DB_PATH))


@app.route('/admin/export/db-backup', methods=['POST'])
@admin_required
def admin_export_db_backup():
    """创建数据库文件备份"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'blog_backup_{ts}.db'
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    shutil.copy2(DB_PATH, backup_path)
    flash(f'数据库备份成功：{backup_name}', 'success')
    return redirect(url_for('admin_export'))


@app.route('/admin/export/download/<filename>')
@admin_required
def admin_export_download(filename):
    """下载备份文件"""
    safe_name = secure_filename(filename)
    fp = os.path.join(BACKUP_DIR, safe_name)
    if not os.path.isfile(fp):
        abort(404)
    return send_file(fp, as_attachment=True, download_name=safe_name)


@app.route('/admin/export/delete/<filename>', methods=['POST'])
@admin_required
def admin_export_delete(filename):
    """删除备份文件"""
    safe_name = secure_filename(filename)
    fp = os.path.join(BACKUP_DIR, safe_name)
    if os.path.isfile(fp):
        os.remove(fp)
        flash(f'已删除：{safe_name}', 'success')
    else:
        flash('文件不存在', 'error')
    return redirect(url_for('admin_export'))


@app.route('/admin/export/json')
@admin_required
def admin_export_json():
    """导出全站数据为 JSON 文件"""
    db = get_db()
    data = {}

    # posts
    posts = db.execute('SELECT * FROM posts ORDER BY id').fetchall()
    data['posts'] = [dict(p) for p in posts]

    # projects
    projects = db.execute('SELECT * FROM projects ORDER BY id').fetchall()
    data['projects'] = [dict(p) for p in projects]

    # links
    links = db.execute('SELECT * FROM links ORDER BY id').fetchall()
    data['links'] = [dict(l) for l in links]

    # comments
    comments = db.execute("""
        SELECT c.*, p.title as post_title
        FROM comments c LEFT JOIN posts p ON c.post_id = p.id
        ORDER BY c.id
    """).fetchall()
    data['comments'] = [dict(c) for c in comments]

    # timeline
    timeline = db.execute('SELECT * FROM timeline ORDER BY id').fetchall()
    data['timeline'] = [dict(t) for t in timeline]

    # categories
    categories = db.execute('SELECT * FROM categories ORDER BY id').fetchall()
    data['categories'] = [dict(c) for c in categories]

    # settings (排除密码等敏感字段)
    settings = db.execute("SELECT * FROM settings WHERE key NOT LIKE '%password%'").fetchall()
    data['settings'] = [dict(s) for s in settings]

    data['exported_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    db.close()

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    buffer = io.BytesIO()
    buffer.write(json_str.encode('utf-8'))
    buffer.seek(0)
    return send_file(buffer, mimetype='application/json',
                     as_attachment=True,
                     download_name=f'blog_export_{ts}.json')


@app.route('/admin/export/markdown')
@admin_required
def admin_export_markdown():
    """导出文章为 Markdown 打包 ZIP"""
    db = get_db()
    posts = db.execute("SELECT * FROM posts WHERE status != 'draft' ORDER BY created_at DESC").fetchall()
    categories = {c['id']: c['name'] for c in db.execute('SELECT id, name FROM categories').fetchall()}
    db.close()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for post in posts:
            p = dict(post)
            # --- YAML front matter ---
            tags = json.loads(p.get('tags', '[]')) if isinstance(p.get('tags'), str) else (p.get('tags') or [])
            cat_name = categories.get(p.get('category_id'), '') if p.get('category_id') else ''
            fm = {
                'title': p['title'],
                'slug': p['slug'],
                'date': (p.get('created_at') or '')[:10],
                'status': p.get('status', 'published'),
                'tags': tags,
                'category': cat_name,
                'read_time': p.get('read_time', 3)
            }
            if p.get('cover'):
                fm['cover'] = p['cover']
            if p.get('excerpt'):
                fm['excerpt'] = p['excerpt']

            yaml_lines = ['---']
            for k, v in fm.items():
                if isinstance(v, list):
                    yaml_lines.append(f'{k}:')
                    for item in v:
                        yaml_lines.append(f'  - {item}')
                else:
                    yaml_lines.append(f'{k}: {v}')
            yaml_lines.append('---')
            front = '\n'.join(yaml_lines) + '\n\n'

            # slug → 文件名
            safe_slug = re.sub(r'[<>:"/\\|?*]', '-', p['slug'])
            zf.writestr(f'{safe_slug}.md', front + p['content'])

    buffer.seek(0)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    return send_file(buffer, mimetype='application/zip',
                     as_attachment=True,
                     download_name=f'blog_posts_{ts}.zip')


# ─────────────── 系统升级 ───────────────

UPGRADE_REPO = 'Contribuv/infowe_blog'
UPGRADE_RELEASE_URL = f'https://github.com/{UPGRADE_REPO}/releases/latest'
# Gitee 镜像仓库：GitHub 检测/下载不稳定时自动回退源（发版后需在 Gitee 同步 tag）
# 可用环境变量 UPGRADE_GITEE_REPO 覆盖
UPGRADE_GITEE_REPO = (os.environ.get('UPGRADE_GITEE_REPO', 'infowe/infowe_blog') or '').strip('/')
# 升级时跳过、绝不覆盖的目录/文件（用户数据与运行时数据）
UPGRADE_SKIP = {
    'data', 'static/uploads', 'uploads', 'backups', 'posts',
    '.git', '__pycache__', '.venv', 'venv',
    '.env', '.flaskenv', 'upgrade.lock', '*.db', '*.session',
}
UPGRADE_MAX_BYTES = 200 * 1024 * 1024  # 下载/解压上限 200MB，防异常包
UPGRADE_LOCK_TTL = 600  # 升级锁超时（秒）：超过视为上次升级异常中断，自动清理后允许重试
UPGRADE_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  'data', 'upgrade_cache.json')  # 版本检测缓存落盘，重启/多进程不丢


def _load_upgrade_cache():
    """启动/首访时从磁盘加载版本检测缓存，避免重启后首个请求必等 GitHub。"""
    try:
        with open(UPGRADE_CACHE_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get('t'), (int, float)):
            # 磁盘 JSON 中 version 是数组（tuple 序列化后的 list），读回需还原为
            # tuple，否则 inject_globals 里 list 与 parse_version 的 tuple 比较
            # 会 TypeError（后台页面 500）
            info = data.get('info')
            if isinstance(info, dict) and isinstance(info.get('version'), list):
                info['version'] = tuple(info['version'])
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {'t': 0, 'ok': None, 'info': None}


def _save_upgrade_cache():
    """把版本检测缓存原子写入磁盘（多进程部署下各 worker 结果一致）。"""
    try:
        tmp = UPGRADE_CACHE_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(UPGRADE_CACHE, f, ensure_ascii=False)
        os.replace(tmp, UPGRADE_CACHE_FILE)
    except OSError:
        pass


UPGRADE_CACHE = _load_upgrade_cache()  # 检测结果缓存：{'t': 时间戳, 'ok': 是否成功, 'info': 版本信息}

# 升级包下载镜像（仅作备用）：默认优先直连 GitHub，连接失败/超时才自动降级到镜像，
# 避免部分网络环境直连 codeload.github.com 下载源码包长时间卡死。
# 可用环境变量 UPGRADE_MIRRORS 覆盖（逗号分隔多个镜像，如 'https://ghproxy.net/,https://gh-proxy.com/'），
# 设空串则纯直连、不使用镜像。
UPGRADE_MIRRORS = [m.rstrip('/') + '/' for m in
                   (os.environ.get('UPGRADE_MIRRORS', 'https://ghproxy.net/') or '').split(',') if m.strip()]
UPGRADE_DOWNLOAD_TIMEOUT = int(os.environ.get('UPGRADE_DOWNLOAD_TIMEOUT', '60'))  # 单次下载超时（秒）


def parse_version(v):
    """'v1.2.3' / '1.2.3' → (1, 2, 3)；无法解析返回 None。"""
    m = re.match(r'^v?(\d+)\.(\d+)\.(\d+)', str(v).strip())
    return tuple(int(x) for x in m.groups()) if m else None


def check_latest_version(force=False):
    """查询最新版本：GitHub Releases 优先，失败自动回退 Gitee 镜像仓库。
    失败静默返回 None（不阻塞页面），结果缓存到磁盘。
    返回 {'tag','version','html_url','body','published_at','source'} 或 None。"""
    now = time.time()
    cached = UPGRADE_CACHE.get('info')
    # 成功/失败都缓存 10 分钟（国内服务器访问 GitHub 慢，避免反复打 API）
    if not force and UPGRADE_CACHE.get('t', 0) and now - UPGRADE_CACHE['t'] < 600:
        return cached
    info = None
    # 源 1：GitHub Releases API
    try:
        req = urllib.request.Request(
            f'https://api.github.com/repos/{UPGRADE_REPO}/releases/latest',
            headers={'User-Agent': 'infowe-Blog-updater', 'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(req, timeout=6, context=_github_ssl_context()) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        tag = (data.get('tag_name') or '').strip().lstrip('v')
        ver = parse_version(tag)
        if ver:
            # 规范化 tag（Gitee 建发行版易把标题填进标签名，如 'v1.3.51：安全加固'），
            # 升级下载 URL 只认规范 tag
            info = {
                'tag': '.'.join(map(str, ver)),
                'version': ver,
                'html_url': data.get('html_url') or UPGRADE_RELEASE_URL,
                'body': (data.get('body') or '').strip()[:2000],
                'published_at': (data.get('published_at') or '')[:10],
                'source': 'github',
            }
    except Exception:
        pass
    # 源 2：Gitee 镜像（GitHub 超时/限流/被墙时的回退，国内直连稳定）
    if info is None and UPGRADE_GITEE_REPO:
        try:
            req = urllib.request.Request(
                f'https://gitee.com/api/v5/repos/{UPGRADE_GITEE_REPO}/releases/latest',
                headers={'User-Agent': 'infowe-Blog-updater'})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            tag = (data.get('tag_name') or '').strip().lstrip('v')
            ver = parse_version(tag)
            if ver:
                info = {
                    'tag': '.'.join(map(str, ver)),
                    'version': ver,
                    'html_url': data.get('html_url') or f'https://gitee.com/{UPGRADE_GITEE_REPO}/releases',
                    'body': (data.get('body') or '').strip()[:2000],
                    'published_at': (data.get('published_at') or data.get('created_at') or '')[:10],
                    'source': 'gitee',
                }
        except Exception:
            pass
    UPGRADE_CACHE['t'] = now
    UPGRADE_CACHE['ok'] = info is not None
    UPGRADE_CACHE['info'] = info
    _save_upgrade_cache()
    return info


def _upgrade_download(url, dest, max_bytes=None, alt_urls=None):
    """流式下载文件到 dest，超过大小上限则中断。

    尝试顺序：直连原始 URL → UPGRADE_MIRRORS 加速镜像 → alt_urls 完整备用源
    （如 Gitee 归档包，国内直连稳定）。全部失败抛出最后一个错误。"""
    max_bytes = max_bytes or UPGRADE_MAX_BYTES

    def _stream_download(u, target):
        req = urllib.request.Request(u, headers={'User-Agent': 'infowe-Blog-updater'})
        with urllib.request.urlopen(req, timeout=UPGRADE_DOWNLOAD_TIMEOUT,
                                    context=_github_ssl_context()) as resp:
            with open(target, 'wb') as f:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
                    if os.path.getsize(target) > max_bytes:
                        raise RuntimeError('下载内容超过大小上限，已取消')

    attempts = [url] + [m + url for m in UPGRADE_MIRRORS] + list(alt_urls or [])
    last_err = None
    for i, u in enumerate(attempts):
        try:
            _stream_download(u, dest)
            if i > 0:
                print(f'[升级] 直连失败，已通过镜像下载：{u}')
            return dest
        except Exception as e:
            last_err = e
            if os.path.exists(dest):
                os.remove(dest)
    raise last_err


def _upgrade_apply(tmp_root, tag):
    """把解压后的新代码覆盖到 BASE_DIR，跳过 UPGRADE_SKIP 中的数据/用户目录。
    返回替换的文件数。"""
    def skip(rel):
        rel = rel.replace('\\', '/')
        for name in UPGRADE_SKIP:
            if name in ('*.db', '*.session'):
                if rel.endswith(name[1:]):
                    return True
            elif rel == name or rel.startswith(name + '/'):
                return True
        return False

    replaced = 0
    for dirpath, dirnames, filenames in os.walk(tmp_root):
        dirnames[:] = [d for d in dirnames if not skip(os.path.relpath(os.path.join(dirpath, d), tmp_root))]
        for fn in filenames:
            src = os.path.join(dirpath, fn)
            rel = os.path.relpath(src, tmp_root)
            if skip(rel):
                continue
            dst = os.path.join(BASE_DIR, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            replaced += 1
    return replaced


def do_upgrade(tag):
    """执行升级：数据备份 → 下载 → 解压 → 校验 → 覆盖代码。返回 (成功标志, 消息)。"""
    lock_path = os.path.join(BASE_DIR, 'upgrade.lock')
    try:
        # 过期锁（上次升级异常中断残留）自动清理，避免永久卡"升级进行中"
        if os.path.exists(lock_path) and time.time() - os.path.getmtime(lock_path) > UPGRADE_LOCK_TTL:
            try:
                os.remove(lock_path)
            except OSError:
                pass
        # 原子创建锁，避免并发重复升级
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(int(time.time())).encode('utf-8'))
        os.close(fd)
    except FileExistsError:
        return False, '升级任务已在进行中，请稍候再试'
    tmp = tempfile.mkdtemp(prefix='infowe_upgrade_')
    try:
        # 1. 数据备份（数据库 + 用户上传）
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        bak_dir = os.path.join(BACKUP_DIR, f'upgrade_{ts}_{tag}')
        os.makedirs(bak_dir, exist_ok=True)
        if os.path.isfile(DB_PATH):
            shutil.copy2(DB_PATH, os.path.join(bak_dir, 'blog.db'))
        if os.path.isdir(UPLOAD_DIR):
            shutil.copytree(UPLOAD_DIR, os.path.join(bak_dir, 'uploads'), dirs_exist_ok=True)

        # 2. 下载源码压缩包（直连优先 → 加速镜像 → Gitee 镜像仓库）
        zip_url = f'https://github.com/{UPGRADE_REPO}/archive/refs/tags/v{tag}.zip'
        alt_urls = ([f'https://gitee.com/{UPGRADE_GITEE_REPO}/archive/v{tag}.zip']
                    if UPGRADE_GITEE_REPO else [])
        zip_path = _upgrade_download(zip_url, os.path.join(tmp, 'release.zip'), alt_urls=alt_urls)

        # 3. 安全解压（拒绝路径穿越、超限文件）
        with zipfile.ZipFile(zip_path) as zf:
            for zi in zf.infolist():
                target = os.path.normpath(os.path.join(tmp, zi.filename))
                if not target.startswith(tmp + os.sep):
                    raise RuntimeError('压缩包内含非法路径，已中止')
                if zi.is_dir():
                    continue
                if zi.file_size > UPGRADE_MAX_BYTES:
                    raise RuntimeError('压缩包内单个文件过大，已中止')
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with zf.open(zi) as src, open(target, 'wb') as dst:
                    shutil.copyfileobj(src, dst)

        # 4. 定位代码根目录并校验新版本
        entries = [d for d in os.listdir(tmp) if os.path.isdir(os.path.join(tmp, d)) and d != 'release.zip']
        root = os.path.join(tmp, entries[0]) if len(entries) == 1 else tmp
        if not os.path.isfile(os.path.join(root, 'app.py')):
            raise RuntimeError('压缩包中未找到 app.py，已中止')
        src_code = open(os.path.join(root, 'app.py'), encoding='utf-8').read()
        m = re.search(r"VERSION\s*=\s*['\"]([^'\"]+)['\"]", src_code)
        new_ver = parse_version(m.group(1)) if m else None
        cur_ver = parse_version(VERSION)
        if not new_ver or new_ver <= cur_ver:
            raise RuntimeError('下载的版本不高于当前版本，已中止')

        # 5. 覆盖代码（跳过数据/用户目录）
        replaced = _upgrade_apply(root, tag)
        if replaced == 0:
            raise RuntimeError('没有可替换的文件，已中止')
        return True, f'升级成功：代码已从 v{VERSION} 更新为 v{tag}（替换 {replaced} 个文件）。数据已自动备份到 backups/upgrade_{ts}_{tag}，请重启服务生效。'
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if os.path.exists(lock_path):
            os.remove(lock_path)


@app.route('/admin/upgrade', methods=['GET', 'POST'])
@admin_required
def admin_upgrade():
    """系统升级页：页面立即渲染，版本检测由前端异步请求 /admin/upgrade/check 完成，避免网络卡顿阻塞页面。"""
    cur_ver = parse_version(VERSION)

    if request.method == 'POST':
        # 升级动作仍需要最新版本信息，超时放宽到前端可感知
        info = check_latest_version(force=True)
        upgradable = bool(info and cur_ver and info['version'] > cur_ver)
        if not upgradable:
            flash('当前已是最新版本，无需升级', 'error')
            return redirect(url_for('admin_upgrade'))
        try:
            ok, msg = do_upgrade(info['tag'])
        except Exception as e:
            ok, msg = False, '升级失败：' + str(e)
        flash(msg, 'success' if ok else 'error')
        return redirect(url_for('admin_upgrade'))
    return render_template('admin/upgrade.html',
                           current_version=VERSION,
                           info=None, upgradable=False)


def _sanitize_html(html):
    """剥离 script/iframe/object/embed、svg、事件属性与 javascript:，抵消 Markdown→HTML 后的注入风险。"""
    html = re.sub(r'<(script|iframe|object|embed|svg)\b[^>]*>.*?</\1>', '', html, flags=re.S | re.I)
    html = re.sub(r'<(script|iframe|object|embed|svg)\b[^>]*/?>', '', html, flags=re.S | re.I)
    html = re.sub(r'\son\w+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)', '', html, flags=re.I)
    html = re.sub(r'javascript\s*:', '', html, flags=re.I)
    html = re.sub(r'data\s*:\s*text/html', '', html, flags=re.I)
    html = re.sub(r'<form\b[^>]*>.*?</form>', '', html, flags=re.S | re.I)
    return html


def _sanitize_stats_code(html):
    """统计代码消毒：仅允许 <script> 标签保留（去除 on* 事件和 javascript:），
    其他所有 HTML 标签和事件属性均剥离。用于 admin_settings 中的 stats_code 存储前消毒。"""
    if not html:
        return ''
    html = re.sub(r'\son\w+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)', '', html, flags=re.I)
    html = re.sub(r'javascript\s*:', '', html, flags=re.I)
    html = re.sub(r'<(?!(script\b|/script>)).*?>', '', html, flags=re.I)
    html = re.sub(r'\n\s*\n+', '\n', html).strip()
    return html


def _md_to_safe_html(text):
    """Markdown → HTML 并轻量消毒。内容来自自有 GitHub Releases（升级页），此消毒仅为兜底。"""
    html = markdown.markdown(text, extensions=['fenced_code', 'nl2br'])
    return _sanitize_html(html)


@app.route('/admin/upgrade/check')
@admin_required
def admin_upgrade_check():
    """异步版本检测接口：返回 JSON，前端据此渲染升级卡片。force=1 跳过缓存。"""
    cur_ver = parse_version(VERSION)
    info = check_latest_version(force=(request.args.get('force') == '1'))
    upgradable = bool(info and cur_ver and info['version'] > cur_ver)
    body = info['body'] if info else ''
    return jsonify({
        'ok': info is not None,
        'current_version': VERSION,
        'latest_version': (info['tag'] if info else ''),
        'tag': (info['tag'] if info else ''),
        'upgradable': upgradable,
        'published_at': (info['published_at'] if info else ''),
        'body': body,
        'body_html': _md_to_safe_html(body) if body else '',
        'release_url': (info['html_url'] if info else UPGRADE_RELEASE_URL),
        'source': (info.get('source', 'github') if info else ''),
    })


# ─────────────── 启动 ───────────────

if __name__ == '__main__':
    # 生产部署请用 gunicorn 等 WSGI 服务器（不走此分支）。
    # debug 默认关闭；本地开发可设环境变量 FLASK_DEBUG=1 开启。
    # 切勿在对外暴露的环境中以 debug=True 运行，否则调试器可被远程代码执行。
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
