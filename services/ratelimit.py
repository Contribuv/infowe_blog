"""跨进程限流（基于 rate_events 表）。

为什么不用进程内字典：线上 gunicorn 4 个 worker，每个进程各有一份内存，
同一 IP 打到不同 worker 就等于没限流。这里统一落 SQLite，多进程共享。
"""

from __future__ import annotations

import random
import time

import db


def allow(bucket: str, key: str, window: float, limit: int = 1) -> bool:
    """window 秒内该 key 的事件数是否还没到 limit。只读，不写。"""
    if not key:
        return False
    now = time.time()
    count = int(
        db.scalar(
            "SELECT COUNT(*) FROM rate_events WHERE bucket=? AND key=? AND ts>=?",
            (bucket, key, now - float(window)),
            0,
        )
        or 0
    )
    return count < int(limit)


def touch(bucket: str, key: str) -> None:
    """记一次事件；顺手以很小的概率清理一天前的旧记录。"""
    if not key:
        return
    now = time.time()
    # 只清理两小时前的数据；随机触发，避免每个请求都扫表
    if random.random() < 0.01:
        try:
            db.execute("DELETE FROM rate_events WHERE ts < ?", (now - 7200,))
        except Exception:
            pass
    db.execute(
        "INSERT INTO rate_events (bucket, key, ts) VALUES (?,?,?)",
        (bucket, key, now),
    )


def count(bucket: str, key: str, window: float) -> int:
    return int(
        db.scalar(
            "SELECT COUNT(*) FROM rate_events WHERE bucket=? AND key=? AND ts>=?",
            (bucket, key, time.time() - float(window)),
            0,
        )
        or 0
    )
