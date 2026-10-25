# Python Blog（Flask + SQLite）

[![version](https://img.shields.io/badge/version-3.1.6-blue)](https://github.com/Contribuv/infowe_blog/releases/tag/v3.1.6)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

一个基于 **Flask + SQLite** 的多模块个人博客系统，功能对齐 Haozi Blog PHP 版。
前台服务端渲染，后台提供完整内容管理，开箱即用；支持从 PHP/MySQL 或旧 Flask SQLite 迁移。

- GitHub：<https://github.com/Contribuv/infowe_blog>
- Gitee：<https://gitee.com/infowe/infowe_blog>

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
| 页面过渡 | 跨文档 View Transition：支持时旧页淡出 / 新页淡入，不支持时自动回退为新页淡入，尊重系统「减弱动态效果」 |

### 后台

- 仪表盘：文章/评论/项目/友链统计、最近更新
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
├── themes/tech/           # 主题静态资源（theme.css/theme.js/info.json/preview.png）
├── uploads/               # 文章图片、评论图片、README 图片
├── data/                  # SQLite 数据库、密钥、项目同步状态
├── backups/               # 数据库备份、JSON/Markdown 导出
├── storage/cache/         # 运行缓存（头像/分享图/README 图/页面缓存）
├── fonts/                 # 水印字体
├── docs/                  # 功能一致性报告等文档
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
| `docs/` | 文档 | 可删 |
| `tools/` | 迁移工具 | 可删（不再迁移时） |

> `data/`、`uploads/`、`backups/`、`storage/` 不要暴露为静态目录，本项目已通过路由限制访问。

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

## 配置说明（后台 → 博客设置）

| 分组 | 内容 |
| --- | --- |
| 站点信息 | 站名、副标题、作者、简介、技能、GitHub、联系邮箱 |
| 导航菜单 | 文章/标签/项目/友链/关于/状态 开关 |
| 评论 | 总开关、审核、邮件通知、评论图片、敏感词 |
| 上传 | 图片/媒体/附件白名单、单文件大小、水印 |
| 邮件 | SMTP 服务器、端口、账号、通知收件人、测试发送 |
| 账号安全 | 用户名、密码、OTP、后台入口路径 |
| 站点地址 | `site_url`、强制 HTTPS、同主域 www 归一 |
| 统计代码 | 只保留 `<script>`，剥离事件属性与 `javascript:` |
| 服务状态 | 监控服务列表、云资源到期日期 |

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

### 6.1 静态资源直出（强烈建议）

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

> **伪静态**：宝塔 Python 项目会自动生成 `rewrite/python_xxx.conf`。
> 如果该文件里有 `location /` 或 `proxy_pass`，请清空或删除这行 include，避免与站点里的反代重复。
> Flask 的 `/tag/`、`/search/`、`/archive/` 都是应用路由，不需要 Nginx rewrite。

### 6.2 页面缓存（已内置）

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

### 10. 更新

```bash
cd /www/wwwroot/infowe.site
git pull
.venv/bin/pip install -r requirements.txt
```

然后在宝塔 Python 项目管理器中点「重启」。

> 升级包含模板/CSS/JS 变更时，重启后建议到后台「数据管理 → 清除页面缓存」。
> 旧页面缓存默认还会保留 5～30 分钟，清除后新模板（例如防白屏内联样式）立即生效。

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

- 版本：**v3.1.6**
- GitHub Releases：<https://github.com/Contribuv/infowe_blog/releases>
- Gitee Releases：<https://gitee.com/infowe/infowe_blog/releases>

---

## License

MIT
