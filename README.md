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
- 依赖：`flask`、`markdown`、`Pillow`（详见 `requirements.txt`）

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
- 评论、上传等文件保存在 `static/uploads/` 下。

## 版本更新日志

### v1.0.1

- 后台仪表盘「友情链接」统计修正：仅计入已通过审核（`approved`）的链接，排除已拒绝/待审核项
- 后台侧边栏底部新增版本号显示（`infowe Blog v1.0.1`），并链接至开源仓库（新窗口打开）
- GitHub 同步支持 Token 认证 + certifi SSL 校验 + 精确错误提示
