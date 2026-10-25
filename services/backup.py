"""数据库备份、导出与 SQLite 导入。"""

from __future__ import annotations

import io
import json
import re
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path

import db
from config import BACKUPS_DIR, DATABASE

TABLES = [
    "posts", "categories", "comments", "projects", "links",
    "timeline", "memories", "service_checks", "settings", "users",
]
REQUIRED_TABLES = {"posts", "settings", "users"}


def _safe_name(filename: str) -> str | None:
    name = Path(filename).name
    if not name or name != filename or name.startswith("."):
        return None
    if not re.fullmatch(r"[\w.\-]+", name):
        return None
    return name


def list_backups() -> list[dict]:
    base = Path(BACKUPS_DIR)
    base.mkdir(parents=True, exist_ok=True)
    items = []
    for path in base.iterdir():
        if not path.is_file() or path.suffix.lower() not in {".db", ".sql", ".sqlite", ".zip", ".json"}:
            continue
        stat = path.stat()
        items.append(
            {
                "filename": path.name,
                "size": _fmt_size(stat.st_size),
                "size_bytes": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            }
        )
    items.sort(key=lambda item: item["mtime"], reverse=True)
    return items


def _fmt_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} B" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def create_db_backup() -> str:
    base = Path(BACKUPS_DIR)
    base.mkdir(parents=True, exist_ok=True)
    name = f"blog_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    dest = base / name
    source = db.get_db()
    target = sqlite3.connect(str(dest))
    try:
        source.backup(target)
    finally:
        target.close()
    return name


def export_json() -> bytes:
    payload: dict = {"exported_at": db.now()}
    for table in TABLES:
        try:
            payload[table] = [dict(r) for r in db.query(f"SELECT * FROM {table}")]
        except sqlite3.Error:
            payload[table] = []
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def export_markdown() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in db.query("SELECT * FROM posts ORDER BY created_at ASC"):
            post = dict(row)
            try:
                tags = json.loads(post.get("tags") or "[]")
            except ValueError:
                tags = []
            front = (
                "---\n"
                f"title: {post.get('title', '')}\n"
                f"slug: {post.get('slug', '')}\n"
                f"date: {post.get('created_at', '')}\n"
                f"status: {post.get('status', '')}\n"
                f"tags: [{', '.join(str(t) for t in tags)}]\n"
                "---\n\n"
            )
            filename = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "-", post.get("slug") or f"post-{post['id']}") + ".md"
            zf.writestr(filename, front + (post.get("content") or ""))
        zf.writestr(
            "README.txt",
            "由 Python 博客导出的 Markdown 文章集合。每条文章含 YAML front matter。\n",
        )
    return buffer.getvalue()


def import_sqlite(path: str | Path, keep_users: bool = True) -> tuple[bool, str]:
    path = Path(path)
    if not path.is_file():
        return False, "文件不存在"

    src = None
    try:
        src = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        src.row_factory = sqlite3.Row
        tables = {r["name"] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = REQUIRED_TABLES - tables
        if missing:
            return False, "缺少数据表：" + "、".join(sorted(missing))
        # 先把源库数据全部读入内存并关闭，避免 Windows 下文件句柄占用导致后续无法删除
        snapshot: dict[str, tuple[list[str], list[tuple]]] = {}
        for table in TABLES:
            if table not in tables:
                continue
            cols = [r["name"] for r in src.execute(f"PRAGMA table_info({table})")]
            rows = src.execute(
                f"SELECT {','.join(cols)} FROM {table}"
            ).fetchall()
            snapshot[table] = (cols, [tuple(r) for r in rows])
    except sqlite3.Error:
        return False, "不是有效的 SQLite 数据库文件"
    finally:
        if src is not None:
            try:
                src.close()
            except sqlite3.Error:
                pass

    # 先备份当前库
    backup_name = create_db_backup()
    counts: dict[str, int] = {}
    try:
        conn = db.get_db()
        for table, (src_cols, rows) in snapshot.items():
            if keep_users and table == "users":
                continue
            dst_cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
            cols = [c for c in src_cols if c in dst_cols]
            if not cols:
                continue
            conn.execute(f"DELETE FROM {table}")
            if rows:
                index = [src_cols.index(c) for c in cols]
                marks = ",".join("?" * len(cols))
                conn.executemany(
                    f"INSERT INTO {table} ({','.join(cols)}) VALUES ({marks})",
                    [tuple(row[i] for i in index) for row in rows],
                )
            counts[table] = len(rows)
        conn.commit()
    except sqlite3.Error as exc:
        return False, f"导入失败：{exc}；可用备份 {backup_name} 恢复"

    from services.settings import ensure_defaults

    ensure_defaults()
    total = sum(counts.values())
    detail = "、".join(f"{k} {v}" for k, v in counts.items())
    return True, f"导入成功，共 {total} 行（{detail}）；导入前已自动备份 {backup_name}"


def delete_backup(filename: str) -> bool:
    name = _safe_name(filename)
    if not name:
        return False
    path = Path(BACKUPS_DIR) / name
    if not path.is_file():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def resolve_backup(filename: str) -> Path | None:
    name = _safe_name(filename)
    if not name:
        return None
    path = Path(BACKUPS_DIR) / name
    return path if path.is_file() else None
