# Python Blog（Flask + SQLite）

[![version](https://img.shields.io/badge/version-3.4.22-blue)](https://github.com/Contribuv/infowe_blog/releases/tag/v3.4.22)
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

- [✨ 功能特性](#功能特性)
- [🧰 技术栈](#技术栈)
- [✅ 环境要求](#环境要求)
- [🚀 快速开始](#快速开始)
- [📁 目录结构](#目录结构)
- [🔗 URL 结构](#url-结构)
- [🔐 后台入口](#后台入口)
- [⚙️ 配置说明](#配置说明)
- [🛠 宝塔面板部署](#宝塔面板部署)
- [🧩 其他部署方式](#其他部署方式)
- [📦 数据迁移](#数据迁移)
- [⬆️ 升级与数据库结构](#升级与数据库结构)
- [💾 备份与恢复](#备份与恢复)
- [❓ 常见问题](#常见问题)
- [🛡 安全建议](#安全建议)
- [📝 更新日志](#更新日志)
- [📄 License](#license)

---

## 功能特性

### 前台

| 模块 | 说明 |
| --- | --- |
| 文章 | Markdown 写作、分类、标签、精选、阅读时长、访问计数、上下篇 |
| 文章状态 | `published` / `draft` / `hidden`（隐藏文章仅 URL 可直达） |
| 浏览 | 全文搜索、标签聚合、年份归档、分页 |
| 订阅 | `/feed.xml` RSS |
| 评论 | 嵌套回复、审核、私密评论、图片、敏感词、IP 归属地、分页 |
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
- 分类 / 标签 / 项目 / 友链 / 时间线 / 评论：增删改查与批量操作
- 上传：图片 / 媒体 / 附件，白名单与大小限制，水印
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
| 图片 | Pillow（水印、分享图、头像裁剪） |
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
| 上传 | 图片/媒体/附件白名单、单文件大小、水印 |
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

### 6. 网站与反向代理

宝塔 → 网站 → 添加站点：

- 域名：`www.infowe.site`、`infowe.site`
- 根目录：`/www/wwwroot/infowe.site`
- PHP：纯静态
- 不要创建 FTP/数据库

站点设置 → **反向代理 → 添加**：

| 项 | 值 |
| --- | --- |
| 代理名称 | python |
| 目标 URL | `http://127.0.0.1:5000` |
| 发送域名 | `$host` |

保存后，确认 **80 和 443 的 server 块都包含**：

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
}
```

> 宝塔的反向代理有时只写入 80，443 仍是静态配置，会导致 **403**。
> 遇到 403 时，检查 443 的 `server {}` 是否也有 `location /`。

### 6.1 静态资源交给 Nginx（推荐）

如果所有请求都 `proxy_pass`，CSS/JS/图片也会经过 Flask。把静态目录交给 Nginx：

```nginx
# 静态资源直出也必须声明 UTF-8，否则 CSS/JS 里的中文会乱码。
# 注意：Nginx 默认 charset_types 不包含 text/css，必须显式补上。
# 这两行放在 server {} 内、所有 location 之前。
charset utf-8;
charset_types text/html text/css text/plain text/xml text/javascript application/javascript application/json application/rss+xml image/svg+xml;

# 必须放在 location / 之前
location ^~ /static/ {
    alias /www/wwwroot/infowe.site/static/;
    expires 7d;
    access_log off;
}

# 注意：这里不能写 ^~，否则下面的模板目录 deny 不会执行
location /themes/ {
    alias /www/wwwroot/infowe.site/themes/;
    expires 7d;
    access_log off;
}

# 主题模板源码不对外（/themes/<key>/templates/）
location ~ ^/themes/[^/]+/templates/ {
    deny all;
    return 404;
}

location /uploads/ {
    alias /www/wwwroot/infowe.site/var/uploads/;
    expires 7d;
    access_log off;
}

# 禁止访问上传目录里的隐藏文件（.originals 等）
location ~ ^/uploads/\. {
    deny all;
}
gzip on;
gzip_min_length 1k;
gzip_types text/plain text/css application/javascript application/json application/rss+xml image/svg+xml;
```

> `alias` 末尾斜杠要与 `location` 一致；`/share-thumb`、`/avatar`、`/readme-img` 是动态生成，不要 alias。
> `/uploads/` **不要写 `^~`**，否则下面的 `location ~ ^/uploads/\.` 不会执行，`.originals` 无痕原图可能被直接下载。
> 静态资源直出后不再经过 Flask 的白名单校验，因此必须保留 `deny` 规则，且不要放开脚本扩展名上传。

> **CSS/JS 中文乱码**：如果静态文件由 Nginx 直出，必须确认响应头带 `charset=utf-8`：
> ```bash
> curl -I https://www.infowe.site/static/css/admin.css
> curl -I https://www.infowe.site/static/js/admin.js
> ```
> 期望分别是 `text/css; charset=utf-8` 和 `application/javascript; charset=utf-8`（部分 Nginx 返回 `text/javascript; charset=utf-8`，也正常）。
> 只返回 `text/css` 说明 `charset_types` 少了 `text/css`，即使已经写了 `charset utf-8;` 也不会生效。
> 项目内 CSS 首行已内置 `@charset "UTF-8";`，自有 JS 已带 UTF-8 BOM；但 Nginx 仍建议按上面的配置声明，避免其他静态资源出现同类问题。

### 6.2 完整 Nginx 配置示例

下面这份配置可以直接对照宝塔生成的站点文件改。**证书路径、日志路径和 `include` 以宝塔实际生成的为准，不要整段覆盖。**

```nginx
# HTTP：统一跳 HTTPS。
# 如果宝塔使用文件方式续签证书，保留它生成的 .well-known 配置。
server {
    listen 80;
    listen [::]:80;
    server_name infowe.site www.infowe.site;

    return 301 https://www.infowe.site$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name infowe.site www.infowe.site;

    # 按宝塔「SSL」页面实际路径填写
    ssl_certificate     /www/server/panel/vhost/cert/infowe.site/fullchain.pem;
    ssl_certificate_key /www/server/panel/vhost/cert/infowe.site/privkey.pem;
    # 其余 ssl_* 配置保持宝塔生成的内容

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    # HSTS 只保留一条；如果宝塔 SSL 配置里已有，不要重复添加

    charset utf-8;
    charset_types text/html text/css text/plain text/xml text/javascript application/javascript application/json application/rss+xml image/svg+xml;

    client_max_body_size 64m;

    gzip on;
    gzip_min_length 1k;
    gzip_types text/plain text/css application/javascript application/json application/rss+xml image/svg+xml;

    # 静态资源直出
    location ^~ /static/ {
        alias /www/wwwroot/infowe.site/static/;
        expires 7d;
        access_log off;
    }

    # 注意：这里不能写 ^~，否则下面的模板目录 deny 不会执行
    location /themes/ {
        alias /www/wwwroot/infowe.site/themes/;
        expires 7d;
        access_log off;
    }

    # 主题模板源码不对外（/themes/<key>/templates/）
    location ~ ^/themes/[^/]+/templates/ {
        deny all;
        return 404;
    }

    # 注意：这里不能写 ^~，否则下面的隐藏文件 deny 不会执行
    location /uploads/ {
        alias /www/wwwroot/infowe.site/var/uploads/;
        expires 7d;
        access_log off;
    }

    # 禁止下载 .originals 无痕原图
    location ~ ^/uploads/\. {
        deny all;
    }

    # 其余请求全部交给 Flask，不需要 rewrite / try_files
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_read_timeout 120s;
    }
}
```

> 如果 Nginx 版本较新，`listen 443 ssl http2;` 可以改成 `listen 443 ssl;` 加 `http2 on;`。
> 宝塔站点配置里通常还有 `include enable-php-xx.conf`、`access_log` 等，保留即可；我们只改反代、静态资源和上面的几项。
> 80 和 443 都要有 `location /`。只在 443 配反代、80 落到静态目录，是宝塔部署里很常见的 403 原因。

### 6.3 伪静态 / Rewrite（重要）

宝塔「网站 → 设置 → 伪静态」**保持为空**，不要选择 WordPress、ThinkPHP 等模板。

对应的伪静态文件正确写法就是**空文件**：

```nginx
# /www/server/panel/vhost/rewrite/python_infowe_site.conf
# 保持为空即可。不要写：
# location / { ... }
# proxy_pass ...
# try_files ...
```

Flask 已经处理了这些路由：

- `/post/<id>`
- `/tag/<tag>`
- `/search/<q>`
- `/archive/<year>`
- 旧参数 URL 的 301 跳转
- 后台自定义入口 `admin_path`

因此**不需要** Nginx `rewrite`、`try_files` 或 `index.php` 规则。

检查宝塔自动生成的伪静态文件：

```bash
ls /www/server/panel/vhost/rewrite/
grep -RE "location /|proxy_pass" /www/server/panel/vhost/rewrite/python_*.conf
```

如果 `rewrite/python_xxx.conf` 里出现 `location /` 或 `proxy_pass`，请清空该文件，或删除站点配置里对应的 `include`。否则会和 6.1 里的 `location /` 重复，可能出现 403 / 502 / 代理规则冲突。

验证应用路由：

```bash
curl -I https://www.infowe.site/tag/Python
curl -I https://www.infowe.site/search/Flask
curl -I https://www.infowe.site/archive/2026
```

应返回 `200` 或正常的 `301`，不是 `404`。80 和 443 的 `server {}` 都要有同样的 `location /` 反代。

### 6.4 页面缓存（已内置）

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

伪静态本身不需要额外 rewrite：`location /` 反代到 5000 即可。
自定义后台入口 `admin_path` 也不需要改 Nginx，项目内部路由会自动生成。

> 如果以后访问量更大，可以再加 Nginx `proxy_cache` 或 CDN 作为一级缓存；
> 记得对带 Cookie 的请求 bypass，并在发布/评论后 purge。

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

#### 10.2 Gunicorn 自动重启（可选）

宝塔默认不会因为 `git pull` 自动重启。项目里的在线升级只更新代码和依赖，最后把 `var/upgrade_state.json` 写成 `done`，然后等人工重启。

如果希望升级完成后自动重启，用仓库里的脚本就够了：它负责等待安装完成、补装依赖、必要时停机迁移数据目录、清页面缓存，再平滑重载或完整启动；`post-merge` hook 负责即时触发，宝塔计划任务负责兜底。

脚本不再依赖 `upgrade_state.json` 的修改时间，而是记录**上次重启时的 Git commit**。只要 HEAD 变了（不管是后台在线升级还是手动 `git pull`），就会在安装完成后重启一次；没有新提交时直接退出。

> 脚本随仓库提供（`tools/infowe-auto-restart.sh`）；hook 与计划任务在服务器上配置，`git pull` 不会覆盖。

**第一步：安装脚本**

完整脚本已随仓库提供：`tools/infowe-auto-restart.sh`。它负责比较 Git HEAD、等待在线升级、补装依赖、停机迁移数据目录、清页面缓存、平滑重载和健康检查。

```bash
cp /www/wwwroot/infowe.site/tools/infowe-auto-restart.sh /root/infowe-auto-restart.sh
chown root:root /root/infowe-auto-restart.sh
chmod 755 /root/infowe-auto-restart.sh
sh -n /root/infowe-auto-restart.sh
```

脚本顶部可改的变量（也可用同名环境变量传入）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `BASE` | `/www/wwwroot/infowe.site` | 项目目录 |
| `PY` | `$BASE/.venv/bin/python` | 项目 venv 的解释器 |
| `PORT` | `5000` | 健康检查用的本地端口 |
| `STOP_CMD` | 空 | 停止命令，如 `systemctl stop infowe`；留空则对 gunicorn master 发 QUIT |
| `START_CMD` | 空 | 启动命令，如 `systemctl start infowe`；留空则重放原 gunicorn 命令行 |
| `BLOG_DATA_DIR` | `$BASE/var` | 数据目录，需与站点实际配置一致 |

行为说明：

- `post-merge` 和计划任务同时触发也不会重复执行（`flock` + HEAD 记录）
- 在线升级状态是 `running` 时最多等 10 分钟；`failed` 或超时直接退出，不带坏依赖重启
- `requirements.txt` 哈希变化时先在 venv 里 `pip install -r requirements.txt`（手动 `git pull` 也会补装）
- **首次迁移到 `var/`**：停服 → `python -m services.storage --force` → 清页面缓存 → 启动 → 健康检查；迁移失败则不启动，避免旧库继续写入
- 普通升级：清页面缓存 → `kill -HUP <master>` 平滑重载，不中断请求
- 启动方式：优先用 `START_CMD`；没配置时按原 master 的 gunicorn 命令行重放，日志写到 `var/gunicorn-restart.log`

> 用宝塔 / systemd / supervisor 守护时，建议显式配置 `STOP_CMD`、`START_CMD`，比脚本重放进程命令行更可靠。

**第二步：可选，配置即时触发**

`post-merge` 在 `git pull` 成功后执行。注意此时 `pip install` 还没结束，所以 hook 只负责启动脚本，真正的重启由脚本等待 `done` 后再做。

```bash
cat > /www/wwwroot/infowe.site/.git/hooks/post-merge <<'EOF'
#!/bin/sh
nohup /root/infowe-auto-restart.sh \
  >>/var/log/infowe-auto-restart.log 2>&1 &
EOF

chmod +x /www/wwwroot/infowe.site/.git/hooks/post-merge
```

**第三步：宝塔计划任务兜底（可选，但推荐）**

`post-merge` 正常触发时，其实不需要计划任务。它不是强制项；但当前如果 hook 偶尔不触发，计划任务是最简单的兜底。

宝塔 → 计划任务 → 添加任务：

- 类型：Shell 脚本
- 名称：infowe 自动重启
- 周期：每分钟
- 脚本：`/root/infowe-auto-restart.sh`

脚本里有 `flock` 和 HEAD 记录，hook 和计划任务同时存在也不会重复重启。如果不加计划任务，就至少确认 `post-merge` 确实收到触发，并检查 `/var/log/infowe-auto-restart.log`。

**验证**

```bash
cat /www/wwwroot/infowe.site/var/upgrade_state.json
cat /www/wwwroot/infowe.site/var/.auto-restart.head

/root/infowe-auto-restart.sh
sleep 2

cat /var/log/infowe-auto-restart.log
ps -eo pid,ppid,lstart,args | grep '[g]unicorn'
```

预期：

- 普通升级：日志出现 `已平滑重载 gunicorn master ...`，master PID 不变、worker 变新
- 首次迁移：日志依次出现 `检测到旧版数据目录`、`迁移数据目录`、`服务已恢复`，迁移完成后 `var/.migrated` 生成
- 生成或更新 `var/.auto-restart.head`、`var/.auto-restart.req`
- 迁移完成后旧的 `data/`、`uploads/`、`backups/`、`storage/` 为空目录（脚本会尽力清理）

手动测试时如果 HEAD 和 `.auto-restart.head` 已经相同，脚本会直接退出，这是正常的。要测试真实重启，可以用一次后台在线升级，或在测试前删掉：

```bash
rm -f /www/wwwroot/infowe.site/var/.auto-restart.head
```

> 旧的 `.auto-restart.stamp` 可以删掉，新脚本不再使用。

如果 `upgrade_state.json` 是 `running`，脚本会等它结束；如果是 `failed`，不会自动重启，避免带着未装好的依赖启动。其他情况下，只要 Git HEAD 变了就会重启。

> 手动执行 `/root/infowe-auto-restart.sh` 时，输出只在终端；日志文件只记录 hook 或计划任务触发的重启。HEAD 没变化时脚本会静默退出，不会写日志。
> `HUP` 只对 master 发，不要对 worker 发。
> 手动 SSH 执行 `git pull` 后，只要 HEAD 变了，hook 和计划任务都会触发自动重启；如果本次升级状态是 `failed`，会跳过自动重启，需要先处理依赖再手动 `kill -HUP <master>`。
> 如果以后 Web 服务从 root 改成 www 运行，`.git/hooks` 通常没有权限操作 root 的 Gunicorn master，这时把脚本放到 root 的宝塔计划任务里执行。
> Gunicorn 的 `--reload` 只监听 Python 文件变化，不处理 `pip install` 的新依赖，也不适合替代这里的明确重启。

### 宝塔常见错误

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 403 Forbidden（nginx） | 443 server 没有反代，落到静态目录 | 在 443 加 `location /` |
| 502 Bad Gateway | uWSGI/gunicorn 未启动、端口/目录不对 | 查看项目日志，确认 5000 返回 200 |
| 413 Request Entity Too Large | Nginx 上传上限太小 | `client_max_body_size 64m` |
| 上传/备份 500 | 目录无写权限 | `chown -R www:www var` |
| 登录后重定向循环 | `site_url` 与访问域名不一致，或未传 `X-Forwarded-Proto` | 修改 `site_url`，检查 Nginx 头 |
| 证书 key usage 错误 | 证书类型/链不对 | 重新申请或重新部署证书 |
| 样式/图片 404 | 只代理了 `/`，漏了 `/static`、`/uploads` | 全部路径统一反代 |

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

- 版本：**v3.4.22**
- GitHub Releases：<https://github.com/Contribuv/infowe_blog/releases>
- Gitee Releases：<https://gitee.com/infowe/infowe_blog/releases>

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

---

## License

MIT
