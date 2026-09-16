# 14 · 开发指南

> 面向新加入的开发者与 AI Agent。**先读 `docs/AGENT_CONTEXT.md`**，再读本文件。

---

## 1. 环境准备

```bash
# 必需
docker    >= 29        # postgres(pgvector:pg18) / redis / minio
uv        >= 0.12      # 后端包管理
node      >= 22        # CI 用 22；本机 24 也能跑（未声明支持范围）
pnpm      == 11.7.0    # CI 已 pin；start.sh 会尝试 corepack 兜底
```

**可选**：`wmctrl` + `notify-send`（`start.sh` 用它把浏览器窗口带到前台）。

---

## 2. 首次启动

```bash
docker compose up -d postgres redis
cd backend
cp .env.example .env
#   最小可用配置：
#     JWT_SECRET=<任意 32 字节字符串>      ← 无默认值，必填
#     AI_PROVIDER=mock                      ← 不消耗真实额度
#     EMBEDDING_PROVIDER=mock
#     VOICE_PROVIDER=mock
#     TTS_PROVIDER=none
uv run alembic upgrade head      # ★ 必须早于 seed
uv run python -m app.scripts.seed
uv run python -m app.scripts.validate_library --all   # 前置门禁
uv run python -m app.scripts.import_library --all     # 幂等
uv run uvicorn app.main:app --port 8002
uv run python -m app.jobs.worker                       # 另开终端，★ 必须
cd ../frontend && pnpm install
VITE_API_PROXY_TARGET=http://127.0.0.1:8002 pnpm dev --port 5174
```

或用一键脚本：`bash scripts/start.sh`（默认只起 postgres；`--with-minio` 加 redis+minio）。

**端口约定**（不要改，8000/5173 被另一个项目占用）：

| 用途 | 端口 |
| --- | --- |
| 后端 API | **8002** |
| 前端 dev | **5174** |
| E2E 自起的 vite | **5175** |
| Postgres / Redis / MinIO | 5432 / 6379 / 9000-9001 |

---

## 3. ⚠️ 跑测试前必读

### 3.1 测试默认直连你的开发数据库

`backend/tests/conftest.py` 只有 11 行，**不设置 `DATABASE_URL`** →
pydantic-settings 读 `backend/.env` → **开发者真实数据库**。

```bash
# 正确做法：显式指定隔离库
createdb -h localhost -U shuangling shuangling_test   # 或用 docker exec
export DATABASE_URL="postgresql+asyncpg://shuangling:shuangling@localhost:5432/shuangling_test"
cd backend
uv run alembic upgrade head
uv run pytest -q
```

`scripts/audit-check.sh` 已经实现了正确的守卫（拒绝未设置 DSN、拒绝与开发库同名），
但**它没有被任何脚本调用**。你可以手动跑它：

```bash
DATABASE_URL=postgresql+asyncpg://.../shuangling_test bash scripts/audit-check.sh
```

> ⚠️ `scripts/ci.sh` **也会污染开发库** —— 它在 `DATABASE_URL` 未设置时
> 从 `backend/.env` 导出后跑 pytest。
>
> ⚠️ `scripts/test-db.sh` **不是**测试库搭建脚本，只是一个手动 `shuangling_audit` 库的
> backup/restore 工具，**没有任何调用方**。

### 3.2 当前基线（2026-09-16 实测，**不要相信文档里的旧数字**）

| 套件 | 结果 |
| --- | --- |
| 后端（干净库，复刻 CI 顺序） | **1 failed / 383 passed** ← CI 恒红，见下 |
| 后端（污染库，第二次跑） | 384 passed |
| 前端 Vitest | **258 passed / 49 files** |
| 前端 `tsc --noEmit` | 0 错误 |
| E2E | **未验证**（会写开发库） |

**已知必失败用例**：`tests/test_content_ai_visibility.py::TestChapterSourceVisibility::test_published_chapter_loads_source`
—— 顺序 bug：该类不依赖 `client` fixture，造数发生在断言之后。
**这是 Phase A 要修的第一件事。**

---

## 4. 代码约定

### 4.1 后端

| 约定 | 说明 |
| --- | --- |
| **Router 不写 SQL** | 编排 → Service → 显式 SQL |
| **绝不使用 `relationship()`** | 全仓 0 处。跨表用显式 `select().join()`。原因见 `worker.py:45-52` 记录的 `MissingGreenlet` 事故 |
| **错误用 `HTTPException(detail={"code","message"})`** | 由 `main.py` 的 handler 转统一信封 |
| **Service 返回 DTO，不返回 ORM 对象** | |
| **幂等靠 DB 唯一约束** | 不要在应用层做「先查再插」 |
| **AI 调用失败不得中断主流程** | 包 `try/except` + 日志 |
| **不要在 Router/Service 里 `get_ai_provider()` 直接建实例** | 走 `factory` |
| **Worker handler 必须幂等** | 会被重放（退避重试 + 孤儿回收） |
| **新增表必须同时改 `models.py` + 写迁移** | 并跑 `alembic check` 确认无漂移 |

### 4.2 前端

| 约定 | 说明 |
| --- | --- |
| **页面不直接 fetch** | 一律经 `shared/services.ts` 单例 |
| **新增服务走 interface + Api 实现** | 在 `shared/services.ts` 注册 |
| **所有错误经 `ApiError`** | 已在 `http.ts` 统一解析 |
| **401 统一派发 `shuangling:unauthorized`** | ⚠️ 若你用原生 `fetch`，必须手动 `emitUnauthorized()`（当前有 2 处遗漏） |
| **加载/空/错误三态齐全** | 用 `shared/ui/ResourceState.tsx`（**目前它是死代码，请开始用它**） |
| **不要新增 mock 服务** | `src/mocks/` 是待删除的死代码 |
| **评论要写清「为什么」** | 本项目注释质量高，请保持 |

