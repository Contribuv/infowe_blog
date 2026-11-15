-- 对象存储插件：本插件上传过的对象清单。
-- 孤儿扫描只在这张表里找候选，绝不遍历整个桶，
-- 因此不会误删用户直接传到 OSS 的其它文件。
CREATE TABLE IF NOT EXISTS oss_objects (
    key TEXT PRIMARY KEY,
    size INTEGER DEFAULT 0,
    uploaded_at TEXT DEFAULT (datetime('now', 'localtime'))
);
