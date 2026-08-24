# 宝塔面板部署教程（小白版）· infowe.site 个人博客

本文面向**完全没接触过服务器部署**的新手，手把手教你用**宝塔面板**把这个 Flask 博客跑起来并绑定域名。

> 你在本机（Windows）开发时是直接 `python app.py` 启动的，但线上必须用宝塔的「Python 项目 + 反向代理 + SSL」方式，这样才稳定、能上 HTTPS、还能拿到访客真实 IP。

---

## 0. 你需要准备什么

| 项目 | 说明 |
|---|---|
| 一台 Linux 服务器 | 阿里云 / 腾讯云 / 华为云均可，系统选 **CentOS 7+/Debian/Ubuntu** |
| 一个域名 | 例如 `infowe.site`，并已**解析（A 记录）到服务器公网 IP** |
| 宝塔面板 | 已安装好（没装的话官网有「一键安装脚本」） |
| 项目代码 | 已上传到服务器，假设放在 `/www/wwwroot/infowe.site` |

> 域名解析：在域名服务商后台，添加一条 A 记录，`主机记录` 填 `@` 和 `www`，`记录值` 填你的服务器 IP。一般 10 分钟内生效。

---

## 一、宝塔里安装必要软件

1. 登录宝塔面板，打开左侧 **「软件商店」**。
2. 搜索并安装下面两个（装过可跳过）：
   - **Nginx**（Web 服务器，必装）
   - **Python 项目**（新版叫这个名字；旧版叫「Python 项目管理器」）
3. 不用装 MySQL（博客用自带 SQLite 数据库，无需额外数据库）。
4. 不用装 PM2（那是给 Node.js 用的，我们用 Python 管理器即可）。

---

## 二、上传项目代码

有两种方式（任选其一）：

**方式 A：宝塔「文件」直接上传（最简单）**
1. 宝塔左侧 → **「文件」** → 进入 `/www/wwwroot/`。
2. 新建文件夹 `infowe.site`。
3. 把本地项目**整个文件夹**上传进去（包含 `app.py`、`requirements.txt`、`templates/`、`static/` 等）。
   - 如果本地是打包的 zip，上传后右键「解压」即可。

**方式 B：用 FTP 工具（如 FileZilla）**
- 主机填服务器 IP，账号密码用宝塔「面板设置 → FTP」里创建的，或直接用 SFTP（端口 22）登录后拖进去。

上传完确认根目录有这三个关键文件：
```
/www/wwwroot/infowe.site/
├── app.py              ← 程序入口
├── requirements.txt    ← 依赖列表
└── templates/          ← 页面模板
```

---

## 三、添加 Python 项目（真正启动博客）

这一步相当于线上的 `python app.py`，但用 gunicorn 更稳定。

1. 宝塔 → **「Python 项目」**（旧版「Python 项目管理器」）→ **「添加项目」**。
2. 按下表填写：

| 配置项 | 填什么 | 备注 |
|---|---|---|
| 项目名称 | `infowe` | 随便起 |
| 路径 | `/www/wwwroot/infowe.site` | 刚才上传的目录 |
| Python 版本 | 选 3.9 / 3.10 / 3.11 | 服务器装了哪个选哪个 |
| 框架 | `Flask` | 选 Flask |
| 启动文件 | `app.py` | 入口文件 |
| 启动对象 / 应用 | `app` | 即 Flask 实例名 `app`（不是 app.py） |
| 端口 | `5000` | 必须和 app.py 一致 |
| 依赖文件 | 勾选，填 `requirements.txt` | 让宝塔自动装依赖 |
| 开机启动 | ✅ 勾选 | 服务器重启后自动跑 |

3. 点 **「提交」**，等待依赖安装（进度在「消息」里）。状态变成 **运行中** 就成功了。

> ⚠️ 此时还不能直接用浏览器访问域名，因为没有绑域名 + 反代，下一步做。

---

## 四、设置密钥（非常重要，必做）

不设置密钥，任何人都能伪造登录进你后台！

1. 先在**服务器终端**（宝塔「终端」或 SSH 工具）执行下面命令，**生成一串随机密钥并复制它**：

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

输出类似：`a1b2c3d4...`（一长串十六进制），**把它复制下来**。

2. 回到宝塔 → **「Python 项目」** → 找到 `infowe` → **「设置」→「环境变量」**，点添加：

| 名称 | 值 |
|---|---|
| `BLOG_SECRET_KEY` | 刚才复制的那串随机字符 |
| `FLASK_DEBUG` | `0` |

3. 保存后，回到项目列表点 **「重启」** 让配置生效。

> 小提示：`FLASK_DEBUG=0` 表示关闭调试模式（线上必须关，否则报错会暴露代码）。

---

