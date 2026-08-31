"""
infowe Blog - Python Flask Backend
SQLite 数据库驱动，完整前台 + 后台管理
新增：GitHub 项目页、搜索、分页、友情链接、精选文章
"""

# 应用版本号（后台显示用，修改请同步更新此处）
VERSION = '1.2.1'

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
import uuid
import threading
import urllib.parse
from datetime import datetime, timezone
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
from flask import Flask, render_template, abort, request, redirect, url_for, session, flash, jsonify, send_from_directory, send_file

app = Flask(__name__)
# secret_key 优先从环境变量读取（部署时务必设置 BLOG_SECRET_KEY），
# 避免源码中硬编码导致 session 被伪造。fallback 仅在本地开发时使用。
app.secret_key = os.environ.get('BLOG_SECRET_KEY', 'infowe-blog-secret-key-2024')


# 在 Nginx 反代后运行时，让 request.remote_addr 自动还原为真实客户端 IP。
# x_for=1 表示信任来自 1 层可信代理（Nginx）转发过来的 X-Forwarded-For 第一个值。
# 只有经过 Nginx 转发的请求才会被改写，直接访问本机的伪造头无效，避免 IP 欺骗。
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

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
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def hash_password(password):
    # 使用 werkzeug 的安全哈希（pbkdf2 + 随机盐 + 多次迭代）
    # 定义放在 init_db 之前，因为 init_db 在模块导入期会被调用，需要此函数已就绪。
    return ws.generate_password_hash(password, method='pbkdf2:sha256', salt_length=16)


def init_db():
    db = get_db()

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
            author TEXT NOT NULL DEFAULT 'Anonymous',
            content TEXT NOT NULL,
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

    # 默认管理员
    admin_exists = db.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    if not admin_exists:
        db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                   ('admin', hash_password('admin123')))

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
    ]
    for k, v in defaults:
        db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    db.commit()
    migrate_from_json(db)
    db.close()


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
    db = get_db()
    rows = db.execute("SELECT key, value FROM settings").fetchall()
    for row in rows:
        app.config[row['key']] = row['value']
    db.close()


# ─────────────── 服务时效 / Server Status ───────────────
# 云资源到期时间查询（阿里云轻量 / 腾讯云域名）+ HTTP(S) 服务可达性监控。
# - 云到期时间：密钥签名调用 OpenAPI，失败自动回退后台手动填写的到期日。
# - 服务监控：守护线程每 5 分钟轮询，结果写入 service_checks 表，前台读聚合。

def _parse_monitor_services():
    """解析 settings 中 monitor_services 的 JSON，返回非空 URL 的服务字典列表。"""
    raw = app.config.get('monitor_services', '[]')
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [s for s in data if isinstance(s, dict) and s.get('url')]
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


def _http_get_json(url, headers=None, timeout=8):
    """GET 请求并解析 JSON；失败抛出异常由调用方兜底。"""
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
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


def _ssl_cert_days(hostname, port=443, timeout=5):
    """直连获取 SSL 证书剩余天数，失败返回 -1。"""
    if not hostname:
        return -1
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=hostname) as tls:
                cert = tls.getpeercert()
        not_after = cert.get('notAfter')
        if not not_after:
            return -1
        exp = datetime.strptime(not_after, '%b %d %H:%M:%S %Y %Z')
        return (exp - datetime.utcnow()).days
    except Exception:
        return -1


def probe_url(url, timeout=5):
    """探测单个 URL：返回 (ok, latency_ms, cert_days, detail)。"""
    url = (url or '').strip()
    if not url.startswith(('http://', 'https://')):
        return False, 0, -1, 'URL 格式错误'
    try:
        p = urllib.parse.urlparse(url)
        hostname = p.hostname
    except Exception:
        return False, 0, -1, 'URL 解析失败'
    start = time.time()
    cert_days = -1
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'infowe-status/1.0'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                code = resp.getcode()
        except urllib.error.HTTPError as e:
            code = e.code
        latency = int((time.time() - start) * 1000)
        if p.scheme == 'https':
            cert_days = _ssl_cert_days(hostname)
        ok = 200 <= code < 400
        return ok, latency, cert_days, 'HTTP %d' % code
    except Exception as e:
        latency = int((time.time() - start) * 1000)
        return False, latency, -1, str(e)[:120]


