# 验收（acceptance）

本目录用于存放各任务的验收标准与验收记录。以下为**当前实现的整体质量门禁基线**（核对日期 2026-08-27）。

## 一、质量门禁（当前基线）

| 门禁 | 基线 | 说明 |
| --- | --- | --- |
| 后端迁移 | `alembic upgrade head` 通过；`alembic check` 无新增 upgrade 操作 | 仅有 `knowledge_chunks.embedding` / `student_episodes.embedding` 的 pgvector 类型识别 INFO，属 autogenerate 已知限制 |
| 后端测试 | **311 passed / 0 failed** | `cd backend && uv run pytest -q` |
| 前端测试 | **191 passed / 38 files** | `cd frontend && pnpm test` |
| 前端类型 | `pnpm exec tsc --noEmit` 通过 | — |
| 前端构建 | `pnpm build` 通过 | — |
| E2E | **9 passed / 0 failed**（串行） | `scripts/ci-e2e.sh` 起 mock 后端 + 真实 Postgres/Redis |
| 内容初始化 | `validate_library --all` PASS；`import_library --all` 幂等 | 正式语料 25 本书 / 56 篇知识文档 |

> 注：以上测试基线为全量绿。**已知非本次改动导致的 2 例偶发/数据态敏感**：`test_content_api::test_list_books_only_published`（当线上 PUBLISHED 书 > 100 时，`limit=100` 会把测试 DRAFT 书挤出）与 `test_admin_api::test_knowledge_upload_reprocess_and_metadata_patch`（Worker/队列时序偶发，单测隔离通过）。已通过数据治理将 PUBLISHED 书收敛到 25，前者的触发条件已消除。

## 二、一键验证入口

```bash
bash scripts/ci.sh
```

该脚本依次执行：依赖检查 → 后端环境准备（mock provider）→ Postgres/Redis 起服 → `alembic upgrade head` → 内容初始化（validate/import library）→ 启动 Worker 冒烟 → `pytest -q` → `pnpm install/test/build` → `scripts/ci-e2e.sh`（起 mock 后端 + seed + Playwright E2E）。任一步失败即以非 0 退出。

GitHub Actions：`.github/workflows/ci.yml` 分 `backend` / `frontend` / `e2e` 三个 job，含 Postgres + Redis service。**远端流水线尚未实测**（本地 `ci.sh` 已验证同一逻辑）。

## 三、当前阶段与相关记录

- 当前阶段：见 `docs/plans/current-phase.md`（Phase 5-B-II 实测收口）。
- 实施后整改：`docs/plans/post-audit-plan.md`（P0-1~P2-2 全部 PASS）。
- 测试数据工厂：`docs/plans/data-factory-report.md`（25 书 / 56 文档生产与验收）。

## 四、数据治理口径（2026-08-27）

线上库曾累积大量 AI 生成的测试/演示数据（692 书 / 602 资源）。已按 manifest 收敛：**保留 25 本正式书（PUBLISHED）+ 56 篇语料文档（READY）**；其余 675 书软归档（status=ARCHIVED）、546 资源标记 FAILED（`error='archived: test data'`），保留 FK/历史。归档后知识资源已用真实 embedding（阿里云百炼 `qwen3.7-text-embedding`，1024 维）重索引（`app/scripts/reindex_embeddings.py`）。

> 维护提醒：全量测试前若本地 DB 的 PUBLISHED 书 > 100，`test_content_api` 可能因 `limit=100` 变化而偶发失败；如遇此类数据态问题，先跑 `app/scripts/preview_data_governance.py` 核对。
