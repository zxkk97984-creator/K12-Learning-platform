# 01 · 仓库地图

> 生成于 2026-09-16。目标不是罗列文件，而是说明**每个目录的职责、模块间关系、哪些是核心、哪些是辅助、哪些已废弃**。

---

## 1. 根目录

| 路径 | 类型 | 职责 | 状态 |
| --- | --- | --- | --- |
| `backend/` | 核心 | FastAPI 模块化单体（API + Worker + 脚本 + 语料） | 活跃 |
| `frontend/` | 核心 | React 19 SPA | 活跃 |
| `scripts/` | 核心 | 一键启动/停止/CI/E2E/测试库隔离脚本 | 活跃 |
| `docs/` | 核心 | 文档基线（需求/架构/契约/计划/验收） | 活跃（部分过时，见 `docs/12-known-issues.md`） |
| `tasks/` | **未跟踪** | 2026-09 T01–T26 优化轮的 plan / todo / acceptance 证据 | 活跃，但**未纳入 git** |
| `docker-compose.yml` | 核心 | 本地依赖服务（postgres/redis/minio）+ 可选 worker | 活跃 |
| `prototypes/shuangling-v3-prototype.html` | 参考 | 152 KB 纯 HTML UI 原型（Phase 0 产物） | 历史参考，非生产代码 |
| `plan.md` | **过期** | 「完成后台实施计划」——2026-08 的 Hermes 调度基线 | 历史，内容已被 `tasks/plan.md` 取代 |
| `霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md` | 主控 | 32 KB 开发总路线（Phase 0–12 定义） | 历史基线，Phase 定义仍有效 |
| `.hermes-tasks/` | 历史 | 88 个 task-XX.md（Hermes→Codex 派发单） | **被 gitignore**，历史归档 |
| `.github/workflows/ci.yml` | 核心 | CI：backend / frontend / e2e 三 job | 活跃 |
| `.agents/`、`.codex/` | 空 | 被 gitignore 的空目录 | 残留 |
| `.opencode/` | 工具 | OpenCode 工具自身依赖（含 `node_modules`） | 工具残留，**不应提交** |
| `.playwright-mcp/` | **未跟踪** | Playwright MCP 的 console/page 快照日志（36 个文件） | 调试残留，应清理 |
| `infra/` | 空 | 只有 `.gitkeep` | **占位，无任何内容** |
| `.env.example`（根） | **过期/误导** | 使用**旧变量名** `LLM_PROVIDER/LLM_API_KEY/LLM_BASE_URL/LLM_MODEL`，与 `backend/app/config.py` 的 `AI_*` **完全不一致**；无任何代码读取 | 建议删除 |
| `backend/空` | **垃圾** | 内容为 `117` 的 4 字节文件 | 误创建的残留 |

---

## 2. backend/ 结构

```
backend/
├── alembic/versions/     23 个迁移（当前 head = a7b8c9d0e1f2）
├── app/
│   ├── main.py           FastAPI 入口：中间件、路由注册、异常处理、/health /metrics
│   ├── config.py         pydantic-settings 全部配置项（单一配置源）
│   ├── worker.py         ⚠️ 兼容 shim → app.jobs.worker.main（无调用方）
│   ├── api/              deps.py（鉴权依赖）+ envelope.py（统一响应信封）
│   ├── ai/               AI Provider 抽象层（LLM / Embedding / Voice）
│   ├── infrastructure/   数据库 / 缓存 / 存储 / 指标 / 限流 / 日志
│   ├── jobs/             PG 表驱动任务队列 + Worker 循环 + 3 个 handler
│   ├── modules/          业务领域模块（modular monolith 的核心）
│   ├── scripts/          运维/数据脚本（seed / 导入 / 重索引 / 校验）
│   └── skills/           Skill 抽象与注册表
├── data/library/         课程语料（books / knowledge / assessments）+ 图片资源
├── evals/                教学评测（37 例 jsonl + runner）
├── tests/                36 个 pytest 文件
├── docs/requirements/    pilot-data-policy.md
├── storage/              ⚠️ 运行时上传产物（被 gitignore，但工作区有 800+ 目录）
├── Dockerfile            API/Worker 共用镜像（CMD 默认 worker）
└── pyproject.toml        uv 管理；pytest 配置在此
```

### 2.1 `app/modules/` —— 业务核心（11 个模块）

