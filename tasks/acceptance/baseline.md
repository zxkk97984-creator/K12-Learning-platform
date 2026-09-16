# T01 · 可重现基线与隔离验收环境

> 日期：2026-09-06。任务 T01（M，依赖：无）。本文件记录本轮可重复基线、隔离测试环境、本轮通过/失败/未执行项。

## 起始 HEAD / 环境类型

- 起始 HEAD：`970ffda7c2fb8d6f74975a4b56794b6f969ee62b`（与 2026-09-06 审计基线一致；未改动历史计划，未删除用户已有文件 `.playwright-mcp/`、`backend/空`）。
- 分支：`master`。
- OS：Linux 7.0.0-31-generic x86_64。
- 已有运行服务：`shuangling-postgres`（pgvector/pg18，5432）、`shuangling-redis`（6379）、`shuangling-minio`（9000/9001）；本机已有一个 `uvicorn app.main:app --port 8002` 在运行（`/health` 返回 `{"status":"ok"}`）。**未杀掉**（属用户开发服务）。

## 依赖版本（脱敏，来自 audit-check）

`uv 0.12.3`；`pnpm 11.7.0`；`docker 29.1.3`；`curl 8.18.0`。

## 数据库测试隔离

用户开发库名：`shuangling`（真实数据：721 books / 369 chapters）。**未重置、未清空。**

为验收新建了专用可丢弃测试库：**`shuangling_audit`**（由本会话创建，仅用于 T01–T26 后端验证）。

可重复执行性已验证（DROP → CREATE → `alembic upgrade head` 始终落在 head `b2c3d4e6f789`）：

```bash
DATABASE_URL=postgresql+asyncpg://shuangling:shuangling@localhost:5432/shuangling_audit \
  uv run alembic upgrade head
```

内容导入与 seed 在隔离库上成功（幂等）：`validate_library --all`（books=25, violations=0）→ `import_library --all` → `seed`（建 admin / xiaoming）。

隔离库终态（只读校验）：25 本全部 `PUBLISHED`、125 chapters、2 用户（admin + xiaoming）。

新增守卫脚本：`scripts/audit-check.sh`（可执行）。它在：
- 未设 `DATABASE_URL` → 拒绝并退出 1（已验证）；
- 指向用户开发库 `shuangling` → 拒绝并退出 1；
- 指向隔离库 → 通过并打印脱敏环境/HEAD/端口/provider 模式（已验证）。

## 本轮通过 / 失败 / 未执行

| 项 | 结果 | 命令 / 说明 |
|---|---|---|
| 隔离测试库初始化可重复 | ✅ 通过 | DROP→CREATE→upgrade head 落 head；反复执行幂等 |
| 内容导入进隔离库 | ✅ 通过（幂等） | `validate_library --all` → `import_library --all` 于 `shuangling_audit` |
| 后端全量 pytest（隔离库） | ✅ 通过 | `DATABASE_URL=...shuangling_audit uv run pytest -q` ≈ **313 passed**, 3 warnings（约 52s） |
| audit-check 无 DSN 拒绝 | ✅ 通过 | 未设 DATABASE_URL → 退出 1 |
| audit-check 指向隔离库通过 | ✅ 通过 | 提供 `shuangling_audit` DSN → 退出 0 |
| 前端 Vitest / build | ⚠️ 未随本轮执行 | T05/T07 及各前端任务时逐项跑；T01 以隔离环境确认后端为主 |
| 完整 `scripts/ci.sh`（含 E2E） | ⏸ 仍未在隔离库跑 | ci.sh 的 e2e 会在 8002 起 mock 后端；现有 8002 被占，需 `BACKEND_PORT` 换端口；T25 回归矩阵时执行 |
| 登录后内部页面真实截图 | ⏸ 待授权 | 演示账号 `xiaoming/demo123`、`admin/admin123` 已在 seed；需确认是否允许本机登录并截图。登录页已有 `tasks/audit-2026-09-06/01-login.png`（历史审计） |
| 真实外部 LLM / 语音 / S3 | ⏸ 未授权未执行 | `backend/.env` 的 `AI_PROVIDER=openai_compatible`（开发服务用之）；验收环境固定 `AI_PROVIDER=mock` |

## 演示账号授权状态

本地演示账号为 README 提供的 `xiaoming/demo123`、`admin/admin123`。`frontend/.env.example` 有 `VITE_SHOW_DEMO_CREDENTIALS`；开发构建默认显示。**是否允许本会话登录这些账号并在真实浏览器截图，未获明确授权；本文件先记录为"待授权/阻塞"。** 不伪造截图，不用生成图顶替。若后续授权，将以真实运行页面补图。

## 尚未验证 / 遗留

- 真实外部 provider（LLM/语音/S3）未验证，属上线前验收。
- 登录后完整学生/管理员内部页面视觉验收，需授权后于真实浏览器补。
- `shuangling_audit` 为本会话专用可丢弃库；交付前不删除以保留验收证据，最终可丢弃。
