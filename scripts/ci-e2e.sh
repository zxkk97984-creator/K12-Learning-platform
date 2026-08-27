#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_PORT="${BACKEND_PORT:-8002}"
API_TARGET="${VITE_API_PROXY_TARGET:-http://127.0.0.1:${BACKEND_PORT}}"
BACKEND_LOG="$(mktemp "${TMPDIR:-/tmp}/shuangling-backend.XXXXXX.log")"
WORKER_LOG="$(mktemp "${TMPDIR:-/tmp}/shuangling-worker.XXXXXX.log")"
BACKEND_PID=""
WORKER_PID=""

cleanup() {
  local code=$?
  if [[ -n "$WORKER_PID" ]] && kill -0 "$WORKER_PID" 2>/dev/null; then
    kill "$WORKER_PID" 2>/dev/null || true
    wait "$WORKER_PID" 2>/dev/null || true
  fi
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
  rm -f "$BACKEND_LOG" "$WORKER_LOG"
  exit "$code"
}
trap cleanup EXIT

# Phase 5-B-I：E2E 前确保 postgres + redis 可用（不启动 minio/worker 镜像）
ensure_deps() {
  # 云端 CI：DATABASE_URL 由 workflow env 指向 GitHub service container 提供的
  # localhost:5432/6379。此时不应再 docker compose up（会和 service container
  # 抢 5432 导致 "port is already allocated"），只做连通探测即可。
  if [[ -n "${DATABASE_URL:-}" ]]; then
    for _ in $(seq 1 30); do
      if (exec 3<>/dev/tcp/127.0.0.1/5432) 2>/dev/null && \
         (exec 3<>/dev/tcp/127.0.0.1/6379) 2>/dev/null; then
        return 0
      fi
      sleep 1
    done
    echo "[ci-e2e] WARN: 云端 service container (5432/6379) 未被探测到，继续"
    return 0
  fi
  if command -v docker >/dev/null 2>&1; then
    if ! docker compose ps postgres 2>/dev/null | grep -q "running"; then
      (cd "$ROOT_DIR" && docker compose up -d postgres >/dev/null)
    fi
    if ! docker compose ps redis 2>/dev/null | grep -q "running"; then
      (cd "$ROOT_DIR" && docker compose up -d redis >/dev/null)
    fi
    for _ in $(seq 1 30); do
      if docker compose exec -T postgres pg_isready -U shuangling >/dev/null 2>&1 \
        && docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
        return 0
      fi
      sleep 1
    done
    echo "[ci-e2e] WARN: postgres/redis 未就绪，继续（可能使用本机已有服务）"
  fi
}

ensure_deps

prepare_backend_env() {
  if [[ ! -f "$BACKEND_DIR/.env" ]]; then
    sed 's|^DATABASE_URL=postgresql://|DATABASE_URL=postgresql+asyncpg://|' \
      "$BACKEND_DIR/.env.example" > "$BACKEND_DIR/.env"
    printf 'AI_PROVIDER=mock\nAI_MODEL=mock-model\nEMBEDDING_PROVIDER=mock\nVOICE_PROVIDER=mock\n' \
      >> "$BACKEND_DIR/.env"
  fi
  export AI_PROVIDER=mock
  export AI_MODEL=mock-model
  export EMBEDDING_PROVIDER=mock
  export VOICE_PROVIDER=mock

  if [[ -n "${DATABASE_URL:-}" ]]; then
    return
  fi

  local db_url="postgresql+asyncpg://shuangling:shuangling@localhost:5432/shuangling"
  local db_line=""
  db_line="$(grep -E '^DATABASE_URL=' "$BACKEND_DIR/.env" | tail -1 || true)"
  if [[ -n "$db_line" ]]; then
    local db_val="${db_line#DATABASE_URL=}"
    case "$db_val" in
      postgresql+asyncpg://*)
        db_url="$db_val"
        ;;
      postgresql://*)
        db_url="postgresql+asyncpg://${db_val#postgresql://}"
        ;;
    esac
  fi
  export DATABASE_URL="$db_url"
}

prepare_backend_env

if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1; then
  echo "✗ 端口 ${BACKEND_PORT} 已有后端在运行；请先停止它，或设置 BACKEND_PORT 换端口"
  exit 1
fi

echo "==> 启动后端 :${BACKEND_PORT}（AI_PROVIDER=mock）"
(
  cd "$BACKEND_DIR"
  exec env AI_PROVIDER=mock AI_MODEL=mock-model EMBEDDING_PROVIDER=mock VOICE_PROVIDER=mock \
    uv run uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT"
) >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

ready=0
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1; then
    ready=1
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    break
  fi
  sleep 1
done
if [[ "$ready" != "1" ]]; then
  echo "✗ 后端未在 60s 内就绪；日志尾部："
  tail -80 "$BACKEND_LOG" || true
  exit 1
fi
echo "    ✓ 后端就绪"

echo "==> 启动后台 Worker（消费 knowledge_ingest / conversation_summary / memory_consolidation）"
(
  cd "$BACKEND_DIR"
  exec env AI_PROVIDER=mock AI_MODEL=mock-model EMBEDDING_PROVIDER=mock VOICE_PROVIDER=mock \
    uv run python -m app.jobs.worker
) >"$WORKER_LOG" 2>&1 &
WORKER_PID=$!

worker_ready=1
for _ in $(seq 1 10); do
  if ! kill -0 "$WORKER_PID" 2>/dev/null; then
    worker_ready=0
    break
  fi
  sleep 0.5
done
if [[ "$worker_ready" != "1" ]]; then
  echo "✗ Worker 进程启动即退出；日志尾部："
  tail -40 "$WORKER_LOG" || true
  exit 1
fi
echo "    ✓ Worker 运行中（pid $WORKER_PID）"

echo "==> 内容初始化（validate_library --all → import_library --all，幂等）"
if ! (cd "$BACKEND_DIR" && uv run python -m app.scripts.validate_library --all >/dev/null); then
  echo "✗ validate_library --all 未通过，禁止导入内容"
  exit 1
fi
echo "    ✓ validate_library --all 通过"
if ! (cd "$BACKEND_DIR" && uv run python -m app.scripts.import_library --all >/dev/null); then
  echo "✗ import_library --all 失败"
  exit 1
fi
echo "    ✓ import_library --all 完成"

echo "==> 执行 seed（恢复 E2E 账号 / 记忆）"
if ! (cd "$BACKEND_DIR" && uv run python -m app.scripts.seed); then
  echo "✗ seed 失败"
  exit 1
fi
echo "    ✓ seed 完成"

echo "==> 运行 Playwright E2E（workers=1，代理目标 ${API_TARGET}）"
if ! (
  cd "$FRONTEND_DIR"
  CI=1 VITE_API_PROXY_TARGET="$API_TARGET" pnpm run test:e2e
); then
  echo "✗ Playwright E2E 失败"
  exit 1
fi
echo "    ✓ E2E 通过"
