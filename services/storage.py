"""运行时数据目录：旧版平铺目录 → var/ 的自动迁移。

v3.2.14 及更早版本把 data/、uploads/、backups/、storage/ 直接放在项目根，
代码与数据混在一起。从本版开始统一收敛到 var/（可用 BLOG_DATA_DIR 指到
项目外，如 /var/lib/infowe_blog）。

迁移规则：
- 幂等：成功后写 var/.migrated，后续启动直接跳过；
- 串行：用文件锁 + 二次检查，gunicorn 多 worker 同时启动也不会并发搬迁；
- 不覆盖：目标已有同名文件时，旧文件整份移到 var/.legacy-<时间戳>/ 保留；
- 不阻塞：任何异常只打印告警，下次启动可重试；
- 自定义 BLOG_DATA_DIR 时不自动搬迁，避免把数据搬错位置。

SQLite 处于 WAL 模式，最新的已提交数据可能还在 blog.db-wal 里；迁移按文件
逐个移动，-wal / -shm 会跟着主库一起进 var/。停服后 SQLite 会自动 checkpoint，
通常只剩 blog.db。迁移前请先停服务，避免旧进程继续写旧 inode。
"""

from __future__ import annotations

import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import IO

import config


def _lock_file(path: Path) -> IO[bytes] | None:
    """跨平台独占锁；拿不到锁或系统不支持时返回 None（退化为无锁）。"""
    try:
        handle = open(path, "a+b")
    except OSError:
        return None
    try:
        try:
            import fcntl
        except ImportError:  # Windows
            import msvcrt

            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            deadline = time.time() + 30
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    if time.time() > deadline:
                        handle.close()
                        return None
                    time.sleep(0.2)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return handle
    except OSError:
        handle.close()
        return None


def _unlock_file(handle: IO[bytes] | None) -> None:
    if handle is None:
        return
    try:
        try:
            import fcntl
        except ImportError:
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        handle.close()


def _merge_dir(src: Path, dest: Path, conflict_root: Path) -> int:
    """把旧目录并入新目录，返回移动的条目数；重名文件移到 conflict_root。"""
    moved = 0
    for item in list(src.iterdir()):
        if item.name == ".gitkeep":
            item.unlink(missing_ok=True)
            continue
        target = dest / item.name
        if not target.exists():
            dest.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item), str(target))
            moved += 1
        elif item.is_dir() and target.is_dir():
            moved += _merge_dir(item, target, conflict_root / item.name)
        else:
            conflict_root.mkdir(parents=True, exist_ok=True)
            keep = conflict_root / item.name
            index = 1
            while keep.exists():
                keep = conflict_root / f"{item.name}.{index}"
                index += 1
            shutil.move(str(item), str(keep))
            moved += 1
    try:
        src.rmdir()
    except OSError:
        pass
    return moved


def migrate_legacy_storage() -> list[str]:
    """把旧版平铺数据目录迁移到 var/，返回迁移摘要（空列表表示无需迁移）。"""
    var_dir = Path(config.VAR_DIR)
    if not getattr(config, "VAR_DIR_IS_DEFAULT", True):
        return []

    var_dir.mkdir(parents=True, exist_ok=True)
    lock = _lock_file(var_dir / ".migrate.lock")
    try:
        if (var_dir / ".migrated").exists():
            return []

        legacy_wal = Path(config.LEGACY_DATA_DIR) / "blog.db-wal"
        if legacy_wal.is_file() and legacy_wal.stat().st_size > 0:
            print("[数据目录] 检测到未合并的 WAL 文件，请确认服务已停止；它会随主库一起迁移")

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        conflict_root = var_dir / f".legacy-{stamp}"
        legacy_map = (
            (Path(config.LEGACY_DATA_DIR), var_dir),
            (Path(config.LEGACY_UPLOADS_DIR), var_dir / "uploads"),
            (Path(config.LEGACY_BACKUPS_DIR), var_dir / "backups"),
            (Path(config.LEGACY_STORAGE_DIR), var_dir / "storage"),
        )
        migrated: list[str] = []
        try:
            for src, dest in legacy_map:
                if not src.is_dir():
                    continue
                count = _merge_dir(src, dest, conflict_root / src.name)
                if count:
                    migrated.append(f"{src.name}({count})")

            # v3.2.13 及更早：数据库在 instance/。var 还没有库时沿用，否则整目录改名保留
            legacy_instance = Path(config.LEGACY_INSTANCE_DIR)
            if legacy_instance.is_dir():
                if (var_dir / "blog.db").exists():
                    backup_name = f"instance.legacy-{stamp}"
                    legacy_instance.rename(legacy_instance.with_name(backup_name))
                    migrated.append(f"instance→{backup_name}")
                else:
                    count = _merge_dir(legacy_instance, var_dir, conflict_root / "instance")
                    if count:
                        migrated.append(f"instance({count})")

            (var_dir / ".migrated").write_text(
                datetime.now().isoformat(timespec="seconds"), encoding="utf-8"
            )
            if migrated:
                print("[数据目录] 已迁移到 var/：" + "、".join(migrated))
            if conflict_root.is_dir():
                print(f"[数据目录] 检测到重名文件，已原样保留在 {conflict_root}")
        except Exception as exc:  # noqa: BLE001
            print(f"[数据目录] 迁移未完成（停止服务后可重试）：{exc}")
        return migrated
    finally:
        _unlock_file(lock)


def main(argv: list[str] | None = None) -> int:
    """命令行入口：python -m services.storage [--force]

    部署脚本在停服后调用（--force 允许把数据迁移到 BLOG_DATA_DIR 指定的目录）。
    """
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if "--force" in args:
        config.VAR_DIR_IS_DEFAULT = True
    elif not getattr(config, "VAR_DIR_IS_DEFAULT", True):
        print("数据目录：已设置 BLOG_DATA_DIR，按设计不自动迁移；确实要迁移请加 --force")
        return 0
    moved = migrate_legacy_storage()
    if not (Path(config.VAR_DIR) / ".migrated").exists():
        print("数据目录：迁移未完成，请检查上面的错误信息")
        return 1
    if moved:
        print("数据目录：已迁移 " + "、".join(moved))
    else:
        print("数据目录：无需迁移或已迁移")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
