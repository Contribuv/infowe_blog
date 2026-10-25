"""全局配置。

路径约定：
- BASE_DIR 为项目根目录；
- templates/  存放前台主题、后台与共享模板；
- themes/     存放主题静态资源（theme.css / theme.js）；
- static/     全站静态资源；
- instance/   SQLite 数据库与密钥；
- uploads/    用户上传；
- backups/    备份与导出。
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

TEMPLATE_DIR = BASE_DIR / "templates"
THEME_TEMPLATE_DIR = TEMPLATE_DIR / "theme"
ADMIN_TEMPLATE_DIR = TEMPLATE_DIR / "admin"
SHARED_TEMPLATE_DIR = TEMPLATE_DIR / "shared"

STATIC_DIR = BASE_DIR / "static"
THEMES_DIR = BASE_DIR / "themes"
UPLOADS_DIR = BASE_DIR / "uploads"
BACKUPS_DIR = BASE_DIR / "backups"
STORAGE_DIR = BASE_DIR / "storage"
CACHE_DIR = STORAGE_DIR / "cache"
DATA_DIR = BASE_DIR / "data"
FONTS_DIR = BASE_DIR / "fonts"
INSTANCE_DIR = BASE_DIR / "instance"

DATABASE = INSTANCE_DIR / "blog.db"
SECRET_KEY_FILE = INSTANCE_DIR / ".secret_key"

# 版本线：Python 重构版独立版本号
VERSION = "3.0.1"

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
