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
    deleted_at TEXT DEFAULT NULL,
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
    notify INTEGER DEFAULT 1,
    qq TEXT DEFAULT '',
    ip_text TEXT DEFAULT '',
    ip_location TEXT DEFAULT '',
    is_ai INTEGER DEFAULT 0,
    ai_state TEXT DEFAULT 'idle',
    ai_meta TEXT DEFAULT '',
    is_owner INTEGER DEFAULT 0,
    is_picked INTEGER DEFAULT 0,
    user_agent TEXT DEFAULT '',
    identity_action TEXT DEFAULT '',
    identity_note TEXT DEFAULT '',
    deleted_at TEXT DEFAULT NULL,
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
    email TEXT DEFAULT '',
    rss TEXT DEFAULT '',
    backlink_url TEXT DEFAULT '',
    feed_state TEXT DEFAULT '',
    feed_error TEXT DEFAULT '',
    feed_checked_at REAL DEFAULT 0,
    feed_count INTEGER DEFAULT 0,
    ai_state TEXT DEFAULT 'idle',
    ai_meta TEXT DEFAULT '',
    ip_text TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS feed_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    link_id INTEGER NOT NULL,
    title TEXT DEFAULT '',
    url TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    published REAL DEFAULT 0,
    fetched_at REAL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_feed_items_url ON feed_items (link_id, url);
CREATE INDEX IF NOT EXISTS idx_feed_items_pub ON feed_items (published DESC);

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

