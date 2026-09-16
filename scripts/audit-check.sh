#!/usr/bin/env bash
# audit-check.sh — T01 可重现基线自检（2026-09-06）
# 只做只读/隔离自检，不自动 seed、不 reset 用户开发库、不打印令牌或口令。
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

DEV_DB_NAME="shuangling"   # 已知用户开发库名；audit 不得指向它
PORT_RE="${1:-8002}"

green() { printf '    \033[32m✓\033[0m %s\n' "$1"; }
red()   { printf '    \033[31m✗\033[0m %s\n' "$1"; }
warn()  { printf '    \033[33m!\033[0m %s\n' "$1"; }

echo "==> 环境类型 / HEAD / 端口"
echo "    HEAD: $(git -C "$ROOT_DIR" rev-parse HEAD)"
echo "    branch: $(git -C "$ROOT_DIR" branch --show-current)"
echo "    os: $(uname -srm)"
echo "    backend probe :${PORT_RE}: $(curl -fsS "http://127.0.0.1:${PORT_RE}/health" 2>/dev/null || echo '未响应')"

echo "==> 依赖版本（脱敏）"
for tool in uv pnpm docker curl; do
  printf '    %-7s %s\n' "$tool" "$(command -v "$tool" >/dev/null 2>&1 && "$tool" --version 2>/dev/null | head -1 || echo '缺失')"
done

echo "==> 数据库测试隔离校验"
if [[ -z "${DATABASE_URL:-}" ]]; then
  red "DATABASE_URL 未设置。审计/测试必须显式提供隔离测试库 DSN；拒绝默认指向用户开发库。"
  exit 1
fi

# 解析数据库名（不打印口令/完整 DSN）
db_name="$(printf '%s' "$DATABASE_URL" | sed -E 's#.*/([^/?]+).*#\1#')"
# 从开发 .env 读取开发库名（只取库名，不打印任何口令）
dev_db_name="$(grep -E '^DATABASE_URL=' "$BACKEND_DIR/.env" 2>/dev/null | tail -1 | sed -E 's#.*/([^/?]+).*#\1#' || true)"
if [[ -z "$dev_db_name" ]]; then
  warn "无法从 backend/.env 解析开发库名；跳过与开发库相等判断。"
else
  printf '    测试库名: %s ; 开发库名: %s\n' "$db_name" "$dev_db_name"
  if [[ "$db_name" == "$dev_db_name" ]]; then
    red "DATABASE_URL 指向用户开发库（$dev_db_name），已拒绝运行。必须使用隔离测试库。"
    exit 1
  fi
fi

if [[ "$db_name" == "$DEV_DB_NAME" ]]; then
  red "DATABASE_URL 指向默认开发库（$DEV_DB_NAME）。请提供隔离测试库。"
  exit 1
fi
if [[ -z "$db_name" || "$db_name" == "$DATABASE_URL" ]]; then
  red "无法解析数据库名，拒绝继续。"
  exit 1
fi

echo "==> Provider 模式"
if [[ "${AI_PROVIDER:-$(grep -E '^AI_PROVIDER=' "$BACKEND_DIR/.env" 2>/dev/null | tail -1 | cut -d= -f2 || echo unknown)}" == "mock" ]]; then
  green "AI_PROVIDER=mock（本地演示，不会消耗真实模型额度）"
else
  warn "AI_PROVIDER 并非 mock——若为真实 provider，本脚本不发起调用，只记录。"
fi

echo "==> 服务就绪检查"
for svc in "5432:postgres" "6379:redis"; do
  port="${svc%%:*}"
  name="${svc##*:}"
  if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
    green "$name 端口 $port 可达"
    exec 3>&- || true
  else
    warn "$name 端口 $port 不可达（若使用本机服务可忽略）"
  fi
done

echo "==> 结论"
echo "    审计基线可执行。以下为仍未运行的项（记录原因，不作伪通过）："
echo "    - 完整后端 pytest / E2E 需在隔离库上经 scripts/ci.sh 运行，日志留存于任务证据。"
echo "    - 登录后内部页面的真实浏览器截图需本地演示账号授权；无授权则记录阻塞。"
echo "    - 真实外部 LLM / 语音调用未授权，不发起。"
green "audit-check 通过（隔离 DSN 校验 + 环境信息采集）"