def probe_all_services(force=False):
    """轮询全部监控服务并写入 service_checks。
    默认按 MONITOR_INTERVAL 窗口去重；force=True 时立即重探。"""
    services = _parse_monitor_services()
    if not services:
        return {}
    with MONITOR_LOCK:
        now = time.time()
        db = get_db()
        results = {}
        for svc in services:
            name = (svc.get('name') or svc.get('url') or '').strip()
            url = (svc.get('url') or '').strip()
            if not name or not url:
                continue
            if not force:
                row = db.execute(
                    "SELECT checked_at FROM service_checks WHERE service_id=? "
                    "ORDER BY checked_at DESC LIMIT 1", (name,)).fetchone()
                if row and now - row['checked_at'] < MONITOR_INTERVAL:
                    continue
            ok, latency, cert_days, detail = probe_url(url)
            db.execute(
                "INSERT INTO service_checks (service_id, checked_at, ok, latency_ms, cert_days, detail) "
                "VALUES (?,?,?,?,?,?)",
                (name, now, 1 if ok else 0, latency, cert_days, detail))
            results[name] = {
                'name': name, 'url': url, 'ok': ok,
                'latency_ms': latency, 'cert_days': cert_days, 'detail': detail,
            }
        for name in results:
            db.execute(
                "DELETE FROM service_checks WHERE service_id=? AND id NOT IN "
                "(SELECT id FROM service_checks WHERE service_id=? ORDER BY id DESC LIMIT 2000)",
                (name, name))
        db.commit()
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


def _login_blocked(ip):
    rec = _LOGIN_ATTEMPTS.get(ip)
    if not rec:
        return False
    if rec.get('lock_until', 0) > time.time():
        return True
    return False


def _register_fail(ip):
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
        conditions.append("created_at LIKE ?")
        params.append(f'{year}%')

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


def db_get_all_tags():
    """获取所有已发布文章的标签集合（去重，按频率排序）"""
    db = get_db()
    tag_counter = {}
    rows = db.execute("SELECT tags FROM posts WHERE status='published'").fetchall()
    for r in rows:
        tags = json.loads(r['tags'])
        for t in tags:
            tag_counter[t] = tag_counter.get(t, 0) + 1
    db.close()
    return sorted(tag_counter.keys(), key=lambda x: (-tag_counter[x], x))


