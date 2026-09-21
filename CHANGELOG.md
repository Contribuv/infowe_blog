# 变更日志

本项目所有重要变更都记录在此文件，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [v1.3.56] - 2026-09-21

### 安全修复
- **硬编码 Secret Key 漏洞**：移除源码中的默认 `infowe-blog-secret-key-2024`，未设置 `BLOG_SECRET_KEY` 时自动生成随机密钥并持久化到 `data/.secret_key`（权限 600），重启后 session 不失效
- **默认管理员密码漏洞**：首次初始化不再使用 `admin123`，改为 `secrets.token_hex` 随机生成 16 位密码，打印到启动日志并同步写入 `data/.initial_admin_password`（权限 600，宝塔文件管理器可直接查看；仅 users 表为空时创建，多 worker 并发首启由触发器兜底），后台改密或忘记密码重置成功后自动删除该文件，日志同步提示首次登录后立即修改
- **密码修改无旧密码验证**：后台设置页修改密码需先输入旧密码并通过 `verify_password` 校验后才允许修改
- **管理员用户名格式校验**：修改管理员用户名时添加正则校验 `^[a-zA-Z0-9_\u4e00-\u9fff-]{2,30}$`，防止恶意用户名
- **登录防爆破内存泄漏**：`_VIEW_COOLDOWN` 和 `_COMMENT_COOLDOWN` 字典添加定期清理机制和最大条目限制，防止长时间运行后内存无限增长

### 功能修复
- **IP 归属地查询逻辑**：修复 `_ip_location` 中 `ip.startswith('127.')` 的粗粒度判断，改用 `ipaddress` 模块精确检测 loopback/private/link-local 地址，避免 `127.0.0.x` 网段误判
- **评论 SQL 结构**：修复 `db_load_comments` 中 SQL 字符串拼接的括号闭合问题，改为安全的 SQL 构造模式，避免后续编辑引入语法错误
- **水印批量重做遗漏根目录**：`_wm_redo_all` 中 `if root == UPLOAD_DIR: continue` 导致 `uploads/` 根目录文件永远不被加水印，已移除该跳过逻辑
- **评论限流清理**：`_COMMENT_COOLDOWN` 在每次评论提交时添加过期条目清理

### 安全加固
- **安全响应头**：`@app.after_request` 统一设置 `X-Content-Type-Options`、`X-Frame-Options`、`X-XSS-Protection`、`Referrer-Policy`、`Content-Security-Policy`（CSP 放行内联脚本与 https 外链脚本——本站模板内联脚本是既定形态且后台统计代码需注入外域脚本；保留 object-src 'none' / base-uri / frame-ancestors 实质防护），HTTPS 下自动添加 `Strict-Transport-Security`
- **Session Cookie 安全**：设置 `SESSION_COOKIE_SAMESITE=Lax`、`SESSION_COOKIE_HTTPONLY=True`，非调试模式启用 `SESSION_COOKIE_SECURE`，`PERMANENT_SESSION_LIFETIME=3600`
- **统计代码 XSS 防护**：`stats_code` 在保存和注入前台前双重消毒（`_sanitize_stats_code`），仅保留 `<script>` 标签，剥离所有事件属性和 `javascript:` 协议
- **Markdown `javascript:` 链接过滤**：`render_post_content` 的 `_a_repl` 新增 `javascript:` 协议检测并添加 `rel="noopener noreferrer"`
- **HTML 消毒增强**：`_sanitize_html` 增加 `svg`、`form`、`data:text/html` 过滤
- **SSRF 防护**：`_clean_monitor_url` 添加内网 IP 检测，禁止 `127.0.0.1`、`192.168.x.x`、`169.254.169.254` 等内网地址作为监控 URL
- **Secret Key 文件权限**：`data/.secret_key` 创建时设置 `chmod 0o600`

### 部署修复
- **requirements.txt 补充 gunicorn**：添加 `gunicorn>=21.0.0`，确保 `pip install -r requirements.txt` 后包含生产 WSGI 服务器
- **Cookie 过期时间**：`blog_commenter` Cookie `max_age` 从 1 年缩短为 30 天

## [v1.3.55] - 2026-09-21

### 修复
- **后台登录族页面移动端可被缩放**：`/admin/login`、`/admin/otp`、`/admin/otp/recover`、`/admin/forgot` 为不继承 base.html 的独立页面，viewport 缺少 `maximum-scale=1.0, user-scalable=no`（iPhone 双击/捏合可放大）——补齐为与 admin/base.html 完全一致的禁缩放配置，并统一 `viewport-fit=cover` 刘海屏安全区

## [v1.3.54] - 2026-09-21

