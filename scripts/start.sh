#!/usr/bin/env bash
# =============================================================================
# 霜铃 · K12 AI 数字教师 V3 —— 一键启动脚本
#
# 用法: bash scripts/start.sh [--with-minio] [--backend-only]
#
# 默认启动: PostgreSQL(docker) → 迁移 → 后端 API(:8002) → Worker(队列消费)
#           → 前端 dev(:5174) → 内容初始化 → 演示账号
#   --with-minio   同时启动 redis + minio（默认只起 postgres，MVP 用不上 redis/minio）
#   --backend-only 只起数据库 + 后端 + Worker（不启动前端）
#
# 说明:
#   - 宿主 8000 被 DAI 项目占用，后端固定用 8002；前端 5173 也被 DAI 前端占用，改用 5174；
#     前端 vite proxy 经 VITE_API_PROXY_TARGET=http://localhost:8002 转发到后端（规避 CORS）。
#   - Worker 与 API 共用 backend 代码与环境（PostgreSQL 表驱动队列，FOR UPDATE SKIP LOCKED），
#     消费 knowledge_ingest / conversation_summary / memory_consolidation 三类任务。
#   - 内容初始化统一走 validate_library --all → import_library --all（幂等）；
#     seed.py 只负责演示账号与演示记忆。
#   - 幂等: 已运行的服务自动跳过；重复执行安全。
#   - PID 记录在 backend/.server.pid / backend/.worker.pid / frontend/.server.pid，
#     stop.sh 据此关闭。
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
    # 浏览器已有实例时，xdg-open 只在后台开新标签、不弹窗口。
    # 1) 有 wmctrl（X11）→ 直接把浏览器窗口激活到前台；
    # 2) 否则发桌面通知提醒用户切换窗口（点击通知可聚焦）。
    sleep 2
    if ! activate_browser_window; then
      command -v notify-send >/dev/null 2>&1 && \
        nohup notify-send -a "霜铃" -u normal "霜铃已启动" "前端已在默认浏览器打开: ${url} （若未见窗口，请切换到浏览器标签页）" >/dev/null 2>&1 &
    fi
  elif command -v powershell.exe >/dev/null 2>&1; then
    nohup powershell.exe -NoProfile -Command "Start-Process '$url'" \
      >/dev/null 2>&1 &
    log "    已请求系统默认浏览器打开: $url"
  else
    warn "    未找到可用的浏览器启动器，请手动打开: $url"
  fi
}

# 把默认浏览器的既有窗口带到前台（仅 X11 会话；无工具/无窗口时静默跳过）
activate_browser_window() {
  local browser_class=""
  case "$(xdg-settings get default-web-browser 2>/dev/null)" in
    microsoft-edge*) browser_class="msedge" ;;
    google-chrome*)  browser_class="google-chrome" ;;
    firefox*)        browser_class="firefox" ;;
    *) return 0 ;;
  esac

  command -v wmctrl >/dev/null 2>&1 || return 0
  [ -n "${DISPLAY:-}" ] || return 0

  # 找到该 class 的第一个窗口并激活 + 切到当前桌面
  local win
  win="$(wmctrl -lx 2>/dev/null | awk -v cls="$browser_class" 'tolower($3) ~ cls {print $1; exit}')"
  if [ -n "$win" ]; then
    wmctrl -i -a "$win" >/dev/null 2>&1 &&
      log "    已将浏览器窗口切换到前台"
  fi
}

# ---------- 1. 依赖检查 ----------
command -v docker >/dev/null || die "docker 未安装"
command -v uv     >/dev/null || die "uv 未安装（后端包管理器）"
[ -x "$(command -v setsid 2>/dev/null || true)" ] || die "setsid 未安装（用于关闭时清理子进程）"
[ "${#PNPM_CMD[@]}" -gt 0 ] || die "pnpm 未安装（前端包管理器）；请先安装 pnpm 或启用 Node Corepack"
cd "$ROOT"

# ---------- 2. 数据库 ----------
log "1/7 启动 PostgreSQL（pgvector:pg18）..."
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

cd "$ROOT/backend"
[ -d .venv ] || { warn "    未找到 .venv，执行 uv sync..."; uv sync; }