def db_get_all_years():
    """获取所有已发布文章的年份集合（降序）"""
    db = get_db()
    rows = db.execute(
        "SELECT DISTINCT substr(created_at,1,4) as year FROM posts WHERE status='published' ORDER BY year DESC"
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


def db_load_home_posts(limit=6):
    """首页文章：精选置顶，其次最新，总数受 limit 限制"""
    db = get_db()
    featured_rows = db.execute(
        "SELECT * FROM posts WHERE status='published' AND is_featured=1 ORDER BY created_at DESC"
    ).fetchall()
    featured_ids = [r['id'] for r in featured_rows]
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
    db.close()
    all_rows = list(featured_rows) + list(latest_rows)
    posts = []
    for r in all_rows[:limit]:
        p = dict(r)
        p['tags'] = json.loads(p['tags'])
        posts.append(p)
    return posts


def db_get_all_tags():
    """获取所有文章的标签集合（含草稿，去重，按频率排序）"""
    db = get_db()
    rows = db.execute("SELECT tags FROM posts").fetchall()
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
    if not content:
        return ''
    content = re.sub(r'^---.*?---\s*', '', content, flags=re.DOTALL)
    # 兜底：历史数据中的自动链接 <URL> 规范化为标准链接（避免 Vditor 编辑往返丢失）
    content = normalize_auto_links(content)
    # Markdown 任务列表 [ ] / [x] -> 带样式的勾选符号
    content = content.replace('[x]', '<i class="ck ck-done">☑</i> ').replace('[ ]', '<i class="ck ck-todo">☐</i> ')
    html = markdown.markdown(
        content,
        extensions=['fenced_code', 'tables', 'nl2br', 'sane_lists', 'toc'],
        extension_configs={'toc': {'slugify': _toc_slugify}}
    )
    # 图片性能优化：懒加载 + 异步解码 + 自动填充空 alt（消除 CLS）
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
        return tag.replace('<img', f'<img loading="lazy" decoding="async" alt="{alt_text}"', 1)
    html = re.sub(r'<img\b[^>]*>', _img_repl, html)
    # 超链接新窗口打开，但页内锚点（href 以 # 开头）除外
    def _a_repl(m):
        tag = m.group(0)
        if re.search(r'href="#', tag):
            return tag  # 页内定位锚点，当前窗口跳转
        if 'target=' in tag:
            return tag
        return tag.replace('<a', '<a target="_blank" rel="noopener"', 1)
    html = re.sub(r'<a\b[^>]*>', _a_repl, html)
    return html


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
               created_at=COALESCE(?, created_at), updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (form_data.get('title', ''), slug, content, excerpt,
             tags, is_featured, read_time, form_data.get('status', 'published'), category_id,
             created_at, post_id)
        )
    else:
        db.execute(
            """INSERT INTO posts (title, slug, content, excerpt, tags, is_featured, read_time, status, category_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))""",
            (form_data.get('title', ''), slug, content, excerpt,
             tags, is_featured, read_time, form_data.get('status', 'published'), category_id,
             created_at)
        )
    db.commit()
    db.close()


def db_delete_post(post_id):
    db = get_db()
    db.execute("DELETE FROM posts WHERE id=?", (post_id,))
    db.commit()
    db.close()


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


