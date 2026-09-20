# 变更日志

本项目所有重要变更都记录在此文件，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [v1.3.48] - 2026-09-20

### 修复
- **修掉了一个严重 bug：线上水印字号永远只有 9px，改档位完全无效**。起因是字体发现逻辑只硬编码了 3 个 Linux 字体路径，生产服务器（宝塔精简系统）上一个都不存在，字体检测结果为空；随后兜底代码调用 `load_default()` 时又没把算好的字号传进去，这个函数返回的是固定 9px 的内置位图字体——于是无论设置 2%/3%/4%（本应 28/52/76px），渲染出来永远是 9px 的蚂蚁字。本地已复现：无字体环境下三档水印与线上一模一样。
- 字体发现重写为三级保障：① 扩充后的已知候选路径；② 运行时动态扫描系统字体目录（含用户字体目录，CJK 命名字体优先）；③ **仓库自带开源中文字体** `fonts/wqy-microhei.ttc`（文泉驿微米黑，Apache-2.0，随代码部署，零系统依赖）。
- 兜底路径也修正：即使三级全空，`load_default(font_size)` 也按档位缩放（Pillow 10.1+，旧版自动回退）。
- 验证：修复前裸系统三档实际字高 9/9/9；修复后 19/37/55，自带字体下英文/中文、横图/竖图/小图共 5 组场景三档全部正确递增。
- **线上生效方式**：部署后到后台设置页重新保存一次水印设置，历史图片会从 `.originals` 无痕原图全部重做（不会叠加旧水印）。

---

## [v1.3.47] - 2026-09-20

### 新增
- 图片水印可以自己选字号了。后台设置的「图片水印」卡片里多了个「水印大小」下拉：小（图宽 2%）/ 标准（图宽 3%）/ 大（图宽 4%）。之前水印字号写死在图宽 2%、还压了个 28px 的顶，横图上文字明显偏小；现在默认档位就改成了「标准」，不进设置页也能感觉到字大了一圈。之所以做成档位而不是让填像素，是因为同样的 28px 在 800px 小图和 1920px 大图上观感完全两回事，档位底下仍然按图宽缩放，所有尺寸的图观感一致。边距也跟着字号走，大字不会贴边。改完保存，历史图片照常走后台自动刷新。

### 优化
- 后台「文件清理」页（/admin/orphans）交互整个重做了一遍。这页列的是 uploads 里没被任何文章引用的孤儿文件，以前最大的问题是：文件大多是粘贴截图，名字是日期加哈希，根本认不出来谁是谁，只能一个个新窗口打开；而且进页面默认是只读列表，得自己摸到右上角的「批量操作」按钮才能删。
  - 图片行直接显示缩略图，桌面端鼠标悬缩略图弹出跟随鼠标的大图（自动避开窗口边缘），非图片显示扩展名方块（PDF/ZIP 之类）。
  - 进页面默认就是批量选择态，点行上任意位置就能勾选（链接除外，移动端不用再戳 16px 的小框框），选中的行整行浅蓝高亮。
  - 加了文件名即时搜索、「全部 / 图片 / 其他」类型切换，文件/大小/上传时间三栏点表头就能排序，再点一次换升降序；筛选时被隐藏的行会自动取消勾选，保证看到的就是要删的。
  - 批量条实时显示「已选 N 个 · 占 XX MB」，没选东西时删除按钮是灰的；删除改成 AJAX 提交，成功的行淡出移除、失败的行标红抖一下，顶部直接提示释放了多少空间，不用再整页刷新。全删完自动切成完成态。
- 删除接口保留了原来的表单提交流程，不发 AJAX 头时行为和以前完全一样，老的调用方式不受影响。

改动：`app.py`（VERSION、水印档位、删除接口 AJAX 支持）、`templates/admin/orphans.html`、`templates/admin/settings.html`、`static/css/admin.css`、`watermark_backfill.py`。

---

## [v1.3.46] - 2026-09-18

### 修复
- 给 SQLite 连接加上了 `busy_timeout=15000`（连接级，每条新连接都设）。之前多 worker 部署 + 服务监控线程同时写库时，写锁短暂碰撞会立刻抛 `database is locked`，高峰时偶发 500；现在 SQLite 会自动等待最长 15 秒再报错，把这种窗口期内的抖动消化掉。
- 加了 Flask 级请求体上限 32MB（`MAX_CONTENT_LENGTH`）。原来上传只靠 `_save_upload` 里的 20MB 检查兜底，但那是读 `Content-Length` 头——分块上传没有这个头就直接跳过检查了，超大文件能一路写进临时目录和 uploads。现在超限在解析阶段就被拒（413），贴地保护磁盘和内存。
- 两处内存缓存加了上限，防止跑久了内存悄悄涨上去：
  - IP 归属地缓存（`_IP_LOC_CACHE`）最多留 2000 条，超了淘汰最早一条。评论 IP 少的时候没感觉，但长年累月跑不清理迟早堆积。
  - 登录失败记录（`_LOGIN_ATTEMPTS`）在每次记录失败前清理：解锁超过 1 天的直接删，总量超 2000（异常爆破 flood）整表重置。

改动：`app.py`（VERSION、`get_db()` busy_timeout、`MAX_CONTENT_LENGTH`、IP 归属地与登录失败缓存清理）。

---

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
