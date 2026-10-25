# Python Blog（Flask + SQLite）

[![version](https://img.shields.io/badge/version-3.0.1-blue)](https://github.com/Contribuv/infowe_blog)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

以 `D:\fnos\blog`（PHP + MySQL 版 Haozi Blog）为功能基准重构的多模块 Python 博客。
前台/后台路由、模板与静态资源尽量与 PHP 版保持一致，存储层改为 SQLite，开箱即用。

- 前台：文章、标签、搜索、分类、归档、RSS、评论、友链、项目、时间线、站点状态
- 后台：文章/分类/项目/友链/时间线/评论管理、上传、孤儿文件清理、主题、设置、状态监控、备份与导入导出
- 安全：单管理员、PBKDF2 密码、登录防爆破、TOTP 双重验证、邮箱找回、同源校验、上传白名单

## 技术栈

| 层 | 选型 |
| --- | --- |
| Web | Flask 3.x（应用工厂 + 路由模块） |
| 数据库 | SQLite（WAL） |
| 模板 | Jinja2（复用 PHP 版 Jinja2 兼容模板） |
| Markdown | `markdown`（表格、代码块、目录、脚注等） |
| 图片 | Pillow（水印、分享缩略图、头像裁剪） |
| HTTP | requests（GitHub 同步、状态探测、头像回源） |

## 目录结构

```
python_blog/
├── app.py                 # 入口：create_app / 全局上下文 / CLI / 开发服务器
├── config.py              # 路径、上传限制、导航配置
├── db.py                  # SQLite 连接、建表、旧库补列
├── schema.sql             # 数据库结构
├── models/                # 数据模型（post/comment/project/link/...）
├── services/              # 业务服务（markdown/upload/auth/otp/github/...）
├── routes/                # 路由（front/auth/admin/assets/api）
├── templates/
│   ├── theme/tech/        # 前台主题模板
│   ├── admin/             # 后台模板
│   └── shared/            # 公共片段
├── static/                # 全站静态资源（后台 CSS/JS、Vditor、图标）
├── themes/tech/           # 主题样式与脚本
├── uploads/               # 上传文件
├── backups/               # 数据库备份
├── storage/cache/         # 头像/分享图/README 图缓存
├── data/                  # 同步状态、导入临时文件
└── instance/blog.db       # SQLite 数据库（首次启动生成）
```

## 快速开始

要求 Python 3.10+（推荐 3.12）。

```powershell
cd D:\python_blog

# 1. 创建虚拟环境并安装依赖
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. 启动（自动建库；首次启动会生成管理员并打印密码）
.\.venv\Scripts\python.exe app.py
```

打开 <http://127.0.0.1:5000>。

首次启动会自动完成：

| 项目 | 内容 |
| --- | --- |
| 数据库 | `instance/blog.db`（SQLite，自动建表） |
| 管理员 | `admin` / `admin123` |
| 示例文章 | 《致使用者的一封信》 |
| 默认分类 | 随笔 |

> ⚠️ 默认密码只用于首次登录，请立即在「博客设置 → 账号安全」修改。
> 宝塔 / gunicorn 部署同样会在首次启动时自动初始化，无需手动建库。

- 后台：`/admin`（可在「博客设置 → 账号安全」改为自定义路径，重启后生效）
- 示例文章会自动出现在首页，可直接删除或改写

前台 URL 采用目录形式：

| 页面 | URL |
| --- | --- |
| 标签 | `/tag/Python` |
| 搜索 | `/search/Python` |
| 年份归档 | `/archive/2025` |

旧参数形式（`/?tag=`、`/?q=`、`/posts?year=`）会 301 到新地址，不影响既有链接。

也可用 Flask CLI：

```powershell
.\.venv\Scripts\python.exe -m flask --app app init-db
.\.venv\Scripts\python.exe -m flask --app app create-admin --username admin
.\.venv\Scripts\python.exe -m flask --app app run --port 5000
```

## 生产部署

Windows 推荐 [waitress](https://docs.pylonsproject.org/projects/waitress/)：

```powershell
.\.venv\Scripts\python.exe -m pip install waitress
.\.venv\Scripts\waitress-serve.exe --listen=0.0.0.0:5000 app:app
```

Linux 推荐 gunicorn：

```bash
.venv/bin/pip install gunicorn
.venv/bin/gunicorn -w 2 -b 127.0.0.1:5000 --timeout 120 app:app
```

### 宝塔面板（Linux）

1. 克隆代码到站点目录：

```bash
cd /www/wwwroot
git clone https://gitee.com/infowe/infowe_blog.git python_blog
cd python_blog
```

2. 创建虚拟环境并安装依赖（宝塔「软件商店 → Python 项目管理器」也可代劳）：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt gunicorn
```

3. 首次启动会自动建库、创建默认管理员 `admin / admin123` 和示例文章。
   如需自定义管理员，可执行（仅在无管理员时有效）：

```bash
.venv/bin/python -m flask --app app create-admin --username admin
```

若已上传本地 `instance/blog.db`，会直接使用其中的数据与管理员。

4. 宝塔「Python 项目管理器 → 添加项目」：

| 项 | 值 |
| --- | --- |
| 项目路径 | `/www/wwwroot/python_blog` |
| 启动方式 | `gunicorn` |
| 启动文件 | `app.py` |
| 端口 | `5000` |
| 运行用户 | `www` |
| 依赖安装 | 勾选（或命令行安装） |

启动命令等价于：

```bash
gunicorn -w 2 -b 127.0.0.1:5000 --timeout 120 app:app
```

5. 网站 → 添加站点 → 反向代理到 `http://127.0.0.1:5000`，或使用 Python 项目管理器的域名映射。

6. 目录权限（SQLite、上传、备份都要可写）：

```bash
chown -R www:www instance uploads backups data storage
```

7. 后台「博客设置」填写 `site_url`，开启 HTTPS，再申请 SSL。

Nginx 反向代理核心配置：

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

> 项目已启用 `ProxyFix`，会信任一层代理的 `Host` / `X-Forwarded-Proto` / `X-Forwarded-For`，
> 因此宝塔开启 HTTPS 后不会出现重定向循环。

### systemd（不使用宝塔进程管理时）

```ini
[Unit]
Description=Python Blog
After=network.target

[Service]
User=www
Group=www
WorkingDirectory=/www/wwwroot/python_blog
Environment="PATH=/www/wwwroot/python_blog/.venv/bin"
ExecStart=/www/wwwroot/python_blog/.venv/bin/gunicorn -w 2 -b 127.0.0.1:5000 --timeout 120 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now python-blog
```

### 更新

```bash
cd /www/wwwroot/python_blog
git pull
.venv/bin/pip install -r requirements.txt
systemctl restart python-blog   # 或宝塔面板重启项目
```

Nginx 反向代理要点：

```nginx
location / {
    proxy_pass http://127.0.0.1:5000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    client_max_body_size 64m;
}
```

> 反向代理下会读取 `X-Forwarded-For`（仅当直连地址是回环/私网时）。
> `site_url` 建议在后台「博客设置」中填写完整站点地址，用于 RSS/分享/邮件中的绝对链接。

## 数据迁移

### 从 PHP 版（MySQL）迁移

项目内置了迁移脚本，会直接连接旧站 MySQL，把 10 张表、设置、管理员、
上传文件与 GitHub README 缓存一次性写入 SQLite（写入前自动备份当前库）：

```powershell
.\.venv\Scripts\python.exe -m pip install pymysql bcrypt

# 先试运行，确认源库表与行数
.\.venv\Scripts\python.exe tools\migrate_from_php.py --dry-run

# 正式迁移（默认读取 D:\fnos\blog\config\config.php）
.\.venv\Scripts\python.exe tools\migrate_from_php.py
```

可选参数：

| 参数 | 说明 |
| --- | --- |
| `--source-dir PATH` | PHP 项目根目录（默认 `D:\fnos\blog`） |
| `--keep-otp` | 保留旧站 OTP 密钥/开关（默认关闭，避免没有旧验证器无法登录） |
| `--keep-users` | 保留当前管理员，不导入旧站 users 表 |
| `--dry-run` | 只连接并统计，不写入 |

迁移后管理员账号/密码沿用 PHP 版（bcrypt 哈希已兼容）。若忘记密码：

```powershell
.\.venv\Scripts\python.exe -m flask --app app reset-password
```

### 从旧 Flask 版迁移

后台「数据管理 → SQLite 导入」上传旧 `blog.db` 即可。导入会：

- 校验必需表；
- 自动备份当前数据库；
- 覆盖业务表（可勾选保留当前管理员账号）；
- 自动补齐缺失设置项。

### 备份与导出

- 数据库备份：`backups/blog_YYYYmmdd_HHMMSS.db`（SQLite 在线备份 API）
- JSON 导出：全表数据
- Markdown 导出：文章 + YAML front matter 的 zip

## 主要配置（后台 → 博客设置）

| 分组 | 说明 |
| --- | --- |
| 站点信息 | 站名、副标题、作者、简介、技能、社交链接 |
| 导航菜单 | 文章/标签/项目/友链/关于/状态 开关 |
| 评论 | 总开关、审核、邮件通知、评论图片上传、敏感词 |
| 上传 | 图片/媒体/附件扩展名白名单、单文件大小上限、水印 |
| 邮件 | SMTP 服务器、端口、账号、通知收件人、测试发送 |
| 账号安全 | 管理员账号名、密码、OTP 双重验证与恢复码 |
| 后台入口 | `admin_path`：自定义后台路径（2-32 位字母/数字/下划线/连字符），重启生效，旧 `/admin` 不再可用 |
| 站点地址 | `site_url`、强制 HTTPS、同主域 www 归一 |
| 统计代码 | 仅保留 `<script>`，剥离事件属性与 `javascript:` |

## 与 PHP 版的差异

| 项目 | 说明 |
| --- | --- |
| 数据库 | MySQL → SQLite（WAL，零外部依赖） |
| 在线升级 | 改为版本检查 + `git pull`，不覆盖运行中的代码 |
| 插件 | 保留 `services/hooks.py` 扩展位，不加载 PHP 插件 |
| IP 归属地 | 默认内网/回环识别；安装 `ip2region` 并放置 `data/ip2region_v4.xdb` 可离线解析 |
| 云到期查询 | 保留配置与界面，到期日期以手工填写为准 |
| MySQL SQL 导入 | 提示改用 SQLite 导入/JSON 迁移 |

## 开发与测试

```powershell
# 语法检查
.\.venv\Scripts\python.exe -m compileall -q .

# 冒烟（启动后）
curl http://127.0.0.1:5000/
curl http://127.0.0.1:5000/feed.xml
```

## 安全提示

- 生产环境务必修改初始密码，建议开启 OTP；
- 使用 HTTPS，并在后台设置 `site_url`；
- `instance/`、`uploads/`、`backups/`、`data/` 不要暴露为静态目录（本项目的 Flask 路由已做限制）；
- 上传目录禁止脚本扩展名（`.php/.html/.svg` 等已在白名单与黑名单双重拦截）。

## 常见问题

### 忘记后台密码

```bash
.venv/bin/python -m flask --app app reset-password
```

默认账号为 `admin / admin123`（首次启动创建）。

### 数据库在哪里

主库：`instance/blog.db`；备份：`backups/`。可直接复制 `blog.db` 迁移。

### 首次启动没有文章

空库会自动写入《致使用者的一封信》。如果使用了自己的数据库，以数据库内容为准；检查 `instance/blog.db` 是否存在、目录是否可写。

### 上传 / 备份失败

确保这些目录对运行用户可写：

```bash
chown -R www:www instance uploads backups data storage
```

### 后台 403 / 502

- 403：Nginx 的 443 server 没有 `location / { proxy_pass http://127.0.0.1:5000; }`
- 502：gunicorn/uWSGI 未启动、端口不对、工作目录不对

### 修改后台入口后进不去

重启服务使新路径生效；如果路径写错，可在数据库把 `settings.admin_path` 改回 `admin`：

```bash
.venv/bin/python -c "from app import app; from services import settings; ctx=app.app_context(); ctx.push(); settings.set_value('admin_path','admin')"
```

## 更新日志

- 当前版本：v3.0.1
- GitHub Releases：https://github.com/Contribuv/infowe_blog/releases
- Gitee Releases：https://gitee.com/infowe/infowe_blog/releases

## License

MIT
