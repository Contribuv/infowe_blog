# PHP 博客 → Python/Flask 多模块重构计划

> 目标：以 `D:\fnos\blog`（Haozi Blog PHP 2.7.17）为功能基准，在 `D:\python_blog`
> 用 Python + Flask + SQLite 重建一个**多文件、模块化**的博客系统，并保持前台/后台
> 交互、路由与模板结构基本一致。

---

## 1. 背景与目标

- 原项目：PHP 8 + MySQL，单入口 `index.php`，自研 Jinja2 兼容模板引擎，
  前台 24 条路由 + 后台 60+ 条路由。
- 旧 Python 版：单文件 `app.py`（约 30 万字符），功能停留在 PHP 版早期，且已停止维护。
- 本次重构：
  1. **多文件**：`app.py` 只做应用工厂与入口，业务拆到 `models/`、`services/`、`routes/`；
  2. **SQLite**：零外部数据库，开箱即用，WAL 模式；
  3. **功能对齐 PHP 版**：以前台 + 后台 + 安全 + 数据迁移为主线；
  4. **模板复用**：PHP 版模板本身是 Jinja2 语法（含 `url_for`），直接移植并按需修文案。

### 非目标（本期不做/降级）

| 项目 | 处理方式 |
| --- | --- |
| PHP 源码在线热升级 | 改为版本检查 + 手动 `git pull` 说明，不做在线覆盖 |
| PHP 插件 Hook 总线 | 预留 `hooks.py`，内置空实现，不加载第三方 PHP 插件 |
| ip2region 18MB 离线库 | 先做内网/回环识别 + 可选外置 xdb；不打包体积巨大的二进制 |
| 阿里云/腾讯云证书到期查询 | 保留配置项与接口占位，不强制依赖云 SDK |
| MySQL 专用 SQL 导入 | 支持 SQLite 备份导入 + JSON/Markdown 导出；MySQL dump 解析降级为提示 |

---

## 2. 技术栈

| 层 | 选型 |
| --- | --- |
| Web | Flask 3.x（应用工厂 + Blueprint） |
| DB | SQLite 3（`sqlite3`，WAL，外键开启） |
| 模板 | Jinja2（复用 `themes/tech` 与 `core/view/admin`） |
| Markdown | `markdown`（扩展：fenced_code / tables / toc / codehilite / sane_lists） |
| 图片 | Pillow（缩略图 / 水印 / 头像缓存） |
| HTTP | `requests`（GitHub 同步、状态探测、头像回源） |
| 密码 | `werkzeug.security`（PBKDF2） |
| OTP | 标准库 `hmac` + `base64` 实现 RFC 6238 |
| 邮件 | `smtplib` + `email` |

运行环境：`D:\python_blog\.venv`（Python 3.12）。

---

## 3. 目录结构

```
D:\python_blog\
├── app.py                     # 入口：create_app()、蓝图注册、CLI、开发服务器
├── config.py                  # 路径 / 密钥 / 上传限制 / 版本
├── db.py                      # 连接管理、schema 初始化、迁移、查询辅助
├── schema.sql                 # 全量建表 SQL
├── requirements.txt
├── PLAN.md
├── README.md
├── models/
│   ├── __init__.py
│   ├── post.py                # 文章：列表/详情/标签/相关/相邻/保存/批量
│   ├── category.py
│   ├── comment.py             # 评论树、审核、批量
│   ├── project.py
│   ├── link.py
│   ├── timeline.py
│   ├── memory.py
│   ├── user.py
│   └── service_check.py
├── services/
│   ├── settings.py            # settings 表读写 + 默认值 + 布尔/JSON 辅助
│   ├── auth.py                # 登录态、密码、防爆破
│   ├── otp.py                 # TOTP、恢复码
│   ├── markdown.py            # 渲染、目录、自动链接、HTML 清洗
│   ├── comments.py            # 提交校验、冷却、评论者 cookie、图片合并
│   ├── upload.py              # 上传、类型白名单、缩略图、孤儿扫描
│   ├── avatar.py              # 头像 URL、代理缓存
│   ├── notify.py              # SMTP 邮件通知
│   ├── ip_location.py         # 内网识别 + 可选 xdb
│   ├── site_url.py            # 绝对地址、HTTPS/www 归一
│   ├── github.py              # 仓库信息 / README 抓取与缓存
│   ├── project_sync.py        # 项目同步状态机
│   ├── status.py              # 站点探活 / 证书天数
│   ├── theme.py               # 主题发现与静态版本
│   ├── backup.py              # SQLite 备份、SQL/JSON/Markdown 导出
│   └── hooks.py               # 空 Hook 总线（插件扩展位）
├── routes/
│   ├── __init__.py
│   ├── front.py               # 首页/文章/标签/搜索/关于/友链/项目/状态/RSS
│   ├── auth.py                # 登录/登出/OTP/找回密码
│   ├── admin.py               # 后台全部管理页
│   ├── assets.py              # 上传文件/主题/静态/头像/分享图/README 图
│   └── api.py                 # /api/status、预览、同步状态等 JSON
├── templates/
│   ├── theme/tech/            # 前台主题（移植自 themes/tech）
│   ├── admin/                 # 后台模板（移植自 core/view/admin）
│   └── shared/                # 公共片段（_comments/_footer_text/_macros）
├── static/                    # 全站静态资源（后台 CSS/JS、vendor、图片）
├── themes/                    # 主题资源（tech/theme.css、theme.js、info.json）
├── uploads/                   # 上传文件（年/月、评论、头像、水印）
├── backups/                   # 数据库备份与导出
├── storage/cache/             # 模板/头像/分享图缓存
├── data/                      # 同步状态、升级缓存
└── instance/blog.db           # SQLite 数据库
```