### 新增
- **文章页公众号式排版（tech 主题）**：移动端（≤767px，平板/手机/桌面窄窗预览统一生效）采用 16px 字号、1.6 行高、24px 段距、两端对齐的「内紧外松」节奏；含 `<br>` 的段落自动排除两端对齐（`:not(:has(br))`），杜绝短行字距被拉伸（如「文档整理日期」元信息段）
- **正文标题字号体系重建**：桌面梯度 h1 26 / h2 22 / h3 19 / h4 17 / h5 16.5 / h6 16（正文 15.5px），移动 23 / 20 / 18 / 17 / 16.5 / 16（正文 16px），标题字重 700 压过 strong 600——修复 h4 与正文仅差 0.5px、h5/h6 被通用 markdown 样式压得比正文还小、标题与加粗同字重导致的层级倒挂

### 修复
- **正文参数被 markdown-body.css 加载顺序覆盖**：文章容器叠加的通用 markdown 样式在主题样式之后加载，同特异性下把字号/行高/段距盖回旧值——改用复合选择器（`.tech-post-body.markdown-body` / `.post-content.markdown-body`）提升优先级，与加载顺序解耦，评论区等短文本渲染不受影响
- **移动排版断点错位**：公众号排版块此前挂在 ≤480px，与主题主移动断点（767px）不一致，平板及桌面窄窗预览完全看不到移动排版——统一至 767px
- **代码块两端对齐残留**：pre 恢复左对齐（防 justify 拉伸折行代码空格），行距 1.6 → 1.5（ASCII 架构图更紧凑）
- 代码块复制按钮 text-align 归位、正文 p 间距随段距体系调整（桌面 20px / 移动 24px）

### 调整
- **全主题字号协调（tech）**：列表卡标题 20 → 18、项目卡名 17 → 18、友链名 15 → 16，与相关文章标题（18）统一为条目标题一族；文章内表格字号统一 inherit 跟随正文（清除 14px 死代码）；默认主题文章正文同步去除两端对齐并统一行高段距
- 保留的差异化设计：首页 Hero 大字（宽屏展示区）、关于页头像名（降级设计）、输入框 16px（防 iOS 聚焦缩放）

## [v1.3.53] - 2026-09-21

### 新增
- **分享卡片图：文章首图自动成为 og:image**（微信朋友圈 / Twitter 等）。图片优先级：文章封面 > 正文第一张本站图 > 默认站图；此前仅封面文章有独立卡片图，未设封面（大多数）一律用默认图
- **/share-thumb/ 4:3 缩略图路由**：uploads 图片按需生成 800×600 居中裁切 JPEG（约 100KB，源图常为 3~8MB 手机直出），首次访问懒生成 + 磁盘缓存（data/share_thumbs/，避开孤儿清理），源图更新自动失效重生成，响应带 Cache-Control 供爬虫缓存；生成失败自动回退原图；隐藏目录（.originals 无痕原图）与路径穿越同样被拒绝
- **正文首图 img 增强**：注入真实 width/height（此前无尺寸属性，微信等爬虫可能跳过无尺寸图）且不加 loading="lazy"，其余图片保持懒加载
- 默认分享图 og-image.png 重制为 4:3（1200×900，此前 1200×630 与微信卡片比例不符），品牌同步为 infowe.site

### 调整
- twitter:card 由 summary_large_image 改为 summary（方卡，4:3 图裁切最小；og:image 与 twitter:image 同源）

## [v1.3.52] - 2026-09-20

### 新增
- **系统升级双源检测**：新增 Gitee 镜像仓库 `infowe/infowe_blog` 作为回退源。版本检测优先 GitHub Releases，超时/限流/不可达时自动切换 Gitee API（6 秒超时，10 分钟结果缓存不变）；升级包下载链路扩展为「GitHub 直连 → 加速镜像 → Gitee 归档包」，任一环节失败自动降级。检测成功时升级卡片显示来源（GitHub / Gitee 镜像），查看按钮文案随来源变化
- **tag 规范化防御**：Gitee 建发行版时易把标题填进标签名（如 `v1.3.51：安全加固`），双源检测统一从 tag_name 解析出语义版本并重构规范 tag，保证下载 URL 始终有效；脏 tag 不再影响升级链路
- `UPGRADE_GITEE_REPO` 环境变量可覆盖 Gitee 仓库地址

### 说明
- Gitee 仓库需与 GitHub 保持同步（发版后在 Gitee「管理 → 强制同步」或本地 `git push` 双远端），且发行版标签名须为规范 `vX.Y.Z` 格式，否则归档包 404

## [v1.3.51] - 2026-09-20

