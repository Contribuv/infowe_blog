# infowe Blog

一个基于 **Flask** 的轻量级个人技术博客，支持 Markdown 写作、文章分类、评论、友情链接、GitHub 项目展示、时间线等。前端为服务端渲染（Jinja2 模板 + 原生 CSS/JS），数据使用 **SQLite** 存储，零外部服务依赖，开箱即用。

## 功能特性

- 文章发布（Markdown）、分类、标签、精选、阅读时长
- 前台：首页、文章详情、分类/标签筛选、搜索、分页、关于页、时间线
- 后台：文章管理、设置、友情链接、项目（GitHub）管理、评论管理
- 评论系统（可开关）
- 友情链接申请与审核
- GitHub 项目页抓取与展示
- 登录防爆破（基于 IP 的失败计数 + 验证码）

## 目录结构

```
blog/
├── app.py                  # 主应用（Flask 入口、路由、DB 初始化）
├── requirements.txt        # Python 依赖
├── gunicorn.conf.py        # 生产 WSGI 服务器配置
├── gunicorn_conf.py        # 另一份 gunicorn 配置样例（宝塔风格）
├── blog.service            # systemd 服务单元样例
├── deploy_infowe.site.conf # Nginx 反代配置样例
├── DEPLOY.md               # 详细部署文档
├── data/                   # 数据库与数据（blog.db、posts.json）
├── posts/                  # Markdown 文章源文件
├── static/                 # 静态资源（CSS / JS / 图片）
└── templates/              # Jinja2 模板
```

## 环境要求

- Python 3.8+
- 依赖：`flask`、`markdown`、`Pillow`、`pillow-heif`（详见 `requirements.txt`）

## 快速开始（本地开发）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动（Windows / 本地开发）
python app.py
```

启动后访问 http://127.0.0.1:5000 ，后台地址 http://127.0.0.1:5000/admin/login 。

### 数据库会自动创建

首次启动时 `app.py` 中的 `init_db()` 会在 `data/blog.db` 自动建库建表（前提是 `data/` 目录存在）。**无需手动创建数据库**。

### 默认管理员账号

> 仅当 `users` 表中不存在 `admin` 时自动创建。

- 用户名：`admin`
- 密码：`admin123`

⚠️ 这是弱密码，**首次登录后请务必到后台「设置」中修改账号名与密码**。

## 后台管理

登录后台 `/admin/login` 后可：

- 发布 / 编辑 / 删除文章
- 修改站点设置、关于页、技能等
- 管理友情链接、GitHub 项目、时间线、评论
- **修改管理员账号名与密码**（在「设置」页）

> 注意：后台修改账号名是对原记录执行 `UPDATE`（改名，不新增），修改后原 `admin` 用户名将不可用，需用新用户名登录。密码需 ≥ 6 位。

## 生产部署

生产环境使用 **Nginx + gunicorn**，完整步骤见 [DEPLOY.md](./DEPLOY.md)。

要点：

1. 安装依赖并安装 `gunicorn`。
2. **务必设置环境变量 `BLOG_SECRET_KEY`** 为强随机串，否则会 fallback 到源码默认值（存在 session 伪造风险）。
3. 用 `gunicorn -c gunicorn.conf.py app:app` 启动，并通过 `blog.service`（systemd）守护。
4. 配置 `deploy_infowe.site.conf`（Nginx 反代 + 可选 HTTPS）。

```bash
# 生成强随机密钥
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## 常用命令

```bash
# 本地开发
python app.py

# 生产启动（gunicorn）
gunicorn -c gunicorn.conf.py app:app

# systemd 重启（修改代码后生效）
sudo systemctl restart blog
```

## 注意事项

- `data/` 目录需存在，`sqlite3.connect` 不会自动创建父目录。
- 若 `data/posts.json` 存在且数据库为空，首次启动会自动迁移其中的文章。
- 评论、上传等文件保存在根目录 `uploads/` 下。

## 版本更新日志

### v1.1.7

- **文章浏览计数**：文章详情页显示「N 次浏览」。精准统计：页面可见且累计停留满 5 秒才计一次（秒开秒关、切后台不计）；同一会话刷新不重复计数（sessionStorage）；服务端对同一 IP 同一文章 60 秒窗口兜底防刷
- **文章分类展示**：文章详情页 `post-header-meta` 显示分类（排序：日期 · 分类 · 阅读时长 · 浏览数）；首页文章卡片同步显示分类；新增 `.card-category` 样式，分类图标与文字垂直居中对齐

### v1.1.6

- **文章标签自动添加**：编辑/创建文章时，输入正文与标题后自动识别候选标签；标签为空时自动将词频最高的 5-7 个标签填入（数量随机取 5-7，选词按词频优先）。识别按小写去重，不再出现 `Python`/`python` 大小写重复；自动添加后建议区自动过滤已选标签

### v1.1.5

- **修复升级页卡片间距与文本行距**：升级页 JS 检测结果卡片包裹在 `#upgrade-result` 容器内，原有间距规则（`.admin-main > .card`）匹配不上，导致结果卡片与「升级说明」卡片紧贴、说明文本上下无行距。已为容器内卡片补齐间距规则
- **静态资源版本号动态化**：`admin.css` / `admin.js` / `style.css` / `main.js` 的缓存版本参数由固定日期改为跟随应用版本号（`t=v版本号`）。升级后版本号自动变化，浏览器自动拉取新资源，无需再手动改版本号

### v1.1.3

- **修复升级页转圈卡死**：此前后台每次请求都会同步请求 GitHub API 检测版本，网络受限时（DNS/TLS 阻塞）整个后台与升级页会长时间转圈。现改为**异步检测**：升级页立即渲染（毫秒级），由前端 JS 请求 `/admin/upgrade/check` 接口填充版本信息；后台其他页面仅读取缓存，不再主动联网