---

## 4. 数据库设计（SQLite）

| 表 | 关键字段 | 说明 |
| --- | --- | --- |
| `posts` | id, title, slug UNIQUE, content, excerpt, tags(JSON), cover, read_time, views, status, is_featured, category_id, created_at, updated_at | status: published/draft/hidden |
| `categories` | id, name, slug UNIQUE, sort_order, created_at | |
| `comments` | id, post_id, project_id, parent_id, author, email, email_hash, website, content, status, is_private, qq, ip_text, ip_location, created_at | 树形靠 parent_id 内存组装 |
| `projects` | id, name, description, url, stars, language, topics(JSON), sort_order, featured, github_repo, custom_name, languages(JSON), created_at | |
| `links` | id, name, url, description, avatar, sort_order, status, created_at | status: approved/pending/rejected |
| `timeline` | id, date, content, sort_order, created_at | 关于页时间线 |
| `memories` | id, title, text, image, date, sort_order, created_at | 记忆卡片（关于页/后台预留） |
| `service_checks` | id, service_id, checked_at, ok, latency_ms, cert_days, detail | 状态监控采样 |
| `settings` | key PRIMARY KEY, value | 全站配置 |
| `users` | id, username UNIQUE, password_hash | 单管理员约束 |
| `login_attempts` | ip, fail_count, last_at, locked_until | 登录防爆破（替代文件） |

索引：`posts(status, created_at)`、`posts(category_id)`、`comments(post_id)`、
`comments(project_id)`、`comments(status)`、`service_checks(service_id, checked_at)`。

---

## 5. 功能对齐矩阵

### 5.1 前台（24 条路由）

| 路由 | 功能 | 实现要点 |
| --- | --- | --- |
| `/` | 首页 | 精选 3 篇 + 最新 N 篇；`?tag=` / `?q=` 过滤；分页信息 |
| `/posts` | 文章列表/归档 | 标签/年份筛选、分页、全部标签与年份 |
| `/post/<id>` | 文章详情 | Markdown + TOC、阅读时长/字数、上下篇、相关文章、分享卡片、评论树 |
| `POST /post/<id>/view` | 浏览计数 | IP+文章 60s 冷却 |
| `POST /post/<id>/comment` | 发表评论 | 校验、冷却、敏感词、图片、审核、通知 |
| `/comment/upload` | 评论图片上传 | 访客上传，白名单 + 大小限制 |
| `/tags` | 标签云 | 按频次分组，组内文章 |
| `/search` | 搜索跳转 | 302 到 `/?q=` |
| `/about` | 关于 | 简介、技能、时间线、统计 |
| `/links` | 友链 | 已审核友链 + 本站信息卡片 |
| `/links/apply` | 友链申请 | 表单校验、pending、成功页 |
| `/status` | 站点状态 | 服务列表、历史可用率 |
| `/api/status` | 状态 JSON | 供前端轮询/徽章 |
| `/projects` | 项目列表 | 自动同步、语言占比 |
| `/projects/<id>` | 项目详情 | GitHub README 缓存、评论 |
| `/feed.xml` | RSS | 最近 20 篇，CDATA |
| `/uploads/...` | 上传文件 | 防穿越、缓存头、Range 可选 |
| `/share-thumb/...` | 4:3 分享图 | Pillow 懒生成 + 缓存 |
| `/avatar/<key>/<size>.png` | 头像代理 | 磁盘缓存 + 回源 |
| `/readme-img` | README 图片代理 | 白名单域名 + 缓存 |
| `/themes/...` `/static/...` | 主题/静态资源 | 防穿越、7 天缓存 |

### 5.2 后台（60+ 条路由）

