# 部署文档 · infowe.site 个人博客

本博客是 Flask 单应用，生产环境用 **Nginx + gunicorn** 部署。本文档覆盖从零到上线的完整步骤。

> 本机（Windows）开发时直接 `python app.py` 即可，下面的生产流程仅适用于 Linux 服务器。

---

## 一、服务器环境准备

```bash
# 1. 安装 Python 与 pip（以 Debian/Ubuntu 为例）
sudo apt update && sudo apt install -y python3 python3-venv python3-pip nginx

# 2. 上传项目代码到服务器（示例目录）
#    scp -r ./ user@server:/var/www/infowe.site
# 假设项目最终位于：/var/www/infowe.site

# 3. 进入项目并创建虚拟环境
cd /var/www/infowe.site
python3 -m venv venv
source venv/bin/activate

# 4. 安装依赖（gunicorn 是生产 WSGI 服务器，必须装）
pip install -r requirements.txt
pip install gunicorn
```

---

## 二、配置环境变量（重要）

生产环境**必须**设置 `BLOG_SECRET_KEY`，否则会 fallback 到源码默认值（可被伪造 session 直接进后台）。

```bash
# 生成强随机密钥
python3 -c "import secrets; print(secrets.token_hex(32))"
# 复制输出结果，下面 systemd 配置里要用到
```

---

## 三、gunicorn 配置

`gunicorn.conf.py` 已随项目提供，关键项：

- 绑定 `127.0.0.1:5000`（仅本机，不对外）
- `workers = 4`（也可通过环境变量 `GUNICORN_WORKERS` 覆盖）
- `debug = False`（安全）

测试能否正常启动：

```bash
source venv/bin/activate
gunicorn -c gunicorn.conf.py app:app
# 看到 "Listening at: http://127.0.0.1:5000" 即成功，Ctrl+C 退出
```

---

## 四、systemd 守护进程

1. 将 `blog.service` 复制到系统目录，并修改占位符：

```bash
sudo cp blog.service /etc/systemd/system/blog.service
sudo nano /etc/systemd/system/blog.service
```

需要修改的地方：
- `WorkingDirectory=/path/to/your/project` → 改成 `/var/www/infowe.site`
- `User=` / `Group=` → 改成你的运行用户（如 `www-data`，需对该目录有读权限）
- `Environment=BLOG_SECRET_KEY=...` → 填第二步生成的随机串
- `ExecStart` 里的 gunicorn 路径 → 若用 venv，改为 `/var/www/infowe.site/venv/bin/gunicorn`

2. 启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now blog
sudo systemctl status blog        # 确认 active (running)
journalctl -u blog -f             # 查看日志
```

---

## 五、Nginx 反代

1. 将 `deploy_infowe.site.conf` 复制到站点目录，修改占位符：

```bash
sudo cp deploy_infowe.site.conf /etc/nginx/sites-available/infowe.site
sudo nano /etc/nginx/sites-available/infowe.site
```

- `alias /path/to/your/project/static` → 改成 `/var/www/infowe.site/static`
- 如需 HTTPS，取消文件底部 443 块的注释，并删除 80 块的 `server` 内容（或保留 80 仅做跳转）

2. 启用并测试：

```bash
sudo ln -s /etc/nginx/sites-available/infowe.site /etc/nginx/sites-enabled/
sudo nginx -t                    # 语法检查
sudo systemctl reload nginx
```

---

## 六、HTTPS（推荐 certbot）

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d infowe.site -d www.infowe.site
# 按提示完成后，certbot 会自动配置 443 并重写 Nginx 配置
```

---

## 七、上线后验证清单

- [ ] 首页、文章页、关于页正常打开
- [ ] 后台 `/admin/login` 可登录，头像上传成功
- [ ] 评论提交后，服务器日志里 `X-Forwarded-For` 解析出**用户真实 IP**（而非 `127.0.0.1`）
- [ ] 访问不存在的页面返回站内 404 页；触发 500 时返回站内 500 页
- [ ] `curl -I https://infowe.site` 返回 200

---

## 八、常见问题

**Q：直接 `python app.py` 能上线吗？**
不能。`__main__` 分支默认 `debug=False`，但仍仅适合本地开发。生产请用 gunicorn，否则无多进程、无守护、无平滑重启。

**Q：改了代码怎么生效？**
```bash
sudo systemctl restart blog
```

**Q：上传文件大小受限？**
Nginx 已设 `client_max_body_size 20m`，如需更大请同步修改 Nginx 配置。

**Q：忘记设置 BLOG_SECRET_KEY 会怎样？**
会 fallback 到源码里的默认值，任何人可据此伪造 session 直接登录后台——**务必设置**。

---

## 九、文件清单

| 文件 | 用途 |
|---|---|
| `gunicorn.conf.py` | gunicorn 生产配置 |
| `deploy_infowe.site.conf` | Nginx 反代配置（含 HTTPS 占位块） |
| `blog.service` | systemd 服务单元 |
| `.gitignore` | 排除日志/缓存/敏感文件 |
| `DEPLOY.md` | 本文件 |