### 4.3 数据库

| 约定 | 说明 |
| --- | --- |
| 迁移**一旦合并即不可变** | 数据修正走新迁移（`b1c2d3e4f5a6` 被回溯修改是一个反面教材） |
| 破坏性迁移要写清 downgrade 后果 | `c7d8e9f0a1b2` 的 downgrade 会清空全部真实向量 |
| 新 FK **必须考虑索引** | 当前 58 个 FK 列有 25 个无索引 |
| `idempotency_keys` 需要清理策略 | 实测已 8442 行 |

---

## 5. 常见任务

### 新增一个 API 端点

1. `modules/<domain>/schemas.py` 加 DTO
2. `modules/<domain>/service.py` 写业务 + SQL
3. `modules/<domain>/router.py` 加路由 + `Depends(require_student/require_admin)`
4. 补测试（含 401/403/404/422 路径）
5. 更新 `docs/contracts/api-contract.md` **和 `docs/07-api.md`**
6. 前端：`shared/api/<x>-service.ts` 加接口 → `api-<x>.ts` 实现 → 页面使用

### 新增一张表

1. `infrastructure/database/models.py`（**不要用 `relationship()`**）
2. `uv run alembic revision --autogenerate -m "..."` → **人工审阅**生成的迁移
3. `uv run alembic upgrade head`
4. `uv run alembic check` 确认无残留漂移
5. 更新 `docs/06-database.md` 与 `docs/contracts/api-contract.md`

### 新增一个后台任务类型

1. `jobs/handlers/<name>.py` 实现 `async def handle_x(session, payload) -> None`
2. `jobs/worker.py:29-42` 的 `resolve_handler` 注册
3. **保证 handler 幂等**（会被重放）
4. 在业务侧 `queue.enqueue(session, "<type>", {...})`
5. 补测试（参考 `tests/test_worker_queue.py`、`test_async_memory_consolidation.py`）

### 新增一门课程内容

1. 在 `backend/data/library/books/<slug>/` 放 `chNN.md`
2. 图片放 `books/<slug>/assets/`，审校题放 `data/library/assessments/<slug>/chNN.json`
3. `uv run python -m app.scripts.validate_library --slug <slug>`（必须先过）
4. `uv run python -m app.scripts.import_library --slug <slug>`
5. 若要审校题生效：**先修 `import_assessments` 的 bug**（见 `docs/12` P1-3）

---

## 6. 排障

| 症状 | 原因 / 处理 |
| --- | --- |
| Alembic 报 "unknown revision" | **4 个迁移未提交**（`docs/12` P1-0）。确认工作区存在 `a4b5…`–`a7b8…` 四个文件 |
| 后端起来但知识资源一直 `UPLOADED` | Worker 没启动。`docker compose up` **不会**启动它。手动 `python -m app.jobs.worker` |
| 限流没走 Redis | `start.sh` 默认不起 redis；且 Redis 不可用时会静默降级为进程内（两种模式都强制） |
| 书库首页全是「分页测试书NN」 | 开发库被测试污染（`docs/12` P0-2）。跑测试前先设隔离 DSN |
| 学生说「AI 忘了我之前说的」 | 已知缺陷：会话摘要会删历史（`docs/12` P0-3） |
| RAG 检索不到某些文档 | 可能是 64 维遗留 chunk（`docs/12` P1-5），检查 `vector_dims(embedding)` |
| 语音没有声音回复 | 设计如此：未配置 `TTS_PROVIDER` 时返回 `TTS_UNAVAILABLE`（不返回假音频） |
| 前端看起来在用 mock | **不是**。`shared/services.ts` 全绑 `Api*Service`；`src/mocks/` 是死代码 |
| CI 红了但本地绿 | 本地跑在开发库上（脏），CI 跑在全新库上。见 `docs/10` §1 |

---

## 7. 提交前检查清单

- [ ] `bash scripts/audit-check.sh`（需先设隔离 `DATABASE_URL`）
- [ ] 后端：`uv run pytest -q`（**隔离库上**）
- [ ] 前端：`npx tsc --noEmit && npx vitest run && pnpm build`
- [ ] 涉及 UI 改动：`bash scripts/ci-e2e.sh`
- [ ] 涉及 schema：`uv run alembic check` 无输出
- [ ] 更新受影响的 `docs/`（尤其 `docs/07-api.md`、`docs/11-feature-status.md`）
- [ ] 若修复了 `docs/12-known-issues.md` 中的条目，同步更新它
- [ ] `git status` 检查是否有未跟踪的新文件被遗漏

---

## 8. 给 AI Agent 的额外提醒

1. **代码优先于文档。** 本仓库文档有 20+ 处已知漂移，已登记在 `docs/15` §3。
2. **改动前先读 `.audit/` 对应报告**（A=AI 738 行 / B=前端 606 行 / C=数据库 1353 行 / D=测试 870 行）。
3. **不要在脏数据库上验证 bug** —— 先确认它在干净环境可复现。
4. **不要为了让测试通过而修改测试的断言语义**（项目 `plan.md` 明确禁止）。
5. **不要引入新的重型依赖**（Celery / LangChain / pydantic-ai / Redis 队列）——
   架构已裁定用自研 PG 队列与自研 Provider 适配器。
6. **保留解释性注释。** 这个项目的注释记录了真实的踩坑经验，是全仓最有价值的资产之一。
7. **当前第一优先级不是写新功能**，而是按 `docs/16` Phase A 把项目恢复到「可提交、可复现」状态。