# ---------- 3. 数据库迁移（全新环境可迁移）----------
log "2/7 执行数据库迁移（alembic upgrade head）..."
if ! uv run alembic upgrade head; then
  die "alembic upgrade head 失败"
fi
log "    迁移完成"

# ---------- 4. 后端 ----------
log "3/7 启动后端 API（uvicorn :${BACKEND_PORT}）..."
if lsof -ti :"$BACKEND_PORT" >/dev/null 2>&1; then
  warn "    :${BACKEND_PORT} 已被占用，跳过启动（可能已在运行）"
else
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

# ---------- 5. 后台 Worker ----------
log "4/7 启动后台 Worker（PostgreSQL 队列消费）..."
if [ -f .worker.pid ] && kill -0 "$(cat .worker.pid)" >/dev/null 2>&1; then
  log "    Worker 已在运行（pid $(cat .worker.pid)），跳过"
else
  nohup setsid uv run python -m app.jobs.worker > /tmp/k12-worker.log 2>&1 &
  echo $! > .worker.pid
  sleep 1
  if ! kill -0 "$(cat .worker.pid)" >/dev/null 2>&1; then
    die "Worker 启动失败（日志: /tmp/k12-worker.log）"
  fi
  log "    Worker 就绪（pid $(cat .worker.pid)，日志: /tmp/k12-worker.log）"
fi

# ---------- 6. 前端 ----------
if [ -z "$BACKEND_ONLY" ]; then
  log "5/7 启动前端 dev（vite :${FRONTEND_PORT}）..."
  if lsof -ti :"$FRONTEND_PORT" >/dev/null 2>&1; then
    warn "    :${FRONTEND_PORT} 已被占用，跳过启动（可能已在运行）"
  else
    cd "$ROOT/frontend"
    [ -d node_modules ] || { warn "    未找到 node_modules，执行 pnpm install..."; "${PNPM_CMD[@]}" install; }
    # 本地开发默认显示演示账号提示（生产构建不设置该变量）
    VITE_API_PROXY_TARGET="http://localhost:${BACKEND_PORT}" \
      VITE_SHOW_DEMO_CREDENTIALS=true \
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
  log "5/7 --backend-only：跳过前端"
fi

# ---------- 7. 内容初始化 + 演示数据 ----------
log "6/7 初始化图书馆内容（validate_library → import_library）..."
cd "$ROOT/backend"
if ! uv run python -m app.scripts.validate_library --all >/tmp/k12-validate-library.log 2>&1; then
  cat /tmp/k12-validate-library.log
  die "validate_library --all 未通过，禁止导入内容（详见上方输出）"
fi
log "    validate_library --all 通过（$(grep -oE 'books=[0-9]+' /tmp/k12-validate-library.log | tail -1)）"

if ! uv run python -m app.scripts.import_library --all >/tmp/k12-import-library.log 2>&1; then
  tail -40 /tmp/k12-import-library.log
  die "import_library --all 失败（日志: /tmp/k12-import-library.log）"
fi
log "    import_library --all 完成（幂等，日志: /tmp/k12-import-library.log）"

log "7/7 检查演示数据（seed 只负责演示账号与演示记忆）..."
if ! curl -sf "http://localhost:${BACKEND_PORT}/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"xiaoming","password":"demo123"}' >/dev/null 2>&1; then
  uv run python -m app.scripts.seed
  log "    演示数据已 seed（xiaoming/demo123, admin/admin123）"
else
  log "    演示账号已存在，跳过 seed"
fi

echo ""
echo "============================================================================"
log "✅ 启动完成！"
echo "    前端:     http://localhost:${FRONTEND_PORT}"
echo "    后端 API: http://localhost:${BACKEND_PORT}/docs"
echo "    Worker:   PostgreSQL 队列消费（日志 /tmp/k12-worker.log）"
echo "    学生账号: xiaoming / demo123"
echo "    管理账号: admin / admin123"
echo "    关闭:     bash scripts/stop.sh"
echo "============================================================================"

if [ -z "$BACKEND_ONLY" ]; then
  open_browser "http://localhost:${FRONTEND_PORT}"
fi
