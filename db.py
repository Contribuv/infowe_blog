"""SQLite 连接与通用查询辅助。"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from flask import current_app, g

from config import DATABASE

# 旧库升级时需要补齐的列：(表, 列名, 列定义)
COLUMN_MIGRATIONS = [
    ("posts", "cover", "TEXT DEFAULT ''"),
    ("posts", "read_time", "INTEGER DEFAULT 3"),
    ("posts", "views", "INTEGER DEFAULT 0"),
    ("posts", "status", "TEXT DEFAULT 'published'"),
    ("posts", "is_featured", "INTEGER DEFAULT 0"),
    ("posts", "category_id", "INTEGER DEFAULT NULL"),
    ("posts", "updated_at", "TEXT"),
    ("comments", "email", "TEXT DEFAULT ''"),
    ("comments", "qq", "TEXT DEFAULT ''"),
    ("comments", "ip_text", "TEXT DEFAULT ''"),
    ("comments", "ip_location", "TEXT DEFAULT ''"),
    ("comments", "project_id", "INTEGER DEFAULT NULL"),
    ("comments", "is_private", "INTEGER DEFAULT 0"),
    ("projects", "github_repo", "TEXT DEFAULT ''"),
    ("projects", "custom_name", "INTEGER DEFAULT 0"),
    ("projects", "languages", "TEXT DEFAULT '[]'"),
    ("links", "status", "TEXT DEFAULT 'approved'"),
    ("links", "avatar", "TEXT DEFAULT ''"),
]


def now() -> str:
    """本地时间字符串，与 PHP / 旧 Flask 版展示一致。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 8000")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(exc: BaseException | None = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def query(sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    return get_db().execute(sql, params).fetchall()


def one(sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    return get_db().execute(sql, params).fetchone()


def scalar(sql: str, params: Sequence[Any] = (), default: Any = None) -> Any:
    row = one(sql, params)
    if row is None:
        return default
    value = row[0]
    return default if value is None else value


def execute(sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
    conn = get_db()
    cur = conn.execute(sql, params)
    conn.commit()
    return cur


def executemany(sql: str, seq: Iterable[Sequence[Any]]) -> sqlite3.Cursor:
    conn = get_db()
    cur = conn.executemany(sql, seq)
    conn.commit()
    return cur


def insert(sql: str, params: Sequence[Any] = ()) -> int:
    cur = execute(sql, params)
    return int(cur.lastrowid or 0)


def init_db(app) -> None:
    """建库、补列、写默认设置；可安全重复执行。"""
    from config import DATABASE as DEFAULT_DB
    from services.settings import ensure_defaults

    db_path = Path(app.config["DATABASE"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema = Path(__file__).resolve().parent / "schema.sql"

    conn = connect(db_path)
    try:
        conn.executescript(schema.read_text(encoding="utf-8"))
        # 旧库补列
        for table, column, ddl in COLUMN_MIGRATIONS:
            cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
            if cols and column not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        # 旧库 comments 可能没有 email_hash
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(comments)")}
        if cols and "email_hash" not in cols:
            conn.execute("ALTER TABLE comments ADD COLUMN email_hash TEXT DEFAULT ''")
        conn.commit()
    finally:
        conn.close()

    with app.app_context():
        ensure_defaults()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