| 模块 | 功能 |
| --- | --- |
| 认证 | 登录、登出、OTP 验证/恢复/设置、邮箱验证码找回、验证码、防爆破 |
| 仪表盘 | 文章/评论/友链/项目统计、待审核、最近评论 |
| 文章 | 列表/搜索/筛选、新建/编辑（Markdown + Vditor）、预览、删除、批量发布/草稿/隐藏/删除、封面上传 |
| 分类 | 列表、新建、编辑、删除（文章置空）、批量删除 |
| 项目 | 列表、新建/编辑、删除、批量、GitHub 单条/全量同步、同步状态轮询 |
| 友链 | 列表、审核/拒绝、新建/编辑、删除、批量 |
| 时间线 | 列表、新建/编辑、删除、批量 |
| 评论 | 列表（待审核置顶）、通过、删除（整棵子树）、批量通过/删除 |
| 上传 | 图片/媒体/文件三类、大小与扩展名限制、水印 |
| 孤儿文件 | 扫描 uploads 中未被引用的文件、预览、批量删除 |
| 状态监控 | 服务配置、立即探测、云端到期查询占位 |
| 主题 | 主题列表、切换 |
| 设置 | 站点信息、导航开关、评论、SMTP、图片水印、敏感词、统计代码、上传限制、社交链接、备案 |
| 数据 | SQLite 备份、下载/删除备份、JSON 导出、Markdown 导出、SQLite 导入 |
| 升级 | 版本检查（GitHub API）、当前版本展示、手动升级说明 |

### 5.3 安全

- 全部 POST 做同源校验（Origin/Referer），并叠加 Flask session CSRF token（对模板无侵入）。
- Session Cookie：HttpOnly / SameSite=Lax；生产可配 Secure。
- 密码 PBKDF2；单管理员唯一约束（程序层 + UNIQUE）。
- 登录失败计数、递增延迟、5 分钟锁定；可选图形验证码。
- OTP：RFC 6238 TOTP，恢复码一次性消费。
- Markdown 链接协议白名单；统计代码只保留 `<script>`；评论正文整体转义。
- 上传：扩展名白名单 + MIME 嗅探 + 大小限制 + 路径穿越防护。
- 反代 IP：仅当直连地址为私网/回环时采信 X-Forwarded-For。

### 5.4 数据兼容

- 可直接读取旧 Flask 版 SQLite（表结构一致，缺列自动 `ALTER TABLE` 补齐）。
- 支持后台导入 SQLite（整库覆盖，导入前自动备份）。
- 导出 JSON（全表）与 Markdown（文章 + front matter）。

---

## 6. 实施阶段

### P0 骨架（本次）
- `config.py` / `db.py` / `schema.sql` / `app.py`
- 设置服务、模板装载、错误页、静态资源与主题目录
- CLI：`init-db`、`create-admin`、`run`

### P1 前台核心
- 文章模型 + Markdown + 首页/列表/详情/标签/搜索/RSS
- 分类、相关文章、上下篇、浏览量
- 模板移植（index/posts/post/tags/base/_footer_text）

### P2 互动
- 评论模型与服务（审核/树/私密/敏感词/图片/冷却）
- 友链、关于、时间线
- 通知邮件、IP 归属地

### P3 后台
- 登录/OTP/找回、仪表盘
- 文章/分类/项目/友链/时间线/评论 CRUD 与批量
- 上传、孤儿清理、主题、设置、状态监控

### P4 项目与状态
- GitHub 仓库同步、README 本地化与缓存
- 项目列表/详情、语言占比
- 状态探测与历史

### P5 数据与运维
- 备份、导出、导入
- 版本检查、部署说明、README
- 冒烟测试（test client 覆盖主要路由）

### 验收标准
1. `python app.py` 可启动，自动建库并生成管理员初始密码；
2. 前台 20+ 路由 200/302 正常，后台登录后可完成文章发布；
3. 评论提交 → 后台审核 → 前台显示闭环；
4. 图片上传 → 文章引用 → 孤儿扫描可识别；
5. 备份/导出/导入可用；
6. 移动端主题样式与原版一致（复用 CSS/JS）。

---

## 7. 与旧 Python 版的关系

- 旧版 `app.py` 作为**行为参考**（评论冷却、OTP、GitHub 缓存等算法），
  不直接复制其单文件结构与乱码字符串。
- 模板与静态资源从 PHP 版移植（PHP 模板引擎本就是 Jinja2 兼容语法）。
- 新增模块化分层、SQLite 迁移、更完整的后台与安全能力。

---

## 8. 实施状态（2026-10-25）

- ✅ P0 骨架：`app.py` / `config.py` / `db.py` / `schema.sql` / CLI
- ✅ P1 前台：首页、文章、标签、搜索、归档、RSS、Markdown 目录
- ✅ P2 互动：评论审核/私密/图片/敏感词/冷却、友链、关于、时间线、邮件通知
- ✅ P3 后台：登录/OTP/找回、仪表盘、文章/分类/项目/友链/时间线/评论 CRUD、上传、孤儿清理、主题、设置、状态
- ✅ P4 项目与状态：GitHub/Gitee 同步、README 缓存、语言占比、探活与历史
- ✅ P5 数据：SQLite 备份、JSON/Markdown 导出、SQLite 导入
- ⚠️ 降级：在线升级改为版本检查 + `git pull`；MySQL SQL 导入改为提示；
  ip2region 离线库改为可选；云到期查询以手工日期为准

当前入口：`python app.py`（默认 5000 端口），模板与静态资源已从 PHP 版移植。

