#!/bin/bash
# infowe 博客：代码更新后自动重启（含旧数据目录迁移）
#
# 触发方式：.git/hooks/post-merge 或宝塔计划任务（每分钟兜底）
#
# 行为：
#   1. Git HEAD 未变化 → 静默退出
#   2. 后台在线升级还在 running → 等待 done（failed/超时则跳过）
#   3. requirements.txt 有变化 → 用项目 venv 补装依赖
#   4. 首次升级到 var/ 数据目录 → 停服 → 迁移 → 启动（迁移失败不启动）
#   5. 普通升级 → 清页面缓存 → 对 gunicorn master 发 HUP 平滑重载
#
# 可按需修改下面几个变量，或通过同名环境变量传入：
#   BASE        项目目录
#   PY          项目 venv 的 python
#   PORT        gunicorn 监听端口（健康检查用）
#   STOP_CMD    停止命令，如 systemctl stop infowe（留空则对 master 发 QUIT）
#   START_CMD   启动命令，如 systemctl start infowe（留空则重放原 gunicorn 命令行）
#   BLOG_DATA_DIR  数据目录，默认 $BASE/var
#
# 首次使用：
#   cp tools/infowe-auto-restart.sh /root/infowe-auto-restart.sh
#   chmod 755 /root/infowe-auto-restart.sh
#   sh -n /root/infowe-auto-restart.sh

set -uo pipefail

BASE=${BASE:-/www/wwwroot/infowe.site}
PY=${PY:-$BASE/.venv/bin/python}
PORT=${PORT:-5000}
STOP_CMD=${STOP_CMD:-}
START_CMD=${START_CMD:-}
DATA_DIR=${BLOG_DATA_DIR:-$BASE/var}

HEADFILE="$DATA_DIR/.auto-restart.head"
LOCK="$DATA_DIR/.auto-restart.lock"
REQHASH="$DATA_DIR/.auto-restart.req"
STATE="$DATA_DIR/upgrade_state.json"
HEALTH_URL="http://127.0.0.1:$PORT/"

log() { echo "[$(date '+%F %T')] $*"; }

mkdir -p "$DATA_DIR" 2>/dev/null || true
exec 9>"$LOCK" || exit 1
flock -n 9 || exit 0

cd "$BASE" || { log "项目目录不存在：$BASE"; exit 1; }

CURRENT=$(git rev-parse HEAD 2>/dev/null || true)
if [ -z "$CURRENT" ]; then
  log "读取 Git HEAD 失败，跳过"
  exit 1
fi
LAST=$(cat "$HEADFILE" 2>/dev/null || true)
if [ "$CURRENT" = "$LAST" ]; then
  exit 0
fi
log "检测到代码更新：${LAST:0:8} -> ${CURRENT:0:8}"

# ── 1. 等后台在线升级结束 ─────────────────────────────────
if grep -Eq '"state"[[:space:]]*:[[:space:]]*"running"' "$STATE" 2>/dev/null; then
  log "在线升级进行中，等待完成（最多 10 分钟）"
  for _ in $(seq 1 300); do
    if grep -Eq '"state"[[:space:]]*:[[:space:]]*"done"' "$STATE" 2>/dev/null; then
      break
    fi
    if grep -Eq '"state"[[:space:]]*:[[:space:]]*"failed"' "$STATE" 2>/dev/null; then
      log "在线升级失败，跳过自动重启"
      exit 1
    fi
    sleep 2
  done
  grep -Eq '"state"[[:space:]]*:[[:space:]]*"done"' "$STATE" 2>/dev/null \
    || { log "等待升级超时，跳过自动重启"; exit 1; }
fi
if grep -Eq '"state"[[:space:]]*:[[:space:]]*"failed"' "$STATE" 2>/dev/null; then
  log "升级状态为 failed，跳过自动重启"
  exit 1
fi

