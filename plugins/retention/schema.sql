-- 留存记录插件专属表：后台关键操作审计流水
CREATE TABLE IF NOT EXISTS op_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    target TEXT DEFAULT '',
    detail TEXT DEFAULT '',
    operator TEXT DEFAULT '',
    ip TEXT DEFAULT '',
    user_agent TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_op_logs_time ON op_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_op_logs_action ON op_logs (action, created_at DESC);