### 新增
- **单管理员硬保证（数据库层）**：本博客仅支持 1 个管理员账号。schema_version=3 迁移自动清理多账号（保留最早创建的 liuhao，删除 admin 等）；创建 SQLite 触发器 `users_single_admin_guard` 拦截一切 users 表 INSERT——任何代码 bug 或手工插库都会被数据库直接拒绝。init_db 默认账号改为仅表空时创建
- **OTP 邮箱找回后直接进入重绑流程**：验证通过登录后台后，302 直达设置页「安全验证」卡片（`#otp-card` 锚点 + `otp_rebind=1` 参数），前端自动勾选开关展开绑定区并生成新密钥二维码，扫码确认即可完成重绑；不想要 OTP 则保持关闭即可

### 修复
- 水印中文在 Linux 服务器渲染为方块：字体候选中预装率极高的西文字体 DejaVu 排在自带中文字体之前，服务器首轮命中后中文全部缺字。修复：仓库自带的 fonts/wqy-microhei.ttc（文泉驿微米黑，Apache-2.0）提升为首选，全平台水印字体一致；系统目录扫描仅接受 CJK 命名字体，杜绝再命中西文字体
- init_db 默认管理员 INSERT 语句含不存在的 created_at 列，全新环境首次启动会崩溃（存量环境因旧表结构未受影响）
- 忘记密码找回简化为唯一管理员：无需输入账号名，页面直接显示账号（users 表已由触发器保证单条）

---

## [v1.3.50] - 2026-09-20

### 新增
- **登录页「忘记密码」找回功能**。登录页新增「忘记密码？」入口（/admin/forgot，无需登录），三步流程：输入账号名 → 绑定邮箱收 6 位验证码 → 设置新密码。
  - 验证码发往后台设置的 notify_email / contact_email（页面显示掩码），10 分钟有效，60 秒重发限频，与 OTP 找回同一套邮件模板风格。
  - 重置精确锁定到发码时校验过的账号（users 表可有多账号，不会误改他人密码）。
  - 未配置 SMTP 时显示替代方案提示；验证码错误与不存在账号均计入登录防爆破（递增延迟 + 锁定），拖慢探测。

### 修复
- 设置页全局开关行（switch-label）与文字垂直偏差 2px：开关中心与首行文字中心精确重合。
- 卡片内设置组间距过紧：组间 12→20px；「label + 开关行」6→10px；纯开关行（OTP / SMTP 通知）上下各加 4px 呼吸空间。
- /admin/otp 与 /admin/otp/recover PC 端卡片靠左：新增单栏变体 login-shell--single，卡片水平 + 垂直屏幕居中（此前误用登录页双列 grid，卡片落入左列）。
- 设置页「账号安全」分组重构：管理员 + 安全验证两卡紧贴成组（card-group 容器参与双栏瀑布流防劈裂，组内合并圆角），安全验证卡从第 8 位移到管理员卡正下方。
- OTP 二维码容器深浅主题适配：容器跟随主题（不再固定白底），白底仅保留在二维码图片区域内，深色主题下与界面一致。
- OTP 验证码容器 display block→flex，修复容器内元素居中与间距失效。

---

## [v1.3.49] - 2026-09-20

### 新增
- **后台 OTP 双重验证（TOTP，RFC 6238 零依赖实现）**。后台设置新增「安全验证」卡片：开启后登录 /admin 需要在账号密码通过后再输入一步 6 位动态验证码，密码泄露也无法直接进入后台。
  - 标准算法（HMAC-SHA1 / 6 位 / 30 秒步长），与 Google Authenticator / Microsoft Authenticator / 1Password / Authy 等通用验证器 App 兼容。
  - 首次开启必须「生成二维码 → 扫码（或手动输入密钥）→ 输入当前验证码」绑定成功后才生效，防止误开把自己锁在门外。
  - 开启同时自动生成 10 个一次性恢复码（只存 SHA-256 哈希，明文仅展示这一次，可下载 txt），用于验证器丢失时登录；每个恢复码只能用一次，用后即从库中移除。
  - 已开启后可随时「重新绑定」换新密钥 + 新恢复码；也可直接关闭此功能。
- **OTP 丢失找回三级保障**：
  1. 恢复码登录（验证码 / 恢复码通用输入框，剩余数量实时提示）；
  2. 邮箱找回：配置了 SMTP 时，向 notify_email / contact_email 发 6 位一次性验证码，验证通过后自动重置 OTP 并引导重新绑定（60 秒重发限制、10 分钟有效）；
  3. 服务器兜底：部署者可在服务器执行 `touch data/.otp_disable` 临时跳过 OTP 验证（防止彻底锁死），登录后设置页提示「清除标记」恢复保护。
- OTP 失败也接入已有登录防爆破（递增延迟 + 15 分钟锁定 + 验证码），拖慢暴力破解。

改动：`app.py`（VERSION、TOTP 工具函数、登录第二因子、找回路由、设置页保存逻辑）、`templates/admin/settings.html`（安全验证卡片 + 恢复码下载）、新建 `templates/admin/otp.html`、`templates/admin/otp_recover.html`。

---

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
