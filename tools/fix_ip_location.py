#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复历史评论的 IP 归属地重复（如：重庆市 重庆市 -> 重庆市）"""

from app import app
from db import get_db
from services import ip_location


def main():
    with app.app_context():
        db = get_db()
        rows = db.execute(
            "SELECT id, ip_location FROM comments WHERE ip_location IS NOT NULL AND ip_location != ''"
        ).fetchall()
        if not rows:
            print("没有需要处理的评论 ip_location")
            return
        updated = 0
        for r in rows:
            old = r["ip_location"] or ""
            newv = ip_location.normalize_display(old)
            if newv != old:
                db.execute(
                    "UPDATE comments SET ip_location = ? WHERE id = ?",
                    (newv, r["id"]),
                )
                updated += 1
        db.commit()
        print(f"处理完成：共 {len(rows)} 条，修复 {updated} 条")


if __name__ == "__main__":
    main()
