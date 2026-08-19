#!/usr/bin/env bash
# =============================================================================
# 霜铃 · K12 AI 数字教师 V3 —— 一键关闭脚本
#
# 用法: bash scripts/stop.sh [--keep-db]
#
# 默认: 关闭前端 + 后端 + 数据库容器（docker compose stop，数据卷保留）
#   --keep-db  只关前端 + 后端，数据库容器保持运行
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

# ---------- 1. 前端 ----------
if [ -f frontend/.server.pid ]; then
  PID="$(cat frontend/.server.pid)"
  if kill -0 "$PID" >/dev/null 2>&1; then
    kill "$PID" 2>/dev/null && log "已关闭前端 dev（pid $PID）"
  else
    warn "前端 pid $PID 已不在运行"
  fi
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

# ---------- 2. 后端 ----------
if [ -f backend/.server.pid ]; then
  PID="$(cat backend/.server.pid)"
  if kill -0 "$PID" >/dev/null 2>&1; then
    kill "$PID" 2>/dev/null && log "已关闭后端 API（pid $PID）"
  else
    warn "后端 pid $PID 已不在运行"
  fi
  rm -f backend/.server.pid
else
  if lsof -ti :8002 >/dev/null 2>&1; then
    lsof -ti :8002 | xargs -r kill 2>/dev/null
    log "已按端口 8002 关闭后端"
  else
    log "后端未在运行"
  fi
fi

# ---------- 3. 数据库 ----------
if [ -z "$KEEP_DB" ]; then
  log "关闭 PostgreSQL 容器（数据卷保留，--keep-db 可跳过）..."
  docker compose stop postgres 2>/dev/null && log "PostgreSQL 已停止" || log "PostgreSQL 未在运行"
else
  log "--keep-db：数据库容器保持运行"
fi

echo ""
log "✅ 关闭完成"
echo "    下次启动: bash scripts/start.sh"
