# Python Blog（Flask + SQLite）

[![version](https://img.shields.io/badge/version-3.8.10-blue)](https://github.com/Contribuv/infowe_blog/releases/tag/v3.8.10)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

这是博客系统的 Python 版：前台用 Flask 服务端渲染，后台管理文章、评论、项目和设置，数据放在 SQLite 里。部署只需要 Python 和 Nginx，不需要额外的数据库服务。

如果你之前用过 PHP 版，文章、分类、标签、友链、项目这些结构基本都保留了下来；迁移工具也放在仓库里。

- GitHub：<https://github.com/Contribuv/infowe_blog>
- Gitee：<https://gitee.com/infowe/infowe_blog>

---

## 📚 目录

|  |  |  |
| --- | --- | --- |
| [✨ 功能特性](#功能特性) | [🧰 技术栈](#技术栈) | [✅ 环境要求](#环境要求) |
| [🚀 快速开始](#快速开始) | [📁 目录结构](#目录结构) | [🔗 URL 结构](#url-结构) |
| [🔐 后台入口](#后台入口) | [⚙️ 配置说明](#配置说明) | [🛠 宝塔面板部署](#宝塔面板部署) |
| [🧩 其他部署方式](#其他部署方式) | [📦 数据迁移](#数据迁移) | [⬆️ 升级与数据库结构](#升级与数据库结构) |
| [💾 备份与恢复](#备份与恢复) | [❓ 常见问题](#常见问题) | [🛡 安全建议](#安全建议) |
| [📝 更新日志](#更新日志) | [📄 License](#license) |  |

---

## 功能特性

### 前台

| 模块 | 说明 |
| --- | --- |
| 文章 | Markdown 写作、分类、标签、精选、阅读时长、访问计数、上下篇 |
| 文章状态 | `published` / `draft` / `hidden`（隐藏文章仅 URL 可直达） |
| 浏览 | 全文搜索、标签聚合、年份归档、分页 |
| 订阅 | `/feed.xml` RSS |
| 评论 | 嵌套回复、审核、私密评论、图片、敏感词、IP 归属地、UA 设备标识、新朋友/回头客/常客标签、分页、内嵌/浮窗双模式、草稿自动保存、跨页锚点直达 |
| 项目 | GitHub/Gitee 同步、语言占比、README 渲染与图片本地化、项目评论 |
| 友链 | 申请、审核、本站信息卡片 |
| 关于 | 简介、技能、时间线 |
| 状态 | 服务探活、可用率、证书天数、云资源到期 |
| 分享 | Open Graph、4:3 分享缩略图、二维码 |
| 页面过渡 | 轻量淡入淡出（约 140ms，无位移），不支持时回退为新页淡入，尊重系统「减弱动态效果」 |
| 首页一言 | 后台自定义文案，一行一条，支持出处；留空使用内置 36 条 |
| 性能 | 页面缓存、CSS 自动压缩、静态资源 7 天缓存、统计代码延迟加载 |

### 后台

- 仪表盘：文章/评论/项目/友链统计、待审核评论/友链申请提醒、最近更新
- 文章：新建、编辑、预览、删除、批量发布/草稿/隐藏
- 回收站：文章软删除，恢复、彻底删除、批量与一键清空
- 分类 / 标签 / 项目 / 友链 / 时间线 / 评论：增删改查与批量操作
- 插件：AI 助手、留存审计内置，后台启用/停用即时生效，无需重启
- 留存审计（插件）：后台操作记录、AI 审核记录、评论留存，日期/关键词筛选与 CSV 导出
- AI 助手：机器人昵称/头像自定义、评论 AI 审核、通过后 AI 回复，审核记录与徽章
- 邮件通知：评论/回复/AI 回复/友链申请 HTML 通知邮件（Outlook 兼容，正文展示真实内容，敏感词除外）
- 上传：图片 / 媒体 / 附件，白名单与大小限制，水印；HEIC/HEIF 自动转 WebP
- 孤儿文件清理：扫描未被引用的上传文件
- 主题切换
- 设置：站点信息、导航、评论、SMTP、水印、敏感词、统计代码、上传限制
- 状态监控：HTTP(S) 探活、历史采样
- 数据：SQLite 备份、JSON/Markdown 导出、SQLite 导入
- 安全：登录防爆破、图片验证码、TOTP 双重验证、邮箱找回密码

### 安全

- 单管理员约束、PBKDF2 密码
- 登录失败计数、递增延迟、5 分钟锁定
- OTP（RFC 6238）与一次性恢复码
- CSRF 同源校验、安全响应头、CSP
- 上传扩展名白名单 + 危险扩展名黑名单
- Markdown 链接协议过滤、统计代码消毒
- 上传/主题/备份路径穿越防护

---

## 技术栈

| 层 | 选型 |
| --- | --- |
| Web | Flask 3.x（应用工厂 + Blueprint 风格路由模块） |
| 数据库 | SQLite（WAL） |
| 模板 | Jinja2 |
| Markdown | `markdown`（表格、代码块、目录、脚注、details） |
| 图片 | Pillow + pillow-heif（水印、分享图、头像裁剪、HEIC/HEIF 转 WebP） |
| CSS | csscompressor（theme.min.css 自动生成） |
| HTTP | requests（GitHub 同步、状态探测、头像/README 图） |
| 生产 | gunicorn / uWSGI + Nginx |

---

## 环境要求

- Python **3.10+**（推荐 3.12）
- SQLite **3.35+**（低于该版本可运行，但自动删除字段会跳过）
- 可选：Nginx、gunicorn 或 uWSGI

---

## 快速开始

### 1. 获取代码

```bash
git clone https://gitee.com/infowe/infowe_blog.git
# 或
git clone https://github.com/Contribuv/infowe_blog.git
cd infowe_blog
```

也可以直接下载压缩包解压。

### 2. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 启动

```bash
python app.py
```

Windows 可直接双击 `run.bat`。

访问 <http://127.0.0.1:5000>。

### 4. 首次启动自动完成

| 项目 | 内容 |
| --- | --- |
| 数据库 | `var/blog.db`（自动建表） |
| 管理员 | `admin` / `admin123` |
| 示例分类 | 随笔 |
| 示例文章 | 《致使用者的一封信》 |

> ⚠️ 默认密码只用于首次登录，请立即在「博客设置 → 账号安全」修改。
> 如果使用已有数据库，则不会覆盖管理员和文章。

---

## 目录结构

```
.
├── app.py                 # 应用工厂、启动入口、CLI 命令
├── config.py              # 路径、版本、上传限制、导航与保留路径
├── db.py                  # SQLite 连接、schema 自动同步
├── schema.sql             # 数据库表结构（唯一基准）
├── models/                # 数据模型：文章/分类/评论/项目/友链/时间线/用户
├── services/              # 业务服务：认证/OTP/Markdown/上传/备份/同步/状态
├── routes/                # 路由：前台/后台/认证/静态资源/API
├── plugins/               # 插件：AI 助手、留存审计（自带路由/模板/静态资源）
├── templates/
│   ├── admin/             # 后台模板
│   └── shared/            # 公共模板片段
├── static/                # 后台 CSS/JS、Vditor、highlight.js、图标
├── themes/tech/           # 前台主题（模板 + 静态资源 + 元数据，单目录自包含）
│   ├── templates/         # base.html、index.html、post.html ...
│   ├── static/            # theme.css / theme.min.css / theme.js
│   ├── info.json          # 主题名称/作者/版本
│   └── preview.png        # 后台主题页预览图
├── var/                   # 运行时数据（可用 BLOG_DATA_DIR 指到项目外）
│   ├── blog.db            # SQLite 数据库、密钥、同步/升级状态
│   ├── uploads/           # 文章图片、评论图片、README 图片
│   ├── backups/           # 数据库备份、JSON/Markdown 导出
│   └── storage/cache/     # 运行缓存（头像/分享图/README 图/页面缓存）
├── fonts/                 # 水印字体
├── tools/                 # 数据迁移脚本
├── run.bat                # Windows 一键启动
└── requirements.txt
```

### 各目录职责

| 目录 | 作用 | 是否可删 |
| --- | --- | --- |
| `var/blog.db` | 数据库、密钥、同步状态 | **不可删**（删了等于重置站点） |
| `var/uploads/` | 用户上传文件 | 不可删（文章图片会失效） |
| `var/backups/` | 备份与导出文件 | 可按需清理旧备份 |
| `var/storage/cache/` | 运行缓存 | 可删，会自动重建 |
| `static/` | 后台与编辑器资源 | 不可删 |
| `themes/` | 前台主题（`templates/` + `static/` + `info.json` + `preview.png`） | 不可删 |
| `templates/` | 后台与公共模板（前台主题模板在 `themes/<key>/templates/`） | 不可删 |
| `fonts/` | 水印字体 | 不启用水印时可删 |
| `tools/` | 迁移工具 | 可删（不再迁移时） |

> `var/` 不要暴露为静态目录，本项目已通过路由限制访问；生产环境建议用 `BLOG_DATA_DIR` 把它放到 Web 根之外。
>
> 生产示例：`export BLOG_DATA_DIR=/var/lib/infowe_blog`，同时把 Nginx 的 `/uploads/` alias 指到该目录。
>
> 从旧版本升级时，根目录的 `data/`、`uploads/`、`backups/`、`storage/` 以及更早的 `instance/` 会在首次启动时
> 自动合并进 `var/`，不需要手动搬；重名文件不会被覆盖，统一保留在 `var/.legacy-<时间戳>/`。
> `theme.min.css` 由 `theme.css` 自动生成；修改主题源文件后首次访问会重新压缩。目录不可写或缺少 `csscompressor` 时自动回退到 `theme.css`。

---

## URL 结构

| 页面 | URL |
| --- | --- |
| 首页 | `/` |
| 文章列表 | `/posts` |
| 文章详情 | `/post/<id>` |
| 标签 | `/tag/<标签>` |
| 搜索 | `/search/<关键词>` |
| 年份归档 | `/archive/<年份>` |
| 项目 | `/projects`、`/projects/<id>` |
| 友链 | `/links`、`/links/apply` |
| 关于 | `/about` |
| 状态 | `/status`、`/api/status` |
| RSS | `/feed.xml` |
| 后台 | `/admin` |

旧参数形式（`/?tag=`、`/?q=`、`/posts?year=`）会 301 到新地址。

---

## 后台入口

默认：`/admin`

可在「博客设置 → 账号安全 → 后台入口路径」改成自定义路径，例如：

```
/manage-2026
```

修改后需要**重启服务**；旧 `/admin` 会返回 404。

如果改错或忘记，可在项目目录执行：

```bash
python -c "from app import app; from services import settings; c=app.app_context(); c.push(); settings.set_value('admin_path','admin')"
```

---

## 配置说明

后台「博客设置」里集中管理站点信息、导航、评论、SMTP、水印、敏感词、统计代码和上传限制。

| 分组 | 内容 |
| --- | --- |
| 站点信息 | 站名、副标题、作者、简介、技能、GitHub、联系邮箱 |
| 首页一言 | 一行一条，`文本\|出处`；留空使用内置文案 |
| 导航菜单 | 文章/标签/项目/友链/关于/状态 开关 |
| 评论 | 总开关、单页条数、后台列表条数、邮件通知、评论图片、敏感词 |
| 上传 | 图片/媒体/附件白名单、单文件大小、水印、HEIC/HEIF 自动转 WebP |
| 邮件 | SMTP 服务器、端口、账号、通知收件人、测试发送 |
| 账号安全 | 用户名、密码、OTP、后台入口路径 |
| 站点地址 | `site_url`、强制 HTTPS、同主域 www 归一 |
| 统计代码 | 只保留 `<script>`，剥离事件属性与 `javascript:` |
| 服务状态 | 监控服务列表、云资源到期日期 |

> 统计代码会在页面 `load` 之后通过 `requestIdleCallback` 执行，不再阻塞首屏和 `load` 事件。

---

## 宝塔面板部署

以下以站点目录 `/www/wwwroot/infowe.site` 为例。

### 1. 安装环境

宝塔 → 软件商店：

- 安装 **Python 项目管理器**（或使用系统的 Python 3.10+）
- 安装 **Nginx**

### 2. 拉取代码

```bash
cd /www/wwwroot
git clone https://gitee.com/infowe/infowe_blog.git infowe.site
cd infowe.site
```

### 3. 创建虚拟环境并安装依赖

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

如果用 uWSGI，还需要：

```bash
.venv/bin/pip install uwsgi
```

如果用 gunicorn：

```bash
.venv/bin/pip install gunicorn
```

### 4. 初始化

首次启动会自动创建数据库、管理员和示例文章，无需手动执行。

如需自定义管理员（仅空库有效）：

```bash
.venv/bin/python -m flask --app app create-admin --username admin
```

### 5. 在宝塔添加 Python 项目

宝塔 → **Python 项目管理器 → 添加项目**：

| 配置 | 值 |
| --- | --- |
| 项目名称 | infowe |
| 项目路径 | `/www/wwwroot/infowe.site` |
| Python 版本 | 3.10+ |
| 启动方式 | uWSGI 或 gunicorn |
| 启动文件 | `app.py` |
| 端口 | `5000` |
| 运行用户 | `www` |

#### uWSGI 配置示例

`uwsgi.ini`：

```ini
[uwsgi]
chdir = /www/wwwroot/infowe.site
module = app:app
master = true
processes = 2
threads = 2
http = 127.0.0.1:5000
venv = /www/wwwroot/infowe.site/.venv
vacuum = true
die-on-term = true
```

> 端口必须是 `127.0.0.1:5000`，不要用 `0.0.0.0:5000`，避免绕过 Nginx/HTTPS。

#### gunicorn 启动命令

```bash
/www/wwwroot/infowe.site/.venv/bin/gunicorn \
  -w 2 -b 127.0.0.1:5000 --timeout 120 app:app
```

启动后验证：

```bash
curl -I http://127.0.0.1:5000/
```

应返回 `200 OK`。

### 6. 域名与反向代理

宝塔「Python 项目」添加后，通常会自动创建站点和反向代理，把域名转到 `127.0.0.1:5000`。新装环境一般不需要再手工改 Nginx。

- **伪静态保持为空**，不要选 WordPress / ThinkPHP 模板，也不要在里面写 `location /`、`proxy_pass`、`try_files`
- 不需要 `rewrite`，文章、标签、搜索、归档、后台入口都由 Flask 自己处理
- 80 和 443 都要能访问；宝塔会自动给 443 配反代
- 访问出现 403 时，先检查站点的反向代理是不是指向 `http://127.0.0.1:5000`，不要先去改伪静态

如果宝塔没有自动生成反代，或者你是手动部署，只需要这一段：

```nginx
location / {
    proxy_pass http://127.0.0.1:5000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header X-Forwarded-Port $server_port;
    proxy_read_timeout 120s;
    client_max_body_size 64m;
}
```

> 静态资源交给 Flask 也能正常访问；访问量上来后再考虑让 Nginx 直接托管 `static/`、`themes/`、`uploads/`。

### 6.1 页面缓存（已内置）

项目已内置应用层页面缓存，不需要额外 Nginx 模块：

- 存储：`var/storage/cache/pages/`
- 只缓存匿名 GET 的 HTML / RSS
- 管理员、提交过评论的访客（`blog_commenter` cookie）自动绕过
- 默认 TTL：
  - 首页、列表：5 分钟
  - 文章、归档、关于：30 分钟
  - 标签、项目、友链、RSS：10 分钟
  - 状态页：1 分钟
- 响应头 `X-Cache: HIT/MISS`，便于确认命中
- 后台保存文章/分类/项目/友链/时间线/评论/设置/主题，或导入数据后，**自动清空页面缓存**
- 访客提交评论只清除对应文章页/项目页，审核通过后再次清除
- 后台「数据管理 → 清除页面缓存」可手动清空

后台自定义入口 `admin_path` 不需要改 Nginx，项目内部路由会自动生成。

> 如果以后访问量更大，可以再加 Nginx `proxy_cache` 或 CDN 作为一级缓存，配置见 6.2；
> 加之前先确认能接受“页面更新延迟”，并配好 bypass 和清理。

### 6.2 可选：Nginx proxy_cache（高流量）

项目自带应用层页面缓存，大多数博客不需要再加 Nginx 缓存。只有访问量上来、Flask 进程顶不住时再用。两层缓存会叠加延迟，必须配 bypass 和清理，否则会出现“发了文章或评论，页面还是旧的”。

**1. 开启缓存区（http 级）**

`proxy_cache_path` 只能写在 `http {}` 里，不能写进站点的 `server {}`。

```bash
mkdir -p /www/server/nginx/cache
chown -R www:www /www/server/nginx/cache
chmod 700 /www/server/nginx/cache
```

> 如果 `ps -o user= -C nginx` 显示的不是 `www`，把上面的用户换成实际运行用户。

在 `/www/server/nginx/conf/nginx.conf` 的 `http {}` 内加一行（宝塔 → 软件商店 → Nginx → 配置修改）：

```nginx
proxy_cache_path /www/server/nginx/cache levels=1:2 keys_zone=blog_cache:20m max_size=2g inactive=10m use_temp_path=off;
```

**2. 站点配置**

把原来的 `location /` 换成：

```nginx
location / {
    proxy_pass http://127.0.0.1:5000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_read_timeout 120s;
    client_max_body_size 64m;

    # 默认不跳过缓存
    set $blog_skip_cache 0;

    # 非 GET / HEAD 不缓存（表单、上传、评论提交）
    if ($request_method !~ ^(GET|HEAD)$) { set $blog_skip_cache 1; }

    # 后台、登录、接口、评论、动态图片不缓存
    # 注意：不要写 upload，否则 /uploads/ 图片也会命中，变成 BYPASS
    if ($request_uri ~* "^/(admin|login|logout|api|comments|share-thumb|avatar|readme-img|status)(/|$|\?)") { set $blog_skip_cache 1; }

    # 管理员 / 评论者带 Cookie 时直接回源，避免看到别人的缓存
    if ($http_cookie ~* "(^|;\s*)(session|blog_commenter)=") { set $blog_skip_cache 1; }

    # 手动绕过：?nocache=1
    if ($arg_nocache) { set $blog_skip_cache 1; }

    proxy_cache blog_cache;
    proxy_cache_key "$host$uri$is_args$args";
    proxy_cache_valid 200 301 302 5m;
    proxy_cache_valid 404 1m;
    proxy_cache_bypass $blog_skip_cache;
    # 带 Set-Cookie 的响应不写入缓存，避免会话串给其他访客
    proxy_no_cache $blog_skip_cache $upstream_http_set_cookie;
    proxy_cache_lock on;
    proxy_cache_lock_timeout 5s;
    proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
    proxy_cache_background_update on;
}
```

如果想看 Nginx 这一层有没有命中，在 `server {}` 里加（不要放进 `location`，否则会覆盖 server 级其他 `add_header`）：

```nginx
add_header X-Nginx-Cache $upstream_cache_status always;
```

验证：

```bash
for i in 1 2; do
  curl -sS -o /dev/null -D - https://www.infowe.site/ | grep -i x-nginx-cache
done
```

第一次 `X-Nginx-Cache: MISS`，第二次 `HIT`。应用自己的 `X-Cache` 仍然表示 Flask 缓存状态，两个都看。

**3. 图片 / CSS / JS 也走 proxy_cache**

不要再给 `/static/`、`/themes/`、`/uploads/` 配 `alias`。`alias` 或 `^~` 会让 Nginx 直接读文件，绕过 `proxy_cache`，`X-Nginx-Cache` 就不会出现 `MISS/HIT`。

把下面两个 deny 和静态资源 location 加到站点配置里（放在 `location /` 前后都行，但两个 deny 必须在静态正则前面）：

```nginx
# 模板源码和上传目录隐藏文件先 deny
location ~ ^/themes/[^/]+/templates/ {
    deny all;
    return 404;
}

location ~ ^/uploads/\. {
    deny all;
}

# 图片 / CSS / JS / 字体：统一走 Nginx 缓存 7 天
location ~* \.(css|js|png|jpe?g|gif|webp|avif|svg|ico|woff2?|ttf|otf)$ {
    proxy_pass http://127.0.0.1:5000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_cache blog_cache;
    proxy_cache_key "$host$uri$is_args$args";
    proxy_cache_valid 200 7d;
    proxy_cache_valid 404 1m;

    # 手动绕过：?nocache=1
    proxy_cache_bypass $arg_nocache;
    proxy_no_cache $arg_nocache $upstream_http_set_cookie;

    proxy_cache_lock on;
    proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
}
```

验证图片 / CSS / JS（用 GET，不要用 `curl -I`，HEAD 不一定会写入缓存）：

```bash
for i in 1 2; do
  curl -sS -o /dev/null -D - https://www.infowe.site/themes/tech/static/theme.min.css | grep -i x-nginx-cache
done

for i in 1 2; do
  curl -sS -o /dev/null -D - https://www.infowe.site/uploads/2026/11/xxx.png | grep -i x-nginx-cache
done
```

预期都是第一次 `MISS`，第二次 `HIT`。

如果出现 `STATIC` 或没有 `X-Nginx-Cache`，说明还有 `alias` / `^~` 在抢；如果出现 `BYPASS`，检查 `location /` 的排除规则里有没有 `upload`。

**4. 清理缓存**

应用层缓存发文章/评论后会自动清，Nginx 这层不会。三种处理方式，按环境选一种。

**方式 A：`ngx_cache_purge`（需要模块）**

先确认 Nginx 编译了模块：

```bash
nginx -V 2>&1 | tr ' ' '\n' | grep -i cache_purge
```

有输出才能用。站点配置里加：

```nginx
location ~ ^/purge(/.*)$ {
    allow 127.0.0.1;
    deny all;
    proxy_cache_purge blog_cache "$host$1$is_args$args";
}
```

清理示例（在服务器本机执行，必须带正确的 Host，否则 key 对不上）：

```bash
# 80 和 443 在同一个 server 块，且 80 不跳转
curl -X PURGE -H "Host: www.infowe.site" http://127.0.0.1:5000/purge/
curl -X PURGE -H "Host: www.infowe.site" http://127.0.0.1:5000/purge/post/89

```


**方式 B：没有模块，用短 TTL**

把 `proxy_cache_valid 200 301 302 5m` 改成 `1m`。发文章/评论后最多 1 分钟旧页面自动过期，不需要 purge。

**方式 C：发布后直接清缓存目录**

在部署脚本或 `git pull` 后执行：

```bash
find /www/server/nginx/cache -type f -delete
```

Nginx 会重新生成缓存文件，不用重启。适合文章不多、能接受短暂回源的站点。

**5. 注意**

- 不要缓存 `/admin`、`/api`、登录、上传、评论提交
- 带 `session` 或 `blog_commenter` Cookie 的请求必须 bypass
- `?nocache=1` 可以临时绕过
- 两层缓存叠加后，页面更新延迟 = Nginx TTL + 应用 TTL；发现更新慢先降 Nginx TTL
- CDN 同理：回源 Host、Cookie bypass、发布后 purge，规则和这一节一致
- 图片一直显示 `BYPASS`：检查排除规则里有没有写 `upload`。`/uploads/` 以 `/upload` 开头，写了 `upload` 会把图片全部跳过

### 7. 申请 SSL

站点设置 → SSL：

- Let's Encrypt 申请证书
- 开启「强制 HTTPS」
- 后台「博客设置」填写 `site_url`，如 `https://www.infowe.site`
- 开启「强制 HTTPS」开关

项目已启用 `ProxyFix`，会信任一层代理的 `X-Forwarded-Proto`，不会出现 HTTPS 重定向循环。

### 8. 目录权限

```bash
cd /www/wwwroot/infowe.site
chown -R www:www var
```

### 9. 防火墙 / 安全组

- 放行 `80`、`443`
- **不要**放行 `5000`（只给本机 Nginx 访问）

### 10. 更新与重启

#### 10.1 手动更新

```bash
cd /www/wwwroot/infowe.site
git pull
.venv/bin/pip install -r requirements.txt
```

然后在宝塔 Python 项目管理器中点「重启」。

Gunicorn 也可以只给 master 发 HUP，让它平滑替换 worker，不会中断正在处理的请求：

```bash
ps -eo pid,ppid,user,args | grep '[g]unicorn'
kill -HUP <master_pid>
```

只对 master 发信号，不要对 worker 发。升级包含模板、CSS、JS 变更时，重启后到后台「数据管理 → 清除页面缓存」，否则旧页面缓存可能还会保留 5～30 分钟。

#### 10.2 更新后自动重启（宝塔）

宝塔的 Python 项目不会因为 `git pull` 自动重启。仓库里的 `tools/infowe-auto-restart.sh` 配合宝塔「计划任务」可以做到：

- 比较 Git HEAD，没有新提交直接退出
- 后台在线升级还在跑时先等待，失败或超时就不重启
- `requirements.txt` 有变化才补装依赖
- 首次从旧目录升级时停机迁移到 `var/`
- 清页面缓存，再对 gunicorn master 发 `HUP` 平滑重载
- 进程找不到或依赖装失败时保留旧进程，不会带着坏环境上线

**第一步：把脚本放到 `/root`**

```bash
cp /www/wwwroot/infowe.site/tools/infowe-auto-restart.sh /root/infowe-auto-restart.sh
chown root:root /root/infowe-auto-restart.sh
chmod 755 /root/infowe-auto-restart.sh
sh -n /root/infowe-auto-restart.sh
```

`/root` 下是独立副本，仓库里脚本更新后要重新复制一次。

**第二步：让 root 能读 Git 仓库**

新版 Git 默认拒绝 root 操作 `www` 拥有的仓库，会报 `detected dubious ownership`。加一次安全目录：

```bash
git config --global --add safe.directory /www/wwwroot/infowe.site
cd /www/wwwroot/infowe.site
git rev-parse --short HEAD
```

能输出 commit 才继续。

**第三步：配置运行环境**

```bash
source py-project-env infowe_site

cat > /root/.infowe-auto-restart.env <<EOF
BASE=/www/wwwroot/infowe.site
PY=$(python -c 'import sys; print(sys.executable)')
PORT=5000
EOF

chmod 600 /root/.infowe-auto-restart.env
```

| 变量 | 说明 |
| --- | --- |
| `BASE` | 项目目录 |
| `PY` | 用于补装依赖和数据迁移，不是启动 gunicorn 的命令 |
| `PORT` | 健康检查端口，和 gunicorn 监听端口一致 |
| `BLOG_DATA_DIR` | 数据目录，默认 `$BASE/var` |
| `STOP_CMD` / `START_CMD` | 宝塔 / systemd / supervisor 托管时填完整停止、启动命令；不填则按原 gunicorn 命令行重放 |

**第四步：手动验证**

```bash
rm -f /www/wwwroot/infowe.site/var/.auto-restart.head
/root/infowe-auto-restart.sh
```

正常输出：

```text
检测到代码更新： -> xxxxxxxx
已平滑重载 gunicorn master ...
完成，记录 commit ...
```

常见报错：

| 日志 | 原因 | 处理 |
| --- | --- | --- |
| `读取 Git HEAD 失败` | root 没有仓库权限 | 执行第二步的 `safe.directory` |
| `未找到 gunicorn master` | 启动命令里没有项目名，或不是 gunicorn | `ps -eo pid,ppid,user,args \| grep -E '[g]unicorn\|[u]wsgi'`，再配 `STOP_CMD` / `START_CMD` |
| `依赖安装失败` | pip 装不上 | 先手动解决依赖，脚本会保留旧进程 |

**第五步：宝塔计划任务（必须）**

宝塔 → 计划任务 → 添加任务：

| 项 | 值 |
| --- | --- |
| 类型 | Shell 脚本 |
| 名称 | infowe 自动重启 |
| 周期 | 每 1 分钟 |
| 脚本 | `/root/infowe-auto-restart.sh` |

这是自动触发源，不加的话脚本不会自己跑。

**可选：post-merge 即时触发**

只有 `git pull` 由 root 执行时才用。`www` 用户读不了 `/root`，hook 会失败。

```bash
cat > /www/wwwroot/infowe.site/.git/hooks/post-merge <<'EOF'
#!/bin/sh
nohup /root/infowe-auto-restart.sh >>/var/log/infowe-auto-restart.log 2>&1 &
EOF
chmod +x /www/wwwroot/infowe.site/.git/hooks/post-merge
```

计划任务和 hook 同时存在不会重复重启，脚本里有 `flock` 和 HEAD 记录。

**验证**

```bash
crontab -l | grep infowe
tail -n 20 /var/log/infowe-auto-restart.log
cat /www/wwwroot/infowe.site/var/.auto-restart.head
ps -eo pid,ppid,lstart,args | grep '[g]unicorn'
```

重启成功后 master PID 不变、worker PID 变新。

### 宝塔常见错误

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 403 Forbidden（nginx） | 宝塔站点没有反向代理，请求落到静态目录 | 在宝塔站点里加反向代理到 `http://127.0.0.1:5000`，伪静态保持为空 |
| 502 Bad Gateway | uWSGI/gunicorn 未启动、端口/目录不对 | 查看项目日志，确认 5000 返回 200 |
| 413 Request Entity Too Large | Nginx 上传上限太小 | `client_max_body_size 64m` |
| 上传/备份 500 | 目录无写权限 | `chown -R www:www var` |
| 登录后重定向循环 | `site_url` 与访问域名不一致，或未传 `X-Forwarded-Proto` | 修改 `site_url`，检查反代头 |
| 证书 key usage 错误 | 证书类型/链不对 | 重新申请或重新部署证书 |

---

## 其他部署方式

### systemd（Linux）

```ini
[Unit]
Description=Python Blog
After=network.target

[Service]
User=www
Group=www
WorkingDirectory=/www/wwwroot/infowe.site
Environment="PATH=/www/wwwroot/infowe.site/.venv/bin"
ExecStart=/www/wwwroot/infowe.site/.venv/bin/gunicorn -w 2 -b 127.0.0.1:5000 --timeout 120 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now python-blog
```

### Windows

```powershell
.\.venv\Scripts\python.exe -m pip install waitress
.\.venv\Scripts\waitress-serve.exe --listen=0.0.0.0:5000 app:app
```

---

## 数据迁移

### 从 PHP 版（MySQL）迁移

```bash
pip install pymysql bcrypt
python tools/migrate_from_php.py --source-dir /path/to/php-blog --dry-run
python tools/migrate_from_php.py --source-dir /path/to/php-blog
```

脚本会读取 PHP 项目的 `config/config.php`，把 10 张表、设置、管理员、上传文件与 README 缓存写入 SQLite：

- 写入前自动备份当前数据库
- 默认关闭 OTP（避免没有旧验证器无法登录）
- 管理员沿用 PHP 版账号与密码（bcrypt 兼容）
- `--keep-otp` 保留 OTP
- `--keep-users` 保留当前管理员

### 从旧 Flask 版迁移

后台上传旧 `blog.db`，或在服务器执行：

```bash
python - <<'PY'
from app import app
from services import backup
print(backup.import_sqlite('/path/to/blog.db', keep_users=True))
PY
```

---

## 升级与数据库结构

升级**不会覆盖** `var/blog.db`。每次启动都会以 `schema.sql` 为基准自动同步表结构：

- 新增字段：自动 `ALTER TABLE ADD COLUMN`
- 删除字段：SQLite 3.35+ 自动 `DROP COLUMN`，低版本跳过并记录
- 检测到结构变化时，先自动备份到 `var/backups/schema_upgrade_YYYYmmdd_HHMMSS.db`
- 只同步字段，不删除表、不修改已有字段类型
- 更早版本的 `instance/` 数据会自动迁移到 `var/`；`data/`、`uploads/`、`backups/`、`storage/` 首次启动时同样自动合并
- 重名文件不会被覆盖，统一保留在 `var/.legacy-<时间戳>/`

查看 SQLite 版本：

```bash
.venv/bin/python -c "import sqlite3; print(sqlite3.sqlite_version)"
```

建议升级前仍在后台「数据管理」手动备份一次。

---

## 备份与恢复

- 后台「数据管理 → 数据库备份」使用 SQLite 在线备份，运行中也可安全备份
- 备份文件：`var/backups/blog_YYYYmmdd_HHMMSS.db`
- 恢复：后台上传 SQLite 备份，或停止服务后用备份文件覆盖 `var/blog.db`
- 支持 JSON 全量导出、Markdown（zip）导出

---

## 常见问题

### 忘记后台密码

```bash
.venv/bin/python -m flask --app app reset-password
```

### 数据库在哪里

`var/blog.db`；备份在 `var/backups/`。

### 首次启动没有文章

空库会自动写入《致使用者的一封信》。如果使用了自己的数据库，以数据库内容为准。

### 上传 / 备份失败

```bash
chown -R www:www var
```

### 修改后台入口后进不去

重启服务；如果路径写错，把 `settings.admin_path` 改回 `admin`（见上文命令）。

### SQLite 报 database is locked

- 已启用 WAL 与 8 秒 busy_timeout
- 建议 gunicorn/uWSGI 使用 2 个 worker，不要开太多写进程
- 避免多个实例共用同一个 `var/blog.db`

---

## 安全建议

- 首次登录后立即修改默认密码
- 建议开启 OTP 双重验证
- 使用 HTTPS，并在后台配置正确的 `site_url`
- 把后台入口改成不易猜到的路径
- 定期备份 `var/blog.db` 与 `var/uploads/`
- 不要把 `var/` 暴露为静态目录
- 生产环境只开放 80/443，5000 仅监听 `127.0.0.1`

---

## 更新日志

当前版本：**v3.8.10**

> 这里只展开最新版本；更早的日志在下方折叠区，点开查看。

### v3.8.10

- 首页「精选推荐」移除与页头彩条位置冲突的 64px 蓝条，改为细分隔线 + 标题侧短竖标记
- 精选区与文章列表的横线两侧留白对称并跟随断点（PC 14px / ≤1000px 8px），与组内卡片间距一致；清理被后置色卡规则覆盖的死声明与过时注释
- PC 双栏开启精选时侧栏下移 36px，首张侧栏卡与首张文章卡顶部对齐

<details>
<summary><b>历史版本（v3.8.9 及更早，点击展开）</b></summary>

### v3.8.9

- 后台「博主设置」新增「首屏标语」输入项：首页大标题上方那行小字可单独配置
- 留空则自动回退副标题，不再需要维护两份文案
- 该项此前一直存在于设置表（首页一直在读），但后台没有入口，属于遗漏，本次补齐

### v3.8.8

- 修复后台锚点定位被 sticky 顶栏遮挡：仪表盘「N 条评论待审核」点进去后，目标卡片头部被顶栏盖住
- 后台内容区锚点统一预留顶栏高度 + 16px 间距，定位后目标完整可见
- 前台主题本来就有同类处理（`#comments`、标题、楼层均为 72~80px），本次补齐后台这一侧

<details>
<summary><b>历史版本（v3.8.7 及更早，点击展开）</b></summary>

### v3.8.7

- 修复移动端后台评论管理「待审核」高亮被切成一截截色带：行级高亮改由整行承担，恢复成一张连续的卡
- 文件清理页「批量选中」「删除失败」的高亮同步改为整行着色
- 桌面端表格保持原样：逐单元格着色仍保留，只在卡片化的窄屏改整行

<details>
<summary><b>历史版本（v3.8.6 及更早，点击展开）</b></summary>

### v3.8.6

- 升级页发布日期改为本地时间，不再显示 `2026-11-07T13:35:50Z` 原始 ISO 串
- 升级页「更新内容」按 markdown 渲染成列表，不再是带 `- ` 前缀的等宽代码块
- 升级页「在 XX 查看」链接跟随「升级源」单选：选哪个源就在哪个源看
- 升级页「发布于」行与「更新内容」区块的上下留白重新对齐
- 邮件通知：操作行与页脚之间补 22px 留白，不再贴死页脚分隔线
- 邮件通知：标题下的时间与文章链接拆成两行显示
- 邮件通知：标题与元信息间距 4px → 8px
- 邮件通知：所有链接去掉下划线（显式 `text-decoration:none`，避免回落浏览器默认下划线）
- 前台主题 9 处悬停下划线改为统一的混色反馈，与导航、卡片标题一致
- 评论区与分享面板 4 处悬停下划线改为变色
- 后台 2 处悬停下划线改为变色

<details>
<summary><b>历史版本（v3.8.5 及更早，点击展开）</b></summary>

### v3.8.5

- 修复移动端首页侧栏「十年之约」卡片贴住页脚：底部内距不再被清零，卡片与页脚间距 0 → 24px
- 首页底部留白规则只在双栏生效，PC 端留白行为保持不变
- AI 插件保存条按所在位置区分样式：配置页为独立圆角卡片，模型管理页为卡片页脚
- AI 插件保存条取消悬浮定位，回归文档流，不再像固定浮层
- 清理移动端侧栏失效样式：描边/圆角/底色声明早已被后置规则覆盖，注释与实际效果相反

<details>
<summary><b>历史版本（v3.8.4 及更早，点击展开）</b></summary>

### v3.8.4

- 归档选择浮窗改为毛玻璃：半透明底 + 背景模糊，打开时透出页面与光斑
- 浮窗描边改半透明；不支持 backdrop-filter 的浏览器回退为不透明底
- 上下篇占位卡统一为全站卡片语言：与可点卡片同底色、同圆角，去掉虚线描边
- 占位卡保留次级色文字、无悬停反馈，仍明确不可点击
- 评论底部 UA（系统 / 浏览器）与时间、属地对齐到同一条文字基线
- 移动端楼中楼回复正文与根评论正文左缘对齐

### v3.8.3

- 修复外链确认浮窗悬停时透明度异常：浮窗不再参与全站卡片悬停，始终使用不透明实色背景
- 浮窗保留 1px 淡描边与阴影，遮罩与按钮交互不变

### v3.8.2

- 评论表单取消外层边框，仅保留淡底色与 6px 圆角，与已去描边的评论楼层保持一致
- 折叠态输入条与展开后的输入框保留自身边框，输入区域仍然可辨

### v3.8.1

- 深色页面底色回调为 `#181b21`，导航玻璃底与首屏防闪白同步调整
- 深色动态光斑大幅减弱：主层 6% / 4% / 2.5%，关闭副光斑层，饱和度降到 95%
- 移除光斑的 `blur()` 与缩放动画，只保留平移，修复深色下出现的块状马赛克
- 移动端文章目录折叠条：去掉 header 多余下边距，保留上下分隔线并让「目录」文字居中
- 关于页作者卡、热力图、状态卡、内容卡补齐全站统一的悬停底色
- 归档条目悬停与卡片间距对齐，圆角统一 6px
- 项目详情内容卡与评论区拆分，评论独立成卡
- 相关推荐与上下篇统一为普通卡片色，悬停反馈一致
- 分页、查看全部归档、友链提交、后台保存主题按钮统一为卡片色 + 6px 圆角
- 修复首页最后一张卡底部内距、查看全部归档上下间距；读者页统计改 2×2 小卡

### v3.8.0

- 全站卡片配色统一为评论区两种卡片色：普通卡文字色 3%、强调卡主色 5%，圆角统一 6px，悬停只加深底色
- 顶部导航改为半透明毛玻璃（blur 16px + saturate 180%），底部细线与轻投影拉开层级
- 亮色页面底色调整为 #f4f6fa，暗色提亮为 #1c1f26，卡片不再用纯灰叠加
- 新增全站动态光斑背景：两层径向渐变缓慢漂移，亮暗各一套，支持系统减弱动效
- 文章整篇收进阅读卡；项目内容卡与评论区拆分，评论区独立成卡
- 相关推荐改为最多 4 张卡片，桌面两列、移动端单列；上下篇悬停与相关推荐一致
- 正文图片加载失败改为紧凑说明条，并同步隐藏对应图片备注
- 关于页时间线日期左对齐并预留长日期宽度，日期标签改中性色，不再用蓝色胶囊
- 移动端取消 390px 内容宽度上限；读者页统计改 2×2 小卡，修复窄屏换行孤行
- 分页、查看全部归档、友链提交、后台保存主题按钮统一为卡片色 + 6px 圆角
- 归档条目悬停与卡片间距对齐；修复首页最后一张卡底部内距和「查看全部归档」上下间距

### v3.7.9

- 内容页宽度统一：项目、友链、圈子、读者、关于、文章归档与文章内页统一 780px 版心；首页保持 1000px 多栏布局
- 项目列表卡片重做：单/双/三栏共用同一结构，图标 + 名称 + 精选 + 两行描述 + 语言与星数；整卡可点，移动端简介完整展开
- 博客圈卡片改为「标题 + 时间徽章 → 摘要 → 出处」结构，作者行弱化；整卡可点
- 博客圈统计与读者页规则说明改为轻量文字，移除模板感卡片；榜单领奖台留言限制为一行
- 归档页改为单栏 780：点击年份标题弹出居中浮窗选择年份与月份，新增按月归档 `/archive/<年>?month=<月>`
- 移动端卡片统一改为横线列表：首页文章、侧栏卡片、归档条目均取消描边与圆角，悬停不再出现背景块
- 移动端首页宽度统一 390px 上限 + 16px 边距，与其他页面一致
- SEO 标题统一为「页面标题 - 首页标题 - 博客名称」，`<title>`、`og:title`、`twitter:title` 三处同步
- 新增柔和主按钮（淡 accent 底）用于首页「查看全部归档」与友链申请「提交申请」；友链申请页返回改为文字链接
- 文章目录滚动条隐藏，修复部分分辨率下右侧出现竖线的问题
- 评论区恢复「缩进 + 1px 细竖线」布局，移除条目间横线，回复更紧凑

### v3.7.8

- 移动端文章正文调整为 16px / 1.75，段落间距 0.85em；文章标题 23px、h2 18.5px
- 移动端项目 README 调整为 15px / 1.75，标题梯度同步收敛
- 移动端项目标题占满整行（20px），不再被 Star / GitHub 按钮挤压；项目描述 15px
- 移动端楼中楼：正文 14px / 1.75，缩进改为左侧细线，头像 20px，回复按钮缩小
- 桌面文章正文 16.5px / 1.82，版心 760px，段落间距 0.65em，h2 20px
- 桌面项目页标题与正文文字统一 760px，代码块和表格保持 780px 全宽
- 修复文章正文段落间距为 0 的问题，恢复段落呼吸感
- PC 评论区保持原有 14px / 13.5px 与 52px 缩进

### v3.7.7

- 留存记录评论 tab 改为「关键列 + 详情」：默认只显示 ID、昵称、身份、状态、内容摘要、评论时间，完整字段点「详情」查看
- 评论留存新增身份动作、身份说明两列，CSV 导出同步包含
- 评论改名写入操作记录：旧昵称 → 新昵称、操作人、IP、设备 UA，便于留存追溯
- 详情弹窗改为内容区独立滚动，默认隐藏滚动条，滚动时显示、停止后自动隐藏
- 修复后台详情弹窗未打开时仍显示空头部的问题
- 移动端详情弹窗单列布局，长文本自动换行，不产生横向溢出

### v3.7.6

- 后台评论管理的身份说明改为可点击「详情」浮窗，长文案不再被单行截断，与 AI 审核说明、人工审核说明保持一致

### v3.7.5

- 评论身份体系：邮箱哈希作为读者身份，昵称作为可变展示名；同一邮箱换昵称时先弹出确认浮窗
- 支持「继续使用原昵称」：服务端直接覆盖为曾用名，避免前端伪造昵称
- 支持「验证后改名」：6 位邮箱验证码、10 分钟有效、最多尝试 5 次，验证通过后签发一次性改名令牌
- 验证码发送限频：单邮箱 60 秒 / 10 分钟 5 次 / 24 小时 10 次，单 IP 每小时 10 次；且只允许已有评论记录的邮箱发送
- 改名成功后同步该邮箱的历史评论昵称，评论区、读者页、排行榜和回复邮件展示保持一致
- 新增统一的验证码邮件模板，复用现有邮件外壳与页脚，不再单独维护第三套样式
- 安全修复：取消「评论邮箱等于 notify_email 就自动过审」，只有已登录管理员才自动通过，避免填写公开联系邮箱绕过审核
- AI 审核与人工审核协同：沿用曾用名 / 验证改名的评论不再由 AI 自动通过，只记录 AI 建议并转人工；同时加固 AI 更新条件，避免覆盖管理员已经做出的审核结果
- 后台评论状态列新增身份说明：首次使用邮箱昵称 / 沿用曾用昵称 / 邮箱验证改名
- 修复评论待审核提示条的图标与文本对齐，「知道了」改为文字按钮
- 验证码发送增加「发送中 / 成功 / 失败」反馈与 toast 提示，成功后自动聚焦验证码输入框

### v3.7.4

- Markdown 表格改为 GitHub 同款折行规则：窄表格保持自然宽度，超过容器宽度时单元格自动换行，不再需要横向滚动查看
- 单元格补充长串断行保护，长 URL / 行内代码不会撑破表格

### v3.7.3

- 回复通知邮件底部新增「我的留言」：被回复的访客可以直接点进自己的读者页，查看在本站的全部公开留言
- 邮件视觉优化：移除顶部色条，头像与正文分区并用细线隔开，正文调整为 15px / 1.85 行高，段落间距更清楚
- 修正回复邮件页脚「直接回复本邮件」的误导文案：邮件回复不会出现在博客评论区，需点击按钮前往文章页
- 邮件顶部品牌行恢复显示站点名，页脚链接显示发件人名称

### v3.7.2

- 关于页新增「写作热力图」：按天统计近一年已发布文章，桌面展示完整 53 周、移动端自动收窄到最近 26 周；悬停可看当天文章数，底部汇总更新天数与最长连更
- 热力图沿用主题变量，暗色 / 亮色自动适配；月份标签与格子逐列对齐，320–1536px 无横向溢出
- 首页保持原样，不占用首屏文章列表空间

### v3.7.1

- 修复 HEIC/HEIF 上传仍提示「图片文件损坏或格式不受支持」：校验前先注册 pillow-heif 解码器，安装依赖后不再需要额外重启才生效
- HEIC/AVIF 内容被改名成 `.jpg` / `.png` 时，按真实格式转成 WebP 再落盘，浏览器可正常显示，不再因为扩展名和内容不一致而失败
- 图片校验失败时把真实原因写入日志（如 `decoder jpeg not available`、`cannot identify image file`），便于定位是文件损坏还是服务器缺解码器

### v3.7.0

- HEIC/HEIF 支持：上传后自动解码并转成 WebP 落盘，Chrome、Firefox 等不支持 HEIC 的浏览器也能正常预览；转码后照常叠加水印、生成分享图，并根据 EXIF 方向自动摆正
- 评论图片上传同步放开 HEIC/HEIF，前端类型校验兼容部分系统未注册 HEIC MIME 的情况
- 新增依赖 `pillow-heif`，后台「图片扩展名」提示同步更新

### v3.6.9

- 移动端悬浮按钮合并为一个：向下滑显示「跳到评论」，向上滑显示「回到顶部」，到评论区后固定为「回到顶部」；两个状态共用同一位置，来回切换不会上下跳，长文任意位置都能回顶部
- 评论说明浮窗：后台评论状态列的 AI 审核、AI 回复、人工审核说明改为可点击，点「详情」弹窗查看全文，长理由不再被单行省略截断
- 私密评论审核修复：私密评论不再无条件绕过审核，只有已通过或待审核的私密评论对管理员可见，被拒绝后仅保留在后台

### v3.6.8

- 文章灯箱移动端手势：支持双指捏合 1×–4× 缩放、放大后单指拖动、双击 2.2× 放大 / 复位；缩放状态下横滑是拖动，不再误切上一张/下一张
- 移动端按钮瘦身与圆角统一：主按钮高 36px、左右 14px，分页 34×34，统一 8px 圆角；透明热区补到约 44px；圈子页「我要申请」改为描述下方的文字链接
- 关闭全站原生跨文档 View Transition：删除 `@view-transition` 相关规则，统一使用 `page-enter` 淡入，修复 Chrome 在表单 POST / 302 后抛出的 `InvalidStateError: ViewTransition opt-in disabled`

### v3.6.7

- 移动端友链申请表单：底部内边距由 4px 收到 16px，提交 / 返回按钮到卡片底部的间距由 5px 提升到 17px，与按钮上方 17px 对称
- 圈子分页间距：分页与「已经看了 N 篇」之间由 12px 调到 24px，分页上下间距统一为 24px

### v3.6.6

- 移动端非首页正文再放宽 8px：`≤480px` 左右留白由 20px 收到 16px，390 屏内容宽 343px、430 屏 348px，约 23–24 个汉字/行；首页列表仍保持 12px 边距和满宽，320 小屏保持 273px

### v3.6.5

- 移动端正文列宽优化：`≤480px` 时除首页外的页面正文最大宽度收到 380px（实际内容宽 335–340px），左右留白 20px；`≤360px` 小屏左右 16px（内容宽 273px）。首页列表保持原来的 12px 边距和满宽，不参与收窄

### v3.6.4

- 文章页 / 项目页目录改版：180px 描边卡片改为 220px 无框文字索引；标题 11.5px 加字距，条目用 2px 左轨道标记当前章节，h3/h4 分级缩进；窄屏保留 `<details>` 折叠，改为上下细线、44px 触控行高，长目录在面板内滚动
- 关于页站点状态改版：移到人物卡后的第一张内容卡，改用「域名 / 服务器 / 证书 / 延迟 / 连通率」文本 + 动态数据；右上角运行状态徽标（正常 / 需关注 / 有异常 / 待探测），原来的两张明细表折叠为「监控明细」，接口每分钟刷新
- 文章图片备注：`![demo.jpg](...)` 会在正文图片下方和灯箱中居中显示弱化备注；空 alt、`null`、`为空null` 等占位值不显示；连续图片画廊中保留单行备注；后台上传自动用原始文件名作为 alt，Vditor 预览实时同步
- 间距统一：主内容底部留白 40px / 移动端 32px 统一收到 24px；分页上下间距统一 24px，并移除项目列表底部多余的 20px；圈子分页与「已经看了 N 篇」收尾块收紧

### v3.6.3

- 移动端首页与列表加宽：`≤480px` 时容器与列表卡片水平内边距由 16px 收到 12px，390px 屏幕文字可用宽度增加约 16px，列表不再显得过窄
- 文章相关推荐收敛：默认由 4 条改为 2 条；板块标题 18px → 15px 并降为次要文字色，行内边距与标题字号同步收紧，移除左侧 2px 主色竖条，让文末回归「收尾」而不是第二个内容区
- 移动端页脚居中：`≤768px` 时版权、导航链接、备案号三行纵向排列并整体居中
- 修复正文表格上下空隙翻倍：内层 `<table>` 被正文块级统一间距规则额外加了 14px 外边距（与 `.table-wrap` 叠加成 28px），清零后恢复单倍间距，表格上下不再发空

### v3.6.2

- 敏感词词库内嵌进页面前把 `</` 转义为 `<\/`，防止词库内容闭合 `<script>` 标签注入
- 评论表单：字数计数临近上限（差 200 字）即标红；支持 `Ctrl/Cmd + Enter` 快捷提交（走原生提交链复用全部校验，提交中防重复）；表情面板新增「最近使用」分组（最多 12 个，本地持久化）；输入框补充 `aria-label`，提交按钮旁显示快捷键提示（macOS 显示 `⌘↵`，移动端隐藏）
- 浮窗表单紧凑化：展开态隐藏「收起评论框」行、博主身份条改紧凑 chip、输入框限高 64-96px，首屏多露出下方楼层
- 正文排版：文章块级元素（引用 / 代码 / 列表 / 表格 / 图片 / 分割线等）上下间距统一 14px（移动端 12px），段落保持原间距；h2 上下总距对齐统一值；代码块间距由外层 wrap 承担，内层 pre 归零不叠加
- 灯箱大图下方居中显示图片备注，正文不再注入备注

### v3.6.1

- 评论归属地改为「省 · 市」：显示为「四川省 · 成都市」「内蒙古自治区 · 呼和浩特市」，直辖市只保留一条，并去掉「IP属地：」前缀；新评论直接按新格式入库，启动时自动迁移历史数据（装了 ip2region 库还会用 IP 重解析被截断的旧值）
- 设备 / 浏览器信息移到作者行末尾，跟在地名后面；图标保持纯色描边，并修正了图标与文字的基线对齐
- 楼中楼间距：每条回复上下各 9px + 细分隔线，最后一条不再额外留底部内边距，卡片顶部与底部留白一致（底部不再多空 9px）；有 UA / 没 UA 的回复间距完全相同
- 评论区垂直节奏与整页对齐：标题 → 表单、表单 → 列表、列表 → 分页统一 20px；文章 → 上下篇、上下篇 → 评论区统一 24px

### v3.6.0

- 友链审核重写：申请页新增「友链页地址」（`links.backlink_url`，启动自动补列）；审核链改为「可访问性 → 敏感词 → AI 内容审核 → 回链检测」，AI 抓取首页标题与正文判断色情、赌博、诈骗、采集等内容风险，未配置模型时自动跳过不阻断；回链优先查申请页，未填则自动发现 `/links`、`/friends`、`/blogroll`、`/about` 及首页含「友链 / link / friend」的锚点，并改为解析 `<a href>` 精确匹配域名（忽略 `www`），不再用字符串包含；后台待审列表新增「验证页 / AI 审核」两列与未通过原因，插件设置新增「友链 AI 内容审核」开关
- AI 对话流式输出：新增 SSE 接口，发消息后实时显示推理过程（逐字、带计时），推理结束正文逐字输出；工具调用期间显示执行状态，回复外层 JSON 自动剥离，浏览器不支持流式时回退到原请求方式
- 评论时间改为相对时间：刚刚 / N 分钟前 / N 小时前 / 昨天 / N 天前，超过 15 天显示完整时间，后台保持完整时间
- 评论设备信息：正文下方显示「系统 + 浏览器」图标文字（不含版本号）；旧评论没有 UA 时整行不渲染，不留空、不塌陷
- 评论回复数修正：根评论显示整条楼中楼的回复总数（此前只统计直接子评论，三层套娃时 3 条只显示 1）；楼中楼回复不再显示数字
- 楼中楼间距修复：分隔线引用了不存在的 `--c-divider` 变量导致线不显示，且首条回复 14px、后续 28px 的断层；改为统一 14px + 细分隔线，有无 UA 行节奏一致
- 评论区布局：左侧内容 + 右侧垂直居中的回复图标，长评论不再把回复入口挤到底部
- 博客圈改版：文章卡片改为单栏，头部头像 + 站点名 + 日期、标题、两行摘要、相对时间 +「阅读全文」；列表底部新增「已经看了 N 篇」，最后一页显示收尾文案；四个统计卡片顺序改为「今日 / 本周 / 本月 / 订阅站点」并把内部改为标签在上的单栏；摘要自动清理短代码与 Markdown 语法；区块间距统一 20px、卡片间距 12px，卡片高度压缩约 20%
- 读者页：规则说明独立成卡片（标题居中、正文左对齐）；领奖台改为亚军 · 冠军 · 季军（冠军居中），移动端仍按 1-2-3 排列；移动端序号从独立一列改为头像左上角标，内容区宽度增加约 44px
- 侧栏与站点细节：博主行改为「博主：名字」，社交链接改为 SVG + 文字；简介保留换行；全站按钮统一黑白配色；文章页删除底部重复标签，「复制链接」改为「复制」

### v3.5.5

- 修复 AI 对话回复中断：默认 60s 请求超时对 reasoning 模型不够（mimo 写 2000 字实测 56s+），升到 120s 并自动迁移旧配置
- 修复 Gitee 源在线升级失败：`pull` 未指定分支，remote 非当前分支的默认上游时报 `did not specify a branch`；改为显式拉取当前分支，detached HEAD 时给出明确提示
- 后台页头「回收站」按钮修复：计数徽章自带 margin/边框把按钮撑高约 10px 且边框内套边框，与「新建文章」一高一低、观感割裂；新增 `.btn .badge` 压平为按钮内扁平胶囊，两按钮等高对齐
- 文章标签禁止重复：前端失焦与提交时大小写不敏感去重（保留首次出现、规范化逗号分隔），后端 `save()` 解析时同步去重兜底，防绕过直接 POST

### v3.5.4

- 留存审计日志改为永久保存：`op_logs` 不再按 180 天自动清理（`KEEP_DAYS = 0`），历史记录全部保留

### v3.5.3

- 主题样式对齐线上版：以 infowe.site 线上主题为唯一样式基准拉回本地，文章内页与项目内页正文版心统一为 780px（窄视口由父容器 padding 收口），下方评论区同步收窄
- 评论区顺序反转：表单在上、评论内容在下；内嵌模式用 flex `order` 实现（不改 DOM），浮窗模式 foot/body 同步反转，两种模式均适配
- 全站扁平化：清除卡片投影、悬停上浮与毛玻璃（弹层/抽屉/搜索面板等浮层按白名单保留），hover 改为淡背景与描边换色
- 评论后台新增「拒绝」：单条与批量均可拒绝，前台不再显示、记录保留在后台；拒绝说明与 AI 未回复原因（随机未抽中/不在时段/命中屏蔽词）在「状态」列单独展示，改回通过时自动清除旧说明
- AI 评论回复策略：新增「每条都回复 / 随机抽一部分回复」与回复概率配置（默认 30%），未抽中的评论只审核不生成回复以省 token；移除已无意义的「评论最长长度」配置
- 回归测试：三视口（1440/768/390）× 17 页 × 深浅色共 70 轮 + 交互自测 5 次全部通过

### v3.5.2

- 首页文章卡片与侧栏卡片统一：文章列表项改为 1px 描边 + 12px 圆角独立卡片，悬停只做淡背景与描边换色（与侧栏博主卡片完全一致，不再位移/上浮/阴影），移动端同时禁用系统点按高亮残留
- 移动端限制整页缩放：viewport 加入 `maximum-scale=1` / `user-scalable=no`，iPhone 上双指、双击不再误放大页面（输入框聚焦时的系统放大仍由移动端 16px 输入框字号兜底，不受影响）
- 修复移动端读者留言榜单边框丢失：4 名起的列表项恢复与 PC 端、前三名领奖台一致的完整描边卡片（此前窄屏被降级为透明分割线）

### v3.5.1

- 读者留言档案：新增 `/readers/<id>` 页面，点击榜单/前三甲的「N 条留言」即可进入该读者的公开留言时间线（不限 6 个月，支持翻页，超过 220 字的留言截断并提供「查看全文」链接回源文章）；档案卡片带悬停高亮，留言数统计（文章数、首次/最近时间）一并展示
- 留言榜单分页：榜单超过一页时底部出现分页条（每页人数由后台 `readers_limit` 控制），首位读者引导文案同步调整
- 全站样式审计：补齐 19 处缺失的触屏 hover 守卫（`@media (hover: hover) and (pointer: fine)`），消除移动端点按后悬停样式残留；清理约 200 行死代码（已下线的互动页、旧灯箱、走心评论区块等未再被引用的规则），theme.css 瘦身 5KB、压缩产物 98KB
- 修复留存审计定时清理报 `Working outside of application context`：后台线程先入应用上下文再判断插件启停（此前在上下文外查库，启动 60 秒后的首轮清理必然抛异常）

### v3.5.0

- 插件启停即时生效：后台启用/停用插件不再需要重启服务。启动时统一注册插件路由，未启用时由守卫直接返回 404；启用时执行建表、启动定时任务并订阅 hooks，停用立即失效。修复更新或新装博客后启用插件、访问插件页面一律 404 的问题
- 插件契约调整：`register(app)` 只注册路由，新增可选 `on_enable(app)` 承担建表/定时任务/hooks；旧插件保持兼容；`hooks.on()` 去重，反复启停不会重复执行回调；插件静态资源也随启用状态开关
- 评论者标签：新增「新朋友 / 回头客 / 常客」三档（1 次 / 2–4 次 / 5 次及以上），按邮箱哈希统计全站已通过评论数；博主与 AI 不参与，楼中楼只保留博主/AI 等身份标识
- 评论 UA 展示：评论提交时记录 User-Agent，前台显示「Chrome · Windows」设备标签（悬停可看完整 UA）；后台评论管理与留存审计的操作记录、评论留存同步显示，CSV 导出也带上设备列
- 评论样式：标签改为长方形小圆角（3px），低饱和淡底 + 同色描边，昵称统一正文色；标签中心与昵称、时间基线对齐
- 数据库：新增 `comments.user_agent`、`op_logs.user_agent`，启动时自动升级并备份

### v3.4.36

- 通知邮件正文真实化：撤销 v3.4.34 的「评论正文不出站」占位设计——新评论、回复、AI 回复通知邮件正文均展示真实内容（此前一律显示占位文案「评论原文内容保持不变」，收件人看不到任何实际内容，通知失去意义）；仅命中敏感词或已拒绝的评论仍只显示「【不当言语】请后台审核」，防止恶意内容随官方邮件外发
- 评论作者行样式修复：徽章（博主 / AI 助手 / 私密 / 待审核）圆角由 20px 胶囊改为 8px 方圆角，与主题标签（tech-tag）一致；行高与内距收紧，与昵称、时间的基线对齐更整齐，内嵌与浮窗评论共用同套 CSS 同步生效
- 留存审计页布局修复（`plugins/retention`）：评论留存 / 操作留存 tab 的长内容列（IPv6 地址、归属地、长 URL、长文本）新增可换行压缩类（`wrap-text`），修复全列强制单行导致的整表超宽横向溢出；移动端卡片视图的数据标签与表头统一

### v3.4.35

- AI 助手修复：`list_comments` 带邮箱/昵称/文章 ID 等具体条件时默认查全部状态评论（此前默认只看待审，全是已通过评论的用户查出来是空，看起来像指令失效）；`max_tokens` 默认 4096→8192，长文重构不再因输出上限打满导致 JSON 截断失败；模型输出被截断时返回明确兜底提示而非残缺结果；system_prompt 内置指令迁移为带 `status:all` 的新写法
- 留存审计页修复（`plugins/retention`）：AI 审计「参数/结果」长 JSON 改为「一行摘要 + 点击展开全文」折叠展示，非法 JSON（历史超长截断残片）同样折叠不再直出；配合 `.wrap-cell` 补 `width` 硬约束（`table-layout:auto` 下仅 `max-width` 会被内容撑破），修复超长内容把卡片/表格撑爆、整页排版溢出的问题
- AI 审计源头修复：审计写入超长 JSON 时改存带截断标记的合法 JSON（此前硬截断产生尾部不闭合的非法残片，是留存页排版爆炸的根源）

### v3.4.34

- 文章回收站：删除文章改为软删除（`posts.deleted_at`），后台新增回收站页，支持恢复、彻底删除、批量操作与一键清空，文章列表带回收站数量角标；前台列表、搜索、RSS、AI 上下文全站过滤已删文章
- 留存审计插件（`plugins/retention`）：三合一审计页——后台操作记录（新增 `op_logs` 表，自动记录登录、文章、友链、评论、设置等关键操作）、AI 审核记录、评论留存（软删除评论可查可恢复）；支持日期区间 + 关键词筛选与 CSV 导出（utf-8-sig，Excel 打开不乱码），日志永久保存（不自动清理）
- 评论通知邮件模板重做：全 table 布局 + 内联样式（Outlook 兼容），8px 圆角体系、32px 圆形头像（gravatar/QQ 头像，无头像用首字母色块兜底）、强调色自动取自当前主题；新增通用通知模板，AI 回复与友链申请通知一并接入 HTML 邮件；评论正文不出站（邮件只放占位文案 + 链接），命中敏感词显示「【不当言语】请后台审核」，回复通知带「你之前说」原评论引用块
- AI 助手增强：机器人昵称/头像后台可配（新增 `ai-bot.svg` 默认头像，历史 AI 评论一键同步身份）；「通过后 AI 回复」同时接管回复评论；AI 审核后自动清页面缓存；后台评论管理显示 AI 审核记录与徽章；ai-avatar 加入上传白名单
- 评论体验：草稿自动保存（localStorage 按文章维度暂存，误刷新不丢稿，提交成功自动清除）；评论分页开启时 `#comment-N` 跨页锚点自动拉取评论片段直达目标楼层，折叠回复自动展开并高亮

### v3.4.33

- 评论浮窗模式上线：后台「评论展示方式」可选 `inline`（内嵌，默认，行为不变）/ `floating`（浮窗）。浮窗模式下页面源码不含评论内容，左下角悬浮按钮带评论数角标，点击弹出原生 `<dialog>` 弹窗并 AJAX 拉取评论片段（`/comment/post/<id>`、`/comment/project/<id>`），支持 `#comment-N` 深链自动定位到弹窗内目标楼层
- 弹窗内完整可用：AJAX 分页（不 pushState、不整页跳转）、整页表单提交后 302 回详情页自动开窗定位、折叠回复展开、表情、图片上传；移动端为贴底抽屉（92dvh 上圆角），暗色主题自适应，打印时隐藏；不支持 `<dialog>` 的环境悬浮按钮保持隐藏、优雅降级
- 配套重构：评论模板拆为 `_comments_body.html`（主体，双模式共用）/ `_comments.html`（inline 壳）/ `_comments_async.html`（片段端点）/ `_comments_popup.html`（浮窗骨架）；`comments.js` 锚点定位对 `<dialog>` 内目标不再触发背后页面滚动（交给浮窗自身的 revealFocus）

### v3.4.32

- 零行为变化重构，为评论浮窗模式（v3.4.33）打地基：`comments.js` 由 IIFE 改为可重入的 `window.initComments(root)`，内部元素查询以 root 为根（`byId` 助手），hashchange / popstate / 灯箱等全局监听加幂等守卫，同一表单重复初始化直接跳过；评论 flash 从 `_comments.html` 提升为页面级 `shared/_flash.html`（文章页 / 项目页各自引入）；`front.py` 抽出 `_comments_context()` 合并两处详情路由的重复评论上下文

### v3.4.31

- 修复老版本 git 上在线升级报「配置 GitHub 远程失败」：`git remote get-url` 是 1.8.5 才有的子命令，CentOS 7 自带的 git 1.8.3 会把已存在的 origin 误判为不存在，改用 `git remote` 列名判断；add 撞名时自动改 set-url 兜底；git 命令统一带 `safe.directory`，兼容仓库属主与运行用户不一致的部署

### v3.4.30

- 修复升级页「升级源」选择行贴卡片左边缘的问题：样式收进 admin.css，与上下内容同样左右留白，间距统一走 spacing 变量

### v3.4.29

- 在线升级支持选择升级源：检测仍同时查询 GitHub 与 Gitee 取更高版本，实际拉取前可单选 GitHub 或 Gitee（默认 GitHub）；首次从 Gitee 升级自动补配远程地址

### v3.4.28

- 修复文章正文 Markdown 目录点击后滑到底部的问题：锚点改逐帧对齐滚动，标题 id 对不上时归一化匹配兜底
- 首页「每日一言」打字机改 rAF 时间轴驱动，消除定时器漂移造成的卡顿
- 评论强制填写邮箱（前端即时校验 + 后端兜底）
- AI 评论回复安全兜底

### v3.4.27

- 修复 IP 归属地直辖市重复显示（如「重庆市 重庆市」）：直辖市在 ip2region/pconline 里省市同名，xdb 与在线兜底两条路径都做相邻片段去重，前台评论属地与后台 badge 一并恢复正常；历史库中已存的重复值也新增展示兜底 `normalize_display` 并提供一键修复脚本 `tools/fix_ip_location.py`；正常的「省 市」组合不受影响

### v3.4.26

- 修复 IP 归属地直辖市重复显示（如「重庆市 重庆市」）：直辖市在 ip2region/pconline 里省市同名，xdb 与在线兜底两条路径都做相邻片段去重，前台评论属地与后台 badge 一并恢复正常；正常的「省 市」组合不受影响

### v3.4.25

- 评论新增「邮箱通知」开关：默认勾选、勾选时邮箱必填、选择记忆 30 天，取消勾选后不再收到回复邮件（含 AI 回复与审核通过后的补发）
- 评论新增昵称校验：纯数字、网址开头、命中敏感词的昵称直接拒绝，前端即时提示、后端兜底
- 修复博主退出登录后评论表单仍回显博主昵称与邮箱：博主身份评论不再写入访客记忆 cookie，退出登录时自动清除
- 修复评论前端校验失效（submit 回调里 return false 并不阻止提交）导致空邮箱仍被提交并整页刷新，改为拦截提交 + Toast 提示 + 红边聚焦
- 修复「修改」资料后旧记忆无条件覆盖新值的问题：本次提交的信息优先，旧记忆只补空字段
- 评论框折叠态改为「输入框占位条」（灰提示 + 写评论，不悬停也能看出可点）；「邮箱通知 / 私密评论」勾选项与表情、图片按钮同行并精简文案；移动端输入框压扁至 14px、去除点按高亮块、焦点环收窄
- AI 评论回复改为只依据当前文章/项目正文生成（正文压单行节选 4000 字喂给模型），修复只喂标题摘要导致的答非所问；项目下的评论也纳入托管，标题/摘要取项目名与描述
- AI 助手新增三项配置：评论最长长度（0 不限）、回复托管时段（全天 / 白天 09-21 / 夜晚 21-09）、AI 回复邮件通知（沿用站点评论通知配置，跳过 @qq.com 邮箱）
- 项目列表支持服务端分页与 URL 语言筛选（`?lang=` 翻页、刷新、分享链接都不丢筛选，语言统计始终按全部项目计算），每页条数可在后台配置，0 表示不分页
- 代码高亮统一收口到 theme.js：不认识的代码块一律按纯文本处理（目录树/流程图不再被误猜成 C#/Bash），新增 Dockerfile 语法包并兼容 .dockerignore
- 全站横向滚动条统一 6px 细条（含 403/404/50x 错误页），代码块与宽表格不再被默认滚动条吃掉一行；按钮、标签、分页、语言芯片统一为圆角矩形 + 悬浮微上浮，主按钮改实心渐变并修复深色下 hover 瞬间跳色
- 首页报头与子页页头统一为细线 + 彩条收口；首页标语可在主题配置独立填写，留空回退站点副标题；一言移除刷新按钮与打字光标，长句最多两行省略
- 文章与项目详情正文统一 920px 阅读宽度；项目 README 正文降为 14px 基准并收紧标题梯度，移动端再降半档
- 首页侧栏滚动时吸附导航下方；博主卡改为纯展示、仅昵称可点进关于页；侧栏统计/社交/分类入口卡片化；窄屏文章列表与站点动态改描边卡片，告别负 margin 外扩导致的背景溢出
- 留言榜单不足 3 人时自动改排布：单人整行、双人半宽，冠军回到首位
- 主题配置页新增「首页标题区」与项目每页条数设置；主题列表的「主题配置」链接改为按钮样式，布局选项 chip 改圆角矩形
- 修复外链提示页「继续访问」在 Chrome 下新窗口与当前页双开：交给 a 标签默认导航，不再用 window.open + noopener 误判拦截
- 页面标题去重（页面名与站名相同时不再重复拼接）；项目页「反馈」按钮改瞬时定位并自动展开评论框；关于页技能条补 ARIA 无障碍属性；友链申请表单卡片化、输入框与评论区同套样式

### v3.4.24

- 留言榜单说明里的「前 10 位」改为跟随后台设置的数量

### v3.4.23

- 后台新增「分类页每页文章数」「留言榜单显示人数」
- 项目页列数独立设置：主题配置可选单栏 / 双栏 / 三栏，卡片同步重做（文件夹图标、星标胶囊、查看项目入口）
- 首页 Hero 重做：标题、副标题、统计胶囊、格言一套组件，单/双栏居中，多栏左文右引，移动端自动堆叠
- 圈子与留言榜单统计改为一条带分割线的数据带，不再用四张独立卡片
- 侧栏去掉最新评论；博主卡改为「博主」胶囊 + 名字 + 三列统计
- 页面里的字符箭头统一替换为内联 SVG 图标

### v3.4.22

- 修复外链浮窗「继续访问」：先保存目标地址再关闭浮窗，避免 href 被清空；弹窗被拦截时回退当前页跳转
- 留言榜前三名改为 2-1-3 领奖台，冠军居中并戴皇冠
- 侧栏顺序调整：最新评论移到最后
- 侧栏文章分类可点击，新增 /category/<id> 分类文章页
- 侧栏博主卡箭头移到名字后面，排版收紧
- 项目卡片统一圆角、星标胶囊和「查看项目」入口
- 圈子统计卡加细主色顶线和主色数字，克制提亮

### v3.4.21

- 修复站外链接确认浮窗样式丢失导致的错位：恢复浮窗 CSS，PC / 移动端都固定屏幕居中
- oreverblog.cn 加入外链白名单，十年之约挂件和页脚标识不再弹确认
- 移除走心评论功能：留言榜单不再显示该区块，后台去掉「设为走心」按钮，/interactions 仍 301 到留言榜单
- 留言榜单第 4 个统计改为「人均留言」

### v3.4.20

- 后台新增「圈子每页条数」，博客圈分页数量不再写死
- 留言榜单前三名加「冠军 / 亚军 / 季军」标签，并用金 / 银 / 铜三色区分卡片描边和徽章
- 走心评论正文最多 3 行，「来自 文章」链接改为主色，明确可点击

### v3.4.19

- 撤销页面标题区 1100px 加宽，恢复与页面内容同宽；关于页顶部 24px 间距保留

### v3.4.18

- 关于页顶部边距与其它页面统一为 24px
- 页面标题区宽度改为 1100px（宽于内容 960、窄于导航 1200），关于页人物卡等正文仍保持原宽度

### v3.4.17

- 文章正文宽度与项目详情页统一为 960（容器 1000 + 左右 20 内边距），悬浮目录同步右移到 500，修复项目页 TOC 与正文重叠
- 十年之约「今天读什么」不再用跨域 iframe：改为服务端抓取、30 分钟缓存、用本站 CSS 渲染，深浅主题都跟侧栏卡片融合
- 侧栏挂件抓取失败时自动隐藏文章列表，只保留「了解十年之约」入口

### v3.4.16

- 导航、页脚宽度从 1000 提到 1200，正文中间区域保持 1000/800，形成更清楚的宽窄层级
- 留言榜单只展示前 10 位，不再分页；前三名改为克制的描边卡片，去掉金银铜渐变和顶部色条，修正顶部直角
- 走心评论改为 CSS 瀑布流两栏，移动端单列，不再分页
- 侧栏博主卡改为「博主 / 昵称」两行结构，删除重复副标题，整块点击进入关于页，并补 hover 反馈
- 侧栏卡片增加 hover；归档页底部按钮收成轻量描边胶囊
- 后台新增「归档页每页文章数」，独立于首页数量和标签/搜索页数量
- 文章正文 800px 容器、16px/1.8 排版、h2 19px、段距 1.1em，宽屏目录同步收窄（正文排版修复）
- 归档页标题改为「文章归档」

### v3.4.15

- 留言榜单第二页起不再把第 16 名当作前三名展示，统一按列表排列

### v3.4.14

- 「互动」并入「读者」：留言榜单页新增走心评论区块，/interactions 301 到 /readers#picked，导航去掉「互动」
- 留言榜单改版：文案参考老张博客，统计卡增至 4 个，前三名做金银铜领奖台，第 4 名起列表展示，每页 15 位，来源链接改为主色
- 归档页标题改为「文章归档」，描述改为「记录每一次折腾与思考」
- 新增站外链接确认浮窗：本站和已收录友链直接放行，其他外链先确认再跳转；PC 居中、移动端底部抽屉
- 主题配置新增「多栏」布局：首页/归档左侧文章，右侧博主信息、热门标签、分类、最新评论和十年之约「今天读什么」挂件，挂件按深浅主题自动切换
- 多栏在 1000px 以下自动上下堆叠，390px 实测无横向溢出
- 侧栏头像、评论头像、归档分页等细节适配

### v3.4.13

- 互动页空状态文案去掉「后台标记」字样，改成面向访客的说法

### v3.4.12

- 新增「读者」页：近 6 个月留言排行，按邮箱哈希/昵称聚合，排除博主和 AI 评论；前三名金银铜徽章，带头像、留言数、最新留言与来源，支持分页
- 新增「互动」页：走心评论墙，后台评论管理每条评论可「设为走心 / 取消走心」，前台只展示已通过、非博主、非 AI 的精选评论
- 导航调整：新增「读者」「互动」，移除「标签」；标签入口保留在归档页页头和页脚，/tags 地址不变
- 友链申请页表单下方增加「申请须知」：AI 初审、防重复提交、RSS 聚合到圈子、处理时间
- 评论表新增 is_owner（博主评论）和 is_picked（走心）字段，启动时自动升级旧库
- 修复后台导航开关只保存部分栏目（圈子、读者、互动等新栏目现在也能正常开关）
- 读者/互动页移动端适配，390px 实测无横向溢出

### v3.4.11

- 文章时间线页面名称由「里程」改为「归档」，导航和首页按钮同步

### v3.4.10

- 里程页年份标题显示该年全年文章数，不再显示当前页条数，分页翻页时数字保持一致

### v3.4.9

- 「文章」页面改为「里程」：按年份分组的时间线，导航、页面标题和首页按钮同步改名；/archive/<年份> 仍保留原有列表视图
- 全站卡片 hover 统一：文章卡、友链卡、圈子卡、统计卡、项目卡、里程条目都是「底色 + 描边 + 上浮 2px + 轻阴影」
- 修复双栏文章卡片鼠标经过没有反馈的问题（基础样式覆盖了 hover 背景）
- 里程页移动端实测 390px 无横向溢出

### v3.4.8

- 友链页：顶部介绍压缩成两行；「收录说明 / 以下情况暂不收录」改为双栏（移动端单列），规则文案同步精简
- 博客圈：页头增加「我要申请」按钮，描述改短；每页 30 → 20 条
- 博客圈移动端修复：卡片恢复左右内边距，标题和摘要长串可断行，分页允许换行，不再横向溢出
- 博客圈统计卡片增加 hover：底色、描边、上浮和轻阴影，与全站卡片一致
- 首页与文章列表的标签最多显示 4 个，超出显示「+N」，鼠标悬停可看剩余标签
- 双栏文章卡片默认透明，鼠标经过才出现底色和描边
- 全站按钮调整：主按钮默认淡蓝底 + 主色字，hover 变实心并上浮；次按钮 hover 增加底色、主色边框和位移

### v3.4.7

- 后台「主题管理」新增 tech「主题配置」入口：文章列表可选单栏 / 双栏；双栏作用于首页和「全部文章」页，860px 以下自动单列，首页「精选」保持单栏；保存后自动清页面缓存
- 关于页人物卡：头像与右侧信息垂直居中，社交链接与文章/标签/分类统计并成一行，减少空白
- 关于页「站点状态」两段间距收紧，域名到期与服务状态之间不再断开
- 友情链接：已填 RSS 的友链在名字旁显示 RSS 标记；页头增加「看看圈子动态」，收录说明补充 RSS 会聚合到圈子

### v3.4.6

- 关于页人物卡改为桌面横向布局（头像左、信息右），头像 118→96，整体高度约压掉一半；移动端保持居中
- 圈子页面标题恢复为「博客圈」（导航仍为 2 字「圈子」）
- 圈子分页在单页时也显示（上下页禁用 + 页码 1），不再因为只有一页而完全隐藏
- 每个 RSS 源保留文章数 8 → 15，单源也能撑起更多内容

### v3.4.5

- 关于页统一卡片：技术栈、网站历程、站点状态都包进同一套边框卡片，历程改成卡片内分割行，状态内层去重边框
- 到期时间标签改为「博客主机 / 博客域名」，不再显示云厂商前缀
- 圈子改为两栏卡片流（移动端单列），每页 30 条，分页显示页码（1 2 3 … 末页）

### v3.4.4

- 关于页「站点状态」去掉常驻说明文字：只有后台探测到新数据、generated_at 变化时才在右上角浮出「状态已更新 · 刚刚」，2.6 秒后淡出；首次访问和缓存未过期不显示
- 「网站历程」重做：从裸竖线列表改成卡片行，日期做成 pill，和状态/技术栈区块统一；首条用主色描边，移动端上下堆叠

### v3.4.3

- 「状态」并入「关于」：域名/服务器到期、在线可用性作为「站点状态」区块放在网站历程后；/status 301 到 /about#status
- 导航移除「状态」；关于页加载 status.js，状态数据仍每 60 秒刷新

### v3.4.2

- 导航顺序调整：「圈子」移到「友链」后面，和内容相关的入口挨在一起

### v3.4.1

- 导航与页面标题「博客圈」改为「圈子」，和其它 2 字导航统一
- 新增后台「圈子管理」页：列出 RSS 源、抓取状态、文章数、最后抓取时间、失败原因，支持单个/全部立即刷新
- 友链新增 eed_state/feed_error/feed_checked_at/feed_count 字段，抓取失败会显示具体原因（HTTP 状态、非 RSS、私网地址等）
- 保存带 RSS 的友链后立即抓取一次，不再等 30 分钟定时任务

### v3.4.0

- 新增「博客圈」页面 /circle：聚合已通过审核的友链 RSS 最新文章，按时间倒序，带站点头像/名称和相对时间，分页 + 统计（订阅站点、本月/本周/今日文章）
- 友链新增 
ss 字段：前台申请表单、后台编辑页都可填；审核通过后自动纳入博客圈
- 新增 services/feeds.py：支持 RSS 2.0 / Atom，SSRF 防护、2MB/8s 限制、摘要去 HTML、30 分钟定时刷新（文件锁多 worker 只跑一个）
- 导航增加「博客圈」，后台导航开关默认可控
- 配色与当前主题一致，移动端 2×2 统计卡 + 单列列表

### v3.3.12

- AI 助手补齐后台操作：项目管理（列表/详情/新建/修改/删除/同步 GitHub）、文章删除、分类删除、评论拒绝/删除、友链拒绝/删除
- 确认规则：新建/修改/删除文章与分类、删除评论/友链/项目强制人工确认；评论审核/回复、友链通过/拒绝、项目同步自动执行
- 项目同步走后台线程，AI 只负责触发，不阻塞对话

### v3.3.11

- 深色主题从 #0f1117 提亮到 #1a1d23，表面、边框、玻璃层同步调整，整体偏炭灰不再发黑
- 浅色主题强调色 #1c5b8f → #2f7ad1，链接、标签、按钮更亮；后台浅色强调色同步提亮到 #2563eb
- 后台主题按钮文案改为「浅色主题 / 深色主题 / 跟随系统」

### v3.3.10

- AI 工具：新增 create_category / update_category，create_post / update_post 支持指定分类（按名称精确匹配）
- 确认规则：新建/修改文章、新建/修改分类这四类强制人工确认，即使开启写操作自动执行
- 修复：部分中转模型把内容全塞进 
easoning_content，content 为空时误报「模型没有返回内容」；改为 reasoning 兜底，并从 reasoning 中解析工具 JSON
- max_tokens 默认从 1200 提到 4096，避免长文章被截断
- 写作风格提示词：第一人称、具体细节、去 AI 腔；用户说「发布」时 status 用 published

### v3.3.9

- IP 归属地改为内置 xdb 解析：把 ip2region 的 Python binding 精简进 services/_ip2region，不再依赖 pip 安装；支持 IPv4（11MB）与 IPv6（37MB）两套 xdb
- 查询顺序：本地 xdb → 在线 pconline 兜底；xdb 放在 ar/ip2region_v4.xdb / ar/ip2region_v6.xdb（不入 git，部署时单独上传）

### v3.3.8

- 修复：评论区 IP 归属地不显示——服务器未安装 ip2region、也没有 xdb 文件，离线查询直接返回空；改为 xdb 不可用时走 pconline 公开接口兜底（2.5 秒超时 + 进程内缓存），部署后补全历史评论归属地

### v3.3.7

- 历史 AI 评论头像补齐：旧版本没写 i_meta.avatar 的 AI 回复，启动时按当前模型补上；头像按模型动态映射，换模型会变
- 新对话提示重写：列出常用指令示例和权限说明

### v3.3.6

- AI 评论头像：内置 8 个头像（plugins/ai_assistant/static/avatars），按模型 ID + 模型名稳定映射；AI 回复评论时写入 i_meta，前台按头像渲染
- 全自动：新增「写操作自动执行」开关（默认开），AI 直接建/改文章、通过/回复评论，不再逐条确认；最多连续 3 个写操作，仍全部写审计
- 敏感词硬拦截：内置领导人/官员/政府敏感词表（plugins/ai_assistant/sensitive.txt），命中直接拒绝，不调用模型；用过滤前原文判断，避免被 * 替换后漏检；AI 回复也做同样过滤
- 历史对话支持删除（hover 显示 ×），删除会话与消息

### v3.3.5

- AI 助手权限规则内置：系统提示词写明工具白名单、读写边界、禁止删除、邮箱脱敏、提示词注入防护
- 工具增强：新增 list_posts（最新/最早、按状态），list_comments 支持按邮箱/作者/文章过滤，list_links 支持关键词
- 工具返回的邮箱做脱敏（***@qq.com）
- 配置页新增「权限规则」说明区块；旧默认提示词自动升级为新版

### v3.3.4

- AI 模型改为独立管理页：去除内置 DeepSeek / GLM 固定卡片，改为用户自己新增、编辑、删除任意多个 OpenAI 兼容模型；每项独立填名称、地址、API Key、模型，可设当前使用
- 助手配置页只保留生成参数、系统提示词和托管开关，顶部显示当前模型
- 聊天消息重做：用户/助手气泡按内容自适应宽度，模型、耗时、token 用量移到气泡下方独立一行
- 发送后立即显示「正在思考」占位和已等待秒数，回复逐字输出；模型返回 
easoning_content 时提供「推理过程」折叠块

### v3.3.3

- AI 助手支持多接口：内置 DeepSeek、智谱 GLM 官方接口，另加一个自定义 OpenAI 兼容接口；每档独立填 API Key 和模型，聊天页顶部下拉切换当前使用
- 对话消息显示模型名、响应耗时、token 用量，历史消息一并展示
- 配置页改为每个接口一张卡片，可直接切换「当前使用」

### v3.3.2

- 修复：AI 聊天页高度算多了，出现页面级滚动条——计算时扣除 .admin-content 上下内边距、页头、flex gap 与后台页脚；聊天页隐藏后台页脚，页面总高刚好等于视口，不再溢出

### v3.3.1

- 插件管理页：插件行加图标块，卡片内边距与后台其它页面统一
- AI 配置页：拆成「接口与模型 / 生成与限额 / AI 托管」三张卡片，字段两列网格、开关卡片化、保存按钮置底
- AI 聊天页：整页高度自适应（按 .admin-content 可用高度计算，窗口缩放/横竖屏自动重算）；消息区独立滚动、输入框固定底部；移动端会话列表横向滚动、单列布局
- 插件静态资源缓存从 7 天改为 60 秒，改样式后不用等浏览器缓存过期

### v3.3.0

插件系统与 AI 助手。

- 插件系统：新增 plugins/ 目录与后台「系统 → 插件管理」，只加载仓库自带插件，支持启停与配置；配置存 plugins 表，升级插件代码不覆盖配置
- AI 助手插件：
  - 配置页：OpenAI 兼容接口（ase_url / pi_key / model / 温度 / 输出上限 / 超时 / 每日调用上限 / 中文系统提示词）
  - 聊天页：后台对话，可读文章、评论、友链、分类、统计；写操作（建文章、改文章、通过评论、回复评论、加友链、通过友链）需二次确认，全部写审计
  - 评论托管：新评论自动审核，通过后结合文章内容生成中文回复，回复带「AI 助手」标识
  - 友链托管：提交后发信要求先挂本站友链，定时检查回链，命中自动通过并发信通知
- 数据结构：plugins 表、comments.is_ai/ai_state/ai_meta、links.email/ai_state/ai_meta，插件专属 i_conversations/ai_messages/ai_audit

### v3.2.23

- 修复：项目页 TOC 点击后仍可能被懒加载图片顶走——改为点击后把待加载图片切成 eager，并连续几帧跟随目标位置，直到页面高度稳定（最多 1.5 秒）；用户滚动/触摸会立即停止跟随

### v3.2.22

- 修复：项目详情页 TOC 点击后跳到页面底部——TOC 初始化只认 .tech-post-body，项目页正文是 .tech-proj-readme-body，整个点击拦截被跳过，退回浏览器默认锚点；补上选择器，并在点击后把待加载的 README 图片改成 eager、加载完重新对齐，避免懒加载把目标位置顶走

### v3.2.21

- 修复：状态页自动探测线程的 ServiceCheck 导入写错模块（models.service_check 里没有同名类），异常被静默吞掉，调度器实际从未执行；改为 rom models import ServiceCheck，并把异常写入日志

### v3.2.20

安全与性能整修。

- 头像：修复 configured_avatar_exists() 拼错路径（BASE_DIR/uploads → ar/uploads），后台上传头像后预览和前台关于页一直不显示；上传改为带时间戳文件名，换头像立即生效；关于页补传 vatar
- 评论图片上传：加 15 秒/张 + 单 IP 30 张/天上限，避免匿名接口被刷磁盘
- 头像/README 图片缓存：目录文件数上限（2000/3000）+ mtime 淘汰；头像 size 只接受 40/100/640；README 代理校验重定向后的最终域名
- 限流：评论/浏览冷却从进程内存改到 SQLite 
ate_events 表，gunicorn 多 worker 下不再失效
- 批量删除文章：引用扫描只做一次，消除 O(n²)
- 相关推荐：每个 tag 一次查询合并为一条 OR SQL
- 页面缓存：低概率清理过期文件，冷门 URL 不再永久残留
- 后台登录验证码：答案不再明文写 session，改存 HMAC 签名
- 后台 POST：已登录会话必须带 Origin/Referer，补齐 CSRF 兜底
- 文章 Markdown：兜底移除 script/style/iframe/object/embed/form、on* 事件与 javascript: URL
- 关于页作者简介：先转义再换行，避免后台字段注入 HTML
- 状态页：新增自动探测线程（5 分钟一次，文件锁保证多 worker 只跑一个）；/api/status 加 20 秒缓存
- 清理 settings.DEFAULTS 里已删除的 pattern_* 配置

### v3.2.19

- 修复：.gitattributes 漏标 *.avif binary，Git 会把 AVIF 当文本做 CRLF→LF 转换，线上每次 git pull 都报 Your local changes ... would be overwritten by merge，升级因此卡住；补齐二进制标记后不再转换，工作区与索引保持一致
- 修复：状态页 SSL 剩余天数一直显示「—」——部分服务器系统 CA 不全，ssl.create_default_context() 报 unable to get local issuer certificate；改为用 certifi 根证书建 context（requests 已依赖，无新增包）

### v3.2.18

tech 主题回到「纯色底 + 内容优先」，并补齐首屏性能。

- 背景：移除全部照片底图、雾带、山脊、江面、江岸灯带与李子坝轻轨动画，页面只剩 --bg 纯色；后台「页面背景装饰」面板与 pattern_* 设置一并删除，	hemes/tech/static 不再包含任何图片
- 浅色配色：底色 #f4f6f9 → #fbfcfd（近白纸面），文字 #161b24，主色 #1c5b8f，边框 #e1e6ed，次级底 #f0f3f7；正文对比约 16:1
- 卡片悬停：撤掉液态玻璃（斜向高光 + 白色内描边 + 大投影），首页文章卡 / 相关推荐 / 上下篇 / 项目卡 / 友链卡 / 搜索建议统一为「实色一档 + 1px 淡描边 + 标题变主色」，深色 #171b25、浅色 #eef2f7
- 评论区：.cmt-form 透明无底色（去掉 ackdrop-filter 与 @supports 覆盖），只留 1px 描边；「以博主身份评论」提示条改用面板色 #161a24 / #f0f3f7 + 细边
- 状态页：改为卡片分区（到期时间 / 服务状态），行内指标做成 pill、状态点带光晕，移动端指标换行；status.js 轮询接口不变
- 首屏性能：新增 gzip 兜底（HTML 34→11.6KB、CSS 63→11.5KB、JS 17.5→7KB），静态压缩结果按 mtime 缓存；页面缓存命中时输出 Cache-Control: public, max-age=30, stale-while-revalidate=120
- 修复：主题静态文件扩展名合法但文件不存在时返回 500，改为 404
- 主题信息：info.json 升到 2.7.1，描述精简为一行

### v3.2.17

- 底图位置：后台「页面背景装饰」新增「显示位置」四选项——跟随分辨率（默认，现状铺满视口）/ PC 左侧固定 / PC 右侧固定 / PC 左右固定；单侧模式在桌面端按固定尺寸贴底，不随分辨率缩放，并用双层 `mask` 交叉淡化上沿与内侧边缘，移动端仍铺满底部；左右模式在宽屏（≥1440px）左右各显示一张后台单独选定的底图（可相同），窄屏只保留右侧，设置项为 `pattern_position` / `pattern_left_image` / `pattern_right_image`
- 底图素材：新增第 4 张「朝天门 4K」，深浅色与 1x/2x 双分辨率各一套，后台主底图与左右固定选择器均可选用
- 移动端底图：跟随分辨率模式下，手机竖屏由「底部 46vh + cover」改为「按屏宽整图等比铺满」（`height: 56.25vw`），不再把 16:9 的图放大到只剩中间约 56%，左右两侧的江面与建筑能完整保留，上沿渐隐不变
- 关于页：作者卡去掉毛玻璃底，改为纯透明 + 1px 边框，底图完整透出（毛玻璃在浅色下泛灰、深色下压暗，观感不如透明）
- 文章列表：鼠标悬停卡片由实色 `--bg-subtle` 改为液态玻璃——斜向高光渐变 + 内描边高光 + 悬浮投影 + `saturate(200%) blur(16px)` 折射，深色下白光调至约浅色的 1/3 避免泛灰；触摸端与窄屏仍不启用悬停
- 页脚：新增「十年之约」成员标识，使用官方深浅双色图片随主题切换，桌面 20px / 移动 18px、`.55` 透明度不抢眼；跟在页脚链接行「RSS」后面，窄屏放不下自然换行不溢出，关于页因正中有完整虫洞区块而自动隐藏
- 关于页：「十年之约」区块移到人物卡正下方，透明底卡片内放成员标识（桌面 32px / 移动 28px）与官方虫洞动图（桌面 40px / 移动 34px），点击随机访问成员博客；虫洞按主题只加载对应配色的一张，不额外下载另一张
- 底图体积：高分屏底图从 3840 降为 2560×1440 中间档（朝天门 4K 由源图缩出，alpha 保持 16 级量化），4K 全屏才升 3840；前三张素材的 3840 文件本就是上采样、无细节增益，高分屏直接用 2048 原图并删除假 4K 文件——主流高分屏用户从 1.0–1.5MB 降到 0.45–0.68MB，磁盘净省约 4MB
- 底图 AVIF：全部 12 张底图按 WebP 同名生成 AVIF 副本（AV1 编码 q40），`theme_static` 路由按请求 `Accept` 头协商返回（`Vary: Accept`），CSS/模板/后台零改动，不支持的老浏览器自动回落 WebP——朝天门 4K 的 3840 档 1487KB→634KB、2560 档 678KB→439KB、2048 档 465KB→312KB，其余素材 1x 档 320–452KB→96–168KB；q40 在 13% 透明度合成后的最大像素差约 0.6/255，肉眼不可见
- 深色底图两处修正：① 深色 2560 档线条色误填为浅色主题的暗色 `(63,68,76)`，深底上灯火全隐只剩灰雾，已按深色原图的亮灰蓝 `(160,174,199)` 重建；② 深色主题底图改用 `mix-blend-mode: screen` 混合，灯线呈发光效果、整片低 alpha 雾被稀释（浅色主题保持 normal 不受影响）
- 毛玻璃：浅色 `.74/.72` → `.84`、深色 `.70/.68` → `.80`（移动端 `.9/.88`），底图从玻璃后透出的线条不再清晰可辨，「磨砂感」更实，浅色主题尤其明显
- 正文链接：Markdown 正文链接悬停下划线移除，与全站「链接无下划线」统一
- 主题管理：tech 主题卡内新增「配置」按钮，点击才展开「页面背景装饰」面板（再点收起，切换主题自动收起），面板不再常驻列表下方让人误以为所有主题都有
- 评论表单：折叠状态下整张卡片都可点击展开并自动聚焦输入框，不再只能点「写评论」那一行
- 友链页：本站信息复制区新增「复制介绍」，与卡片展示的站点简介同源
- 链接样式：补齐全局 `a { text-decoration: none }` 兜底，清掉没有类名的链接（如友链页「申请友链」）与头像/图标链接残留的浏览器默认下划线；正文悬停下划线保持不变

### v3.2.16

tech 主题视觉与可访问性整修：重做深浅色分层（实色 / 半透明 / 毛玻璃 / 透明），并补齐键盘与读屏细节。

- 页面底图：深浅各 3 套图案、1x/2x 双分辨率，随主题切换；后台「主题」页可选择图案、调整透明度（0 关闭），设置项为 `pattern_image` / `pattern_opacity` / `pattern_enabled`
- 毛玻璃分层：代码块、目录卡、评论表单三处采用毛玻璃（浅 `.74` / 深 `.70`，14–16px 模糊）；不支持 `backdrop-filter` 时回退实色，移动端降低模糊半径并提高不透明度
- 代码高亮改由主题变量统一驱动，覆盖 `markdown-body.css` 的硬编码色；深浅两态所有 token 对比度均 ≥4.5:1
- 配色修正：浅色强调色加深至 `#1f5fd6`；深色强调色实底按钮改用深字（对比度 2.52 → 7.05）；交互控件描边统一提一档到 `--border-strong`
- 交互：主题按钮三态图标（自动/浅色/深色）、文章筛选下拉支持 ↑↓/Home/End/Esc/Tab、移动端抽屉增加焦点圈定与焦点回收、目录当前项自动滚入视野、复制按钮等触控热区扩大
- 可访问性与 SEO：移除 `user-scalable=no` 与手势拦截脚本恢复缩放；补齐 `aria-controls`/`aria-expanded`/`aria-modal`/`aria-hidden`；新增 `<meta name="description">`（与 `og:description` 同源）；文章列表标题层级修正
- 构建：`csscompressor` 会把 `@supports not (` 压成 `not(` 导致降级规则静默失效，降级写法改为「默认实色 + 正向特性查询」

### v3.2.15

- 运行时数据（数据库、上传、备份、缓存）统一收敛到 `var/`，代码目录不再混入数据，`var/` 整目录被 git 忽略
- 新增 `BLOG_DATA_DIR` 环境变量，可把数据放到 Web 根之外（如 `/var/lib/infowe_blog`），升级或回滚代码不影响数据
- 首次启动自动迁移旧 `data/`、`uploads/`、`backups/`、`storage/` 与更早的 `instance/`：带文件锁、幂等执行，重名文件保留在 `var/.legacy-<时间戳>/`
- 新增 `python -m services.storage [--force]` 手动迁移命令，部署脚本可在停服后先迁移再启动
- 重写自动重启脚本 `tools/infowe-auto-restart.sh`：支持停机迁移、依赖补装、健康检查、`STOP_CMD` / `START_CMD` 配置
- 部署文档同步：Nginx `/uploads/` alias、目录权限、自动重启脚本路径全部改为 `var/`

</details>

---

## License

MIT