# ── 2. 依赖变化补装（手动 git pull 时在线升级不会跑 pip） ──
NEW_REQ=$(sha256sum requirements.txt 2>/dev/null | awk '{print $1}')
OLD_REQ=$(cat "$REQHASH" 2>/dev/null || true)
if [ -n "$NEW_REQ" ] && [ "$NEW_REQ" != "$OLD_REQ" ]; then
  log "requirements.txt 有变化，安装依赖"
  if ! "$PY" -m pip install -r requirements.txt; then
    log "依赖安装失败，保留旧进程"
    exit 1
  fi
  echo "$NEW_REQ" > "$REQHASH"
fi

# ── 3. 是否需要把旧数据目录迁移到 var/ ────────────────────
NEED_MIGRATE=0
if [ ! -f "$DATA_DIR/.migrated" ]; then
  for d in data uploads backups storage instance; do
    if [ -d "$BASE/$d" ] && [ -n "$(find "$BASE/$d" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]; then
      NEED_MIGRATE=1
      break
    fi
  done
fi

find_master() {
  pgrep -o -f 'gunicorn.*infowe' 2>/dev/null \
    || ps -eo pid,args | awk '/[g]unicorn/ && $0 !~ /worker/ && /infowe/ { print $1; exit }'
}

clear_page_cache() {
  rm -rf "$DATA_DIR/storage/cache/pages"/* 2>/dev/null || true
}

health_check() {
  for _ in $(seq 1 30); do
    if curl -fsS -o /dev/null --max-time 3 "$HEALTH_URL"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

MASTER=$(find_master || true)

if [ "$NEED_MIGRATE" = "1" ]; then
  log "检测到旧版数据目录，需要停机迁移到 $DATA_DIR"

  if [ -n "$STOP_CMD" ]; then
    log "停止服务：$STOP_CMD"
    sh -c "$STOP_CMD" || true
  elif [ -n "${MASTER:-}" ] && kill -0 "$MASTER" 2>/dev/null; then
    CMD=$(ps -p "$MASTER" -o args= 2>/dev/null || true)
    log "停止 gunicorn master $MASTER（QUIT）"
    kill -QUIT "$MASTER" 2>/dev/null || true
    for _ in $(seq 1 30); do
      kill -0 "$MASTER" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$MASTER" 2>/dev/null; then
      log "master 30 秒未退出，发送 TERM"
      kill -TERM "$MASTER" 2>/dev/null || true
      sleep 3
    fi
  else
    log "未发现运行中的 gunicorn，视为已停止"
    CMD=""
  fi

  # 停服后再迁移：SQLite 已 checkpoint，WAL 会随主库一起移动
  if [ -f "$BASE/services/storage.py" ]; then
    log "迁移数据目录 → $DATA_DIR"
    if ! ( cd "$BASE" && BLOG_DATA_DIR="$DATA_DIR" "$PY" -m services.storage --force ); then
      log "数据目录迁移失败，为避免旧库继续写入，本次不启动；处理后可手动重启"
      exit 1
    fi
  else
    log "代码中缺少 services/storage.py，跳过数据目录迁移"
  fi

  clear_page_cache

  if [ -n "$START_CMD" ]; then
    log "启动服务：$START_CMD"
    sh -c "$START_CMD" || true
  elif [ -n "${CMD:-}" ]; then
    log "未配置 START_CMD，按原命令行重启"
    nohup sh -c "cd '$BASE' && exec $CMD" >>"$DATA_DIR/gunicorn-restart.log" 2>&1 &
  else
    log "无法确定启动方式，请手动启动服务（迁移已完成，下次启动即可用）"
    exit 1
  fi

  if health_check; then
    log "服务已恢复：$HEALTH_URL"
  else
    log "健康检查失败：$HEALTH_URL，请查看项目日志"
    exit 1
  fi
else
  if [ -z "${MASTER:-}" ] || ! kill -0 "$MASTER" 2>/dev/null; then
    log "未找到 gunicorn master，跳过平滑重载（服务可能未运行）"
    echo "$CURRENT" > "$HEADFILE"
    exit 0
  fi
  clear_page_cache
  if kill -HUP "$MASTER"; then
    log "已平滑重载 gunicorn master $MASTER"
  else
    log "向 master 发送 HUP 失败"
    exit 1
  fi
fi

echo "$CURRENT" > "$HEADFILE"
log "完成，记录 commit ${CURRENT:0:8}"
