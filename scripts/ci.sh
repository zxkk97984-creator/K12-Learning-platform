#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
START_TS="$(date +%s)"
TOTAL_STEPS=9
CURRENT_STEP=0

banner() {
  CURRENT_STEP=$((CURRENT_STEP + 1))
  printf '\n==> [%s/%s] %s\n' "$CURRENT_STEP" "$TOTAL_STEPS" "$1"
}

ok() {
  printf '    ✓ %s\n' "$1"
}

die() {
  printf '    ✗ %s\n' "$1" >&2
  exit 1
}

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

ensure_postgres() {
  if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    # 无 Docker 守护进程时沿用本机已运行 Postgres；后续 migration/pytest 会真实暴露连接问题。
    return
  fi
  (cd "$ROOT_DIR" && docker compose up -d postgres >/dev/null)
  local ready=0
  for _ in $(seq 1 30); do
    if (cd "$ROOT_DIR" && docker compose exec -T postgres pg_isready >/dev/null 2>&1); then
      ready=1
      break
    fi
    sleep 2
  done
  [[ "$ready" == "1" ]] || die "Postgres 未在 60s 内就绪"
}

banner "检查依赖"
for tool in uv pnpm docker curl; do
  command -v "$tool" >/dev/null 2>&1 || die "缺少依赖：$tool"
done
ok "依赖齐全（uv / pnpm / docker / curl）"

banner "后端环境准备（AI_PROVIDER=mock）"
prepare_backend_env
ok "后端环境就绪"

banner "数据库服务准备（Postgres）"
ensure_postgres
ok "Postgres 可用"

banner "后端 migration（alembic upgrade head）"
if ! (cd "$BACKEND_DIR" && uv run alembic upgrade head); then
  die "alembic upgrade head 失败"
fi
ok "migration 通过"

banner "后端 pytest"
if ! (cd "$BACKEND_DIR" && uv run pytest -q); then
  die "pytest 失败"
fi
ok "pytest 通过"

banner "前端依赖安装（frozen-lockfile）"
if [[ -f "$FRONTEND_DIR/pnpm-lock.yaml" ]]; then
  if ! (cd "$FRONTEND_DIR" && pnpm install --frozen-lockfile); then
    die "pnpm install 失败"
  fi
else
  if ! (cd "$FRONTEND_DIR" && pnpm install); then
    die "pnpm install 失败"
  fi
fi
ok "前端依赖就绪"

banner "前端 Vitest"
if ! (cd "$FRONTEND_DIR" && pnpm test); then
  die "Vitest 失败"
fi
ok "Vitest 通过"

banner "前端 build"
if ! (cd "$FRONTEND_DIR" && pnpm build); then
  die "build 失败"
fi
ok "build 通过"

banner "E2E（自动起后端 :8002 + Playwright）"
if ! bash "$ROOT_DIR/scripts/ci-e2e.sh"; then
  die "E2E 失败"
fi
ok "E2E 通过"

END_TS="$(date +%s)"
ELAPSED=$((END_TS - START_TS))
printf '\n==> CI 全部通过，总耗时 %s 秒\n' "$ELAPSED"