| 模块 | 文件 | 职责 | 核心度 |
| --- | --- | --- | --- |
| `identity` | router/service/schemas/security/storage | 登录、JWT、/me、偏好、头像、教师风格列表 | 核心 |
| `content` | router/service/schemas/**assets**(新) | 书库、书籍、章节、内容块、知识点、**库图片资源** | 核心 |
| `learning` | router/service/schemas | 学习会话、学习事件、进度、**章节完成** | 核心 |
| `conversation` | router/service/schemas/teacher_context/**context_window**(新) | 对话、SSE 流式、TeacherContext 构建、上下文窗口 | **最核心** |
| `quiz` | router/service/schemas/skill/chapter_source/quiz_bank | 测验会话、出题、判分、提示、错题讲解 | 核心 |
| `memory` | router/service/schemas/pipeline/agent_md | 记忆候选、记忆、证据、画像、情节、agent.md | 核心 |
| `knowledge` | router/service/schemas/ingestion/retrieval | 知识资源、分块、向量检索、RAG | 核心 |
| `recommendation` | router/service/schemas | 规则推荐 + 下一步学习行动 | 核心 |
| `admin` | router/service/schemas | 后台内容/风格/资源管理 + 统计 | 辅助（但量大） |
| `voice` | router/schemas/ws | 语音 WebSocket（ASR/TTS 双向流） | 边缘 |
| （`app/skills/`） | base/registry | Skill 抽象与注册表 | ⚠️ 见下 |

> ⚠️ **`app/skills/` 与 `app/modules/quiz/skill.py` 是两套并存的「Skill」概念。**
> `app/skills/registry.py` 是 Phase 0 的骨架；`app/modules/quiz/skill.py` 是真实使用的实现。
> 需确认 `app/skills/registry.py` 是否有真实调用方（见 `docs/08-ai-system.md`）。

### 2.2 `app/ai/` —— AI Provider 抽象

| 文件 | 内容 |
| --- | --- |
| `base.py` | `AIProvider` ABC：`stream_chat()`、`model_info`、`last_usage` |
| `factory.py` | `get_ai_provider()` 按 `settings.ai_provider` 选择 |
| `mock.py` | 确定性 mock（默认本地演示） |
| `openai_compatible.py` | 真实 LLM 适配器（httpx + SSE 解析，**无第三方 SDK**） |
| `embedding.py` | Embedding Provider（mock 64 维哈希 / openai_compatible 真实） |
| `voice.py` | ASR/TTS Provider（mock / none / aliyun DashScope） |

### 2.3 `app/infrastructure/`

| 路径 | 内容 |
| --- | --- |
| `database/models.py` | **1465 行，32 张表的全部 ORM 定义（单一文件，关键枢纽）** |
| `database/engine.py` / `session.py` / `base.py` | async engine、session factory、DeclarativeBase |
| `cache/redis.py` | 分布式锁 + 缓存（带本地降级） |
| `rate_limit.py` | Redis 固定窗口 / 进程内滑动窗口限流 |
| `metrics_registry.py` | 进程内 Prometheus 文本指标 |
| `observability.py` | 访问日志（结构化，**不记录正文/密码/Authorization**） |
| `storage/` | `base.py`（抽象）/ `local.py` / `s3.py`（手写 SigV4） |

### 2.4 `app/jobs/`

| 文件 | 内容 |
| --- | --- |
| `queue.py` | `enqueue` / `claim_next`（FOR UPDATE SKIP LOCKED）/ `mark_success` / `mark_failed`（指数退避）/ `recover_stale_running` |
| `worker.py` | Worker 主循环 + `resolve_handler` 分发（3 类任务） |
| `handlers/knowledge.py` | `knowledge_ingest` → 解析/分块/嵌入 |
| `handlers/conversation.py` | `conversation_summary` → 长对话摘要 |
| `handlers/memory.py` | `memory_consolidation` → 记忆/画像/情节生成 |

> Worker 入口有两个：`python -m app.jobs.worker`（**实际使用**）与 `python -m app.worker`（shim，无调用方）。

### 2.5 `app/scripts/`（11 个脚本 + 3 篇 knowledge_seed）

| 脚本 | 用途 | 被谁调用 |
| --- | --- | --- |
| `seed.py` | 演示账号 + 演示记忆 | `start.sh`、`ci.sh`、`ci-e2e.sh`、CI |
| `validate_library.py` | 语料结构校验（661 行，规则 R1–R?） | `start.sh`、`ci.sh`、`ci-e2e.sh`、CI |
| `import_library.py` | 幂等导入 25 书 + 知识文档 | 同上 |
| `import_assessments.py` | **审校题库导入** | ⚠️ **仅测试调用，未接入任何启动/CI 链路** |
| `ingest_knowledge.py` | 知识文档入库 | 手动 |
| `reindex_embeddings.py` | 向量重索引（`--dry-run`/`--limit`） | 手动 |
| `rebuild_memory.py` | 记忆重建 | 手动 |
| `archive_noncorpus.py` | 归档非语料数据 | 手动（一次性） |
| `preview_data_governance.py` | 数据治理预览 | 手动 |
| `verify_s3.py` | S3 联调验证 | 手动 |

### 2.6 `data/library/`

```
data/library/
├── books/<slug>/chNN.md         25 本书的章节 Markdown
├── books/<slug>/assets/         3 本书的教学图片（T10–T12 新增）
├── assessments/<slug>/chNN.json 3 本书的审校题（T22b 新增）
├── knowledge/*.md               56 篇知识文档
└── README.md                    语料编写规范
```

---

## 3. frontend/ 结构

```
frontend/
├── src/
│   ├── app/            router（唯一路由表）+ providers（QueryClient）
│   ├── pages/         10 个页面（9 学生 + 5 管理，AdminLayout 为壳）
│   ├── features/      auth / conversation / companion / quiz / memory / learning / screen-context / voice / feedback
│   ├── entities/      6 个纯类型定义（admin/book/conversation/memory/quiz/student）
│   ├── shared/        api（服务层）/ ui（AppLayout、BottomNav、ResourceState）/ hooks / lib / styles
│   └── mocks/         ⚠️ 见下：几乎全部为死代码
├── e2e/               12 个 Playwright spec + helpers.ts
├── public/pets/       5 套桌宠雪碧图资源
├── dist/              构建产物（被 gitignore）
└── playwright.config.ts  4 个 project（chromium / mobile-390 / tablet-820 / desktop-1280）
```

### 3.1 关键架构约定：接口 + 实现 + 注册表

前端服务层采用 **interface + Api 实现 + 单一注册表** 模式：

| 接口（类型契约） | 真实实现 | 死代码 mock 实现 |
| --- | --- | --- |
| `api/student-service.ts` | `api/api-student-service.ts` | `mocks/services/student-service.ts` |
| `api/content-service.ts` | `api/api-content-service.ts` | `mocks/services/content-service.ts` |
| `api/conversation-service.ts` | `api/api-conversation-service.ts` | `mocks/services/conversation-service.ts` |
| `api/quiz-service.ts` | `api/api-quiz-service.ts` | `mocks/services/quiz-service.ts` |
| `api/memory-service.ts` | `api/api-memory-service.ts` | `mocks/services/memory-service.ts` |
| `api/recommendation-service.ts` | `api/api-recommendation.ts` | `mocks/services/recommendation-service.ts` |

**唯一切换点：`src/shared/services.ts`** —— 当前 6 个服务**全部**绑定到 `ApiXxxService`（真实后端）。
注释明写「替换边界：Phase 2 起逐个把实例替换为 ApiXxxService」。

### 3.2 `src/mocks/` 的真实状态 —— 结论：**已废弃（死代码）**

精确检索 `['"]@/mocks` 在 `src/` 与 `e2e/` 中的全部引用（排除 `src/mocks/` 自身），**只有 2 处命中**：

| 命中 | 性质 |
| --- | --- |
| `src/features/conversation/components/QuickActions.tsx:3` → `QUICK_ACTIONS` | **生产代码引用 mock 目录中的静态配置表**（不是 mock 服务，只是放错位置） |
| `src/pages/library/LibraryPage.test.tsx:7` → `mockBooks` | 测试夹具 |

- 6 个 `mocks/services/*.ts`（MockContentService 等）**零外部引用** → 完全死代码。
- `mocks/data/{books,memory,quizzes,student}.ts` 除上述 1 处测试引用外**全部死代码**。
- 已验证生产构建产物 `dist/assets/*.js` 中**不含** `MockContentService` / `MockQuizService` / `MockConversationService` 字符串 → 已被 tree-shaking 剔除，**不存在运行时被 mock 数据顶替的风险**。

> ⚠️ 这是一条容易被误判的路径：新维护者看到 `src/mocks/` 目录很大（5 个 service + 5 个 data，约 1700 行）
> 会以为「前端还在用 mock」。实际不会。但保留它们会持续误导，应清理（见 `docs/13-technical-debt.md`）。

---

## 4. 模块依赖关系（后端）

```
                    ┌──────────────────────────────┐
    HTTP/SSE  ────► │  app/main.py  (中间件/异常/路由) │
                    └──────────────┬───────────────┘
                                   │ Depends(get_current_user / require_student / require_admin)
                    ┌──────────────▼───────────────┐
                    │  modules/*/router.py          │  只做编排：解析 DTO、调用 service、包信封
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │  modules/*/service.py         │  业务规则 + SQL（无 ORM 关系导航，全部显式 select）
                    └──┬────────┬────────┬─────────┘
                       │        │        │
        ┌──────────────▼─┐ ┌────▼─────┐ ┌▼──────────────────┐
        │ infrastructure │ │  app/ai  │ │ modules/*/skill.py │
        │ db/cache/store │ │ Provider │ │ (quiz / memory)    │
        └────────────────┘ └──────────┘ └───────────────────┘
                       │
        ┌──────────────▼───────────────────────────────┐
        │ PostgreSQL (32 表) │ Redis (锁/缓存/限流) │ 本地磁盘/S3 │
        └──────────────────────────────────────────────┘
                       ▲
                       │ 同一套 session / service
        ┌──────────────┴───────────────┐
        │  app/jobs/worker.py  (独立进程) │  ← background_jobs 表驱动
        │  handlers: knowledge /        │
        │            conversation /     │
        │            memory             │
        └───────────────────────────────┘
