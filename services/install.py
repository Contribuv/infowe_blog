"""首次启动初始化：默认管理员与示例文章。

只在空库时执行，可安全重复调用（多 worker 并发时捕获唯一约束冲突）。
"""

from __future__ import annotations

import sqlite3

import db
from models import Category, Post, User

INITIAL_USERNAME = "admin"
INITIAL_PASSWORD = "admin123"

LETTER_TITLE = "致使用者的一封信"
LETTER_SLUG = "a-letter-to-users"
LETTER_TAGS = "公告,开始"

LETTER_CONTENT = """你好，欢迎使用 **Python Blog**。

这是站点首次启动时自动创建的示例文章，用来确认一切已经正常运行。

## 从这里开始

- 后台地址：`/admin`（可在「博客设置 → 账号安全」中改成自定义路径）
- 默认账号：`admin`
- 默认密码：`admin123`
- **第一次登录后，请立即修改密码**

## 建议的下一步

1. 修改站点名称、副标题、作者与头像
2. 按需关闭不需要的导航项
3. 配置 SMTP，开启评论邮件通知
4. 在「数据管理」中定期备份数据库
5. 建议开启 OTP 双重验证

## 写作

文章使用 Markdown，支持标题、列表、表格、代码块、任务列表、脚注与自动目录。

```python
print("Hello, Python Blog")
```

- [x] 启动站点
- [ ] 写下第一篇文章

祝写作愉快。

—— Python Blog
"""


def seed_initial_data() -> None:
    """空库初始化：默认管理员 + 一个示例分类 + 一篇示例文章。"""
    created_user = False
    try:
        if User.count() == 0:
            User.create(INITIAL_USERNAME, INITIAL_PASSWORD)
            created_user = True
    except (RuntimeError, sqlite3.IntegrityError):
        # 多 worker 同时初始化时，另一个进程已经创建
        created_user = False

    if int(db.scalar("SELECT COUNT(*) FROM posts", (), 0) or 0) == 0:
        try:
            category_id = db.scalar("SELECT id FROM categories WHERE slug = 'essay'")
            if not category_id:
                category_id = Category.save(
                    {"name": "随笔", "slug": "essay", "sort_order": 0}
                )
            Post.save(
                {
                    "title": LETTER_TITLE,
                    "slug": LETTER_SLUG,
                    "content": LETTER_CONTENT,
                    "excerpt": "欢迎使用 Python Blog，这是首次启动自动创建的示例文章。",
                    "tags": LETTER_TAGS,
                    "status": "published",
                    "is_featured": "1",
                    "category_id": str(category_id),
                }
            )
        except sqlite3.IntegrityError:
            # 并发初始化时另一进程已插入
            pass

    if created_user:
        print("=" * 60)
        print("  首次启动初始化完成")
        print(f"  后台账号：{INITIAL_USERNAME}")
        print(f"  初始密码：{INITIAL_PASSWORD}")
        print("  登录后请立即修改密码！")
        print("=" * 60)
