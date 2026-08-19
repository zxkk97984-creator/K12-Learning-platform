# 霜铃 · K12 AI 数字教师 V3

面向 K12 场景的 AI 数字教师平台（V3），当前处于 **Phase 12：生产化收尾与比赛交付**。功能主线包括：学生认证与画像、课程内容、对话 + RAG、随堂测验、学习记忆、多 AI 教师角色、Admin 内容管理、语音交互（Mock）等。

## 架构简述

- 前端：React 19 SPA（Vite + Tailwind + Zustand + TanStack Query），见 `frontend/`
- 后端：FastAPI Modular Monolith（Python 3.12 + SQLAlchemy async + Alembic），见 `backend/`
- 数据：PostgreSQL + pgvector（向量检索）、Redis、MinIO
- 完整架构图：[docs/architecture/diagrams.md](./docs/architecture/diagrams.md)
- 架构与数据设计：[docs/architecture/project-architecture.md](./docs/architecture/project-architecture.md)、[docs/architecture/database-design.md](./docs/architecture/database-design.md)

## 如何阅读基线文档

所有开发任务请先阅读执行总控文件（保留在仓库根目录）：**[霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md](./霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md)**。

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
├── frontend/             前端应用（React 19 SPA）
├── backend/              后端服务（FastAPI Modular Monolith）
├── scripts/              一键 CI / E2E 脚本
├── docker-compose.yml    本地依赖服务（postgres/pgvector、redis、minio）
├── .env.example          环境变量占位示例（不含任何真实密钥）
└── .gitignore / .editorconfig
```

## 本地启动

1. 启动依赖服务（至少 Postgres）：

   ```bash
   docker compose up -d postgres
   ```

2. 后端：

   ```bash
   cd backend
   cp .env.example .env   # 按需填写 JWT_SECRET / AI_*（密钥禁止提交）
   uv run alembic upgrade head
   uv run python -m app.scripts.seed
   uv run uvicorn app.main:app --port 8002
   ```

3. 前端（另一个终端）：

   ```bash
   cd frontend
   pnpm install
   VITE_API_PROXY_TARGET=http://127.0.0.1:8002 pnpm dev
   ```

## 演示账号

- 学生：`xiaoming` / `demo123`
- 管理员：`admin` / `admin123`

⚠️ 以上仅为本地演示凭据，生产环境必须修改默认密码并配置强 `JWT_SECRET`。

## AI Provider 开关

- `AI_PROVIDER=mock`：默认本地演示，不依赖外部 LLM。
- `AI_PROVIDER=openai_compatible`：接入 OpenAI 兼容真实 LLM，需配置 `AI_BASE_URL`、`AI_API_KEY`、`AI_MODEL`（例如 DeepSeek 官方 API）。
- 模板见 `backend/.env.example`；CI / E2E 强制使用 `mock`，不会消耗真实模型额度。

## 当前阶段

见 [docs/plans/current-phase.md](./docs/plans/current-phase.md)。

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