CREATE TABLE IF NOT EXISTS plugins (
    key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT DEFAULT '',
    enabled INTEGER DEFAULT 0,
    config TEXT DEFAULT '{}',
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
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

-- 评论者身份：邮箱哈希 -> 当前统一昵称（改名需邮箱验证码）
CREATE TABLE IF NOT EXISTS comment_identities (
    email_hash TEXT PRIMARY KEY,
    email TEXT NOT NULL DEFAULT '',
    current_author TEXT NOT NULL DEFAULT '',
    previous_author TEXT DEFAULT '',
    verified_at TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- 改名验证码：只存哈希，一次性使用
CREATE TABLE IF NOT EXISTS email_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_hash TEXT NOT NULL,
    email TEXT NOT NULL DEFAULT '',
    code_hash TEXT NOT NULL,
    new_author TEXT NOT NULL DEFAULT '',
    purpose TEXT NOT NULL DEFAULT 'rename',
    expires_at INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    used_at TEXT DEFAULT '',
    ip TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_email_codes_email ON email_codes (email_hash, created_at DESC);

-- 读者账号：邮箱 + 密码注册登录（与单管理员 users 表隔离）
-- email_hash 为身份主键，与 comment_identities / comments 共用同一哈希体系
CREATE TABLE IF NOT EXISTS reader_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_hash TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL DEFAULT '',
    link TEXT NOT NULL DEFAULT '',
    avatar_url TEXT NOT NULL DEFAULT '',
    verified_at TEXT DEFAULT '',
    last_login_at TEXT DEFAULT '',
    -- 注册昵称审核：approved 正常；manual 待人工审核（禁止登录）；rejected 已拒绝
    review_status TEXT NOT NULL DEFAULT 'approved',
    review_note TEXT NOT NULL DEFAULT '',
    reviewed_at TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT DEFAULT (datetime('now', 'localtime'))
);

-- 注册昵称审核留存：每次注册的机审结论 + 人工处理轨迹，一条注册一条记录
-- source: local（敏感词）/ ai（模型）/ manual；decision: pass / review
CREATE TABLE IF NOT EXISTS reader_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 0,
    email_hash TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    decision TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    operator TEXT NOT NULL DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    reviewed_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_reader_reviews_status ON reader_reviews (status, id DESC);
CREATE INDEX IF NOT EXISTS idx_reader_reviews_hash ON reader_reviews (email_hash);

-- 站内通知：回复 / 审核通过等提醒，按 email_hash 归属
CREATE TABLE IF NOT EXISTS comment_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_hash TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT 'reply',
    comment_id INTEGER NOT NULL DEFAULT 0,
    parent_id INTEGER NOT NULL DEFAULT 0,
    post_id INTEGER DEFAULT NULL,
    project_id INTEGER DEFAULT NULL,
    from_author TEXT NOT NULL DEFAULT '',
    excerpt TEXT NOT NULL DEFAULT '',
    is_read INTEGER NOT NULL DEFAULT 0,
    is_emailed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_notif_hash_read ON comment_notifications (email_hash, is_read, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notif_comment ON comment_notifications (comment_id);

-- 博主通知：新评论 / 被回复。与读者通知分开，避免两套身份混用同一个已读状态。
-- 只有评论区真正公开的评论才写入；待审核项由 comments.status='pending' 实时查询，不复制一份。
CREATE TABLE IF NOT EXISTS admin_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL DEFAULT 'new',
    comment_id INTEGER NOT NULL DEFAULT 0,
    parent_id INTEGER NOT NULL DEFAULT 0,
    post_id INTEGER DEFAULT NULL,
    project_id INTEGER DEFAULT NULL,
    from_author TEXT NOT NULL DEFAULT '',
    excerpt TEXT NOT NULL DEFAULT '',
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_admin_notif_read ON admin_notifications (is_read, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_notif_comment ON admin_notifications (comment_id);

-- 一次性回填：已有公开评论补进通知表（标记已读，只作历史记录），
-- NOT EXISTS 保证与运行期写入互不重复，重复执行安全。
INSERT INTO admin_notifications
    (type, comment_id, parent_id, post_id, project_id, from_author, excerpt, is_read, created_at)
SELECT CASE WHEN c.parent_id > 0 THEN 'reply' ELSE 'new' END,
       c.id, COALESCE(c.parent_id, 0), c.post_id, c.project_id,
       COALESCE(NULLIF(c.author, ''), '匿名'),
       substr(replace(replace(COALESCE(c.content, ''), char(10), ' '), char(13), ' '), 1, 120),
       1, c.created_at
FROM comments c
WHERE c.status = 'approved' AND c.deleted_at IS NULL
  AND COALESCE(c.is_owner, 0) = 0 AND COALESCE(c.is_private, 0) = 0
  AND NOT EXISTS (SELECT 1 FROM admin_notifications n WHERE n.comment_id = c.id);

-- 评论投票：每个身份（email_hash 或访客令牌）对每条评论最多一票
-- kind: 1 = 点赞，-1 = 不喜欢；同一人对同一条只能二选一，再点同一边即取消
CREATE TABLE IF NOT EXISTS comment_likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comment_id INTEGER NOT NULL,
    voter_hash TEXT NOT NULL DEFAULT '',
    kind INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    UNIQUE(comment_id, voter_hash)
);
CREATE INDEX IF NOT EXISTS idx_like_comment ON comment_likes (comment_id);
CREATE INDEX IF NOT EXISTS idx_like_voter ON comment_likes (voter_hash);

-- 图形验证码一次性令牌：session cookie 只是签名可读，答案可重放，
-- 必须在服务端记录使用状态；过期记录顺手清理。
CREATE TABLE IF NOT EXISTS captcha_tokens (
    nonce TEXT PRIMARY KEY,
    used_at TEXT DEFAULT '',
    expires_at INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_captcha_expiry ON captcha_tokens (expires_at);

-- 读者头像上传次数（按用户 + 自然日），防止循环换头像刷 OSS 请求
CREATE TABLE IF NOT EXISTS reader_avatar_usage (
    user_hash TEXT NOT NULL,
    day TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_hash, day)
);

-- 头像内容人工审核：上传先进队列，管理员通过后才会真正展示
CREATE TABLE IF NOT EXISTS reader_avatar_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 0,
    email_hash TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    operator TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime')),
    reviewed_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_avatar_reviews_status ON reader_avatar_reviews (status, id DESC);
CREATE INDEX IF NOT EXISTS idx_avatar_reviews_user ON reader_avatar_reviews (user_id, status);
