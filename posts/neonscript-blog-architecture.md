---
title: "NeonScript：用 Flask + SQLite 手搓一个完整博客系统"
date: 2026-08-04
tags: ["Python", "Flask", "博客", "全栈", "SQLite", "开源"]
read_time: 12
excerpt: "从零搭建一个轻量级 Markdown 博客：Flask 后端 + SQLite 数据层 + Jinja2 模板，含完整后台管理、GitHub 项目展示、评论系统、RSS 等。本文全面复盘架构设计、技术选型、核心代码实现与功能测试。"
---

## 缘起

每次换笔记工具都折腾好久，最终决定**自己写一个**。目标很明确：

- 用 Markdown 写文章
- 代码干净，可以长期维护
- 带后台管理，别每次都去改数据库
- 能展示 GitHub 开源项目
- 部署简单，一个 Python 脚本跑起来

于是有了 **NeonScript** —— 约 870 行 Python 代码驱动的博客系统。

---

## 技术栈一览

| 层次 | 选型 | 理由 |
|------|------|------|
| Web 框架 | **Flask** | 极简、灵活、Python 生态好 |
| 数据库 | **SQLite** | 零配置、单文件部署、够用 |
| 模板引擎 | **Jinja2** | Flask 内置、继承机制好用 |
| Markdown | **Python-Markdown** | 支持栅栏代码块、表格、SaneLists |
| 前端样式 | 手写 CSS | 无框架依赖，加载快 |
| 图标 | **Lucide Icons** | SVG 图标、按需引入 |

---

## 项目结构

```
neonscript/
├── app.py              # 主程序（~870 行）
├── blog.db             # SQLite 数据库（自动生成）
├── posts/              # Markdown 源文件
├── templates/
│   ├── base.html       # 前台基础模板
│   ├── index.html      # 首页（搜索 + 分页 + 精选）
│   ├── post.html       # 文章详情（评论 + 相关推荐）
│   ├── projects.html   # 项目展示页
│   ├── tags.html       # 标签云
│   ├── links.html      # 友情链接
│   ├── about.html      # 关于页
│   └── admin/          # 后台模板（7 个页面）
├── static/
│   ├── css/
│   │   ├── style.css   # 前台样式
│   │   └── admin.css   # 后台样式
│   └── js/
└── requirements.txt    # 依赖：flask, markdown
```

---

## 数据库设计（6 张表）

```sql
-- 文章表（核心）
posts (
    id, title, slug UNIQUE, content, excerpt,
    tags JSON, cover, read_time,
    is_featured, status, created_at, updated_at
)

-- 开源项目表
projects (
    id, name, description, url,
    stars, language, topics JSON,
    sort_order, featured
)

-- 友情链接表
links (
    id, name, url, description, sort_order
)

-- 评论表
comments (
    id, post_id FK→posts, author, content, created_at
)

-- 系统设置表
settings (key UNIQUE, value)

-- 用户表
users (username UNIQUE, password_hash)
```

设计要点：

1. **Tags 存为 JSON 字符串** —— 用 `LIKE '%"tag"%'` 检索，避免多表 JOIN
2. **Slug 唯一约束** —— URL 友好的文章标识
3. **外键级联删除** —— 删文章自动清理评论
4. **排序字段** —— 项目和链接支持手动调整顺序

---

## 核心功能实现

### 1. 文章分页搜索

```python
PAGE_SIZE = 6

def db_load_posts(status='published', tag=None, search=None, page=1, per_page=PAGE_SIZE):
    conditions = []
    params = []

    if status:
        conditions.append("status=?")
        params.append(status)
    if tag:
        conditions.append("tags LIKE ?")
        params.append(f'%"{tag}"%')
    if search:
        conditions.append("(title LIKE ? OR content LIKE ? OR excerpt LIKE ?)")
        s = f'%{search}%'
        params.extend([s, s, s])

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    # 总数（计算分页用）
    total = db.execute(f"SELECT COUNT(*) FROM posts {where}", params).fetchone()['c']

    # 精选文章置顶 + 时间倒序
    offset = (page - 1) * per_page
    rows = db.execute(
        f"SELECT * FROM posts {where}
         ORDER BY is_featured DESC, created_at DESC
         LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()

    return posts, total
```

