#!/usr/bin/env bash
# =============================================================================
# 霜铃 · K12 AI 数字教师 V3 —— 一键启动脚本
#
# 用法: bash scripts/start.sh [--with-minio] [--backend-only]
#
# 默认启动: PostgreSQL(docker) → 后端 API(:8002) → 前端 dev(:5174)
#   --with-minio   同时启动 redis + minio（默认只起 postgres，MVP 用不上 redis/minio）
#   --backend-only 只起数据库 + 后端（不启动前端）
#
# 说明:
#   - 宿主 8000 被 DAI 项目占用，后端固定用 8002；前端 5173 也被 DAI 前端占用，改用 5174；
#     前端 vite proxy 经 VITE_API_PROXY_TARGET=http://localhost:8002 转发到后端（规避 CORS）。
#   - 幂等: 已运行的服务自动跳过；重复执行安全。
#   - PID 记录在 backend/.server.pid / frontend/.server.pid，stop.sh 据此关闭。
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT=8002
FRONTEND_PORT=5174
WITH_MINIO="${1:-}"
BACKEND_ONLY="${2:-}"

# 图形化启动器通常不会读取 ~/.bashrc，因而不会加载 NVM 的 Node/pnpm 路径。
# 先补常见用户级路径，避免「终端里有 pnpm、双击脚本却找不到」的环境差异。
export PATH="$HOME/.local/bin:$HOME/.local/share/pnpm:$PATH"
if [ -d "$HOME/.nvm/versions/node" ]; then
  for node_bin in "$HOME"/.nvm/versions/node/*/bin; do
    [ -x "$node_bin/node" ] && export PATH="$node_bin:$PATH"
  done
fi

PNPM_CMD=()
if command -v pnpm >/dev/null 2>&1; then
  PNPM_CMD=(pnpm)
elif command -v corepack >/dev/null 2>&1; then
  # Node 自带 Corepack 时，不要求用户额外建立 pnpm 全局软链接。
  PNPM_CMD=(corepack pnpm)
else
  PNPM_CMD=()
fi

for arg in "$@"; do
  case "$arg" in
    --with-minio) WITH_MINIO=1 ;;
    --backend-only) BACKEND_ONLY=1 ;;
  esac
done

log()  { echo -e "\033[1;32m[START]\033[0m $*"; }
warn() { echo -e "\033[1;33m[WARN ]\033[0m $*"; }
die()  { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; exit 1; }

open_browser() {
  local url="$1"
  local opener=""

  # 启动脚本可能来自终端、桌面启动器或 WSL，按当前系统选择默认浏览器启动器。
  if command -v xdg-open >/dev/null 2>&1; then
    opener="xdg-open"
  elif command -v gio >/dev/null 2>&1; then
    opener="gio"
  elif command -v open >/dev/null 2>&1; then
    opener="open"
  fi

  if [ -n "$opener" ]; then
    if [ "$opener" = "gio" ]; then
      nohup gio open "$url" >/dev/null 2>&1 &
    else
      nohup "$opener" "$url" >/dev/null 2>&1 &
    fi
    log "    已请求系统默认浏览器打开: $url"
  elif command -v powershell.exe >/dev/null 2>&1; then
    nohup powershell.exe -NoProfile -Command "Start-Process '$url'" \
      >/dev/null 2>&1 &
    log "    已请求系统默认浏览器打开: $url"
  else
    warn "    未找到可用的浏览器启动器，请手动打开: $url"
  fi
}

# ---------- 1. 依赖检查 ----------
command -v docker >/dev/null || die "docker 未安装"
command -v uv     >/dev/null || die "uv 未安装（后端包管理器）"
[ -x "$(command -v setsid 2>/dev/null || true)" ] || die "setsid 未安装（用于关闭时清理子进程）"
[ "${#PNPM_CMD[@]}" -gt 0 ] || die "pnpm 未安装（前端包管理器）；请先安装 pnpm 或启用 Node Corepack"
cd "$ROOT"

# ---------- 2. 数据库 ----------
log "1/4 启动 PostgreSQL（pgvector:pg18）..."
if docker ps --format '{{.Names}}' | grep -q '^k12.*postgres\|-postgres-1$'; then
  log "    PostgreSQL 已在运行，跳过"
else
  if [ -n "$WITH_MINIO" ]; then
    docker compose up -d postgres redis minio
    log "    PostgreSQL + Redis + MinIO 已启动"
  else
    docker compose up -d postgres
    log "    PostgreSQL 已启动（redis/minio 用 --with-minio 启动）"
  fi
  # 等待健康
  for i in $(seq 1 30); do
    if docker exec "$(docker compose ps -q postgres)" pg_isready -U shuangling -d shuangling >/dev/null 2>&1; then
      break
    fi
    [ "$i" = 30 ] && die "PostgreSQL 30s 内未就绪"
    sleep 1
  done
  log "    PostgreSQL 就绪"
fi

# ---------- 3. 后端 ----------
log "2/4 启动后端 API（uvicorn :${BACKEND_PORT}）..."
if lsof -ti :"$BACKEND_PORT" >/dev/null 2>&1; then
  warn "    :${BACKEND_PORT} 已被占用，跳过启动（可能已在运行）"
else
  cd "$ROOT/backend"
  [ -d .venv ] || { warn "    未找到 .venv，执行 uv sync..."; uv sync; }
  nohup setsid uv run uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" \
    > /tmp/k12-backend.log 2>&1 &
  echo $! > .server.pid
  for i in $(seq 1 30); do
    if curl -sf "http://localhost:${BACKEND_PORT}/api/v1/ping" >/dev/null 2>&1; then
      break
    fi
    [ "$i" = 30 ] && die "后端 30s 内未就绪（日志: /tmp/k12-backend.log）"
    sleep 1
  done
  log "    后端就绪: http://localhost:${BACKEND_PORT}（pid $(cat .server.pid)）"
fi

# ---------- 4. 前端 ----------
if [ -z "$BACKEND_ONLY" ]; then
  log "3/4 启动前端 dev（vite :${FRONTEND_PORT}）..."
  if lsof -ti :"$FRONTEND_PORT" >/dev/null 2>&1; then
    warn "    :${FRONTEND_PORT} 已被占用，跳过启动（可能已在运行）"
  else
    cd "$ROOT/frontend"
    [ -d node_modules ] || { warn "    未找到 node_modules，执行 pnpm install..."; "${PNPM_CMD[@]}" install; }
    VITE_API_PROXY_TARGET="http://localhost:${BACKEND_PORT}" \
      nohup setsid "${PNPM_CMD[@]}" dev --port "$FRONTEND_PORT" --strictPort > /tmp/k12-frontend.log 2>&1 &
    echo $! > .server.pid
    for i in $(seq 1 30); do
      if curl -sf "http://localhost:${FRONTEND_PORT}" >/dev/null 2>&1; then
        break
      fi
      [ "$i" = 30 ] && die "前端 30s 内未就绪（日志: /tmp/k12-frontend.log）"
      sleep 1
    done
    log "    前端就绪: http://localhost:${FRONTEND_PORT}（pid $(cat .server.pid)）"
  fi
else
  log "3/4 --backend-only：跳过前端"
fi

# ---------- 5. 演示数据 ----------
log "4/4 检查演示数据（seed）..."
cd "$ROOT/backend"
if ! curl -sf "http://localhost:${BACKEND_PORT}/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"xiaoming","password":"demo123"}' >/dev/null 2>&1; then
  uv run python -m app.scripts.seed
  uv run python -m app.scripts.seed_content
  log "    演示数据已 seed（xiaoming/demo123, admin/admin123）"
else
  log "    演示账号已存在，跳过 seed"
fi

echo ""
echo "============================================================================"
log "✅ 启动完成！"
echo "    前端:     http://localhost:${FRONTEND_PORT}"
echo "    后端 API: http://localhost:${BACKEND_PORT}/docs"
echo "    学生账号: xiaoming / demo123"
echo "    管理账号: admin / admin123"
echo "    关闭:     bash scripts/stop.sh"
echo "============================================================================"

if [ -z "$BACKEND_ONLY" ]; then
  open_browser "http://localhost:${FRONTEND_PORT}"
fi