## 五、添加站点 + 反向代理（让域名能访问）

「反向代理」的作用：访客访问 `https://infowe.site` → Nginx 接到请求 → 转给本机 `127.0.0.1:5000` 的 Flask 程序 → 再把结果返回给访客。

### 5.1 添加站点

1. 宝塔 → **「网站」→「添加站点」**。
2. 填写：
   - **域名**：`infowe.site` 和 `www.infowe.site`（一行一个）
   - **根目录**：`/www/wwwroot/infowe.site`（或留默认，反代后不依赖它）
   - **PHP 版本**：选「纯静态」/「不建数据库」
3. 点 **「提交」**。

### 5.2 添加反向代理

1. 进入刚建的站点 → **「反向代理」→「添加反代」**。
2. 填写：

| 配置项 | 填什么 |
|---|---|
| 代理名称 | `flask`（随便起） |
| 目标 URL | `http://127.0.0.1:5000` |
| 发送域名 | `$host` |

3. 点 **「提交」**。

此时访问 `http://infowe.site`（注意还是 http）应该已经能看到博客首页了。

### 5.3 检查反代配置（拿真实访客 IP 用）

1. 在站点「反向代理」里点 **「配置文件」**，确认里面有这几行（宝塔默认一般已带，重点看 `X-Forwarded-For`）：

```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

2. 如果**缺少** `X-Forwarded-For $proxy_add_x_forwarded_for;` 这一行，手动补上，然后点「保存」。
   - 这行配合代码里的 `ProxyFix`，能让后台评论区记录到**访客真实 IP**，而不是统统显示 `127.0.0.1`。

---

## 六、开启 HTTPS（免费 SSL 证书）

让网站变成 `https://`，浏览器地址栏显示小锁。

1. 进入站点 → **「SSL」→「Let's Encrypt」**。
2. 勾选域名 `infowe.site` 和 `www.infowe.site`。
3. 勾选 **「强制 HTTPS」**（可选，勾了 http 会自动跳 https）。
4. 点 **「申请」**，等几秒提示成功。
5. 证书**自动续期**，以后不用管。

> 申请前请确保：域名已正确解析到本服务器 IP，且服务器**安全组/防火墙放行了 80 和 443 端口**，否则签发会失败。

---

## 七、放行端口 & 安全设置

1. 宝塔左侧 → **「安全」**，确认 **放行** 了 `80` 和 `443` 端口（一般默认放）。
2. **不要**对外放行 `5000` 端口！Flask 只给本机 Nginx 反代用，对外开放有安全风险。
3. 如果使用云厂商（阿里云/腾讯云等）的「安全组」，也要在云后台放行 80、443。

---

## 七点五、Nginx 性能优化（让网站访问明显变快）

宝塔默认配置够用，但有几个关键项能让首屏速度和重复访问体验上一个台阶。**全部都是可选**，按需做。

### 7.5.1 补齐 gzip 类型（CSS/JS/字体/SVG 体积砍 60%+）

宝塔默认的 `gzip_types` 通常不全，缺字体和 SVG，会导致 woff2、svg 这些体积大的资源明文传输。

1. 宝塔左侧 → **「软件商店」→ Nginx → 配置文件**（或直接编辑 `/www/server/nginx/conf/nginx.conf`）。
2. 顶部 `http { }` 块里找 `gzip_types` 那一行（没有就加在 `gzip on;` 下面），**替换**为：

```nginx
    gzip on;
    gzip_min_length 1k;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/javascript application/javascript application/json application/xml image/svg+xml font/ttf font/otf application/wasm;
    gzip_vary on;
    gzip_disable "MSIE [1-6]\.";
```

3. 保存后在终端执行 `nginx -t` 检查语法，没报错就 `nginx -s reload` 让它生效。

> 宝塔有时把 gzip 写在独立的 `include` 文件里（如 `conf.d/gzip.conf`），直接编辑那个文件效果一样。

### 7.5.2 给静态资源加缓存头（重复访问秒开）

现在 `expires 30d` 已经够了，但缺 `Cache-Control: immutable`，浏览器在某些场景下还是会发条件请求。加一行 `add_header` 兜底：

1. 进入站点 → **「设置」→「配置文件」**，找到 `server { }` 块。
2. 在 `location /static` 和 `location /uploads` 两个块里**各加一行**（替换原配置也行）：

```nginx
    # 静态资源（本地化后的 vendor/、css/、js/、icons/、images/）
    location /static {
        alias /www/wwwroot/infowe.site/static;   # ← 改成你项目里的实际路径
        expires 30d;
        access_log off;
        add_header Cache-Control "public, max-age=2592000, immutable";
    }

    # 上传文件（v1.0.6 起位于项目根 uploads/）
    location /uploads {
        alias /www/wwwroot/infowe.site/uploads;  # ← 改成你项目里的实际路径
        expires 30d;
        access_log off;
        add_header Cache-Control "public, max-age=2592000, immutable";
    }
```