### 2. Markdown 渲染

```python
def render_post_content(content):
    # 去除 YAML front matter
    content = re.sub(r'^---.*?---\s*', '', content, flags=re.DOTALL)
    return markdown.markdown(
        content,
        extensions=['fenced_code', 'tables', 'nl2br', 'sane_lists']
    )
```

### 3. 相关文章推荐

基于标签匹配的简单推荐算法：

```python
def db_get_related_posts(current_id, tags, limit=3):
    results = []
    for tag in tags:
        rows = db.execute(
            """SELECT * FROM posts
               WHERE status='published' AND id!=?
               AND tags LIKE ? ORDER BY created_at DESC LIMIT ?""",
            (current_id, f'%"{tag}"%', limit)
        ).fetchall()
        for r in rows:
            if r['id'] not in [x['id'] for x in results]:
                results.append(r)
        if len(results) >= limit:
            break
    return results[:limit]
```

### 4. RSS 订阅源

用标准库 `xml.etree.ElementTree` 手写 XML，零依赖：

```python
@app.route('/feed.xml')
def rss_feed():
    posts, _ = db_load_posts(per_page=20)
    rss = Element('rss', version='2.0')
    channel = SubElement(rss, 'channel')
    SubElement(channel, 'title').text = blog_name
    SubElement(channel, 'link').text = request.url_root

    for p in posts:
        item = SubElement(channel, 'item')
        SubElement(item, 'title').text = p['title']
        SubElement(item, 'link').text = f"{request.url_root}post/{p['slug']}"
        SubElement(item, 'guid').text = f"{request.url_root}post/{p['slug']}"

    return app.response_class(xml_str, mimetype='application/rss+xml')
```

### 5. 密码安全

```python
app.secret_key = 'neonscript-blog-secret-key-2024'

def hash_password(password):
    return hashlib.sha256((password + app.secret_key).encode()).hexdigest()
```

**⚠️ 关键教训**：最初用了 `secrets.token_hex(32)` 随机生成 secret_key，导致每次重启密码哈希都失效。已改为固定值并添加了管理面板的密码修改功能。

### 6. 数据库兼容迁移

```python
# 兼容旧数据库：添加新列（不删库不重建）
try:
    db.execute("SELECT is_featured FROM posts LIMIT 1")
except sqlite3.OperationalError:
    db.execute("ALTER TABLE posts ADD COLUMN is_featured INTEGER DEFAULT 0")
```

这种方式比删库重建安全得多，保留用户已有数据。

---

## 后台管理系统

### 路由总览（12 个端点）

| 路由 | 方法 | 功能 |
|------|------|------|
| `/admin/login` | GET/POST | 登录 |
| `/admin/dashboard` | GET | 统计仪表盘 |
| `/admin/posts` | GET | 文章列表（搜索/分页/筛选） |
| `/admin/posts/new` | GET/POST | 新建文章 |
| `/admin/posts/<id>/edit` | GET/POST | 编辑文章 |
| `/admin/posts/<id>/delete` | POST | 删除文章 |
| `/admin/posts/<id>/preview` | GET | AJAX 预览 |
| `/admin/projects` | GET | 项目列表 |
| `/admin/projects/new` | GET/POST | 添加项目 |
| `/admin/projects/<id>/edit` | GET/POST | 编辑项目 |
| `/admin/links` | GET | 链接列表 |
| `/admin/links/new` | GET/POST | 添加链接 |
| `/admin/comments` | GET | 评论管理 |
| `/admin/comments/<id>/delete` | POST | 删除评论 |
| `/admin/settings` | GET/POST | 博客设置 |

### 登录鉴权

