#!/usr/bin/env bash
# 测试环境数据库备份/恢复（仅针对可丢弃的隔离验收库，默认 shuangling_audit）。
# 用于：把验收用的隔离库状态导出为 .dump，或从 .dump 恢复，便于复现与回退。
#
# 安全边界：
#  - 默认只操作 shuangling_audit（由执行 agent 创建的专用可丢弃测试环境）。
#  - 明确禁止对真实开发库 shuangling 执行破坏性恢复，除非以环境变量
#    TEST_DB_ALLOW_PROD_RESTORE=1 显式授权（默认拒绝）。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CTX="${CTX:-docker}"                 # docker | host
DB_NAME="${TEST_DB_NAME:-shuangling_audit}"
PGUSER="${PGUSER:-shuangling}"
BACKUP_DIR="${BACKUP_DIR:-/tmp/shuangling-db-backups}"
PROTECTED_DB="shuangling"            # 真实开发库，禁用恢复

usage() {
  echo "用法: $0 <backup|restore> [备份文件.dump]"
  echo "  默认数据库: ${DB_NAME}（隔离验收库）"
  echo "  CTX=${CTX}  docker(默认) | host  —— 走 docker compose exec 还是本机 psql"
}

backup() {
  local out="${1:-${BACKUP_DIR}/${DB_NAME}-$(date +%Y%m%d-%H%M%S).dump}"
  mkdir -p "$(dirname "$out")"
  echo "==> 备份 ${DB_NAME} → ${out}"
  if [[ "$CTX" == "docker" ]]; then
    docker compose -f "$ROOT_DIR/docker-compose.yml" exec -T postgres \
      pg_dump -U "$PGUSER" -Fc "$DB_NAME" > "$out"
  else
    pg_dump -U "$PGUSER" -Fc "$DB_NAME" > "$out"
  fi
  echo "    ✓ 备份完成：$(du -h "$out" | cut -f1)"
}

restore() {
  local in="${1:?需要指定 .dump 文件}"
  [[ "$DB_NAME" == "$PROTECTED_DB" && "${TEST_DB_ALLOW_PROD_RESTORE:-0}" != "1" ]] && {
    echo "✗ 拒绝：恢复目标是真实开发库 ${PROTECTED_DB}。如确属测试场景，用 TEST_DB_ALLOW_PROD_RESTORE=1 显式授权。" >&2
    exit 1
  }
  [[ -f "$in" ]] || { echo "✗ 备份文件不存在：$in" >&2; exit 1; }
  echo "==> 从 ${in} 恢复到 ${DB_NAME}（先终止连接 + drop + create）"
  local terminate="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${DB_NAME}' AND pid<>pg_backend_pid();"
  if [[ "$CTX" == "docker" ]]; then
    docker compose -f "$ROOT_DIR/docker-compose.yml" exec -T postgres \
      psql -U "$PGUSER" -d postgres -c "$terminate" >/dev/null
    docker compose -f "$ROOT_DIR/docker-compose.yml" exec -T postgres \
      psql -U "$PGUSER" -d postgres -c "DROP DATABASE IF EXISTS ${DB_NAME};" >/dev/null
    docker compose -f "$ROOT_DIR/docker-compose.yml" exec -T postgres \
      psql -U "$PGUSER" -d postgres -c "CREATE DATABASE ${DB_NAME};" >/dev/null
    # docker compose exec 的 pg_restore 只见容器内文件系统，须先把宿主 .dump 拷入容器
    docker compose -f "$ROOT_DIR/docker-compose.yml" cp "$in" "postgres:/tmp/shuangling-restore.dump"
    docker compose -f "$ROOT_DIR/docker-compose.yml" exec -T postgres \
      pg_restore -U "$PGUSER" -d "$DB_NAME" --no-owner /tmp/shuangling-restore.dump
    docker compose -f "$ROOT_DIR/docker-compose.yml" exec -T postgres rm -f /tmp/shuangling-restore.dump
  else
    psql -U "$PGUSER" -d postgres -c "$terminate"
    psql -U "$PGUSER" -d postgres -c "DROP DATABASE IF EXISTS ${DB_NAME};"
    psql -U "$PGUSER" -d postgres -c "CREATE DATABASE ${DB_NAME};"
    pg_restore -U "$PGUSER" -d "$DB_NAME" --no-owner "$in"
  fi
  echo "    ✓ 恢复完成"
}

case "${1:-}" in
  backup)  shift; backup "${1:-}";;
  restore) shift; restore "${1:-}";;
  *) usage; exit 1;;
esac