### v1.1.2

- **修复升级锁卡死**：升级过程异常中断（进程被杀/断电）会残留 `upgrade.lock` 导致永久提示"升级任务已在进行中"。现锁文件记录时间戳，超过 10 分钟自动视为过期并清理，可正常重试升级

### v1.1.1

- **修复文章链接丢失**：正文中的 Markdown 自动链接 `<https://...>` 在 Vditor 编辑器往返转换时会丢失（打开编辑页再保存 URL 即消失）。现已在编辑页加载、保存、渲染三层统一规范化为标准链接 `[URL](URL)`，编辑保存不再丢链接

### v1.1.0

- **文章编辑体验**：Slug 自动生成改为纯 ASCII（剔除中文），新增 Slug 实时预览；摘要支持从正文自动获取（保存时后端自动截取 + 编辑页「从正文自动获取」按钮）
- **标签自动识别增强**：标签库统计含草稿文章；正文高频英文术语自动提取为候选标签（如 fnos/oauth/websocket）；自动识别区与常用标签区扩容至 20 个
- **文章阅读体验**：正文超链接默认新窗口打开（页内 `#` 锚点除外）；标题自动生成锚点 ID，支持 `#12-章节名` 页内定位；任务列表 `[ ]`/`[x]` 渲染为勾选符号；正文排版优化（行高 1.85、标题层级清晰、表格/代码字号增大）
- **后台编辑页面板自适应彻底修复**：侧栏内容不超视口时固定跟随，超高时自动回退随页面滚动，任何分辨率/缩放均不裁剪
- **登录页品牌动态化**：表单品牌区显示博客名称，左侧品牌区显示首页标题（留空则用站点名）
- **换行符规范化**：新增 `.gitattributes` 统一 LF，消除 Windows 下 git diff/status 换行警告刷屏

### v1.0.9

- **修复 iOS 18 HEIC 上传失败**：iPhone（iOS 18 起）拍摄的 HEIC 元数据结构变化，内置 libheif < 1.18.2 的 pillow-heif（如 0.15.0 / libheif 1.17.6）解码时报 `Metadata not correctly assigned to image`。需将 pillow-heif 升级至 ≥ 0.18（内置 libheif ≥ 1.18.1，推荐 0.22.0 / libheif 1.19.7）
- **HEIC 诊断增强**：启动时打印 pillow_heif / libheif / Pillow 版本；解码失败时错误提示透出真实异常与版本号，便于定位（此前为笼统的"文件可能损坏"提示）

### v1.0.8

- **修复系统升级卡住**：升级包下载改为直连 GitHub 优先、连接失败/超时（60s）后自动降级镜像，避免部分网络环境直连 codeload 长时间挂起；镜像列表可用环境变量 `UPGRADE_MIRRORS` 配置（逗号分隔，设空串则纯直连）
- **修复 HEIC 上传误报**：`pillow_heif` 解码改为 `open_heif()` 直解码，不再依赖 Pillow 插件注册机制（解决已安装 pillow_heif 仍提示"缺少解码支持"的问题）；错误提示区分"未安装"与"解码失败"两种原因；头像上传同步支持 HEIC

### v1.0.7

- **上传目录迁移**：附件存储由 `static/uploads/` 迁至项目根目录 `uploads/`，新增 `/uploads/` 静态路由；服务器升级后启动时自动迁移旧文件并批量替换数据库中已存储的 `/static/uploads/` URL 为 `/uploads/`（幂等，重复启动安全）
- **修复上传严重 Bug**：修复 `_save_upload` 分支嵌套错误，此前非图片类文件（zip/pdf/mp4 等）上传后不会落盘却返回 URL，产生大量死链
- 升级保护目录新增根目录 `uploads/`；Nginx 配置样例新增 `/uploads` 静态 location（HTTP/HTTPS 两处）

### v1.0.6

- 新增 HEIC/HEIF 照片上传支持（iPhone 拍摄照片）：pillow-heif 解码后自动转 JPEG 压缩存储，覆盖文章编辑器与头像上传
- 修复后台 `/admin/posts/new` 编辑页右侧设置面板在部分分辨率下显示不全的问题：短视口回退阈值由 760px 提升至 900px，覆盖 1366×768 等常见笔记本分辨率

### v1.0.5

- 系统升级检测优化：成功检测缓存由 1 小时缩短至 10 分钟，避免新版发布后提示滞后
- 升级页新增「重新检测」按钮（强制跳过缓存重新查询 GitHub Releases）
- 首页 `/?tag=xxx` 与文章列表 `/posts?tag=xxx` 的 `<title>` 显示「标签 - 站点名称」

### v1.0.3

- 新建 / 编辑文章支持自定义发布日期（`datetime-local` 选择，留空默认当前时间）
- 编辑页标签自动识别（标题、正文） + 常用标签快捷点选，可手动补齐未识别标签
- 新增系统升级：后台检测 GitHub Releases 最新版本，可一键备份数据（数据库 + 上传文件）后下载覆盖代码升级，文章 / 分类 / 评论 / 设置等数据保留
- 后台侧边栏版本号改为链接至升级页，检测到新版本时仪表盘与侧边栏均有提示

### v1.0.2

- 文章详情页正文区域接入 `post-card` 卡片样式，与首页卡片风格统一、自适应更好看

### v1.0.1

- 后台仪表盘「友情链接」统计修正：仅计入已通过审核（`approved`）的链接，排除已拒绝/待审核项
- 后台侧边栏底部新增版本号显示（`infowe Blog v1.0.1`），并链接至开源仓库（新窗口打开）
- GitHub 同步支持 Token 认证 + certifi SSL 校验 + 精确错误提示
