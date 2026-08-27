#!/usr/bin/env bash
# =============================================================================
# 霜铃 · K12 AI 数字教师 V3 —— 一键关闭脚本
#
# 用法: bash scripts/stop.sh [--keep-db]
#
# 默认: 关闭前端 + 后端 + 后台 Worker + 数据库容器（docker compose stop，数据卷保留）
#   --keep-db  只关前端 + 后端 + Worker，数据库容器保持运行
#
# 幂等: 已关闭的服务静默跳过；重复执行安全。
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEEP_DB=""
[ "${1:-}" = "--keep-db" ] && KEEP_DB=1

log()  { echo -e "\033[1;34m[STOP ]\033[0m $*"; }
warn() { echo -e "\033[1;33m[WARN ]\033[0m $*"; }

cd "$ROOT"

stop_pid() {
  local pid="$1"
  local label="$2"

  if ! kill -0 "$pid" >/dev/null 2>&1; then
    warn "$label pid $pid 已不在运行"
    return
  fi

  # start.sh 用 setsid 建立独立进程组；优先整组关闭，避免 pnpm/uvicorn
  # 的 Node/Python 子进程残留。兼容旧版 PID 文件时回退为单进程 kill。
  if kill -0 -- "-$pid" >/dev/null 2>&1; then
    kill -TERM -- "-$pid" 2>/dev/null || true
  else
    kill -TERM "$pid" 2>/dev/null || true
  fi

  for _ in $(seq 1 20); do
    kill -0 "$pid" >/dev/null 2>&1 || break
    sleep 0.1
  done

  if kill -0 "$pid" >/dev/null 2>&1; then
    if kill -0 -- "-$pid" >/dev/null 2>&1; then
      kill -KILL -- "-$pid" 2>/dev/null || true
    else
      kill -KILL "$pid" 2>/dev/null || true
    fi
  fi
  log "已关闭 $label（进程组/进程 $pid）"
}

cleanup_port() {
  local port="$1"
  local label="$2"
  local pids
  pids="$(lsof -ti :"$port" 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    printf '%s\n' "$pids" | xargs -r kill -TERM 2>/dev/null || true
    log "已清理 $label 端口残留进程（:$port）"
  fi
}

# ---------- 1. 前端 ----------
if [ -f frontend/.server.pid ]; then
  PID="$(cat frontend/.server.pid)"
  stop_pid "$PID" "前端 dev"
  rm -f frontend/.server.pid
else
  # 无 PID 文件时按端口兜底
  if lsof -ti :5174 >/dev/null 2>&1; then
    lsof -ti :5174 | xargs -r kill 2>/dev/null
    log "已按端口 5174 关闭前端"
  else
    log "前端未在运行"
  fi
fi
cleanup_port 5174 "前端"

# ---------- 2. 后台 Worker ----------
if [ -f backend/.worker.pid ]; then
  PID="$(cat backend/.worker.pid)"
  stop_pid "$PID" "后台 Worker"
  rm -f backend/.worker.pid
else
  # 无 PID 文件时按进程特征兜底（仅匹配本项目 worker 入口，避免误伤）
  WORKER_PIDS="$(pgrep -f 'python -m app\.jobs\.worker' 2>/dev/null || true)"
  if [ -n "$WORKER_PIDS" ]; then
    printf '%s\n' "$WORKER_PIDS" | xargs -r kill -TERM 2>/dev/null || true
    log "已按进程特征关闭后台 Worker"
  else
    log "后台 Worker 未在运行"
  fi
fi

# ---------- 3. 后端 ----------
if [ -f backend/.server.pid ]; then
  PID="$(cat backend/.server.pid)"
  stop_pid "$PID" "后端 API"
  rm -f backend/.server.pid
else
  if lsof -ti :8002 >/dev/null 2>&1; then
    lsof -ti :8002 | xargs -r kill 2>/dev/null
    log "已按端口 8002 关闭后端"
  else
    log "后端未在运行"
  fi
fi
cleanup_port 8002 "后端"

# ---------- 4. 数据库 ----------
if [ -z "$KEEP_DB" ]; then
  log "关闭 PostgreSQL 容器（数据卷保留，--keep-db 可跳过）..."
  docker compose stop postgres 2>/dev/null && log "PostgreSQL 已停止" || log "PostgreSQL 未在运行"
else
  log "--keep-db：数据库容器保持运行"
fi

echo ""
log "✅ 关闭完成"
echo "    下次启动: bash scripts/start.sh"