使用 session + 装饰器模式：

```python
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    ...
```

---

## 前台页面

### 首页
- 文章列表 + 分页器（页码带省略号）
- 搜索框（标题 / 内容 / 摘要全文检索）
- 标签筛选
- 精选文章区域

### 文章详情
- Markdown 渲染（代码高亮、表格）
- **相关文章推荐**（基于标签匹配）
- **评论区**（昵称 + 内容，最长 2000 字）
- 分享按钮 + CC BY-NC-SA 4.0 许可声明

### GitHub 项目页
- 卡片式布局，展示项目名称、描述、语言、Star 数、标签
- 按语言筛选
- 语言分布统计

### 其他
- 标签云（含文章计数）
- 友情链接（头像 + 描述卡片）
- 关于页（技能进度条、个人介绍、GitHub 链接）
- RSS Feed（/feed.xml）

---

## 测试结果

手动测试全部通过，覆盖 13 个页面：

### ✅ 后台功能（8 项）
| 模块 | 测试项 | 结果 |
|------|--------|------|
| 登录 | 用户名密码验证、错误提示 | 通过 |
| 仪表盘 | 统计卡片（文章数/项目数/链接数/评论数）| 通过 |
| 文章管理 | 列表/搜索/筛选/CRUD | 通过 |
| 项目管理 | 新增/编辑/删除，含表单验证 | 通过 |
| 友情链接 | 新增/编辑/删除 | 通过 |
| 评论管理 | 查看/删除，关联文章标题 | 通过 |
| 博客设置 | 所有字段保存 + 密码修改 | 通过 |
| Markdown 预览 | AJAX 实时预览 | 通过 |

### ✅ 前台功能（7 项）
| 页面 | 测试项 | 结果 |
|------|--------|------|
| 首页 | 分页/搜索/标签筛选/精选 | 通过 |
| 文章详情 | 渲染/相关推荐/许可声明 | 通过 |
| 评论 | 提交/计数更新/内容截断 | 通过 |
| 项目页 | 卡片展示/语言筛选/统计 | 通过 |
| 友链页 | 链接展示/头像 | 通过 |
| RSS | XML 格式/20 篇文章 | 通过 |
| 关于页 | 技能条/个人介绍 | 通过 |

### 🔧 修复的问题
1. `secret_key` 随机生成 → 改为固定值，解决密码每次重启失效
2. 删除 `import secrets` 残留导入
3. 数据库 `is_featured` 列不存在 → 添加 ALTER TABLE 迁移逻辑

---

## 设计理念

### 1. 极简依赖
只依赖 `flask` 和 `markdown` 两个第三方库，不需要 pip install 一堆东西。

### 2. 数据层封装
所有数据库操作统一为 `db_*` 函数，路由层不直接写 SQL：

```
路由层 (app route)
    ↓
数据层 (db_* functions)
    ↓
SQLite
```

### 3. 单文件可部署
只需 `app.py` + `templates/` + `static/` + `posts/`，无复杂的构建流程。

### 4. 渐进增强
从 JSON 文件存储迁移到 SQLite，从基本博客功能扩展到项目管理 + 评论 + RSS。

---

## 未来计划

- 文章草稿自动保存
- Markdown 编辑器集成（如 EasyMDE）
- 文章访问量统计
- 站点地图（sitemap.xml）
- 图片上传管理

---

## 总结

用 Flask + SQLite 自建博客的好处：

1. **完全可控** —— 每一行代码都清楚
2. **极简部署** —— `python app.py` 就跑起来
3. **数据自主** —— 一个 blog.db 文件，随时备份
4. **持续迭代** —— 想加什么功能自己写

870 行 Python 代码，6 张数据库表，13 个页面，一个麻雀虽小五脏俱全的博客系统。如果你也在寻找一个轻量级的博客方案，NeonScript 也许是个不错的起点。

> 源码地址：[GitHub - NeonScript Blog](https://github.com/neonscript/blog)