> ⚠️ `alias` 路径必须以 `/` 结尾，且目录要真实存在，否则 nginx 启动失败。`immutable` 配合代码里 `?t=v1.1.8` 版本号才安全——以后改静态资源就改 `app.py` 的 `VERSION`。

3. 如果站点开启了 HTTPS（80 块 + 443 块），两个块都要写。
4. 保存后 `nginx -t && nginx -s reload`。

### 7.5.3 验证生效

在服务器终端跑：

```bash
curl -I https://你的域名/static/css/style.css
```

应该看到：
- `Content-Encoding: gzip`（gzip 生效）
- `Cache-Control: public, max-age=2592000, immutable`（缓存头生效）

### 7.5.4 这一步做完后能省多少？

| 资源 | 优化前 | 优化后 |
|---|---|---|
| `style.css`（假设 30KB） | 明文 30KB | gzip 后 ~6KB |
| `highlight.min.js`（46KB） | 明文 46KB | gzip 后 ~12KB |
| 字体 woff2 | 明文传输 | gzip/缓存后大幅减少 |
| 重复访问 | 浏览器仍发条件请求 | 直接命中磁盘缓存 |

---

### 7.5.5 （可选）Brotli 压缩：比 gzip 再省 15-20%

gzip 已能让体积减半，Brotli 是同级别里压缩率更高的算法，对 CSS/JS/HTML 效果尤其明显。**前提是 nginx 编译了 brotli 模块**，宝塔默认不带。

1. 先检查你的 nginx 是否已带 brotli：

```bash
nginx -V 2>&1 | grep -i brotli
```

2. **有输出** → 模块已就绪，直接在 nginx 配置 `http { }` 块里加：

```nginx
    brotli on;
    brotli_comp_level 6;
    brotli_types text/plain text/css text/javascript application/javascript application/json application/xml image/svg+xml font/ttf font/otf application/wasm;
```

保存后 `nginx -t && nginx -s reload`。

3. **无输出** → 当前 nginx 没编译 brotli。两种选择：
   - 宝塔 →「软件商店」→ Nginx →「安装」旁的「更换版本」，选一个标注带 brotli 的版本重装（不同宝塔版本选项不同，注意看说明）；
   - 或跳过。**收益只有 15-20%，不装也不影响站点正常运行**。

### 7.5.6 （可选）CDN 边缘缓存：访客从就近节点拿静态资源

如果用了 Cloudflare（免费）、七牛/腾讯云 CDN 等，可以把静态资源交给 CDN 缓存，访客不用每次回你服务器。

以 **Cloudflare 免费版**为例（其他 CDN 同理）：
1. 域名接入 Cloudflare（改 DNS 到它给的地址）。
2. 左侧 **「Caching」→「Cache Rules」→「Create rule」**：

| 设置项 | 值 |
|---|---|
| When incoming requests match | `URI Path starts with /static` 或 `/uploads` |
| Cache eligibility | Eligible for cache |
| Edge TTL | 30 天（**30 days**） |
| Cache key | 默认即可（含 `?t=v1.1.7` 版本号，改版后自动失效） |

3. 保存后，`/static/css/style.css` 等资源由 Cloudflare 边缘节点直接返回，你服务器只处理动态页面。

> ⚠️ 注意：**只缓存 `/static` 和 `/uploads`** 这类带版本号的静态资源，千万不要缓存 `/`、`/posts` 等动态页面，否则改文章不生效、评论也缓存错乱。本项目模板里的静态资源 URL 都带 `?t=v{{ version }}`，天然适合 CDN 缓存。

### 7.5.7 代码高亮库瘦身：highlight.js 11.7.0 完整包 → 10.7.3 common 版

文章页用 highlight.js 做代码高亮。原使用的 `highlight.min.js` 是 **11.7.0 完整包（含 190+ 种语言）**，明文 1MB、gzip 后仍有约 301KB，是**文章页加载变慢的真瓶颈**（首页/列表页不加载它，不受影响）。

实际测量后改为 `highlight.js@10.7.3` 的 **common 构建（37 种常用语言）**：

| 资源 | 版本 | 明文 | gzip |
|---|---|---|---|
| `vendor/highlight.js/highlight.min.js` | 11.7.0 完整包 | 1049 KB | 301 KB |
| `vendor/highlight.js/highlight.min.js` | 10.7.3 common | 135 KB | 42 KB |

文件**仍命名** `highlight.min.js`，所以 `templates/base.html` 里的引用不用改，只换文件本体即可。

