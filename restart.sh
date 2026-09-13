#!/usr/bin/env bash
# ============================================================
# infowe-blog 一键重启脚本（Linux）
# 用法：bash restart.sh
# 作用：停掉占用 5000 端口的旧进程 → 后台重新拉起
# （仅适用于 python app.py 直跑、端口 5000 的部署方式）
# ============================================================
set -u
PORT="${PORT:-5000}"
APP_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[1/2] 查找并停止占用 ${PORT} 端口的进程..."
PIDS="$(lsof -ti tcp:"${PORT}" 2>/dev/null || true)"
if [ -n "$PIDS" ]; then
    echo "   找到 PID: $PIDS，正在停止..."
    kill $PIDS 2>/dev/null || true
    sleep 2
    # 2 秒不退则强杀
    kill -9 $PIDS 2>/dev/null || true
else
    echo "   未发现占用 ${PORT} 端口的进程"
fi

echo "[2/2] 启动新进程..."
cd "$APP_DIR" || exit 1
mkdir -p logs
# 用 python3，若不存在则回退 python
PY=python3
command -v "$PY" >/dev/null 2>&1 || PY=python
nohup "$PY" app.py >> logs/app.log 2>&1 &

echo "重启完成（PID: $!）。日志输出到 logs/app.log"