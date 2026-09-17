# 变更日志

本项目所有重要变更都记录在此文件，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [v1.3.45] - 2026-09-17

### 新增
- 后台设置页加了一栏「统计代码」，想挂百度统计或者 Google Analytics 不用再手改模板了。以前得自己往 base 里塞脚本，升级一次丢一次，还得记着哪个文件动过。现在把整段脚本粘进设置页保存，前台每个页面都会在底部自动带上，tech 和 default 两套主题都覆盖，以后换主题也不丢；留空就什么都不注入。
- 只有管理员能填，按 HTML 原样输出，跟主流 CMS 的「自定义代码」是同一套路。

改动：`app.py`（VERSION、保存字段、全局注入）、`templates/admin/settings.html`、`templates/tech/base.html` 和 `templates/default/base.html`。

---

## [v1.3.44] - 2026-09-17

### 修复
- 时区又出问题了。v1.3.43 只把库里已有的 UTC 行搬到了 CST，但写入端还在吃 SQLite 的 `DEFAULT CURRENT_TIMESTAMP`——那玩意存的永远是 UTC。部署上去以后新评论、新文章照样按 UTC 落库，过几天新老数据又分成两套。
- 这回从写入端解决：app.py 加了 `_now()`（`datetime.now().strftime()`，本地 CST），所有 INSERT 和 UPDATE 都自己显式写 created_at / updated_at，不再依赖默认值。
- 顺手在 init_db() 里挂了个自动迁移钩子，读 `settings.schema_version`，小于 2 就在首次启动时跑一次 UTC→CST 转换（posts 里的纯日期和 12:00:00 整点是历史 CST 数据，跳过；其余表全部 +8h）。换服务器或者拿旧库启动都能自己修回来。

改动：`app.py`（VERSION、`_now()`、迁移钩子、所有 SQL），写完把 `settings.schema_version` 置为 2。

---

## [v1.3.43] - 2026-09-17

### 修复
- 把时区彻底收拢到一层：库里只存 CST，模板直接切片显示，中间不再有 UTC→CST 的转换层。
- 起因是 v1.3.42 那套 filter 一刀切加 8 小时，可 posts 表里其实混着三套时区：早期导入脚本用 `datetime.now()` 存的是 CST，Hexo 迁移的占位是 12:00:00 整点（也是 CST），id 34 之后 `CURRENT_TIMESTAMP` 存的才是 UTC。filter 对前两类又加了一次 8 小时，时间直接跑飞。
- 数据用 `_migrate_tz.py` 分类处理：纯日期行和 12:00:00 整点原样保留，其余 UTC 行 +8h；comments / projects / timeline / links 全是 UTC，统一 +8h。迁移前备份了 `data/blog.db.bak`。
- 代码层退回去：10 个模板里 19 处 `| csttime` / `| cstdate` 还原成 `[:16]` / `[:10]`，删掉那两个 Jinja filter 和注册；年份筛选 SQL 去掉 `+8 hours`；RSS 的 pubDate 改成先给 CST 字符串补 `+08:00` 再按 RFC822 输出。

改动：`app.py` 和三套主题共 10 个模板，另外动了 `data/blog.db` 数据本身。

---

## [v1.3.42] - 2026-09-17（已在 v1.3.43 回滚）

### 修复
- 凌晨 0 点到 8 点发的文章，日期显示成前一天。库里存的是 UTC，模板拿 `created_at[:10]` / `[:16]` 直接截字符串，截出来的自然是 UTC 时间。
- 当时的做法是注册 `cstdate` / `csttime` 两个 Jinja filter，把字符串补上 `timezone.utc` 再转 `+8h` 输出，三套主题 10 个模板共 27 处改走 filter；年份筛选 SQL 也改成先 `datetime(created_at, '+8 hours')` 再取年；RSS 的 pubDate 按 RFC822 带时区输出，解析失败就退回原值，避免整个 RSS 500。
- 这个方案后来在 v1.3.43 里被换掉了，原因见上面的记录。

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