> ⚠️ 为什么不直接用 11.x 的 common 版？highlight.js 从 11.0 起 common 构建只提供 ESM 模块（`es/common.min.js`），无法直接用 `<script src>` 加载，需要打包器或 `type="module"` 改造，性价比低。10.7.3 是**最后一个带 UMD common 单文件**的版本，最省事。
>
> 10.x 与 11.x 的 `hljs.highlightAll()` API 以及 `atom-one-dark` 主题 CSS **完全兼容**，博客常用的 python / java / javascript / bash / json / yaml / xml / css / sql 都在 37 种之内。已实测本地文件含 39 个语言注册、无冷门语言，确认是 common 版。
>
> 部署时把整个 `static/vendor/highlight.js/` 目录上传到服务器即可（文件命名没变，无需动 nginx 或模板）。

---

## 八、上线后验证（照着勾）

- [ ] 浏览器打开 `https://infowe.site`，首页正常显示
- [ ] 随便点开一篇文章、关于页能正常看
- [ ] 后台 `https://infowe.site/admin/login` 能登录，上传头像成功
- [ ] 提交一条评论，后台看到的是**访客真实 IP**（不是 127.0.0.1）
- [ ] 随便访问一个不存在的地址（如 `/post/99999`），显示的是站内 404 页
- [ ] 命令行跑 `curl -I https://infowe.site` 返回 `200`

---

## 九、常用操作命令（复制即用）

下面这些在宝塔「终端」或 SSH 里执行。

```bash
# 1) 生成强随机密钥（部署第四步用）
python3 -c "import secrets; print(secrets.token_hex(32))"

# 2) 查看 Python 项目运行日志（排错用）
#    宝塔路径：Python 项目 → infowe → 设置 → 日志
#    或用命令看实时输出（需进入项目目录）：
cd /www/wwwroot/infowe.site && tail -f /www/wwwlogs/infowe.site.log

# 3) 测试 Nginx 配置是否有语法错误
nginx -t

# 4) 重载 Nginx（改了反代/SSL 配置后执行）
systemctl reload nginx

# 5) 重启 Python 项目（改了代码后执行）
#    宝塔里：Python 项目 → infowe → 重启
```

> 宝塔面板里大部分操作点按钮就行，命令行只是备用。改完代码记得去「Python 项目」点**重启**，不用重启 Nginx。

---

## 十、常见问题（小白必看）

**Q1：添加 Python 项目后访问域名显示 502 Bad Gateway？**
- 先看「Python 项目」状态是不是 **运行中**；不是就点启动。
- 端口是不是 `5000`，必须和 `app.py` 里一致。
- 看项目日志（Python 管理器里有「日志」按钮），常见原因：依赖没装全、或 `BLOG_SECRET_KEY` 没设导致启动报错。

**Q2：改了代码怎么让它生效？**
回到宝塔「Python 项目」→ 找到 `infowe` → 点 **「重启」** 即可，不用动 Nginx。

**Q3：上传头像/图片失败，或报 413？**
在站点「设置 → 配置文件」的 `server` 块里加一行 `client_max_body_size 20m;`，点保存重载 Nginx。

**Q4：忘了设置 BLOG_SECRET_KEY 会怎样？**
会退回代码里的默认值，别人能伪造登录进你后台，**务必设置**（见第四步）。

**Q5：HTTPS 申请失败？**
- 确认域名 A 记录已解析到本服务器 IP（可 `ping 你的域名` 看是不是这个服务器）。
- 确认 80 端口在安全组和宝塔「安全」里都放行了。
- 等 DNS 生效（几分钟到几小时）再试。

**Q6：反向代理是什么意思，一定要做吗？**
一定要。Flask 自己不能直接漂亮地对外提供 https 和静态资源加速。反代就是让 Nginx 当「前台接待」，把访客请求转给 Flask 这个「后台员工」。按第五步点几下按钮就行，不用懂原理。

---

## 十一、本项目附带的部署文件

| 文件 | 用途 |
|---|---|
| `DEPLOY_BT.md` | 本文件（宝塔小白教程） |
| `DEPLOY.md` | 纯命令行（无宝塔）部署教程 |
| `gunicorn.conf.py` | gunicorn 生产配置（宝塔管理时可不手动用） |
| `deploy_infowe.site.conf` | Nginx 原生配置样例（想手写 Nginx 时参考） |
| `blog.service` | systemd 服务文件（无宝塔的 Linux 用） |
| `.gitignore` | 忽略日志/缓存等不需要上传的文件 |

---

照着上面 0→十 步走完，你的博客就能用 `https://你的域名` 稳定访问了。遇到报错先看「项目日志」和「Nginx 错误日志」（宝塔「文件」里 `/www/wwwlogs/` 目录下），基本都能定位。
