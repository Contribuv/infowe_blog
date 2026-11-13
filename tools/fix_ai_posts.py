#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清理历史 AI 文章：正文重复标题、YAML 头、标签格式。

代码修复只影响之后新发布的文章；已经入库的历史数据不会自己变干净。
部署到线上后，在服务器上执行本脚本即可处理存量文章。

用法：
    python tools/fix_ai_posts.py            # 只预览，不改库
    python tools/fix_ai_posts.py --apply    # 实际写入（先自动备份数据库）
    python tools/fix_ai_posts.py --id 94 --id 99 --apply
    python tools/fix_ai_posts.py --set-tags '75=抖音直播,Mac,直播伴侣,采集卡' --apply

只会做机械、安全的清理：
    1. 删除正文开头的 YAML front matter；
    2. 删除与文章标题相同/高度相似的第一个 H1；
    3. 删除紧跟其后的「**标签**：」等元信息行；
    4. 标签去重（大小写不敏感）、去 # / 引号、拆中英文分隔符、最多 8 个。

标签语义是否合理（例如把代码词当标签）脚本无法判断，会在末尾单独列出，
需要人工决定是否修改；确认后可用 --set-tags 指定新标签重跑。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from app import app  # noqa: E402
from config import DATA_DIR  # noqa: E402
import db  # noqa: E402
from models import Post  # noqa: E402
from plugins.ai_assistant.tools import (  # noqa: E402
    _normalize_tags,
    _strip_title_from_content,
)


def _backup() -> Path:
    """写入前备份数据库，命名与 db.py 的结构升级备份保持一致。"""
    source = Path(app.config["DATABASE"])
    folder = Path(DATA_DIR) / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"manual_cleanup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    return target


def _suspicious(tags: list[str]) -> list[str]:
    """列出无法自动判断、可能需要人工调整的标签。"""
    issues: list[str] = []
    if len(tags) > 6:
        issues.append("数量偏多")
    for tag in tags:
        if len(tag) > 12:
            issues.append(f"过长：{tag}")
        if re.search(r"[，、。！？;；]", tag):
            issues.append(f"含标点：{tag}")
        # 纯小写英文短词大概率是代码词 / 变量名，正常标签也可能命中，仅提示
        if re.fullmatch(r"[a-z]{2,8}", tag):
            issues.append(f"疑似代码词：{tag}")
    return issues


