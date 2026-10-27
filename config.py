"""全局配置。

路径约定：
- BASE_DIR 为项目根目录，只放代码与静态资源；
- templates/  存放前台主题、后台与共享模板；
- themes/     存放主题静态资源（theme.css / theme.js）；
- static/     全站静态资源；
- var/        运行时数据根目录（可用环境变量 BLOG_DATA_DIR 指到项目外）：
  - var/blog.db、var/.secret_key、var/*.json 等运行期状态
  - var/uploads/   用户上传
  - var/backups/   备份与导出
  - var/storage/   运行期缓存
- 旧版本的 data/、uploads/、backups/、storage/、instance/ 由启动时自动迁移。
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

TEMPLATE_DIR = BASE_DIR / "templates"
THEME_TEMPLATE_DIR = TEMPLATE_DIR / "theme"
ADMIN_TEMPLATE_DIR = TEMPLATE_DIR / "admin"
SHARED_TEMPLATE_DIR = TEMPLATE_DIR / "shared"

STATIC_DIR = BASE_DIR / "static"
THEMES_DIR = BASE_DIR / "themes"
PLUGINS_DIR = BASE_DIR / "plugins"
FONTS_DIR = BASE_DIR / "fonts"


def _var_dir() -> Path:
    """运行时数据根目录。

    默认项目内 var/；生产部署可用 BLOG_DATA_DIR 指到 Web 根之外
    （如 /var/lib/infowe_blog），升级代码时数据完全不受影响。
    """
    raw = os.environ.get("BLOG_DATA_DIR", "").strip()
    path = Path(raw).expanduser() if raw else BASE_DIR / "var"
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


VAR_DIR = _var_dir()
VAR_DIR_IS_DEFAULT = not os.environ.get("BLOG_DATA_DIR", "").strip()

# 运行期状态（数据库、密钥、同步/升级状态、ip2region 库等）直接放在 var/ 根下
DATA_DIR = VAR_DIR
UPLOADS_DIR = VAR_DIR / "uploads"
BACKUPS_DIR = VAR_DIR / "backups"
STORAGE_DIR = VAR_DIR / "storage"
CACHE_DIR = STORAGE_DIR / "cache"

DATABASE = DATA_DIR / "blog.db"
SECRET_KEY_FILE = DATA_DIR / ".secret_key"

# 旧版目录：仅用于启动时自动迁移，业务代码不再读写
LEGACY_DATA_DIR = BASE_DIR / "data"
LEGACY_UPLOADS_DIR = BASE_DIR / "uploads"
LEGACY_BACKUPS_DIR = BASE_DIR / "backups"
LEGACY_STORAGE_DIR = BASE_DIR / "storage"
LEGACY_INSTANCE_DIR = BASE_DIR / "instance"   # v3.2.13 及更早版本的数据库位置

# 版本线：Python 重构版独立版本号
VERSION = "3.3.6"

# 上传限制
MAX_CONTENT_LENGTH = 64 * 1024 * 1024  # 单请求 64MB
UPLOAD_MAX_SIZE = 20 * 1024 * 1024     # 单文件 20MB
COMMENT_IMAGE_MAX_SIZE = 8 * 1024 * 1024

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".ico", ".avif"}
MEDIA_EXTS = {".mp4", ".webm", ".mp3", ".wav", ".ogg", ".m4a", ".flac"}
FILE_EXTS = {
    ".pdf", ".zip", ".7z", ".rar", ".tar", ".gz", ".bz2",
    ".txt", ".md", ".json", ".csv", ".yml", ".yaml",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".py", ".js", ".css", ".sql", ".sh", ".bat",
}

# 会话
SESSION_COOKIE_NAME = "blog_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 14

# 导航项（key, 显示名, 链接）
NAV_PAGES = [
    ("posts", "文章", "/posts"),
    ("tags", "标签", "/tags"),
    ("projects", "项目", "/projects"),
    ("links", "友链", "/links"),
    ("about", "关于", "/about"),
    ("status", "状态", "/status"),
]

# 自定义后台入口时禁止占用的前台/系统路径
ADMIN_PATH_RESERVED = {
    "admin", "tag", "tags", "search", "archive", "posts", "post", "projects",
    "links", "about", "status", "api", "uploads", "themes", "static",
    "feed.xml", "robots.txt", "sitemap.xml", "favicon.ico", "assets",
    "login", "logout", "comment", "avatar", "share-thumb", "readme-img",
}
