"""SQLite 连接与通用查询辅助。"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from flask import current_app, g

from config import DATABASE

# 旧库升级：以 schema.sql 为唯一基准，自动补列 / 删列（删除前自动备份）。
COLUMN_MIGRATIONS: list[tuple[str, str, str]] = []


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


def _backup_database(conn: sqlite3.Connection, reason: str = "schema_upgrade") -> str:
    from config import BACKUPS_DIR

    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{reason}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    dest = Path(BACKUPS_DIR) / name
    target = sqlite3.connect(str(dest))
    try:
        conn.backup(target)
    finally:
        target.close()
    return name


def _expected_schema(schema_text: str) -> dict[str, list[dict]]:
    """在内存库执行 schema.sql，得到每张表的期望列定义。"""
    memory = sqlite3.connect(":memory:")
    memory.row_factory = sqlite3.Row
    try:
        memory.executescript(schema_text)
        tables = [
            r["name"]
            for r in memory.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {
            table: [dict(r) for r in memory.execute(f'PRAGMA table_info("{table}")')]
            for table in tables
        }
    finally:
        memory.close()


def _add_column_sql(table: str, col: dict) -> str | None:
    if col.get("pk"):
        # 主键列无法通过 ADD COLUMN 补，正常旧库不会缺
        return None
    name = col["name"]
    type_ = (col.get("type") or "TEXT").strip() or "TEXT"
    notnull = bool(col.get("notnull"))
    default = col.get("dflt_value")
    is_text = any(t in type_.upper() for t in ("TEXT", "CHAR", "CLOB"))
    if default is not None and str(default).startswith("("):
        # ADD COLUMN 不接受非常量默认值（如 datetime(...)）
        default = "''" if is_text else "0"
    parts = [f'ALTER TABLE "{table}" ADD COLUMN "{name}" {type_}']
    if default is not None:
        parts.append(f"DEFAULT {default}")
    elif notnull:
        parts.append("DEFAULT ''" if is_text else "DEFAULT 0")
    if notnull:
        parts.append("NOT NULL")
    return " ".join(parts)


def _split_sql(script: str) -> list[str]:
    """按完整语句拆分 SQL（兼容触发器内部的分号）。"""
    statements: list[str] = []
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        statements.append(buffer.strip())
    return statements


def _execute_schema(conn: sqlite3.Connection, script: str, phase: str) -> None:
    """分两阶段执行：先建表，补列后再建索引/触发器。"""
    for statement in _split_sql(script):
        upper = statement.lstrip().upper()
        is_index = upper.startswith("CREATE INDEX") or upper.startswith("CREATE UNIQUE INDEX")
        is_trigger = upper.startswith("CREATE TRIGGER")
        if phase == "tables" and (is_index or is_trigger):
            continue
        if phase == "indexes" and not (is_index or is_trigger):
            continue
        conn.execute(statement)


def sync_schema(conn: sqlite3.Connection, schema_text: str) -> list[str]:
    """按 schema.sql 同步表结构：新增缺失列、删除多余列。

    - 先建缺失表，补/删列，最后建索引与触发器（避免旧表缺列导致索引创建失败）
    - 只在检测到差异时备份当前数据库（backups/schema_upgrade_*.db）
    - 删除列需要 SQLite 3.35+；低版本会跳过并记录
    - 不删除表、不修改已有列类型，避免误伤数据
    """
    _execute_schema(conn, schema_text, "tables")
    expected = _expected_schema(schema_text)

    changes: list[tuple[str, str, object]] = []
    for table, expected_cols in expected.items():
        actual = {
            r["name"]: dict(r)
            for r in conn.execute(f'PRAGMA table_info("{table}")')
        }
        expected_names = {c["name"] for c in expected_cols}
        for col in expected_cols:
            if col["name"] not in actual:
                changes.append(("add", table, col))
        for name in actual:
            if name not in expected_names:
                changes.append(("drop", table, name))

    if not changes:
        _execute_schema(conn, schema_text, "indexes")
        return []

    backup = _backup_database(conn, "schema_upgrade")
    applied: list[str] = []
    for action, table, payload in changes:
        if action == "add":
            col = payload  # type: ignore[assignment]
            sql = _add_column_sql(table, col)
            if not sql:
                continue
            try:
                conn.execute(sql)
                applied.append(f"+ {table}.{col['name']}")
            except sqlite3.Error as exc:
                applied.append(f"! {table}.{col['name']}: {exc}")
        else:
            name = str(payload)
            if sqlite3.sqlite_version_info < (3, 35, 0):
                applied.append(
                    f"! {table}.{name}: 当前 SQLite {sqlite3.sqlite_version} 不支持 DROP COLUMN"
                )
                continue
            try:
                conn.execute(f'ALTER TABLE "{table}" DROP COLUMN "{name}"')
                applied.append(f"- {table}.{name}")
            except sqlite3.Error as exc:
                applied.append(f"! {table}.{name}: {exc}")

    # 索引/触发器放在补列之后，旧表缺列也能成功
    _execute_schema(conn, schema_text, "indexes")
    conn.commit()
    print(f"[数据库升级] 检测到结构变化，已备份：backups/{backup}")
    for item in applied:
        print(f"  {item}")
    return applied


def init_db(app) -> None:
    """建库、同步表结构、写默认设置；可安全重复执行。"""
    from services.settings import ensure_defaults

    db_path = Path(app.config["DATABASE"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema = Path(__file__).resolve().parent / "schema.sql"
    schema_text = schema.read_text(encoding="utf-8")

    conn = connect(db_path)
    try:
        sync_schema(conn, schema_text)
    finally:
        conn.close()

    with app.app_context():
        ensure_defaults()


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