def _save_post(post: dict, *, content: str | None = None, tags: list[str] | None = None,
               regenerate_excerpt: bool = False) -> None:
    """按现有字段回写一篇文章；没有显式要求时保留原摘要。"""
    Post.save(
        {
            "title": post["title"],
            "slug": post.get("slug") or "",
            "content": (post.get("content") or "") if content is None else content,
            "tags": ",".join(tags) if tags is not None else ",".join(post.get("tags") or []),
            "status": post["status"],
            "category_id": str(post.get("category_id") or ""),
            "cover": post.get("cover") or "",
            "is_featured": "1" if post.get("is_featured") else "0",
            "created_at": post.get("created_at") or "",
            "excerpt": post.get("excerpt") or "",
            "excerpt_manual": "0" if regenerate_excerpt else "1",
        },
        int(post["id"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="清理历史 AI 文章的标题与标签")
    parser.add_argument("--apply", action="store_true", help="实际写入数据库")
    parser.add_argument("--id", type=int, action="append", dest="ids", help="只处理指定文章 id，可重复")
    parser.add_argument(
        "--set-tags",
        action="append",
        dest="set_tags",
        metavar="ID=标签1,标签2",
        help="直接指定某篇文章的新标签，可重复；用于人工确认后的语义修正",
    )
    args = parser.parse_args()

    overrides: dict[int, list[str]] = {}
    for spec in args.set_tags or []:
        if "=" not in spec:
            parser.error(f"--set-tags 格式应为 ID=标签1,标签2，收到：{spec}")
        raw_id, raw_tags = spec.split("=", 1)
        try:
            pid = int(raw_id)
        except ValueError:
            parser.error(f"--set-tags 的文章 id 不是整数：{raw_id}")
        tags = [t for t in _normalize_tags(raw_tags).split(",") if t]
        if tags:
            overrides[pid] = tags

    with app.app_context():
        if args.ids:
            rows = db.query(
                f"SELECT id FROM posts WHERE deleted_at IS NULL AND id IN ({','.join('?' * len(args.ids))})",
                args.ids,
            )
        else:
            rows = db.query("SELECT id FROM posts WHERE deleted_at IS NULL ORDER BY id")

        plans: list[dict] = []
        for row in rows:
            post = Post.get(int(row["id"]))
            if not post:
                continue
            old_content = post.get("content") or ""
            old_tags = [str(t) for t in (post.get("tags") or [])]
            new_content = _strip_title_from_content(post.get("title") or "", old_content)
            new_tags = _normalize_tags(old_tags)
            new_tag_list = [t for t in new_tags.split(",") if t]
            if new_content == old_content and new_tag_list == old_tags:
                continue
            plans.append(
                {
                    "post": post,
                    "content": new_content,
                    "content_changed": new_content != old_content,
                    "tags_changed": new_tag_list != old_tags,
                    "old_tags": old_tags,
                    "new_tag_list": new_tag_list,
                }
            )

        override_plans: list[dict] = []
        for pid, tags in overrides.items():
            post = Post.get(pid)
            if not post:
                print(f"#{pid} 不存在或已删除，跳过 --set-tags")
                continue
            old_tags = [str(t) for t in (post.get("tags") or [])]
            if old_tags != tags:
                override_plans.append({"post": post, "old_tags": old_tags, "new_tag_list": tags})

        if not plans and not override_plans:
            print("没有需要清理的文章")
            return

        if plans:
            print(f"共发现 {len(plans)} 篇正文/标签需要机械清理：\n")
            for plan in plans:
                post = plan["post"]
                print(f"#{post['id']} {post['title']}")
                if plan["content_changed"]:
                    print("  正文：将删除开头的重复标题 / YAML 头 / 标签元信息")
                if plan["tags_changed"]:
                    print(f"  标签：{plan['old_tags']} -> {plan['new_tag_list']}")
                print()

        if override_plans:
            print(f"共指定 {len(override_plans)} 篇标签修正：\n")
            for plan in override_plans:
                post = plan["post"]
                print(f"#{post['id']} {post['title']}")
                print(f"  标签：{plan['old_tags']} -> {plan['new_tag_list']}")
                print()

        # 只提示、不自动改：语义问题没法用规则判断
        flagged = []
        for row in rows:
            post = Post.get(int(row["id"]))
            if not post:
                continue
            issues = _suspicious([str(t) for t in (post.get("tags") or [])])
            if issues:
                flagged.append((post["id"], post["title"], issues))
        if flagged:
            print("以下标签建议人工确认（脚本不会自动修改）：")
            for pid, title, issues in flagged:
                print(f"  #{pid} {title[:28]}：{'；'.join(issues)}")
            print()

        if not args.apply:
            print("以上为预览。确认无误后加 --apply 执行，执行前会自动备份数据库。")
            return

        backup = _backup()
        print(f"已备份数据库：{backup}")

        changed = 0
        for plan in plans:
            post = plan["post"]
            _save_post(
                post,
                content=plan["content"],
                tags=plan["new_tag_list"],
                regenerate_excerpt=plan["content_changed"],
            )
            changed += 1
            print(f"已处理 #{post['id']} {post['title']}")

        # 语义标签修正放在最后：同一篇既做机械清理又指定标签时，以人工指定为准
        for plan in override_plans:
            post = Post.get(int(plan["post"]["id"]))
            if not post:
                continue
            _save_post(post, tags=plan["new_tag_list"])
            changed += 1
            print(f"已修正标签 #{post['id']} {post['title']}")

        print(f"\n完成：共处理 {changed} 篇")


if __name__ == "__main__":
    main()
