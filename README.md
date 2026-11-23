# Python Blog（Flask + SQLite）

[![version](https://img.shields.io/badge/version-3.9.53-blue)](https://github.com/Contribuv/infowe_blog/releases/tag/v3.9.53)
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

当前版本：**v3.9.53**

> 最近一次更新完整展开；更早的 152 个版本压缩为摘要，统一收在下方折叠区。

### v3.9.53

- **折叠条去双层边框**：表单外层已是卡片边界，占位条不再重复描边与底色，避免「框里套框」
- **折叠条与评论卡同宽**：折叠态去掉表单内距并按评论卡缩进（桌面 17px / 移动 13px），左右边缘与下方楼层完全对齐，不再收窄一截
- **去掉占位条悬停变色**：鼠标划过整条不再变色（保留手型提示可点），只有「登录」按钮响应悬停
- **登录按钮悬停加强**：底色加深一档 + 主色投影 + 上浮 1px，按下回弹，比原来仅轻微提亮更明显
- **动作行文字对齐**：「登录」「收起」统一 20px 行高与 inline-flex 居中，与字数统计、快捷提示、提交按钮同一条中线
- **跳过验证后直接进入评论**：点「跳过验证，直接评论」会展开评论框并平滑滚动到表单、聚焦昵称输入

### v3.9.52

- **评论区未登录入口改版**：去掉表单上方「填写昵称 + 邮箱即可参与评论…」整条提示与「登录 / 注册」双链接，折叠条右侧改为一个实心「登录」按钮（对应参考站把登录放在发送位置的写法）
- **登录入口收进表单**：点「登录」直接打开登录浮窗（登录 / 注册 / 跳过验证），不会顺带展开评论框；展开评论框后「登录」退到动作行，与「收起」同级
- **跳过验证的语义**：跳过验证只展开昵称 / 邮箱输入，不建立身份，折叠条仍保留登录入口；提交成功后由服务端记住身份并显示身份条
- **已登录身份条保留**：博主 / 注册用户 / 已记住访客仍显示紧凑身份信息、管理账号与退出入口，不再出现面向新访客的长文案
- 其他：登录按钮统一按 `data-login-open` 绑定，评论抽屉的「登录」入口同步兼容

### v3.9.51

- **通知中心重构（正确性）**：博主与读者彻底分流——新增 `admin_notifications` 记录「新评论 / 被回复」，待审核项实时查 `comments`，不再把评论 id 当通知 id；已读接口不再因评论开关返回 403
- **通知时机修正**：待审核评论不再提前写站内通知，审核通过（后台单条 / 批量 / AI 自动通过 / AI 工具通过）统一补写「已通过」「被回复」「博主通知」；删除评论树时同步清理通知，铃铛不再指向不存在的评论
- **通知链接分页**：通知 URL 按 `comments_per_page` 算出真实页码（`?cpage=n#comment-id`），不再跳到错误分页的锚点
- **抽屉改版对齐评论区参考**：顶部改为「小标题 + 主标题 + 说明」+ 图标，底部固定三栏导航（我的概览 / 我的评论 / 我的账户）；「我的评论」补搜索框与「全部 / 提及 / 我的 / 待审」分段筛选，「我的账户」展示身份资料或访客登录入口
- **概览排版**：统计格改 2×2 带图标，热力图补星期刻度与「近 N 周 · 共 N 条」，一周分布柱顶显示数值，底部新增「最近发言」（待审项标注「审核中」）
- **通知列表可读性**：待处理条目最多两行、标签与时间回到首行对齐，未读总数与角标严格一致
- **评论开关联动**：关闭评论后前台不再渲染铃铛，`notify.js` 也不再轮询通知接口
- 其他：`comment_notify` 默认值统一为「开」（后台表单与代码判断一致）；已有公开评论一次性回填进博主通知表（标记已读，只作历史记录）

### v3.9.50

- **审核结果邮件通知**：后台「通过 / 拒绝 / 删除」读者账号后会给本人发信——通过时告诉他可以登录了，拒绝时带上你填写的理由与联系邮箱，删除时发一封注销回执（只说明账号已删除、评论保留，不引导重新注册）；SMTP 未配置或开关关闭时静默跳过，不影响后台操作
- **拒绝理由输入框**：用户管理的「审核说明」列改为可编辑，理由随「拒绝」提交并落库（`review_note`）；点「通过」不会带上这个字段
- **拒绝立即生效**：`verify_token` 增加审核状态校验，被拒绝 / 待审核的账号即使已经登录，token 也会立刻失效，不能再靠 30 天有效期绕过
- **删除保留历史**：删除只清 `reader_users` 一行，评论正文、评论身份、审核留存全部保留，可在「留存记录」里按邮箱哈希追溯；操作写入审计（`user.delete`）
- **账号通知开关**：后台设置新增「账号审核结果通知」，与评论邮件通知解耦，可单独关闭
- 其他：留存记录补 `user.review` / `user.review.queue` / `user.delete` 中文动作名，不再显示英文原码

<details>
<summary><b>历史版本（v3.9.52 及更早，共 152 个版本，点击展开）</b></summary>

### v3.9.49

- **读者账号体系**：邮箱 + 密码注册 / 登录，登录态用 itsdangerous 签名 token 写入 HttpOnly Cookie（`blog_reader_session`），前端只通过 `/api/reader/me` 读状态；注册需先过算术图形验证码，昵称走 AI 机器审核，判定违规转人工并留痕
- **站内通知中心**：评论区铃铛 + 右侧抽屉，四个 tab（概览 / 我的评论 / 我的回复 / 我的@）；未读角标与评论区入口同步，博主视角额外汇总待审核与新评论动态
- **我的概览**：统计格、待处理（待审核 + 未读通知合并成收件箱）、活跃度热力图、一周分布；博主按 `is_owner` 归集、访客按 `email_hash` 归集，避免换邮箱后统计归零
- **评论投票**：新增点赞 / 不喜欢（`comment_likes.kind`），同一身份对同一条只能一票，再点取消、点另一边改票；待审核评论不出现投票与回复入口
- **评论弹窗与身份条**：身份条改为纯文字链、统一 13px 与行高；游客已有身份时不再重复出现「登录」；提示文案更新
- **待审核评论常驻**：本人提交的待审核评论在评论区置顶常驻（不占用公开分页名额），翻页也不会消失
- **缓存与身份同步**：个性化页面 `no-store`，JSON 接口一律不缓存，退出登录后浏览器前进 / 后退不会再显示旧身份
- 其他：楼中楼回复图标与楼主行对齐、评论灯箱与投票状态样式统一

### v3.9.48

- **灯箱打开时隐藏悬浮按钮**：回到顶部 / 跳到评论 / 评论浮窗按钮加入 `body.lightbox-open` 隐藏名单；此前只靠 z-index 压在遮罩下，毛玻璃上仍能看到淡淡轮廓

### v3.9.47

- **评论图片灯箱统一**：评论区灯箱改用与照片墙 / 文章相同的 `.pw-lightbox` / `.pw-lb-*` 结构，遮罩、毛玻璃、按钮悬停、计数、备注与移动端尺寸全部共用
- **评论多图轮转**：同一条评论区内的图片作为一组，可上一张 / 下一张；只有一张时自动隐藏上下页与计数；保留捏合缩放、拖动、双击还原，并新增横滑切图
- **评论灯箱键盘与关闭**：支持 `←` / `→` 切换、`Esc` 关闭，打开时隐藏导航、锁定页面滚动
- **极简备注规则**：图片备注只在用户写了自定义说明时显示；`[]` 为空或「图片 / image / img / photo / picture」等占位词不显示，也不占位
- **占位 alt 清洗**：文章正文、文章灯箱、评论渲染、评论灯箱四处统一处理，历史内容里的「图片」也不再当作备注

### v3.9.46

- **灯箱遮罩提高不透明度**：深色 `.74 → .9`、浅色 `.8 → .92`，保留 `blur(18px)` 的毛玻璃质感，但不再透出页面文字与卡片，避免干扰图片阅读

### v3.9.45

- **灯箱按钮悬停**：照片墙与文章灯箱共用按钮悬停——背景提亮、边框变白、轻微放大，按下缩回；左右按钮保留垂直居中，不会跳动
- **文章灯箱多图轮转**：整篇文章的图片作为一组，任意一张点开都能上一张 / 下一张；只有一张图时上下页与计数自动隐藏
- **文章灯箱复用照片墙样式**：遮罩、模糊、内边距、图片圆角与阴影、按钮、计数、备注全部对齐，移动端尺寸同步
- **灯箱主题自适应**：配色改用 CSS 变量，深色为近黑遮罩 + 白字，浅色为纸白遮罩 + 深色字，按钮同步切换白底深色图标
- **灯箱毛玻璃**：深色遮罩 `.74`、浅色 `.8`，配合 `blur(18px) saturate(120%)`；手机降为 `blur(12px)`，不支持毛玻璃的浏览器退回近乎不透明以保证对比

### v3.9.44

- **修正后台背景开关文案**：标题由「首页背景」改为「全站背景」，说明改为「前台全站显示，文章与项目详情页自动降级（粒子更少、不画连线）」，并去掉已经不存在的前台鼠标光晕描述
- **代码注释同步**：`particles.js` 与 settings 默认值注释一并更新，避免后续维护时按旧文案理解

### v3.9.43

- **全站代码粒子背景**：登录页那套代码字符粒子抽成 `static/js/particles.js`，前台全站挂载；阅读页（文章 / 项目详情）降级为 16 个粒子、不画连线、透明度 0.6，其它页面 30 个带连线
- **粒子开关**：后台「设置 → 首页背景」可整体启停，默认开启；关闭后所有页面不再输出 canvas 与脚本
- **粒子性能与可访问性**：切到后台标签页自动暂停，系统开启「减少动态效果」不启动，打印时隐藏；前台不显示鼠标光晕，登录页保留
- **评论表单阴影**：主评论表单改用全站卡片阴影，与文章卡片一致；内联回复框仍保持无阴影
- **浅色页脚层次**：页脚底色收到与页面相差约 4 级，顶线改成 11% 文字色渐变，既看得出「地面」又不突兀
- **页头分割线**：首页头与子页页头的 1px 实线改成两端淡出的渐变，浅色下不再像硬边框
- **登录页结构修正**：主题切换与粒子脚本拆开，补上缺失的 `</script>`，外部脚本正常加载

### v3.9.42

- **升级横幅只在有新版本时显示**：没有更新或检测失败时不再显示「已是最新版本」占位条，仪表盘更干净，也消除了进入页面时「正在检查更新…」的闪动
- **检查更新入口移到页头**：仪表盘标题右侧新增「检查更新」按钮，手动检测时按钮依次反馈「正在检测… / 发现新版本 / 已是最新 / 检测失败」
- **有新版本才展开横幅**：自动或手动检测到新版本后，横幅才出现并给出「去升级」入口

### v3.9.41

- **评论图片审核隔离**：评论图改走 `/comment-img` 中转，未通过审核（待审核 / 已拒绝 / 已删除）返回「审核中」占位图，审核通过后才返回原图；`/uploads/comment/...` 直链一律 404
- **带图评论强制人工**：AI 托管遇到含图评论直接转人工（`ai_state=review`），不再自动放行
- **拒绝不删图、删除才删图**：拒绝只改状态；删除评论时连同整棵回复树里的图片从本地与 OSS 一并清理
- **评论图走 OSS**：通过审核后 `/comment-img` 302 到对象存储（公有直链 / 私有现签），未同步完成时本地兜底；直链 404，不再暴露 `/uploads/comment`
- **后台审核体验**：评论列表显示「含图 · 人工审核」标记与 64×64 缩略图；点缩略图弹出浮窗预览原图，多图可左右切换，支持 `Esc` / 点遮罩 / `×` 关闭，键盘 `←` `→` 切图
- **上传预览**：评论图上传后本地用 `blob:` 预览，不再依赖已封禁的服务端直链

### v3.9.40

- **照片墙按日分组**：恢复「月份 → 日期 → 网格」，每天一个独立小网格与日期标题（如「11 月 17 日 · 4 张」），不再把整月挤成一张图墙
- **NEW 标记**：最新 7 天文章里的照片打 NEW 标；用版本号 + localStorage 记录，第一次访问才亮，看过自动消失
- **时间线收尾文案**：「已经翻到最早了 · 文章写到哪里，照片就记到哪里」；照片超过 500 张时提示只展示最近 500 张
- **移动端间距**：日期 16px、月份 28px、底部文案 32px，网格 3 列

### v3.9.39

- **照片缩略图统一 4:3**：时间线不再按原图比例排得高低参差，也不裁成 1:1 方块。本站 45 张照片的宽高比中位数正好是 4:3，统一后平均可见面积 75.1%（1:1 只有 68.5%），格子尺寸完全一致（123.2×92.4）
- **照片时间线按月连续排列**：取消「每天一张独立网格」，同月照片接排，行尾不再大段留白。6 列下格子利用率从 44% 提升到 62.5%（11 月 16 张从 5 段半空变成 3 行 89% 填满）；日期信息移入卡片悬停提示与灯箱
- **懒加载预加载距离收紧**：400px → 200px，首屏缩略图请求从 19 张降到 16 张，滚动时按需递增
- **页面缓存签名改用纳秒 mtime**：修复开发时同一秒内连续改模板、缓存仍命中旧 HTML 的问题

### v3.9.38

- **灯箱加载态排版**：加载中图片还没有 `src` 时先给一个占位尺寸（PC 520×315 / 手机 312×287），「图片加载中」与下方「收录于…」文章名不再挤在一起；实测间距 PC 159px、手机 139px
- **提示与图片间距**：灯箱内容列间距 12px → 14px，加载提示左右留 16px，长文案不贴边

### v3.9.37

- **照片墙**：新页面 `/photos`，从文章正文与封面自动提取图片，按文章发布时间分月/日分组；「时间线 / 照片流」两种视图切换，照片流按宽度自适应 1~4 列。后台「导航菜单」可单独启停
- **照片墙灯箱**：计数、收录文章链接、预加载与「加载中」动画；加载失败显示提示而不是破图；支持键盘、滑动、点击关闭
- **缩略图与流量**：`/photo-thumb` 本地生成 320/560/960 档 WebP，`sizes` 按实际格子宽度计算，列表统一选 320w；本地没有源图时回退 OSS
- **灯箱大图**：默认 302 到 OSS（公有直链 / 私有现签），8 秒未响应自动回退本地；加载期间图片不可见，不会再出现「破图 + 文件名」
- **水印存储简化**：上传时按当前开关决定是否叠水印，不再另存 `originals` 副本；历史 `originals` 一并清理（本地与 OSS）
- **孤儿清理重做**：对象存储侧改用 ListObjectsV2 遍历桶（历史对象、手动上传也能识别），本地与 OSS 合并列出并标记来源；新增「全部 / 仅本地 / 仅 OSS」筛选
- **批量删除提速**：每批 4 个并发删除，前端按批更新进度、逐行移除，不再整批等几分钟
- **确认对话框**：后台新增 `adminConfirm`，替代原生 confirm；OSS 插件页的孤儿区收敛到「文件清理」，只保留跳转
- **图片懒加载**：正文、友链、评论区、后台补齐 `loading="lazy"`，正文补 `decoding="async"`
- **文章页灯箱**：打开时隐藏导航，与照片墙一致，不再被毛玻璃导航压住
- **导航**：「照片墙」改名「照片」，位置调到「归档」之后
- **缓存**：`/photos` 不再让浏览器缓存旧 HTML，灯箱 302 不缓存签名地址

### v3.9.36

- **大文件同步超时放宽**：向对象存储 PUT 的读超时从 120 秒提到 300 秒。同步历史原图时出现过「连接已建立、写入阶段超时」（`The write operation timed out`），几 MB 的相机原图在慢速网关上 120 秒传不完；重试即可成功，仍失败的会留在失败列表里
- **原图缺失自动回退**：水印关闭时页面图片换成 `originals` 版本，同时带上 `data-fallback-src` 与 `onerror`；远端原图没同步上去时浏览器自动退回带水印的展示图，不再裂图
- **孤儿清理不再被 OSS 挡住**：对象存储启用时，本地孤儿（含孤立原图）也会正常列出和清理。孤儿本来就没有内容引用，删掉不影响「停用插件后的回退」
- **删除同步到对象存储**：`文件清理` 与文章删除这两条路径，本地删除后都会同步删掉 OSS 上的展示图、原图与预览副本；插件新增删除能力，停用后自动退回纯本地
- **页面说明同步**：清理页明确写出「对象存储启用时也可清理，删除会同步 OSS」，避免误解

### v3.9.35

- **原图与展示图分路径**：无痕原图从隐藏目录 `.originals` 迁到公开的 `originals/`，启动时自动迁移（幂等）。展示图仍是 `/uploads/...`，原图是 `/uploads/originals/...`，数据库只存展示图路径
- **水印开关真正可逆**：关闭水印后，正文图片、封面、分享图会自动换成 `originals` 版本；重新开启立即切回。只改 `<img src>`，视频、音频、附件保持原地址；原图缺失时保留展示图，不会 404
- **原图同步对象存储**：上传时展示图推 `uploads/...`、原图推 `uploads/originals/...`，私有桶各自现签。历史原图在插件页点「同步本地文件到 OSS」补传
- **编辑器预览跟随开关**：预览中转路由也按水印开关取原图，后台看到的就是发布后的效果
- **孤立原图纳入清理**：`originals/` 里「展示图已不存在」的原图会出现在「文件清理」里（备注「孤立原图」）；展示图还在的原图跟着展示图走，不会被单独删除。OSS 侧同样保护被引用展示图对应的原图对象
- **输出顺序**：先归一化缓存里可能残留的旧签名地址，再按水印开关换原图，最后才按当前策略重新签名

### v3.9.34

- **修复私有桶项目图 403**：README 缓存里写死了预签名地址（默认 15 分钟过期），而缓存按天活着，`data/project_cache/*.json` 因此攒下一批永久死链。现在下载与渲染都只产出规范路径 `/uploads/...`，签名统一留到响应输出时现场生成
- **缓存里不再出现签名**：页面缓存写盘前、命中后各做一次归一化，历史缓存中已经混进去的直链与预签名地址会自动剥回规范路径；代码块里的 `curl .../uploads/x` 示例不受影响
- **兜底不依赖插件状态**：新增规则只认带 `X-Amz-Signature` 且路径含 `/uploads/` 的地址，对象存储插件停用后也能清掉旧签名
- **文章页本就正确**：正文缓存存的是规范路径，命中时重新签名；问题只在项目 README 这条链路上，本次一并收敛到同一套「缓存存规范、输出才签名」的规则

### v3.9.33

- **修复编辑器预览不解析提示框**：`:::tip[标题]` 三行被 Vditor 的软换行渲染成一个 `<p>` + `<br>`，而预览区的装饰逻辑要求标记独占一个段落，整块被漏掉。现在先按 `<br>` 拆回多个 `<p>` 再交给原逻辑，四种类型都能正常显示
- **引用卡片加类型配色**：文章走主蓝、项目走绿色，左侧 3px 色条 + 同色淡底 + kicker 着色，与提示框的左边框语言一致；悬停同色系加深一档，仍不位移
- **移动端保留类型标识**：小屏原本直接隐藏「引用文章/引用项目」，现在改成 10.5px 小字保留，一眼能看出卡片类型
- **卡片类间距统一 14px**：提示框原来 10px、引用卡片 12px、段落 16px，三种间距混排；现在提示框、引用卡片与代码块/表格/列表一起纳入正文块级 14px 规则，段落仍保持 16.8px 的行文节奏

### v3.9.32

- **新增站内引用卡片**：正文写 `[[post:107]]` 或 `[[projects:3]]`，保存后渲染成文章 / 项目卡片；支持 `[[post:107|自定义标题]]`。代码块里的同名文本保持原样，引用语法不会进摘要与字数统计
- **卡片与正文区分**：文章正文本身就在白卡里，引用卡片改用「卡内嵌入层」的 `--inset-bg`（亮色比卡面暗一档、深色亮一档），不再用描边和阴影；悬停只加深一档底色，不位移、不出彩色边框
- **编辑器实时渲染**：Vditor 不认这个语法，前台保存后才生效，所以后台预览区做了 DOM 替换——批量请求 `embed-info` 接口拿标题/摘要/封面，渲染成和正文一致的卡片，悬停行为也同步
- **文末操作按钮亮色悬停加深**：「分享/复制/返回」常态是 `text 6%` 的淡底，悬停只叠到 `--hover-bg`，亮色下几乎看不出；改为直接 `text 13%` 并把文字提到主色。上一版被通用 hover 规则压掉，这次提高特异性
- **去掉编辑器工具栏「更多」**：里面 9 项（主题切换、devtools、info、help 等）多数与站点重复或写作时用不到，删掉后工具栏只留常用操作

### v3.9.31

- **修复部分删除后「删除选中」无法再次点击**：上一版删除完成后按当前勾选数把按钮禁用了，但之后再次勾选没有监听器去更新状态，按钮就一直灰着。现在把 checkbox 的 `change` 委托到列表容器上，勾选、取消、全选都会同步按钮；扫描重建表格、删除移除行都不会丢监听器
- **全选也走委托**：不再在扫描回调里单独绑定，避免每次扫描重复挂监听器，也顺手修掉「全选后按钮仍不可点」

### v3.9.30

- **删除 OSS 孤儿对象有进度了**：原来点「删除选中」只发一个 POST，服务端逐个 `s3.delete`（每个 500~800ms），50 个要等 40 秒且毫无反馈。现在前端每批 5 个调用同一接口，进度条实时显示 `X / Y（N%）`，**成功的行直接从表格消失**，跳过的（仍被引用）和失败的保留在列表里可重试
- **删除期间禁用扫描**：避免中途重新扫描把列表替换掉、进度对不上；结束后自动恢复
- **中途失败可续**：进度停在当前位置，提示「已处理 X / Y，未处理的可重新勾选后再删」，按钮恢复可用

### v3.9.29

- **上传立即返回，不再等对象存储**：本地落盘 + 校验完就把 URL 交给编辑器，远端上传和预览副本挪到后台。端到端（选文件 → 内容出现在编辑器）实测 1107ms → 162ms，服务端 `save()` 1393ms → 128ms
- **一致性靠保存时兜底**：保存文章/评论时 `sync_remote_urls()` 只处理「后台还在传」和「传失败过」的文件——还在传就等它结束（最多 30 秒），失败过就补传一次；历史文件直接跳过。实测正常保存 0ms，上传后立刻保存 978ms，失败补传 832ms
- **同一文件不会并发上传**：按 URL 的 `RLock` 包住发布与补传，后到的线程等前一个完成后再走 HEAD 命中
- **进度条说清楚在等什么**：字节发完后切成不确定态流动动画，标题改「正在保存到云端」，百分比位置显示「同步中」，不再停在 100% 假装卡死
- **头像目录不进对象存储**：`/uploads/avatar/` 在存量迁移、上传发布、页面地址改写、批量回写四处全部跳过。头像是站点品牌资源，进了 OSS 反而会出现「本地已换、远端还是旧图」
- **OSS 插件页两处体验**：扫描中的纯文本换成小转环加载态；删除确认从原生 `prompt()` 换成自定义浮窗（输入「删除」才启用确认按钮，未勾选时改用行内提示）

### v3.9.28

- **预览副本改后台生成**：960 宽 WebP 副本原来在上传请求里同步做（PIL 缩放 + 推对象存储，约 0.8 秒），请求被它拖住，进度条停在 100% 干等。现在挪到后台线程，**原图仍然同步传完才返回**，所以「请求返回 = 远端有原文件」的保证不变；副本晚到或失败只影响预览回落本地缩略图。231KB 图片服务端耗时 1.84s → 1.39s
- **插入编辑器不再固定等 350ms**：实测 Vditor 的 input 处理是同步重建，连续插入 5 段总耗时 37ms，原来的 350ms/张完全是过度保守。改成零等待，只在源码区长度没增长时退化为 80ms 兜底（防止将来升级后改成异步渲染）。没有用 `requestAnimationFrame`——后台标签页会被浏览器暂停，反而卡住
- **批量上传感知明显**：一次传 8 张图，光排队插入就从 2.8s 降到几乎为 0；端到端（选文件到内容出现在编辑器）实测 2.2s → 1.1s

### v3.9.27

- **评论表单不再有「浮起来」的框**：楼层卡和表单卡共用同一条 `box-shadow`，而表单是透明底，最后只剩一圈阴影，看起来像蒙了层玻璃。现在楼层卡保留阴影，表单卡单独去掉
- **展开时间距只给一方**：「收起评论框」的下内距和内容区上内距都是 12px，叠成 24px；去掉前者后回到 12px
- **博主身份条降为辅助信息**：47px 的实底条 + 3px 蓝色左边框 + 头像光环，压成 25px 一行——保留 20px 头像作为「以谁的身份」的锚点，去掉底色、边框和光环
- **游客「已记住」条同样瘦身**：40px 的提示条压成 25px 一行「昵称 · 邮箱」，去掉「直接输入内容即可评论」这句解释，与博主身份条同一套语言
- **网址输入默认收起**：未记住的游客只看到昵称 + 邮箱两列，网址收进「＋ 网址（选填）」，点了才展开第三列；已记住或填过网址时按原样显示
- **内联回复不再显示「收起评论框」**：顶部已有「回复 @xx 取消」，展开态再留一行 summary 既重复又白占 33px；主评论框保留它作为唯一收起入口

### v3.9.26

- **编辑器预览合并成一条通道**：图片、视频、音频、附件统一走 `/admin/preview/asset/`，由后端按当前策略实时决定「此刻从哪儿取」——未启用对象存储读本地，启用且远端有对象就 302 过去（公有桶直链、私有桶现签），远端没有则回落本地。此前图片和视频各有一套逻辑，行为还对不上
- **上传时多存一份预览副本**：图片额外转一份 960 宽 WebP 推到对象存储的 `previews/` 前缀，预览直接取它。实测原图 521KB 的截图副本只有 34KB，既走对象存储又不用等原图。副本跟着原图走，原图仍被引用时孤儿扫描不会单独删它
- **签名在请求时现算，不写进正文**：DOM 里只放稳定中转地址，浏览器真正来取时才 302 并现场签名，页面开一小时也不会失效；落库前 `normalize_text()` 还会把中转地址剥回 `/uploads/...`，双保险
- **视频签名放宽到 1 小时**：点播放才加载（`preload="none"`），签名窗口覆盖一整集，避免长视频播到一半断流
- **「预览文章」接口同步改写**：返回的 HTML 里图片、视频、附件全部走中转，预览效果与发布后一致；远端对象缺失或权限变化时，播放器/图片报错会自动退回本地副本

### v3.9.25

- **编辑器预览改用缩略图**：后台分屏预览原来直接加载本地原图（手机原图动辄 4000px、几 MB），一次插入十几张既卡后台又占出站带宽。现在预览区图片走 `/admin/preview/uploads/` 按 960 宽转 WebP 并缓存，实测 521KB 的截图降到 34KB、231KB 降到 12KB，二次访问直接读缓存
- **只改预览区，不碰正文**：缩略图替换限定在 `.vditor-preview` 内，编辑区（ir / wysiwyg）的 `img` 原样保留，保存时写进正文的仍是 `/uploads/...` 规范路径；原图地址存在 `data-full-src`，随时可查
- **抢在请求前替换**：识别新增预览节点后同步换 `src`，不走防抖——否则原图早已开始下载；实测插入后只有一条缩略图请求，没有原图请求
- **后台预览仍读本地副本**：对象存储启用时访客走 OSS，后台预览为了不让预签名地址写进正文，继续读本地；这次只是把「读本地」的成本压到最小
- **固定档位防刷**：`?w=` 只接受 480 / 960 / 1440，其余一律按 960 处理；缓存目录按文件数上限自动清理，响应带 `Cache-Control: private`
- **编辑器里的视频改成「点了才加载」**：预览区 `video` / `audio` 加 `preload="none"`，插入视频不再自动拉流；点播放才向 `/admin/preview/media/` 要地址，后端 302 到对象存储（私有桶现签，签名窗口正好覆盖播放期），本站零字节
- **远端没有就回落本地**：历史文件可能没迁到对象存储，所以中转前先确认远端有没有（结果缓存 5 分钟），避免先 302 到 404 再回退；直链不可达时播放器报错，前端自动换回 `/uploads/`

### v3.9.24

- **修复编辑器上传后插入不完整**：图片与视频现在各自独占段落，图片的文件名会稳定渲染成图注（`figcaption`），视频在分屏源码模式下不再「上传成功却消失在编辑器里」。源码模式改为直接写入文本节点再触发解析，避开 `insertValue` 丢弃真实 DOM 和 `execCommand` 规范化换行两个坑
- **批量上传改为排队插入**：多张图片、多个视频一次选中时依次进入编辑器，进度浮窗等全部插入完成才收起，不会出现内容晚一拍冒出来
- **上传文件名保留中文**：此前一律经过 `secure_filename()`，中文名被整段删光后退化成 `file.png` / `file.mp4`；现在只替换路径分隔符、Windows 保留字符和 URL 特殊字符，中文、日文、韩文原样保留，图注与下载名都可读
- **工具栏上传按钮提示补全**：按钮的 `aria-label` / `title` 由「上传图片或文件」改为「上传图片 / 视频 / 音频 / 附件」，与实际支持的格式一致

### v3.9.23

- **修复更新日志里泄露对象存储地址**：项目页 README 中的 Nginx 配置示例 `location ~ ^/uploads/\.` 被页面输出改写当成真实资源，替换成带 OSS 端点、Access Key ID 与签名的预签名地址，等于把这些信息一起公开。现在代码区域（`<pre>` / `<code>` / `<script>` / `<style>` / `<textarea>`）不参与地址改写，示例文本原样展示，真实图片照旧按策略签名
- **README 渲染链路同步修复**：`services/github.py` 的 README 图片地址转换同样跳过代码块。它在视图里执行，改写结果会写入页面缓存，不修的话缓存里的示例也会变成预签名链接
- **更新日志调整**：只展开最新版本，更早的版本统一收进 `<details>` 折叠区，页面不再一屏铺开几十个版本

### v3.9.22

评论区卡片补齐阴影，楼层卡与表单卡的四件套令牌终于一致；页面缓存的资源签名纳入 `static/` 下的 CSS/JS，改独立样式表后刷新即生效。

### v3.9.21

页脚链接顺序对齐顶部导航并分成两组，「十年之约」标识由双色图片改为文字链接；小屏按宽度逐级收起次要入口，403/404/50x 页面同步。

### v3.9.20

修复后台编辑器把图片显示成会过期的预签名地址：后台一律保留 `/uploads/`，正文、封面、评论在落库前统一归一化图片地址。

### v3.9.19

对象存储改为「数据库只存规范路径、输出时按桶策略改写」，私有桶改用预签名直链；补上评论与 README 图片兼容、孤儿对象扫描和配置页状态展示。

### v3.9.18

新增对象存储插件，上传双写本地与 S3 兼容存储，支持存量文件分批迁移、停用后批量回滚，以及反向代理场景的签名兼容模式。

### v3.9.17

修复三处配置与线程报错：AI 助手体积上限的 `step` 校验拦截保存、旧的最大输出 tokens 被下限卡住、友链定时审核缺少请求上下文导致整轮崩溃。

### v3.9.16

文章详情页导航栏的「写作」入口改为直达当前文章的编辑页，移动端抽屉同步，其它页面行为不变。

### v3.9.15

友链审核新增域名、内容、结构与速度四层本地体检，自动通过条件收紧，已收录友链每 7 天抽检；同时加入提交去重限流、外链 `nofollow` 与 AI 发文标题标签清洗。

### v3.9.14

修复孤儿文件清理误删被拒评论图片与文章封面，补齐 uploads 根目录扫描和删除前二次复检；友链列表页瘦身、申请页按真实流程重排。

### v3.9.13

修复「站点状态」卡内明细浮出双层阴影，监控明细药丸改用卡内嵌层令牌 `--inset-bg`，深浅主题都不再出现暗块。

### v3.9.12

楼中楼改为按时间正序平铺渲染，修复三级以上嵌套时同级回复被挤到末尾；后台已拒绝评论恢复一键通过入口。

### v3.9.11

移动端文章页顶部留白由 24px 收到 20px，缩小与列表页的高度差，PC 端保持不变。

### v3.9.10

重做提示框（admonition）排版：标题独立成紧凑标题行，块内段距收紧，整盒高度 94px 降到 80px，并用更高特异性压住正文段落规则。

### v3.9.9

首页报头收成「标题 + 一行格言」，与子页页头同构；多栏报头改单列左对齐，侧栏首卡无条件与主列首卡对齐。

### v3.9.8

AI 长文输出上限由 8000 放宽到 8192~32768 tokens、超时上限提到 600 秒；侧栏「最新评论」改为纯文字两级结构，正文降到 16px/1.8。

### v3.9.7

支持 Docusaurus / MkDocs 的 `:::` 提示框语法并映射 20 余种别名；全站卡片改为不透明表面色、悬停只给整卡可点的容器，按钮分页与评论区同步重做，衬线标题字体子集化到 341KB。

### v3.9.6

全站主按钮统一为柔和 accent 配色并修复 hover 文字对比度；分页按钮收口到一套变量，新增统一的分页窗口函数，搜索改为居中毛玻璃浮窗。

### v3.9.5

评论表单拆成「工具行 / 动作行」两个容器，间距改由 `gap` 统一控制，修复被特异性规则压掉的 flex 间距；移动端触控热区与文章页头部节奏同步调整。

### v3.9.4

文章底部操作区独立成卡，文末五段间距统一 24px；首页报头留白按视觉补偿，友链页与窄屏目录细节一并对齐。

### v3.9.3

移动端分页精简为「首页 / 当前 / 后一 / 末页」加前后页，五个列表模板统一切换；目录与文章页顶部留白统一，竖条改用 flex 居中。

### v3.9.2

标签云取消分档字号、统一为 13px 药丸，关于页卡片留白统一 20px；首页新增 `--home-gap` 统一间距，报头统计改药丸并修复归档按钮压页脚。

### v3.9.1

关于页标题样式统一；favicon 链接带 mtime 版本参数，页面缓存记录模板与主题资源签名，改动样式或模板后旧 HTML 自动失效。

### v3.9.0

全站卡片统一到同一组 `--card-*` 令牌，评论区并入卡片语言；标签与筛选控件改柔和小药丸，文章头部移出阅读卡，代码块、表头、引用块建立统一内嵌层级。

### v3.8.13

删除后台博主设置里重复的「首屏标语」输入项，该项统一由主题配置维护，保存其它设置不再清空标语。

### v3.8.12

精选不再影响归档等列表排序；归档列表重做为统一卡片结构，悬停只对鼠标宽屏启用，首页报头显示范围可在主题配置里选择。

### v3.8.11

侧栏博主卡改为「标题 + 内容」骨架，博主名升到主标题级；精选徽章换成统一 SVG 星标，修复侧栏末卡压住页脚线。

### v3.8.10

首页「精选推荐」去掉与页头冲突的蓝条，改为细分隔线加短竖标记，间距跟随断点，PC 双栏侧栏下移与首卡对齐。

### v3.8.9

后台博主设置补上「首屏标语」入口，留空自动回退站点副标题，不再需要维护两份文案。

### v3.8.8

修复后台锚点定位被 sticky 顶栏遮挡，内容区统一预留顶栏高度加 16px 间距。

### v3.8.7

修复移动端后台评论管理「待审核」高亮被切成色带，改为整行着色；文件清理页同步处理，桌面表格保持逐格着色。

### v3.8.6

升级页发布日期改本地时间、更新内容按 Markdown 渲染、查看链接跟随升级源；邮件与全站悬停下划线统一去掉，改为混色反馈。

### v3.8.5

修复移动端首页侧栏「十年之约」贴住页脚；AI 插件保存条按位置区分样式并回归文档流，清理移动端侧栏失效样式。

### v3.8.4

归档选择浮窗改毛玻璃并支持降级；上下篇占位卡统一为全站卡片语言，评论 UA 行与楼中楼正文左缘对齐。

### v3.8.3

修复外链确认浮窗悬停时透明度异常，浮窗不再参与全站卡片悬停，固定使用不透明实色背景。

### v3.8.2

评论表单取消外层边框，只保留淡底色与 6px 圆角，折叠态输入条和展开后的输入框仍保留自身边框。

### v3.8.1

深色页底回调到 `#181b21` 并大幅减弱动态光斑，去掉模糊与缩放动画修复块状马赛克；关于页、项目页、归档与分页等卡片语言统一。

### v3.8.0

全站卡片配色统一、导航改半透明毛玻璃，新增全站动态光斑背景；文章整篇收进阅读卡，相关推荐改卡片网格，移动端宽度与读者页统计同步调整。

### v3.7.9

内容页版心统一 780px，项目与圈子卡片重做并支持整卡点击；归档改为单栏加年月浮窗筛选，移动端列表去卡片化，SEO 标题统一格式。

### v3.7.8

细化移动端正文、项目 README、标题与楼中楼的字号行高，桌面正文与项目页宽度收敛，修复正文段落间距为 0 的问题。

### v3.7.7

留存记录评论 tab 改为「关键列 + 详情」浮窗，新增身份动作与身份说明两列并同步 CSV，评论改名写入操作记录。

### v3.7.6

后台评论管理的身份说明改为可点击「详情」浮窗，长文案不再被单行截断，与 AI / 人工审核说明保持一致。

### v3.7.5

建立评论身份体系：邮箱哈希作为身份、昵称作为可变展示名，支持沿用曾用名与邮箱验证码改名；补发送限频、历史昵称同步与审核协同，并修复填写公开邮箱可绕过审核。

### v3.7.4

Markdown 表格改为 GitHub 同款折行规则，窄表格保持自然宽度，超宽单元格自动换行，长 URL 与行内代码不再撑破表格。

### v3.7.3

回复通知邮件新增「我的留言」入口并优化版式，修正「直接回复本邮件」的误导文案，邮件回复不会出现在评论区。

### v3.7.2

关于页新增「写作热力图」，按天统计近一年发文，桌面 53 周、移动端 26 周，悬停看当天数量并汇总更新天数与最长连更。

### v3.7.1

修复 HEIC/HEIF 上传仍报「格式不受支持」：校验前注册解码器，按真实格式转 WebP，失败时把真实原因写入日志。

### v3.7.0

支持 HEIC/HEIF 上传，自动解码转 WebP 后照常叠加水印、生成分享图并按 EXIF 摆正；评论图片同步放开。

### v3.6.9

移动端悬浮按钮合并为「跳到评论 / 回到顶部」两态；评论审核说明改为详情浮窗；修复私密评论无条件绕过审核。

### v3.6.8

文章灯箱支持移动端双指缩放、放大后拖动与双击复位；移动端按钮尺寸圆角统一，关闭原生 View Transition 修复 Chrome 报错。

### v3.6.7

调整移动端友链申请表单底部间距，提交/返回按钮上下留白对称；圈子分页与收尾文案间距统一 24px。

### v3.6.6

移动端非首页正文再放宽 8px，左右留白收到 16px，390 屏约 23~24 个汉字一行，首页列表保持满宽。

### v3.6.5

移动端正文列宽收到 380px 上限、左右留白 20px，小屏 16px；首页列表不参与收窄，避免整页显得过窄。

### v3.6.4

文章与项目页目录改为 220px 无框文字索引，关于页站点状态改版并支持每分钟刷新；正文图片备注与全站底部间距统一 24px。

### v3.6.3

移动端首页与列表加宽；相关推荐由 4 条收敛为 2 条并弱化标题；移动端页脚居中，修复表格上下间距翻倍。

### v3.6.2

敏感词词库输出前转义防注入；评论表单加入计数标红、快捷键提交与最近表情，正文块级间距统一 14px，灯箱备注改到图下居中。

### v3.6.1

评论归属地改为「省 · 市」并自动迁移历史数据，设备信息移到作者行；楼中楼与评论区垂直节奏统一。

### v3.6.0

友链审核重写为可访问性、敏感词、AI 内容审核与精确回链检测四段；AI 对话支持 SSE 流式输出，评论改相对时间并补设备信息，博客圈与读者页同步改版。

### v3.5.5

AI 对话超时提到 120 秒、修复 Gitee 源升级未指定分支；后台回收站按钮等高，文章标签前后端统一去重。

### v3.5.4

留存审计日志改为永久保存，不再按 180 天自动清理历史记录。

### v3.5.3

主题样式对齐线上版并统一正文版心 780px，评论区改为表单在上；全站扁平化，后台新增评论「拒绝」与 AI 回复概率策略，完成三视口 70 轮回归。

### v3.5.2

首页文章卡与侧栏卡统一为描边圆角卡片，移动端限制整页缩放，修复读者榜单窄屏边框丢失。

### v3.5.1

新增读者留言档案页与榜单分页；全站补齐 19 处触屏 hover 守卫并清理约 200 行死代码，修复留存清理线程缺少应用上下文。

### v3.5.0

插件启停即时生效，无需重启即可建表、启停定时任务与 hooks；新增评论者「新朋友 / 回头客 / 常客」标签与 UA 设备展示。

### v3.4.36

通知邮件恢复展示真实评论正文，仅敏感词或已拒绝内容保留占位；修正评论徽章圆角与留存审计页长文本溢出。

### v3.4.35

AI 助手带具体条件查询评论时默认查全部状态，输出上限提到 8192；留存审计页长 JSON 改折叠展示，审计写入改为合法截断 JSON。

### v3.4.34

文章改为软删除并新增回收站；新增留存审计插件（操作记录、AI 审核、评论留存，支持筛选与 CSV）；重做评论通知邮件模板，AI 助手支持自定义身份与草稿保存。

### v3.4.33

评论浮窗模式上线，可选内嵌或悬浮弹窗，AJAX 拉取评论片段并支持深链定位、分页、表单与移动端贴底抽屉。

### v3.4.32

为评论浮窗模式做零行为变化重构：评论脚本改为可重入初始化，抽出共用的评论上下文与 flash 模板。

### v3.4.31

修复老版本 git 在线升级误判远程地址，兼容 git 1.8.3 与仓库属主不一致的部署环境。

### v3.4.30

修复升级页「升级源」选择行贴卡片左边缘的问题，样式收进后台样式表并与上下内容同留白。

### v3.4.29

在线升级支持在 GitHub 与 Gitee 之间单选升级源，首次从 Gitee 升级自动补配远程地址。

### v3.4.28

修复正文目录点击后滑到底部；每日一言打字机改 rAF 时间轴驱动，评论强制填写邮箱并补 AI 回复安全兜底。

### v3.4.27

修复直辖市归属地重复显示（如「重庆市 重庆市」），两条解析路径都做相邻片段去重，并提供历史数据修复脚本。

### v3.4.26

修复直辖市归属地重复显示，前台评论属地与后台徽章恢复正常，「省 市」组合不受影响。

### v3.4.25

评论新增邮箱通知开关与昵称校验，修复博主昵称残留与前端校验失效；AI 回复改为依据正文生成，项目列表支持分页与语言筛选，全站滚动条与按钮统一。

### v3.4.24

留言榜单说明里的「前 10 位」改为跟随后台设置的数量。

### v3.4.23

后台新增分类页文章数、留言榜显示人数与项目页列数设置；首页 Hero 重做，圈子与榜单统计改为数据带，字符箭头统一换成 SVG。

### v3.4.22

修复外链浮窗「继续访问」被清空地址；留言榜前三名改为 2-1-3 领奖台，侧栏新增分类页入口并调整顺序，项目卡片统一圆角与入口。

### v3.4.21

修复外链确认浮窗样式丢失与错位，加入外链白名单；移除走心评论功能，榜单第四个统计改为人均留言。

### v3.4.20

后台新增「圈子每页条数」；留言榜前三名加冠亚季军标签并用金银铜三色区分，走心评论正文限制 3 行。

### v3.4.19

撤销页面标题区 1100px 加宽，恢复与页面内容同宽，关于页顶部 24px 间距保留。

### v3.4.18

关于页顶部边距与其它页面统一为 24px，页面标题区宽度加宽到 1100px。

### v3.4.17

文章与项目详情正文宽度统一 960 并右移悬浮目录；「今天读什么」改为服务端抓取加 30 分钟缓存，抓取失败自动隐藏。

### v3.4.16

导航与页脚加宽到 1200，形成宽窄层级；留言榜改为前 10 位、前三名用克制的描边卡；正文改 800px 与 16px/1.8 排版，后台新增归档页每页数。

### v3.4.15

留言榜第二页起不再把第 16 名当作前三名展示，统一按列表排列。

### v3.4.14

「互动」并入「读者」并新增走心评论区；留言榜改版为 4 张统计卡加金银铜领奖台；新增站外链接确认浮窗与「多栏」布局。

### v3.4.13

互动页空状态文案去掉「后台标记」字样，改成面向访客的说法。

### v3.4.12

新增「读者」留言榜与「互动」走心评论墙，导航随之调整；友链申请页补「申请须知」，评论表新增博主与走心字段。

### v3.4.11

文章时间线页面名称由「里程」改为「归档」，导航与首页按钮同步。

### v3.4.10

归档页年份标题显示该年全年文章数，翻页时数字保持一致。

### v3.4.9

「文章」页改为按年分组的「里程」时间线，全站卡片 hover 统一，修复双栏文章卡鼠标经过无反馈。

### v3.4.8

友链页与博客圈文案压缩、布局调整；列表标签最多显示 4 个超出显示 +N，按钮与双栏卡片 hover 统一。

### v3.4.7

后台主题配置新增文章列表单/双栏选项；关于页人物卡与站点状态间距收紧，友链名字旁显示 RSS 标记。

### v3.4.6

关于页人物卡改横向布局并压缩高度；圈子标题恢复「博客圈」，单页也显示分页，单源保留文章数提到 15。

### v3.4.5

关于页技术栈、网站历程、站点状态统一为卡片；到期标签改「博客主机 / 博客域名」，圈子改两栏卡片流。

### v3.4.4

站点状态去掉常驻说明，仅在后台数据更新时短暂浮出提示；网站历程改为卡片行并统一日期胶囊。

### v3.4.3

「状态」并入「关于」，导航移除状态入口，状态数据仍每 60 秒刷新。

### v3.4.2

导航顺序调整，「圈子」移到「友链」后面，内容相关入口挨在一起。

### v3.4.1

导航与标题「博客圈」简化为「圈子」；新增后台圈子管理页，友链新增 RSS 抓取状态字段，保存后立即抓取一次。

### v3.4.0

新增「博客圈」页面，聚合已通过友链的 RSS 最新文章并带统计；新增 feeds 服务，支持 RSS/Atom、SSRF 防护与 30 分钟定时刷新。

### v3.3.12

AI 助手补齐项目管理、文章/分类/评论/友链的删除与审核操作，并区分强制人工确认与可自动执行的动作。

### v3.3.11

深色主题从近黑提亮到炭灰，浅色强调色加亮；后台主题按钮文案改为「浅色 / 深色 / 跟随系统」。

### v3.3.10

AI 新增分类创建与修改工具，四类写操作强制确认；修复推理模型把内容全塞进推理字段导致的误报，默认输出上限由 1200 提到 4096。

### v3.3.9

IP 归属地改为内置 xdb 解析，精简 ip2region binding 不再依赖 pip 安装，本地查询不可用时再走在线兜底。

### v3.3.8

修复服务器缺少 ip2region 与 xdb 时归属地为空，改为在线接口兜底并补全历史评论归属地。

### v3.3.7

为历史 AI 评论按当前模型补齐头像映射，重写新对话提示并加入常用指令示例与权限说明。

### v3.3.6

AI 评论按模型 ID 映射头像；新增「写操作自动执行」开关与敏感词硬拦截，历史对话支持删除。

### v3.3.5

AI 助手内置权限规则（工具白名单、读写边界、提示词注入防护），工具支持更多查询条件并对邮箱脱敏。

### v3.3.4

AI 模型改为独立管理页，可自由新增、编辑、删除任意 OpenAI 兼容模型；聊天气泡与推理过程折叠重做。

### v3.3.3

AI 助手支持 DeepSeek、智谱 GLM 与自定义兼容接口，可下拉切换；消息显示模型名、耗时与 token 用量。

### v3.3.2

修复 AI 聊天页高度算多导致页面级滚动条，扣除后台内边距、页头、flex 间距与页脚。

### v3.3.1

插件管理页与 AI 配置页排版重做；AI 聊天页高度自适应、消息区独立滚动，插件静态资源缓存从 7 天降到 60 秒。

### v3.3.0

引入插件系统与 AI 助手插件：支持 OpenAI 兼容接口、后台对话、评论托管与友链托管，写操作需二次确认并全部记审计。

### v3.2.23

修复项目页目录点击后被懒加载图片顶走，点击时把待加载图片切成 eager 并连续跟随，直到页面高度稳定。

### v3.2.22

修复项目页目录点击跳到页面底部，补上项目正文选择器，并对齐懒加载图片避免目标位置被顶走。

### v3.2.21

修复状态自动探测线程导入类名错误导致调度从未执行，改为正确导入并把异常写入日志。

### v3.2.20

安全与性能整修：修复头像路径、给上传加限额、缓存加淘汰、限流落库、优化批量删除与相关推荐查询，补 CSRF 兜底与 Markdown 过滤，新增状态自动探测。

### v3.2.19

补齐 `.gitattributes` 的 AVIF 二进制标记，修复 `git pull` 被 CRLF 转换卡住；状态页 SSL 改用 certifi 根证书。

### v3.2.18

tech 主题回到纯色底、移除全部背景图装饰；重做浅色配色与卡片悬停，状态页改卡片分区，新增 gzip 兜底与页面缓存响应头。

### v3.2.17

后台背景装饰新增显示位置四种模式与左右固定底图，新增朝天门素材；移动端底图改按屏宽等比铺满，补 AVIF 副本并压缩高分屏体积，毛玻璃与链接样式统一。

### v3.2.16

tech 主题视觉与可访问性整修：加入可切换底图与毛玻璃分层、代码高亮改主题变量，补键盘操作、ARIA 与描述 meta，并移除缩放限制。

### v3.2.15

运行时数据统一收敛到 `var/`，新增 `BLOG_DATA_DIR` 与启动自动迁移，重写自动重启脚本并同步部署文档。

</details>

---

## License

MIT
