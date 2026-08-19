# 霜铃 · K12 AI 数字教师 V3

面向 K12 场景的 AI 数字教师平台（V3 版本），当前处于 **Phase 0：项目初始化与基线固化**。本阶段只建立仓库骨架与文档基线，不包含任何业务实现。

## 如何阅读基线文档

所有开发任务请先阅读执行总控文件（保留在仓库根目录）：

- **[霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md](./霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md)** — 执行总控文件，定义多 Agent 协同开发的组织方式与任务推进流程

其余基线资料已归入对应目录：

- 产品需求基线：`docs/requirements/产品需求总纲.md`
- 架构设计基线：`docs/architecture/project-architecture.md`
- 开发实施路线：`docs/plans/development-roadmap.md`
- UI/交互原型：`prototypes/shuangling-v3-prototype.html`

## 目录结构

```text
.
├── docs/                 文档基线（需求 / 架构 / 契约 / 计划 / 验收）
├── prototypes/           UI / 交互原型
├── frontend/             前端应用（Phase 0 仅占位）
├── backend/              后端服务（Phase 0 仅占位）
├── scripts/              开发 / 运维脚本（Phase 0 仅占位）
├── infra/                基础设施编排（Phase 0 仅占位）
├── docker-compose.yml    本地依赖服务（postgres/pgvector、redis、minio）
├── .env.example          环境变量占位示例（不含任何真实密钥）
└── .gitignore / .editorconfig
```

## 开发约定

- 默认分支：`master`；本地开发仓库，不设置 remote、不 push。
- 真实密钥只写入 `.env`（已被 `.gitignore` 排除）；`docker-compose.yml` 仅使用占位/默认值。
- Phase 0 结束前禁止实现业务代码（Domain Model / API Contract / Database Schema 等均属后续任务）。

## 一键验证

本地质量门禁（后端 migration + pytest + 前端 Vitest/build + E2E）：

```bash
bash scripts/ci.sh
```

脚本会自动：

- 使用 `AI_PROVIDER=mock`（不接真实 LLM）；
- 在无 `backend/.env` 时从 `.env.example` 生成默认环境；
- 通过 Docker Compose 确保 Postgres 可用（已有本机 DB 则沿用）；
- 执行 `alembic upgrade head` 与 `uv run pytest -q`；
- 执行 `pnpm install --frozen-lockfile`、`pnpm test`、`pnpm build`；
- 由 `scripts/ci-e2e.sh` 自动在 `:8002` 起 mock 后端、执行 seed，再串行运行 Playwright E2E，结束后自动清理后端进程。

任一步失败会立即以非 0 退出码停止。
