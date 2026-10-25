"""把 PHP 版（MySQL）数据库迁移到本项目（SQLite）。

用法：
    python tools/migrate_from_php.py                # 默认读取 D:\\fnos\\blog
    python tools/migrate_from_php.py --dry-run      # 只检查，不写入
    python tools/migrate_from_php.py --keep-otp     # 保留旧站 OTP 密钥/开关
    python tools/migrate_from_php.py --keep-users   # 保留当前管理员，不导入 users

迁移内容：
- 10 张业务表（保留主键 id）
- settings（补齐本项目默认键；默认关闭 OTP，避免没有旧验证器时无法登录）
- uploads 上传文件（合并复制）
- GitHub 项目 README 缓存
- 自动备份当前 SQLite 数据库

依赖：PyMySQL、bcrypt（旧管理员密码为 PHP password_hash 生成的 bcrypt）。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import db  # noqa: E402
from app import create_app  # noqa: E402
from services import backup, settings as settings_service  # noqa: E402

TABLES: dict[str, dict] = {
    "categories": {
        "columns": ["id", "name", "slug", "sort_order", "created_at"],
        "defaults": {"sort_order": 0},
    },
    "posts": {
        "columns": ["id", "title", "slug", "content", "excerpt", "tags", "cover",
                    "read_time", "views", "status", "is_featured", "category_id",
                    "created_at", "updated_at"],
        "defaults": {"excerpt": "", "tags": "[]", "cover": "", "read_time": 3,
                     "views": 0, "status": "published", "is_featured": 0},
    },
    "comments": {
        "columns": ["id", "post_id", "project_id", "parent_id", "author", "email",
                    "email_hash", "website", "content", "status", "is_private", "qq",
                    "ip_text", "ip_location", "created_at"],
        "defaults": {"author": "Anonymous", "email": "", "email_hash": "", "website": "",
                     "status": "pending", "is_private": 0, "qq": "", "ip_text": "",
                     "ip_location": ""},
    },
    "projects": {
        "columns": ["id", "name", "description", "url", "stars", "language", "topics",
                    "sort_order", "featured", "github_repo", "custom_name", "languages",
                    "created_at"],
        "defaults": {"description": "", "url": "", "stars": 0, "language": "", "topics": "[]",
                     "sort_order": 0, "featured": 0, "github_repo": "", "custom_name": 0,
                     "languages": "[]"},
    },
    "links": {
        "columns": ["id", "name", "url", "description", "avatar", "sort_order", "status",
                    "created_at"],
        "defaults": {"description": "", "avatar": "", "sort_order": 0, "status": "approved"},
    },
    "timeline": {
        "columns": ["id", "date", "content", "sort_order", "created_at"],
        "defaults": {"sort_order": 0},
    },
    "memories": {
        "columns": ["id", "title", "text", "image", "date", "sort_order", "created_at"],
        "defaults": {"title": "", "text": "", "image": "", "date": "", "sort_order": 0},
    },
    "service_checks": {
        "columns": ["id", "service_id", "checked_at", "ok", "latency_ms", "cert_days", "detail"],
        "defaults": {"ok": 0, "latency_ms": 0, "cert_days": -1, "detail": ""},
    },
}


def php_config(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")

    def value(key: str, default: str = "") -> str:
        match = re.search(rf"'{key}'\s*=>\s*'([^']*)'", text)
        return match.group(1) if match else default

    return {
        "host": value("host"),
        "port": int(value("port", "3306") or 3306),
        "dbname": value("dbname"),
        "user": value("user"),
        "pass": value("pass"),
        "charset": value("charset", "utf8mb4"),
    }


def normalize(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def mysql_rows(cursor, table: str) -> list[dict]:
    cursor.execute(f"SELECT * FROM `{table}`")
    return [dict(row) for row in cursor.fetchall()]


def copy_uploads(source_dir: Path, target_dir: Path) -> tuple[int, int]:
    candidates = [source_dir / "uploads", source_dir / "storage" / "uploads"]
    files = 0
    total = 0
    for source in candidates:
        if not source.is_dir():
            continue
        for path in source.rglob("*"):
            if not path.is_file() or path.name == ".gitkeep":
                continue
            rel = path.relative_to(source)
            dest = target_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists() or dest.stat().st_size != path.stat().st_size:
                shutil.copy2(path, dest)
            files += 1
            total += path.stat().st_size
    return files, total


def migrate_project_cache(source_dir: Path, target_dir: Path) -> int:
    cache_file = source_dir / "storage" / "cache" / "project_gh.json"
    if not cache_file.is_file():
        return 0
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return 0
    if not isinstance(data, dict):
        return 0
    target_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for repo, payload in data.items():
        if not isinstance(payload, dict):
            continue
        name = repo.replace("/", "__") + ".json"
        (target_dir / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="PHP(MySQL) → Python(SQLite) 数据迁移")
    parser.add_argument("--source-dir", default=r"D:\fnos\blog", help="PHP 项目根目录")
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写入")
    parser.add_argument("--keep-otp", action="store_true", help="保留旧站 OTP 配置（默认关闭）")
    parser.add_argument("--keep-users", action="store_true", help="保留当前管理员账号，不导入 users")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    source_dir = Path(args.source_dir)
    config_file = source_dir / "config" / "config.php"
    if not config_file.is_file():
        print(f"[错误] 未找到配置文件：{config_file}")
        return 1

    try:
        import pymysql
    except ImportError:
        print("[错误] 缺少 PyMySQL，请先执行：.venv\\Scripts\\python.exe -m pip install pymysql bcrypt")
        return 1

    conf = php_config(config_file)
    print(f"[连接] {conf['user']}@{conf['host']}:{conf['port']}/{conf['dbname']}")
    try:
        conn = pymysql.connect(
            host=conf["host"], port=conf["port"], user=conf["user"], password=conf["pass"],
            database=conf["dbname"], charset=conf["charset"],
            cursorclass=pymysql.cursors.DictCursor, connect_timeout=10,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[错误] MySQL 连接失败：{exc}")
        return 1

    app = create_app({"TESTING": False})
    with conn:
        with conn.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            existing = {list(row.values())[0] for row in cursor.fetchall()}
            missing = set(TABLES) - existing
            if missing:
                print(f"[错误] 源库缺少数据表：{', '.join(sorted(missing))}")
                return 1

            counts = {}
            for table in TABLES:
                cursor.execute(f"SELECT COUNT(*) AS c FROM `{table}`")
                counts[table] = int(cursor.fetchone()["c"])
            cursor.execute("SELECT COUNT(*) AS c FROM settings")
            settings_count = int(cursor.fetchone()["c"])
            cursor.execute("SELECT COUNT(*) AS c FROM users")
            users_count = int(cursor.fetchone()["c"])

            print("\n[源库统计]")
            for table, count in counts.items():
                print(f"  {table:<16} {count}")
            print(f"  {'settings':<16} {settings_count}")
            print(f"  {'users':<16} {users_count}")

            if args.dry_run:
                print("\n[dry-run] 未写入任何数据。")
                return 0

            with app.app_context():
                backup_name = backup.create_db_backup()
                print(f"\n[备份] 当前 SQLite 已备份：{backup_name}")

                sql_conn = db.get_db()
                try:
                    sql_conn.execute("BEGIN")
                    # 1) 业务表整表覆盖
                    for table, meta in TABLES.items():
                        sql_conn.execute(f"DELETE FROM {table}")
                        rows = mysql_rows(cursor, table)
                        columns = meta["columns"]
                        defaults = meta["defaults"]
                        values = []
                        for row in rows:
                            item = []
                            for col in columns:
                                value = normalize(row.get(col))
                                if value is None and col in defaults:
                                    value = defaults[col]
                                if col in {"created_at", "updated_at"} and not value:
                                    value = db.now()
                                item.append(value)
                            values.append(item)
                        if values:
                            marks = ",".join("?" * len(columns))
                            sql_conn.executemany(
                                f"INSERT INTO {table} ({','.join(columns)}) VALUES ({marks})",
                                values,
                            )
                        print(f"  [导入] {table:<16} {len(values)} 行")

                    # 2) settings
                    sql_conn.execute("DELETE FROM settings")
                    cursor.execute("SELECT `key`, `value` FROM settings")
                    rows = cursor.fetchall()
                    pairs = [(str(r["key"]), "" if r["value"] is None else str(r["value"])) for r in rows]
                    if pairs:
                        sql_conn.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", pairs)
                    if not args.keep_otp:
                        sql_conn.execute("DELETE FROM settings WHERE key IN "
                                         "('otp_enabled','otp_secret','otp_recovery_codes','otp_emergency_off')")
                    print(f"  [导入] {'settings':<16} {len(pairs)} 行")

                    # 3) users（单管理员）
                    if not args.keep_users:
                        cursor.execute("SELECT * FROM users")
                        users = cursor.fetchall()
                        if users:
                            sql_conn.execute("DELETE FROM users")
                            for user in users[:1]:
                                sql_conn.execute(
                                    "INSERT INTO users (id, username, password_hash) VALUES (?,?,?)",
                                    (user.get("id") or 1, user.get("username") or "admin",
                                     user.get("password_hash") or ""),
                                )
                            print(f"  [导入] {'users':<16} 1 行（原管理员：{users[0].get('username')}）")

                    sql_conn.commit()
                except Exception as exc:  # noqa: BLE001
                    sql_conn.rollback()
                    print(f"\n[错误] 写入 SQLite 失败，已回滚：{exc}")
                    return 1

                # 4) 补齐本项目新增设置键
                settings_service.ensure_defaults()
                if not args.keep_otp:
                    sql_conn.execute(
                        "UPDATE settings SET value='0' WHERE key='otp_enabled'"
                    )
                sql_conn.commit()

                # 5) 上传文件
                uploads_files, uploads_bytes = copy_uploads(source_dir, BASE_DIR / "uploads")
                print(f"  [文件] uploads {uploads_files} 个（{uploads_bytes / 1024 / 1024:.2f} MB）")

                # 6) 项目 README 缓存
                cache_count = migrate_project_cache(source_dir, BASE_DIR / "data" / "project_cache")
                if cache_count:
                    print(f"  [缓存] 项目 README {cache_count} 个")

                # 7) 行数校验
                print("\n[校验]")
                ok = True
                for table in TABLES:
                    actual = int(sql_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                    flag = "OK" if actual == counts[table] else "差异"
                    if actual != counts[table]:
                        ok = False
                    print(f"  {flag:<4} {table:<16} 源 {counts[table]} / 本地 {actual}")
                user_actual = int(sql_conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
                print(f"  {'OK' if user_actual == 1 else '差异':<4} {'users':<16} 本地 {user_actual}")
                print(f"  {'OK':<4} settings       本地 "
                      f"{int(sql_conn.execute('SELECT COUNT(*) FROM settings').fetchone()[0])}（含默认键）")

                if not ok:
                    print("\n[提示] 部分表行数不一致，请检查源库是否有触发器/视图过滤。")
                    return 2

                print("\n[完成] 迁移成功。")
                if not args.keep_otp:
                    print("       OTP 已重置为关闭状态（旧验证器不再生效）。")
                if not args.keep_users:
                    print("       管理员已使用 PHP 版账号，原密码可直接登录。")
                print("       建议重启服务后检查前台/后台，并在后台重新保存一次「博客设置」。")
                return 0


if __name__ == "__main__":
    raise SystemExit(main())
