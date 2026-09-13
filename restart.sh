#!/usr/bin/env bash
# ============================================================
# infowe-blog 一键重启脚本（Linux）—— 自适应托管方式
# 用法：bash restart.sh
#
# 两种模式：
#   1) 服务由 supervisor 托管（如宝塔 Python 项目管理器）
#      → 调用 supervisorctl restart <程序名>，交由托管器重启
#   2) 裸进程（python app.py 直跑）
#      → 停掉占用端口的旧进程，nohup 后台重新拉起
# ============================================================
set -u
PORT="${PORT:-5000}"
APP_DIR="$(cd "$(dirname "$0")" && pwd)"

# 定位监听端口的进程（lsof 取第一个）
WEB_PID="$(lsof -ti tcp:"${PORT}" 2>/dev/null | head -1)"

# 沿父进程链向上最多 10 层，判断是否由 supervisord 托管
is_supervisor_child() {
    local pid="$1" p n i
    for i in $(seq 1 10); do
        [ -r "/proc/$pid/status" ] || break
        n="$(awk '/^Name:/{print $2}' "/proc/$pid/status")"
        if [ "$n" = "supervisord" ]; then
            return 0
        fi
        p="$(awk '/^PPid:/{print $2}' "/proc/$pid/status")"
        [ -z "$p" ] && break
        [ "$p" -le 1 ] && break
        pid="$p"
    done
    return 1
}

# ---------- 模式 1：supervisor 托管 ----------
if [ -n "$WEB_PID" ] && is_supervisor_child "$WEB_PID"; then
    echo "[supervisor 托管] 服务由 supervisord 管理，改用托管器重启"
    SUPERVISORCTL=""
    for c in supervisorctl /www/server/panel/pyenv/bin/supervisorctl; do
        if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then
            SUPERVISORCTL="$c"
            break
        fi
    done
    if [ -z "$SUPERVISORCTL" ]; then
        echo "检测到服务由 supervisor 托管，但未找到 supervisorctl 命令。"
        echo "请到宝塔面板 → Python 项目管理器，手动重启该项目。"
        exit 1
    fi
    # 从 supervisorctl status 输出中按 PID 匹配程序名（格式：名称 RUNNING pid N, ...）
    PROG="$("$SUPERVISORCTL" status 2>/dev/null | awk -v pid="$WEB_PID" \
            '$0 ~ ("pid " pid "[, ]") {print $1; exit}')"
    if [ -n "$PROG" ]; then
        echo "匹配到程序: $PROG，执行 supervisorctl restart $PROG"
        exec "$SUPERVISORCTL" restart "$PROG"
    fi
    # 匹配不到程序名：结束进程，由 supervisor 的 autorestart 自动拉起（加载新代码）
    echo "未能匹配程序名，直接结束进程，交由 supervisor 自动拉起"
    kill "$WEB_PID" 2>/dev/null || true
    exit 0
fi

# ---------- 模式 2：裸进程（python app.py 直跑） ----------
echo "[1/2] 查找并停止占用 ${PORT} 端口的进程..."
if [ -n "$WEB_PID" ]; then
    echo "   找到 PID: $WEB_PID，正在停止..."
    kill "$WEB_PID" 2>/dev/null || true
    sleep 2
    # 2 秒不退则强杀
    kill -9 "$WEB_PID" 2>/dev/null || true
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