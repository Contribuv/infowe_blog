# 变更日志

本项目所有重要变更都记录在此文件，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [v1.3.43] - 2026-09-17

### 修复
- **彻底统一时区存储：数据库只存 CST（中国时区 +8h），模板直接切片显示，不再有 UTC→CST 转换层**
  - 根因：v1.3.42 一刀切 `csttime`/`cstdate` filter 在 UTC 存值上 +8h 是对的，但 posts 表存在三套时区——id=2~5 导入脚本用 `datetime.now()` 存 CST、id=7~33 Hexo 迁移占位 `12:00:00` 整点（实际是 CST）、id=34+ CURRENT_TIMESTAMP 存 UTC；filter 对前两类错误二次 +8h 导致显示 +16h
  - 数据迁移（`_migrate_tz.py`）：posts.created_at 分类——纯日期行跳过、`12:00:00` 整点跳过、其余 CURRENT_TIMESTAMP 产生的 UTC 行 +8h；comments/projects/timeline/links 全 UTC +8h；**已备份 data/blog.db → data/blog.db.bak**
- **回滚 v1.3.42 模板 filter**：10 个模板 19 处 `| csttime` / `| cstdate` 还原为 `[:16]` / `[:10]`；删除 app.py `_csttime` / `_cstdate` 函数和 Jinja filter 注册；年份筛选 SQL 去掉 `+8 hours` 偏移；RSS pubDate 改把 DB CST 字符串补 `+08:00` timezone 后 `format_datetime()` 输出 RFC822

### 影响文件
- `app.py` VERSION → 1.3.43
- `templates/admin/comments.html` / `post_edit.html` / `posts.html`
- `templates/default/_comments.html` / `index.html` / `post.html` / `posts.html`
- `templates/tech/index.html` / `post.html` / `posts.html`
- DB：`data/blog.db`（已迁移，备份同目录 `.bak`）

---

## [v1.3.42] - 2026-09-17（已在 v1.3.43 回滚）

### 修复
- **时区：UTC 存值被直接截断显示，凌晨 0-8 点发布显示成"前一天"**：SQLite `CURRENT_TIMESTAMP` 存 UTC，模板里 `created_at[:10]` / `[:16]` 直接截字符串得到 UTC 日期/时间。现注册 `cstdate` / `csttime` Jinja filter，UTC 字符串补 `timezone.utc` 后 `.astimezone(+8h)` 输出，模板全部改用 filter（admin + default + tech 三套主题共 10 个模板 27 处）。
- **年份筛选 SQL 对 UTC 存值不准**：`db_load_posts(year)` 原 `created_at LIKE 'YYYY%'`，改 `substr(datetime(created_at, '+8 hours'), 1, 4) = ?`；`db_get_all_years()` 同步改。
- **RSS pubDate 输出 UTC 字符串不合规**：pubDate 必须 RFC822 带时区，现转 CST 用 `email.utils.format_datetime()` 输出，解析失败降级原值避免 RSS 500。

### 影响文件
- `app.py`（新增 2 个 Jinja filter + 改 3 处 SQL/RSS + VERSION → 1.3.42）
- `templates/admin/comments.html` / `post_edit.html` / `posts.html`
- `templates/default/_comments.html` / `index.html` / `post.html` / `posts.html`
- `templates/tech/index.html` / `post.html` / `posts.html`

---

## [v1.3.39] - 2026-09-14

### 修复
- **登录页高度对齐**：`.login-card` 与左侧 aside 高度不一致问题。统一两边内容布局，避免出现一边过高/过短的视觉割裂。
- **后台页脚**：移除"Powered by"文案，仅保留 `© YYYY Blog · 管理后台`，与前台页脚区分语义。
- **登录页错误提示**：`.login-error` 加左侧 3px accent 条 + 警告图标（lucide alert-triangle SVG）。
- **登录页字段标签**：账号 / 密码 / 验证码 label 前加 SVG 图标（user / lock / shield），通过 CSS `mask-image` 引用，色随 `currentColor` 跟随主题。

### 新增
- **后台 → 关于页面**：`footer_copyright_year` / `footer_copyright_owner` / `footer_powered_by` 三个表单字段，缺省自动回退（年→服务器当前年、主体→`blog_name`、Powered→`Python & Flask`）。
- **全站页脚片段**：`templates/_footer_text.html` 统一渲染，渲染顺序为 `Powered by X © YYYY Blog`（Powered 在前）。admin 登录页、admin 后台底栏、default 主题前台、tech 主题前台统一调用同一片段。
- **登录卡片 focus-within**：任意字段聚焦时，卡片边框过渡到 accent 蓝。

### 优化
- **`.login-card`**：去掉硬编码 `min-height`，改由内容自适应 + `clamp()` 响应式 padding。
- **`.login-hint`**：实线分隔改为虚线，左侧加 accent 小圆点视觉锚。
- **`.field input`**：hover 时边框向 accent 渐变；focus 时背景从 `--bg-input` 切到 `--bg-surface` 增强对比。

### 影响文件
- `templates/_footer_text.html` （新增）
- `templates/admin/login.html`
- `templates/admin/base.html`
- `templates/admin/settings.html`
- `templates/default/base.html`
- `templates/tech/base.html`
- `static/css/admin.css`

---

## [v1.3.38] - 之前
项目同步前端反馈优化（AJAX 原地轮询 + 实时进度 + 完成状态可视化）。
