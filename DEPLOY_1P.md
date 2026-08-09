# 1Panel 面板部署教程（小白版）· infowe.site 个人博客

本文面向新手，教你用 **1Panel 面板**把 Flask 博客部署上线并绑定域名 + HTTPS。

> 1Panel 和宝塔类似，但更轻量、界面更现代。它**没有「Python 项目」一键托管**，所以我们需要：自己准备一个带 sqlite3 的 Python → 用进程守护跑 gunicorn → 用 1Panel 的「网站（OpenResty 反向代理）」把域名指过来。

---

## 0. 准备清单

| 项目 | 说明 |
|---|---|
| Linux 服务器 | 腾讯云 / 阿里云 / 华为云等，系统 Debian/Ubuntu/CentOS |
| 域名 | 已解析（A 记录）到服务器公网 IP |
| 1Panel | 已安装（官网有一键脚本） |
| 项目代码 | 上传到服务器，假设 `/opt/infowe.site` |

---

## 一、上传项目代码

1. 1Panel 左侧 → **「主机」→「文件」**，进入 `/opt`，新建文件夹 `infowe.site`。
2. 把本地项目**整个目录**上传进去（含 `app.py`、`requirements.txt`、`templates/`、`static/`、`.env` 等）。
   - 也可在本机打包成 zip 上传后右键解压。
3. 确认根目录有 `app.py`、`requirements.txt`、`.env`。

---

## 二、准备 Python 环境（关键：必须有 sqlite3）

1Panel **不提供 Python 版本管理**，要用服务器系统自带的 Python。

**SSH 进服务器，先测系统 Python 是否带 sqlite3：**

```bash
python3 --version
python3 -c "import sqlite3; print('sqlite3 OK', sqlite3.sqlite_version)"
```

- 输出 `sqlite3 OK ...` → 系统 Python 可用，记下路径：`which python3`（通常是 `/usr/bin/python3`）。
- 报错（ImportError）→ 先装开发库：

```bash
# Debian / Ubuntu
sudo apt update && sudo apt install -y python3 python3-venv python3-pip libsqlite3-dev

# CentOS / Rocky
sudo dnf install -y python3 python3-pip sqlite-devel
```

装完再测一次上面的 `import sqlite3`，确认 OK。

**建议用虚拟环境（干净、好管理）：**

```bash
cd /opt/infowe.site
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
deactivate
```

> 记下虚拟环境里的 python 和 gunicorn 路径，下一步要用：
> - Python：`/opt/infowe.site/venv/bin/python`
> - gunicorn：`/opt/infowe.site/venv/bin/gunicorn`

---

## 三、用进程守护跑 gunicorn（让服务常驻）

1Panel 里没有 systemd 编辑界面，但可以用 **「主机」→「进程守护」**（1Panel 自带 Supervisor 类功能）来托管。

### 3.1 如果没有「进程守护」入口

用 systemd（SSH 执行）：

```bash
sudo tee /etc/systemd/system/infowe.service > /dev/null <<'EOF'
[Unit]
Description=infowe blog (gunicorn)
After=network.target

[Service]
WorkingDirectory=/opt/infowe.site
Environment=FLASK_DEBUG=0
ExecStart=/opt/infowe.site/venv/bin/gunicorn -c gunicorn.conf.py app:app
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now infowe
sudo systemctl status infowe        # 看到 active (running) 即成功
```

> 说明：`gunicorn.conf.py` 里已设 `bind = "127.0.0.1:5000"`，只对内网开放，安全。

### 3.2 验证 gunicorn 已监听

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5000
# 返回 200 即正常
```

---

## 四、1Panel 添加网站 + 反向代理

1. 1Panel 左侧 → **「网站」→「创建网站」**。
2. 选 **「反向代理」** 类型（不是「运行时」/「静态」）。
3. 填写：
   - **主域名**：`infowe.site`
   - **代理地址**：`http://127.0.0.1:5000`
   - 其他默认。
4. 提交。

> 1Panel 默认会用 OpenResty（Nginx）生成反代配置，并自动带上 `X-Forwarded-For` 等头，配合代码的 `ProxyFix` 能拿到访客真实 IP。

