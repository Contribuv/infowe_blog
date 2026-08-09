## 一个不合格的 Dockerfile

```dockerfile
FROM python:3.12
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
CMD ["python", "app.py"]
```

这个 Dockerfile 能跑，但问题很多：镜像巨大、以 root 运行、缓存无效。下面是改进版。

## 最佳实践 Dockerfile

```dockerfile
# 1. 明确基础镜像版本 + slim 减小体积
FROM python:3.12-slim AS builder

# 2. 先安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# 3. 虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 4. 先复制依赖文件（利用 Docker 缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 生产阶段，最小化
FROM python:3.12-slim

# 6. 创建非 root 用户
RUN useradd --create-home --shell /bin/bash app

# 7. 复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 8. 复制应用代码
COPY --chown=app:app . /app
WORKDIR /app

# 9. 切换到非 root 用户
USER app

# 10. 健康检查
HEALTHCHECK --interval=30s --timeout=3s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# 11. 明确端口
EXPOSE 8000

CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "app:app"]
```

## 关键原则

### 1. 多阶段构建

编译依赖不进最终镜像，大幅减小体积。

### 2. 非 root 运行

```yaml
# docker-compose.yml 中也不要乱加 privileged
services:
  app:
    user: "1000:1000"  # 明确用户
```

### 3. .dockerignore

```dockerignore
__pycache__
*.pyc
.git
.env
venv/
*.egg-info/
```

### 4. 日志输出到 stdout

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler()]  # stdout
)
```

## 总结

一条好 Dockerfile 的五个标准：
- **小**（多阶段构建 + slim 镜像）
- **安全**（非 root + 最小权限）
- **快**（利用缓存层）
- **可观测**（健康检查 + 日志）
- **可重现**（固定版本号）
