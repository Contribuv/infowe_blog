"""本地缓存目录的容量兜底。

头像代理、README 图片代理都会把外部资源落到 cache 目录，
key 由 URL/QQ 号决定，等于外部可控；不设上限会被慢慢刷满磁盘。
"""

from __future__ import annotations

from pathlib import Path


def cap(folder: Path, max_files: int, keep_ratio: float = 0.8) -> int:
    """文件数超过 max_files 时，按 mtime 从旧到新删到 keep_ratio。

    返回删除数量。目录不存在或读取失败时静默返回 0。
    """
    try:
        files = [p for p in folder.iterdir() if p.is_file()]
    except OSError:
        return 0
    if len(files) <= max_files:
        return 0
    try:
        files.sort(key=lambda p: p.stat().st_mtime)
    except OSError:
        return 0
    target = int(max_files * keep_ratio)
    removed = 0
    for path in files[: max(0, len(files) - target)]:
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            continue
    return removed