```

**关键架构约定（代码强制）**：
1. **Router 不写 SQL**，Service 不碰 HTTP（`content/service.py:79` 注释明示）。
2. **无 SQLAlchemy `relationship()`** —— `models.py` 全篇只有 `ForeignKey` 列，没有一处 `relationship(`。跨表一律显式 `select(...).join(...)`。这是**有意为之**的约定，新代码必须遵守。
3. **统一响应信封** `{"data": ..., "meta": ...}` / `{"error": {"code","message","details"}}`（`app/api/envelope.py`）。
4. **所有错误通过 `HTTPException(detail={"code","message"})`**，由 `main.py` 的 handler 转成信封。
5. **AI 调用失败不得中断主流程** —— conversation service 中 RAG / TeacherContext / evidence 全部包在 `try/except` 且注释「must not break chat」（`service.py:624,652,687`）。

---

## 5. 测试与 CI 布局

| 层 | 位置 | 数量 |
| --- | --- | --- |
| 后端单测/集成 | `backend/tests/*.py` | 36 文件 / 387 collected |
| 前端单测 | `frontend/src/**/*.test.ts(x)` | 49 文件 |
| E2E | `frontend/e2e/*.spec.ts` | 12 spec × 4 project |
| 教学评测 | `backend/evals/teaching_cases.jsonl` | 37 例（离线规则评测） |
| CI | `.github/workflows/ci.yml` | 3 job（backend / frontend / e2e） |
| 本地质量门禁 | `scripts/ci.sh`（11 步） | 覆盖 migration→pytest→vitest→build→e2e |
| 环境自检 | `scripts/audit-check.sh` | **只读**，强制隔离 DSN 校验 —— ⚠️ **但没有任何脚本调用它** |
| 测试库备份 | `scripts/test-db.sh` | ⚠️ 是手动 `shuangling_audit` 库的 backup/restore 工具，**不是**测试库搭建脚本，且无任何调用方 |

---

## 6. 当前 Git 状态（2026-09-16）

```
branch: master    HEAD: 970ffda (2026-08-28)    提交总数: 98
工作区: 96 modified + ~46 untracked  →  +3353 / -1142 行
```

**未提交的工作 = 2026-09-06 起的 T01–T26 优化轮**（后端 35 文件、前端 58 文件、CI、文档、4 个新迁移、19 个新后端文件、19 个新前端文件、`tasks/` 全部验收证据）。

最近一次提交 `970ffda fix(seed): give E2E demo memory a linked evidence` 是 CI 修复；
**真正的功能开发停在 2026-09-16**（数据库中出现当日创建的测试书与后台任务）。

> 详见 `docs/15-project-status.md` 与 `docs/12-known-issues.md`。