如需手动确认/补充反代头，编辑该网站的配置文件，确保有：

```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

---

## 五、开启 HTTPS（1Panel 一键证书）

1. 进入网站 → **「证书」/「SSL」** → 申请 **Let's Encrypt 免费证书**（填邮箱，勾选域名）。
2. 申请成功后，网站设置里开启 **「强制 HTTPS」**。
3. 1Panel 会自动改 443 配置并保留反代。

> 申请前确保：域名已解析到本服务器 IP，且云厂商安全组 + 服务器防火墙放行 **80 / 443**。

---

## 六、环境变量（密钥）说明

项目根目录的 `.env` 文件内容（已生成）：

```ini
BLOG_SECRET_KEY=你的随机密钥
FLASK_DEBUG=0
```

因为我们是用 `gunicorn -c gunicorn.conf.py app:app` 直接启动 `app.py`，而 `app.py` 里用 `os.environ.get('BLOG_SECRET_KEY', ...)` 读取，**所以 `.env` 必须被加载**。

最简单的方式：在 `ExecStart` 同环境里导出，或改用支持 dotenv 的启动。推荐直接用 systemd 的 `EnvironmentFile`：

```bash
sudo tee -a /etc/systemd/system/infowe.service > /dev/null <<'EOF'
EnvironmentFile=/opt/infowe.site/.env
EOF
sudo systemctl daemon-reload
sudo systemctl restart infowe
```

（若用 1Panel 进程守护，在「环境变量」里手动加这两项：`BLOG_SECRET_KEY`、`FLASK_DEBUG=0` 即可。）

---

## 七、上线验证清单

- [ ] `curl http://127.0.0.1:5000` 返回 200
- [ ] 浏览器打开 `https://infowe.site` 首页正常
- [ ] 文章页、关于页正常
- [ ] 后台 `/admin/login` 能登录，头像上传成功
- [ ] 评论区记录到**访客真实 IP**（不是 127.0.0.1）
- [ ] 不存在的页面返回站内 404

---

## 八、常用命令（复制即用）

```bash
# 查看服务状态 / 日志
sudo systemctl status infowe
sudo journalctl -u infowe -f

# 改了代码后重启
sudo systemctl restart infowe

# 重新安装依赖（代码/依赖变动后）
cd /opt/infowe.site && source venv/bin/activate && pip install -r requirements.txt

# 测试端口
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5000
```

---

## 九、常见问题

**Q：gunicorn 启动报 `No module named 'sqlite3'`？**
系统 Python 缺 sqlite3。按第二步装 `libsqlite3-dev` / `sqlite-devel` 后重跑 `import sqlite3` 测试，再用虚拟环境重装依赖。

**Q：1Panel 没有「Python 项目」怎么办？**
正常。1Panel 用「进程守护 + 网站反代」组合，本文就是这套方案，不用宝塔那种一键 Python。

**Q：访问域名 502？**
- gunicorn 是否在跑：`sudo systemctl status infowe`
- 端口是否 5000 且绑定 127.0.0.1
- 防火墙/安全组是否放行 80、443

**Q：改了代码不生效？**
`systemctl restart infowe`（或 1Panel 进程守护重启）。Nginx/OpenResty 不用动。

**Q：忘记设 BLOG_SECRET_KEY？**
会退回代码默认值，有 session 伪造风险。务必在 `.env` 或进程守护环境变量里设置并重启。

---

## 十、本项目部署文件清单

| 文件 | 用途 |
|---|---|
| `DEPLOY_1P.md` | 本文件（1Panel 教程） |
| `DEPLOY_BT.md` | 宝塔面板教程 |
| `DEPLOY.md` | 纯命令行 Linux 教程 |
| `gunicorn.conf.py` | gunicorn 生产配置（绑 127.0.0.1:5000） |
| `.env` | 密钥与调试开关 |
| `blog.service` | systemd 服务文件（本教程第三步用） |
| `deploy_infowe.site.conf` | Nginx 原生配置样例 |
| `.gitignore` | 忽略日志/缓存/密钥文件 |
