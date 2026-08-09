# gunicorn 配置文件 —— 生产部署用
# 启动示例：gunicorn -c gunicorn.conf.py app:app

import os

# 绑定的内部地址（由 Nginx 反代，不对外网直接暴露）
bind = "127.0.0.1:5000"

# worker 数量：建议 (2 × CPU核心数) + 1；这里是单站轻量博客，4 个足够
workers = int(os.environ.get("GUNICORN_WORKERS", "4"))

# worker 类型：sync 足够；如需长连接可换 gthread
worker_class = "sync"

# 每个 worker 最大并发请求数，到量后重启，防内存泄漏
max_requests = 1000
max_requests_jitter = 50

# 超时（秒）
timeout = 60
graceful_timeout = 30
keepalive = 5

# 日志
accesslog = "-"
errorlog = "-"
loglevel = "info"

# 进程文件（可选，便于 systemd 管理）
pidfile = "gunicorn.pid"

# 避免 worker 把调试器打开（生产必须 False）
reload = False