def _github_ssl_context():
    """构造用于访问 GitHub API 的 SSL 上下文。

    优先使用 certifi 提供的 CA 证书包（跨平台稳定，避免服务器缺少
    系统 CA 时出现的 CERTIFICATE_VERIFY_FAILED）；certifi 不可用时
    回退到系统默认证书。
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


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
    req = urllib.request.Request(api, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8, context=_github_ssl_context()) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        code = getattr(e, 'code', 0)
        if code == 403:
            last_gh_error = ('GitHub API 请求被拒绝（403）：多为未配置 Token 导致匿名限额(60/小时)耗尽，'
                             '或仓库为私有且无权限。请在「设置」中填入 GitHub Token。')
        elif code == 404:
            last_gh_error = '仓库不存在或无访问权限（404）：请检查地址，或仓库为私有需在「设置」配置 Token。'
        elif code == 401:
            last_gh_error = 'GitHub Token 无效或无权限（401）：请检查「设置」中的 Token。'
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
        lang_req = urllib.request.Request(
            f"https://api.github.com/repos/{slug}/languages", headers=lang_headers)
        with urllib.request.urlopen(lang_req, timeout=8, context=_github_ssl_context()) as lang_resp:
            lang_data = json.loads(lang_resp.read().decode('utf-8'))
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
    }


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
            "UPDATE projects SET name=?, description=?, url=?, stars=?, language=?, languages=?, topics=?, sort_order=?, featured=?, github_repo=?, custom_name=? WHERE id=?",
            (name, description, url, stars, language, languages, topics,
             int(form_data.get('sort_order', 0) or 0), 1 if form_data.get('featured') == '1' else 0, github_repo or '', is_custom, project_id)
        )
    else:
        db.execute(
            "INSERT INTO projects (name, description, url, stars, language, languages, topics, sort_order, featured, github_repo, custom_name) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (name, description, url, stars, language, languages, topics,
             int(form_data.get('sort_order', 0) or 0), 1 if form_data.get('featured') == '1' else 0, github_repo or '', is_custom)
        )
    db.commit()
    db.close()


def db_delete_project(project_id):
    db = get_db()
    db.execute("DELETE FROM projects WHERE id=?", (project_id,))
    db.commit()
    db.close()


# ─────────────── 友情链接数据层 ───────────────

def db_load_links(status=None):
    db = get_db()
    if status:
        rows = db.execute(
            "SELECT * FROM links WHERE status=? ORDER BY sort_order ASC, created_at DESC",
            (status,)).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM links ORDER BY sort_order ASC, created_at DESC").fetchall()
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

def db_load_comments(post_id):
    db = get_db()
    rows = db.execute("SELECT * FROM comments WHERE post_id=? ORDER BY created_at ASC", (post_id,)).fetchall()
    db.close()
    return rows_to_list(rows)


def db_save_comment(post_id, author, content):
    db = get_db()
    db.execute("INSERT INTO comments (post_id, author, content) VALUES (?,?,?)", (post_id, author, content))
    db.commit()
    db.close()


def db_delete_comment(comment_id):
    db = get_db()
    db.execute("DELETE FROM comments WHERE id=?", (comment_id,))
    db.commit()
    db.close()


# ─────────────── 全局上下文 ───────────────

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
        'author': app.config.get('author', ''),
        'author_bio': app.config.get('author_bio', ''),
        'about_intro': app.config.get('about_intro', ''),
        'skills': app.config.get('skills', ''),
        'social_github': app.config.get('social_github', ''),
        'contact_email': app.config.get('contact_email', ''),
        'avatar': app.config.get('avatar', ''),
        'all_tags': db_get_all_tags(),
        'links': db_load_links(),
        'version': VERSION,
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
        posts = db_load_home_posts(home_count)
        featured = [p for p in posts if p['is_featured']]
        total = len(posts)

    # 附加分类名称
    categories = {c['id']: c['name'] for c in db_load_categories()}
    for p in posts:
        cid = p.get('category_id')
        p['category_name'] = categories.get(cid, '') if cid else ''

    return render_template('index.html',
                           posts=posts, current_tag=tag, search_query=search,
                           page=1, total_pages=1, total=total,
                           featured=featured,
                           total_categories=len(db_load_categories()))


@app.route('/posts')
def posts_page():
    page = request.args.get('page', 1, type=int)
    tag_filter = request.args.get('tag', '').strip() or None
    year_filter = request.args.get('year', '').strip() or None
    per_page = int(app.config.get('posts_per_page', '20') or 20)
    posts, total = db_load_posts(status='published', tag=tag_filter, year=year_filter,
                                  page=page, per_page=per_page)
    total_pages = max(1, math.ceil(total / per_page))
    # 附加分类名称
    categories = {c['id']: c['name'] for c in db_load_categories()}
    for p in posts:
        cid = p.get('category_id')
        p['category_name'] = categories.get(cid, '') if cid else ''
    # 获取全部标签和年份（不受筛选影响）
    all_tags = db_get_all_tags()
    all_years = db_get_all_years()
    return render_template('posts.html', posts=posts,
                           page=page, total_pages=total_pages, total=total,
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
    content_html = render_post_content(post['content'])
    related = db_get_related_posts(post['id'], post['tags'])
    comments_enabled = str(app.config.get('comments_enabled', '1')) in ('1', 'on', 'true', 'yes')
    comments = db_load_comments(post['id']) if comments_enabled else []

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

    return render_template('post.html', post=post, content=content_html,
                           related=related, comments=comments,
                           prev_post=prev_post, next_post=next_post,
                           comments_enabled=comments_enabled)


# 浏览计数去重：同一 IP 对同一文章在窗口期内只计一次（兜底防刷新/多端刷次数）
_VIEW_COOLDOWN = {}
_VIEW_COOLDOWN_WINDOW = 60  # 秒


@app.route('/post/<int:post_id>/view', methods=['POST'])
def post_view(post_id):
    """浏览计数：由前端在页面停留满阈值后上报（sendBeacon），秒开秒关不计数。"""
    ip = request.remote_addr
    key = (ip, post_id)
    now = time.time()
    last = _VIEW_COOLDOWN.get(key, 0)
    if now - last < _VIEW_COOLDOWN_WINDOW:
        return ('', 204)
    _VIEW_COOLDOWN[key] = now
    db = get_db()
    db.execute("UPDATE posts SET views = views + 1 WHERE id = ?", (post_id,))
    db.commit()
    db.close()
    return ('', 204)


@app.route('/post/<int:post_id>/comment', methods=['POST'])
def post_comment(post_id):
    # 评论开关关闭时，直接拦截上传
    if str(app.config.get('comments_enabled', '1')) not in ('1', 'on', 'true', 'yes'):
        abort(403)
    post = db_get_post_by_id(post_id)
    if not post:
        abort(404)
    author = request.form.get('author', 'Anonymous').strip() or 'Anonymous'
    content = request.form.get('content', '').strip()
    if content and len(content) <= 2000:
        db_save_comment(post['id'], author, content)
        flash('评论已提交', 'success')
    else:
        flash('评论内容不能为空且不能超过2000字', 'error')
    return redirect(url_for('post_detail', post_id=post_id))


@app.route('/tags')
def tags():
    return render_template('tags.html')


@app.route('/about')
def about():
    skills_str = app.config.get('skills', '[]')
    try:
        skills = json.loads(skills_str)
    except json.JSONDecodeError:
        skills = []
    about_intro = app.config.get('about_intro', '')
    author = app.config.get('author', '')
    github = app.config.get('github_username', '') or app.config.get('social_github', '')
    db = get_db()
    timeline_rows = db.execute(
        "SELECT id, date, content FROM timeline ORDER BY sort_order ASC, date DESC"
    ).fetchall()
    db.close()
    timeline = [dict(r) for r in timeline_rows]
    return render_template('about.html', skills=skills, about_intro=about_intro,
                           author=author, github=github, timeline=timeline)


@app.route('/status')
def status_page():
    """前台服务状态页（Sever Status）。SSR 首批数据 + JS 轮询 /api/status。"""
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


@app.route('/links')
def links_page():
    links = db_load_links(status='approved')
    return render_template('links.html', links=links)


@app.route('/links/apply', methods=['GET', 'POST'])
def links_apply():
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
        SubElement(item, 'pubDate').text = p['created_at']
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
    return redirect(url_for('admin_login'))


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
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
                           captcha_required=captcha_required, captcha_question=captcha_question)


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))


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
    db_delete_post(post_id)
    flash('文章已删除', 'success')
    return redirect(url_for('admin_posts'))


@app.route('/admin/posts/<int:post_id>/preview')
@admin_required
def admin_post_preview(post_id):
    post = db_get_post_by_id(post_id)
    if not post:
        return jsonify({'html': ''})
    html = render_post_content(post['content'])
    return jsonify({'html': html})


@app.route('/admin/posts/preview-content', methods=['POST'])
@admin_required
def admin_preview_content():
    content = request.form.get('content', '')
    html = render_post_content(content)
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


@app.route('/admin/projects/<int:project_id>/sync', methods=['POST'])
@admin_required
def admin_project_sync(project_id):
    """同步单个项目：重新从 GitHub 拉取实时数据。"""
    db = get_db()
    row = db.execute("SELECT url FROM projects WHERE id=?", (project_id,)).fetchone()
    db.close()
    if not row:
        flash('项目不存在', 'error')
        return redirect(url_for('admin_projects'))
    gh = fetch_github_repo(row['url'])
    if not gh:
        flash('同步失败：' + (last_gh_error or '无法获取 GitHub 数据（地址无效或已达 API 限额）'), 'error')
        return redirect(url_for('admin_projects'))
    db_save_project({
        'url': gh['url'], 'sort_order': request.form.get('sort_order', '0'),
        'featured': request.form.get('featured', '')
    }, project_id, keep_name=True)
    flash('已从 GitHub 同步：' + gh['name'] + '（★' + str(gh['stars']) + '）', 'success')
    return redirect(url_for('admin_projects'))


@app.route('/admin/projects/sync-all', methods=['POST'])
@admin_required
def admin_projects_sync_all():
    """批量同步全部项目，按 GitHub 仓库去重，不重复。"""
    projects = db_load_projects()
    ok = skipped = failed = 0
    seen = set()
    for p in projects:
        slug = parse_github_repo(p['url'])
        if not slug:
            skipped += 1
            continue
        if slug in seen:  # 本次批量内去重，不重复请求
            skipped += 1
            continue
        seen.add(slug)
        gh = fetch_github_repo(p['url'])
        if not gh:
            failed += 1
            continue
        db_save_project({
            'url': gh['url'], 'sort_order': p['sort_order'],
            'featured': '1' if p['featured'] else ''
        }, p['id'], keep_name=True)
        ok += 1
    flash(f'同步完成：成功 {ok} 个，跳过(重复/无GitHub) {skipped} 个，失败 {failed} 个', 'success')
    return redirect(url_for('admin_projects'))


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
            "INSERT INTO timeline (date, content, sort_order) VALUES (?, ?, ?)",
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


# ─────────────── 后台: 评论管理 ───────────────

@app.route('/admin/comments')
@admin_required
def admin_comments():
    db = get_db()
    rows = db.execute(
        "SELECT c.*, p.title as post_title, p.id as post_id FROM comments c LEFT JOIN posts p ON c.post_id=p.id ORDER BY c.created_at DESC"
    ).fetchall()
    db.close()
    return render_template('admin/comments.html', comments=rows_to_list(rows))


@app.route('/admin/comments/<int:comment_id>/delete', methods=['POST'])
@admin_required
def admin_comment_delete(comment_id):
    db_delete_comment(comment_id)
    flash('评论已删除', 'success')
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
    # 避免重名覆盖
    base = secure_filename(os.path.splitext(file.filename)[0]) or 'file'
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
            with open(os.path.join(target_dir, filename), 'wb') as f:
                f.write(data)
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


# 根目录 /uploads 静态文件服务（v1.0.6 起上传目录移至项目根）
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


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


# ─────────────── 后台: 设置 ───────────────

def _avatar_file_exists():
    """判断 config 中 avatar 指向的文件是否真实存在，避免显示已删除的图。"""
    avatar = app.config.get('avatar', '')
    if not avatar:
        return False
    rel = avatar.split('/static/', 1)[-1] if '/static/' in avatar else ''
    if not rel:
        return False
    return os.path.exists(os.path.join(BASE_DIR, 'static', rel))


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
            u = (u or '').strip()
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


@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    if request.method == 'POST':
        for key in ['blog_name', 'blog_subtitle', 'author', 'author_bio',
                     'about_intro', 'skills', 'avatar', 'github_username',
                     'social_github', 'github_token', 'contact_email', 'home_title', 'icp_beian', 'police_beian',
                     'home_posts_count', 'posts_per_page']:
            if key in request.form:
                save_setting(key, request.form[key])
                app.config[key] = request.form[key]
        # 复选框未勾选时不会随表单提交，需单独处理为关闭态
        comments_on = '1' if request.form.get('comments_enabled') else '0'
        save_setting('comments_enabled', comments_on)
        app.config['comments_enabled'] = comments_on

        db = get_db()
        cur_user = session.get('admin_username', 'admin')
        # 修改管理员账号名
        new_username = request.form.get('admin_username', '').strip()
        if new_username and new_username != cur_user:
            exist = db.execute("SELECT id FROM users WHERE username=?", (new_username,)).fetchone()
            if exist:
                flash('账号名已存在，未修改', 'error')
            else:
                db.execute("UPDATE users SET username=? WHERE username=?", (new_username, cur_user))
                session['admin_username'] = new_username
                flash('管理员账号名已修改为：' + new_username, 'success')
        # 修改密码
        new_pwd = request.form.get('new_password', '')
        if new_pwd and len(new_pwd) >= 6:
            db.execute("UPDATE users SET password_hash=? WHERE username=?",
                       (hash_password(new_pwd), session.get('admin_username', 'admin')))
            flash('密码已修改', 'success')
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
        db.commit()
        db.close()
        flash('设置已保存', 'success')
        return redirect(url_for('admin_settings'))
    return render_template('admin/settings.html',
                           admin_username=session.get('admin_username', 'admin'),
                           admin_avatar=app.config.get('avatar', ''),
                           avatar_exists=_avatar_file_exists())


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
# 升级时跳过、绝不覆盖的目录/文件（用户数据与运行时数据）
UPGRADE_SKIP = {
    'data', 'static/uploads', 'uploads', 'backups', 'posts',
    '.git', '__pycache__', '.venv', 'venv',
    '.env', '.flaskenv', 'upgrade.lock', '*.db', '*.session',
}
UPGRADE_MAX_BYTES = 200 * 1024 * 1024  # 下载/解压上限 200MB，防异常包
UPGRADE_LOCK_TTL = 600  # 升级锁超时（秒）：超过视为上次升级异常中断，自动清理后允许重试
UPGRADE_CACHE = {}  # 检测结果缓存：{'t': 时间戳, 'ok': 是否成功, 'info': 版本信息}

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
    """查询 GitHub Releases 最新版本。失败静默返回 None（不阻塞页面），结果缓存。
    返回 {'tag','version','html_url','body','published_at'} 或 None。"""
    now = time.time()
    cached = UPGRADE_CACHE.get('info')
    # 失败缓存 10 分钟防反复打 GitHub；成功缓存 10 分钟（国内服务器访问慢，且避免新版发布后检测延迟）
    ttl = 600 if UPGRADE_CACHE.get('ok') is False else 600
    if not force and UPGRADE_CACHE and now - UPGRADE_CACHE.get('t', 0) < ttl:
        return cached
    info = None
    try:
        req = urllib.request.Request(
            f'https://api.github.com/repos/{UPGRADE_REPO}/releases/latest',
            headers={'User-Agent': 'infowe-Blog-updater', 'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(req, timeout=6, context=_github_ssl_context()) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        tag = (data.get('tag_name') or '').strip().lstrip('v')
        if tag and parse_version(tag):
            info = {
                'tag': tag,
                'version': parse_version(tag),
                'html_url': data.get('html_url') or UPGRADE_RELEASE_URL,
                'body': (data.get('body') or '').strip()[:2000],
                'published_at': (data.get('published_at') or '')[:10],
            }
    except Exception:
        pass
    UPGRADE_CACHE['t'] = now
    UPGRADE_CACHE['ok'] = info is not None
    UPGRADE_CACHE['info'] = info
    return info


def _upgrade_download(url, dest, max_bytes=None):
    """流式下载文件到 dest，超过大小上限则中断。

    优先直连原始 URL；连接失败/超时后自动按 UPGRADE_MIRRORS 列表逐个尝试镜像，
    全部失败则抛出最后一个错误。"""
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

    attempts = [url] + [m + url for m in UPGRADE_MIRRORS]
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

        # 2. 下载源码压缩包（直连优先，失败自动降级镜像）
        zip_url = f'https://github.com/{UPGRADE_REPO}/archive/refs/tags/v{tag}.zip'
        zip_path = _upgrade_download(zip_url, os.path.join(tmp, 'release.zip'))

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


@app.route('/admin/upgrade/check')
@admin_required
def admin_upgrade_check():
    """异步版本检测接口：返回 JSON，前端据此渲染升级卡片。force=1 跳过缓存。"""
    cur_ver = parse_version(VERSION)
    info = check_latest_version(force=(request.args.get('force') == '1'))
    upgradable = bool(info and cur_ver and info['version'] > cur_ver)
    return jsonify({
        'ok': info is not None,
        'current_version': VERSION,
        'latest_version': (info['tag'] if info else ''),
        'tag': (info['tag'] if info else ''),
        'upgradable': upgradable,
        'published_at': (info['published_at'] if info else ''),
        'body': (info['body'] if info else ''),
        'release_url': (info['html_url'] if info else UPGRADE_RELEASE_URL),
    })


# ─────────────── 启动 ───────────────

if __name__ == '__main__':
    # 生产部署请用 gunicorn 等 WSGI 服务器（不走此分支）。
    # debug 默认关闭；本地开发可设环境变量 FLASK_DEBUG=1 开启。
    # 切勿在对外暴露的环境中以 debug=True 运行，否则调试器可被远程代码执行。
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
