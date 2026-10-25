# Python Blog（Flask + SQLite）

[![version](https://img.shields.io/badge/version-3.2.12-blue)](https://github.com/Contribuv/infowe_blog/releases/tag/v3.2.12)
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
| 评论 | 嵌套回复、审核、私密评论、图片、敏感词、IP 归属地 |
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
| 数据库 | `data/blog.db`（自动建表） |
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
│   ├── theme/tech/        # 前台主题模板
│   ├── admin/             # 后台模板
│   └── shared/            # 公共模板片段
├── static/                # 后台 CSS/JS、Vditor、highlight.js、图标
├── themes/tech/           # 主题静态资源（theme.css/theme.min.css/theme.js/info.json/preview.png）
├── uploads/               # 文章图片、评论图片、README 图片
├── data/                  # SQLite 数据库、密钥、项目同步状态
├── backups/               # 数据库备份、JSON/Markdown 导出
├── storage/cache/         # 运行缓存（头像/分享图/README 图/页面缓存）
├── fonts/                 # 水印字体
├── tools/                 # 数据迁移脚本
├── run.bat                # Windows 一键启动
└── requirements.txt
```

### 各目录职责

| 目录 | 作用 | 是否可删 |
| --- | --- | --- |
| `data/` | 数据库、密钥、同步状态 | **不可删**（删了等于重置站点） |
| `uploads/` | 用户上传文件 | 不可删（文章图片会失效） |
| `backups/` | 备份与导出文件 | 可按需清理旧备份 |
| `storage/cache/` | 运行缓存 | 可删，会自动重建 |
| `static/` | 后台与编辑器资源 | 不可删 |
| `themes/` | 主题静态资源 | 不可删 |
| `templates/` | 页面模板 | 不可删 |
| `fonts/` | 水印字体 | 不启用水印时可删 |
| `tools/` | 迁移工具 | 可删（不再迁移时） |

> `data/`、`uploads/`、`backups/`、`storage/` 不要暴露为静态目录，本项目已通过路由限制访问。
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
| 评论 | 总开关、审核、邮件通知、评论图片、敏感词 |
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

location ^~ /themes/ {
    alias /www/wwwroot/infowe.site/themes/;
    expires 7d;
    access_log off;
}

location /uploads/ {
    alias /www/wwwroot/infowe.site/uploads/;
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

    location ^~ /themes/ {
        alias /www/wwwroot/infowe.site/themes/;
        expires 7d;
        access_log off;
    }

    # 注意：这里不能写 ^~，否则下面的隐藏文件 deny 不会执行
    location /uploads/ {
        alias /www/wwwroot/infowe.site/uploads/;
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

- 存储：`storage/cache/pages/`
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
chown -R www:www data uploads backups storage
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

宝塔默认不会因为 `git pull` 自动重启。项目里的在线升级只更新代码和依赖，最后把 `data/upgrade_state.json` 写成 `done`，然后等人工重启。

如果希望升级完成后自动重启，用一个脚本就够了：脚本负责等待安装完成、清页面缓存、给 Gunicorn master 发 HUP；`post-merge` hook 负责即时触发，宝塔计划任务负责兜底。

脚本不再依赖 `upgrade_state.json` 的修改时间，而是记录**上次重启时的 Git commit**。只要 HEAD 变了（不管是后台在线升级还是手动 `git pull`），就会在安装完成后重启一次；没有新提交时直接退出。

> 下面内容都在服务器上配置，不属于项目代码，`git pull` 不会覆盖。

**第一步：创建重启脚本**

`/root/infowe-auto-restart.sh`：

```bash
#!/bin/bash
set -u

BASE=/www/wwwroot/infowe.site
STATE="$BASE/data/upgrade_state.json"
HEADFILE="$BASE/data/.auto-restart.head"
LOCK="$BASE/data/.auto-restart.lock"

exec 9>"$LOCK"
flock -n 9 || exit 0

CURRENT=$(git --git-dir="$BASE/.git" --work-tree="$BASE" rev-parse HEAD 2>/dev/null || true)
LAST=$(cat "$HEADFILE" 2>/dev/null || true)
[ -n "$CURRENT" ] || exit 1
[ "$CURRENT" = "$LAST" ] && exit 0

# 在线升级中：等 pip install 完成
running=0
if grep -Eq '"state"[[:space:]]*:[[:space:]]*"running"' "$STATE" 2>/dev/null; then
  running=1
  for i in $(seq 1 300); do
    if grep -Eq '"state"[[:space:]]*:[[:space:]]*"done"' "$STATE" 2>/dev/null; then
      break
    fi
    if grep -Eq '"state"[[:space:]]*:[[:space:]]*"failed"' "$STATE" 2>/dev/null; then
      echo "upgrade failed, skip restart"
      exit 1
    fi
    sleep 2
  done
fi

if [ "$running" = "1" ]; then
  grep -Eq '"state"[[:space:]]*:[[:space:]]*"done"' "$STATE" 2>/dev/null || exit 1
fi

# 失败状态不自动重启，避免带着未装好的依赖启动
if grep -Eq '"state"[[:space:]]*:[[:space:]]*"failed"' "$STATE" 2>/dev/null; then
  exit 1
fi

# 取最老的 gunicorn 进程，即 master
MASTER=$(pgrep -o -f 'gunicorn.*infowe\.site' || true)

if [ -z "${MASTER:-}" ]; then
  MASTER=$(ps -eo pid,args | awk '
    /[g]unicorn/ && $0 !~ /worker/ && /infowe\.site/ { print $1; exit }
  ')
fi

if [ -z "${MASTER:-}" ] || ! kill -0 "$MASTER" 2>/dev/null; then
  echo "gunicorn master not found"
  exit 1
fi

# 清页面缓存，再平滑替换 worker
rm -rf "$BASE/storage/cache/pages"/* 2>/dev/null || true

if kill -HUP "$MASTER"; then
  echo "$CURRENT" > "$HEADFILE"
  echo "$(date '+%F %T') reloaded gunicorn master $MASTER commit ${CURRENT:0:8}"
fi
```

```bash
chown root:root /root/infowe-auto-restart.sh
chmod 755 /root/infowe-auto-restart.sh
sh -n /root/infowe-auto-restart.sh
```

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
cat /www/wwwroot/infowe.site/data/upgrade_state.json
cat /www/wwwroot/infowe.site/data/.auto-restart.head

/root/infowe-auto-restart.sh
sleep 2

cat /var/log/infowe-auto-restart.log
ps -eo pid,ppid,lstart,args | grep '[g]unicorn'
```

预期：

- 日志出现 `reloaded gunicorn master ... commit ...`
- 生成或更新 `.auto-restart.head`
- master PID 不变
- worker PID 变新、启动时间变新

手动测试时如果 HEAD 和 `.auto-restart.head` 已经相同，脚本会直接退出，这是正常的。要测试真实重启，可以用一次后台在线升级，或在测试前删掉：

```bash
rm -f /www/wwwroot/infowe.site/data/.auto-restart.head
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
| 上传/备份 500 | 目录无写权限 | `chown -R www:www data uploads backups storage` |
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

升级**不会覆盖** `data/blog.db`。每次启动都会以 `schema.sql` 为基准自动同步表结构：

- 新增字段：自动 `ALTER TABLE ADD COLUMN`
- 删除字段：SQLite 3.35+ 自动 `DROP COLUMN`，低版本跳过并记录
- 检测到结构变化时，先自动备份到 `backups/schema_upgrade_YYYYmmdd_HHMMSS.db`
- 只同步字段，不删除表、不修改已有字段类型
- 旧版 `instance/blog.db` 会自动迁移到 `data/blog.db`

查看 SQLite 版本：

```bash
.venv/bin/python -c "import sqlite3; print(sqlite3.sqlite_version)"
```

建议升级前仍在后台「数据管理」手动备份一次。

---

## 备份与恢复

- 后台「数据管理 → 数据库备份」使用 SQLite 在线备份，运行中也可安全备份
- 备份文件：`backups/blog_YYYYmmdd_HHMMSS.db`
- 恢复：后台上传 SQLite 备份，或停止服务后用备份文件覆盖 `data/blog.db`
- 支持 JSON 全量导出、Markdown（zip）导出

---

## 常见问题

### 忘记后台密码

```bash
.venv/bin/python -m flask --app app reset-password
```

### 数据库在哪里

`data/blog.db`；备份在 `backups/`。

### 首次启动没有文章

空库会自动写入《致使用者的一封信》。如果使用了自己的数据库，以数据库内容为准。

### 上传 / 备份失败

```bash
chown -R www:www data uploads backups storage
```

### 修改后台入口后进不去

重启服务；如果路径写错，把 `settings.admin_path` 改回 `admin`（见上文命令）。

### SQLite 报 database is locked

- 已启用 WAL 与 8 秒 busy_timeout
- 建议 gunicorn/uWSGI 使用 2 个 worker，不要开太多写进程
- 避免多个实例共用同一个 `data/blog.db`

---

## 安全建议

- 首次登录后立即修改默认密码
- 建议开启 OTP 双重验证
- 使用 HTTPS，并在后台配置正确的 `site_url`
- 把后台入口改成不易猜到的路径
- 定期备份 `data/blog.db` 与 `uploads/`
- 不要把 `data/`、`uploads/`、`backups/` 暴露为静态目录
- 生产环境只开放 80/443，5000 仅监听 `127.0.0.1`

---

## 更新日志

- 版本：**v3.2.12**
- GitHub Releases：<https://github.com/Contribuv/infowe_blog/releases>
- Gitee Releases：<https://gitee.com/infowe/infowe_blog/releases>

---

## License

MIT
