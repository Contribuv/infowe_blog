-- Python 博客 SQLite 结构（与 PHP 版 / 旧 Flask 版兼容）
PRAGMA foreign_keys = ON;

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
    is_featured INTEGER DEFAULT 0,
    category_id INTEGER DEFAULT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_posts_status_time ON posts (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_posts_category ON posts (category_id);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER DEFAULT NULL,
    project_id INTEGER DEFAULT NULL,
    parent_id INTEGER DEFAULT NULL,
    author TEXT NOT NULL DEFAULT 'Anonymous',
    email TEXT DEFAULT '',
    email_hash TEXT DEFAULT '',
    website TEXT DEFAULT '',
    content TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    is_private INTEGER DEFAULT 0,
    qq TEXT DEFAULT '',
    ip_text TEXT DEFAULT '',
    ip_location TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_comments_post ON comments (post_id);
CREATE INDEX IF NOT EXISTS idx_comments_project ON comments (project_id);
CREATE INDEX IF NOT EXISTS idx_comments_status ON comments (status, created_at DESC);

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
    languages TEXT DEFAULT '[]',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    description TEXT DEFAULT '',
    avatar TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    status TEXT DEFAULT 'approved',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS timeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    content TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '',
    image TEXT NOT NULL DEFAULT '',
    date TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
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

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS login_attempts (
    ip TEXT PRIMARY KEY,
    fail_count INTEGER NOT NULL DEFAULT 0,
    last_at REAL NOT NULL DEFAULT 0,
    locked_until REAL NOT NULL DEFAULT 0
);

-- 单管理员硬约束
CREATE TRIGGER IF NOT EXISTS users_single_admin_guard
BEFORE INSERT ON users
WHEN (SELECT COUNT(*) FROM users) >= 1
BEGIN
    SELECT RAISE(ABORT, 'only one admin account is allowed');
END;

-- 通用限流事件：评论/图片上传/浏览量等按 (bucket, key) 计数
CREATE TABLE IF NOT EXISTS rate_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bucket TEXT NOT NULL,
    key TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rate_events ON rate_events (bucket, key, ts);
