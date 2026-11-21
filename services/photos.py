"""照片墙：聚合文章正文与封面里的图片，按文章发布时间分组。

照片的唯一来源是文章（正文图片 + 封面），不单独维护图库：

- 不建表、不后台上传、不做相册，避免出现「文章里没有、照片墙里有」的脱节；
- 同一张图被多篇文章引用时只出现一次，归到最新那篇的日期；
- 头像、评论图、项目文件、originals 副本不属于「文章照片」，直接排除。

日期口径用文章的 ``created_at``（本站的发布时间就是创建时间），
这样照片墙的时间线和归档、文章页完全一致。
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import db
from config import UPLOADS_DIR
from services import upload

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")

# 文章里可能出现的非照片资源：头像 / 评论图 / 项目文件 / 原图副本
SKIP_PREFIXES = (
    "/uploads/avatar/",
    "/uploads/ai-avatar/",
    "/uploads/comment/",
    "/uploads/projects/",
    "/uploads/originals/",
)

MAX_PHOTOS = 500

# 「新照片」的口径：文章发布在最近 7 天内，卡片打 NEW 标
NEW_DAYS = 7


def _is_photo(url: str) -> bool:
    path = str(url or "").split("?", 1)[0].split("#", 1)[0].lower()
    if not path.startswith("/uploads/"):
        return False
    if path.startswith(SKIP_PREFIXES):
        return False
    return path.endswith(IMAGE_EXTS)


def _post_images(row) -> list[str]:
    """一篇文章里的照片，封面优先，其余按正文出现顺序。"""
    content = str(row["content"] or "")
    cover = str(row["cover"] or "")

    ordered: list[str] = []
    for url in upload.extract_urls(cover):
        if url not in ordered:
            ordered.append(url)
    content_urls = upload.extract_urls(content)
    for url in sorted(content_urls, key=lambda u: content.find(u) if u in content else 10**9):
        if url not in ordered:
            ordered.append(url)
    return [u for u in ordered if _is_photo(u)]


def _parse_date(value: str) -> datetime:
    text = str(value or "")[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return datetime.now()


def _photo_exists(url: str, remote_on: bool) -> bool:
    """这张图是否真的能打开：本地有文件，或对象存储有对象。

    文章正文里的 `<img src>` 可能指向一个从未成功上传的文件（历史死链），
    照片墙不能把它当照片展示，否则缩略图和大图都会 404。
    """
    rel = str(url or "")
    if rel.startswith("/uploads/"):
        rel = rel[len("/uploads/"):]
    if rel and (Path(UPLOADS_DIR) / rel).is_file():
        return True
    if not remote_on:
        return False
    try:
        return bool(upload.remote_exists(url))
    except Exception:  # noqa: BLE001
        # 远端查询失败时保守保留：宁可显示占位，也不误删一张好图
        return True


def _drop_missing(items: list[dict]) -> list[dict]:
    """过滤掉本地与对象存储都不存在的图片（并行检查，避免串行 HEAD 拖慢页面）。"""
    if not items:
        return items
    try:
        remote_on = upload.remote_active()
    except Exception:  # noqa: BLE001
        remote_on = False
    with ThreadPoolExecutor(max_workers=8) as pool:
        exists = list(pool.map(lambda item: _photo_exists(item["url"], remote_on), items))
    return [item for item, ok in zip(items, exists) if ok]


def collect(limit: int = MAX_PHOTOS) -> tuple[list[dict], int, str]:
    """返回 (按月份分组的列表, 照片总数, 新照片版本号)。

    只统计已发布文章；草稿和回收站里的文章不会被当成「已展示的照片」。
    正文里引用了但不存在的文件（本地和 OSS 都没有）会被过滤掉。
    """
    rows = db.query(
        "SELECT id, title, content, cover, created_at FROM posts "
        "WHERE status = 'published' ORDER BY created_at DESC, id DESC"
    )

    seen: set[str] = set()
    items: list[dict] = []
    for row in rows:
        for url in _post_images(row):
            if url in seen:
                continue
            seen.add(url)
            rel = url[len("/uploads/"):]
            items.append(
                {
                    "url": url,
                    # 编码后再拼：中文、#、? 都不会破坏 srcset / href
                    "thumb": "/photo-thumb/" + quote(rel, safe="/"),
                    "name": rel.rsplit("/", 1)[-1],
                    "post_id": row["id"],
                    "post_title": str(row["title"] or ""),
                    "date": str(row["created_at"] or ""),
                }
            )

    items = _drop_missing(items)
    total = len(items)

    # 预先读宽高：照片流在图片真正下载前就能占住位置。
    # 否则未加载的图片高度为 0，整列挤在首屏，懒加载会退化成一次全加载。
    shown = items[: max(1, limit)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        sizes = list(pool.map(lambda item: upload.image_dims(item["url"]), shown))
    for item, size in zip(shown, sizes):
        if size:
            item["width"], item["height"] = int(size[0]), int(size[1])
    months: dict[tuple[int, int], dict] = {}
    for item in items[: max(1, limit)]:
        dt = _parse_date(item["date"])
        month = months.setdefault(
            (dt.year, dt.month),
            {"label": f"{dt.year} 年 {dt.month} 月", "count": 0, "days": {}},
        )
        day = month["days"].setdefault(
            (dt.year, dt.month, dt.day),
            {"label": f"{dt.month} 月 {dt.day} 日", "count": 0, "photos": []},
        )
        month["count"] += 1
        day["count"] += 1
        day["photos"].append(item)

    result = []
    for month in months.values():
        month["days"] = list(month["days"].values())
        result.append(month)

    # 新照片：文章发布时间在最近 7 天内
    cutoff = datetime.now() - timedelta(days=NEW_DAYS)
    for item in items[: max(1, limit)]:
        item["is_new"] = _parse_date(item["date"]) >= cutoff

    # 版本号：最新文章时间 + 总数。文章新增图片但时间不变时，总数会变
    bk = f"{items[0]['date'] if items else ''}|{total}"
    return result, total, bk
