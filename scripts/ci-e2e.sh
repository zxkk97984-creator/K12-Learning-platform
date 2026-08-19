#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_PORT="${BACKEND_PORT:-8002}"
API_TARGET="${VITE_API_PROXY_TARGET:-http://127.0.0.1:${BACKEND_PORT}}"
BACKEND_LOG="$(mktemp "${TMPDIR:-/tmp}/shuangling-backend.XXXXXX.log")"
BACKEND_PID=""

cleanup() {
  local code=$?
  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
    wait "$BACKEND_PID" 2>/dev/null || true
  fi
  rm -f "$BACKEND_LOG"
  exit "$code"
}
trap cleanup EXIT

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
