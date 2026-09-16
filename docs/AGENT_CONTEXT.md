# AGENT_CONTEXT.md

> **给新加入的 AI Agent / 开发者的第一份文件。**
> 目标：读完本文件后，你能在较短时间内**正确**理解这个项目，而不是重新猜测架构。
>
> 生成于 2026-09-16，基于对当前工作区代码、数据库与运行实例的全量审计。
> 详细证据见 `docs/00`–`docs/16`；原始审计报告见 `.audit/`。

---

## 1. 项目是什么

**霜铃（Shuangling）· K12 AI 数字教师 V3** —— 面向 K12 学生的 **AI 通识教育**学习平台。

- 学生端闭环：`登录 → 书库 → 阅读 → 页面感知 AI 对话 → 随堂测验 → 错题讲解 → 复习 → 继续学习`
- 核心隐喻：一位可换风格的 AI 数字教师 + 一只陪伴桌宠（Companion）
- 语料范围：**AI / 编程 / 数据 / 机器人 / 计算思维 / 数字素养**，`backend/data/library/books/` 下 **25 本书**
- 角色只有两种：`STUDENT`、`ADMIN`（`users.user_type` 的 CheckConstraint）

**边界（代码中完全不存在，不要想象）**：教师布置作业、班级、家长端、排行榜、支付、多租户。

**产品硬约束**：**禁止 mastery / score / percent 数字列**。画像只用 5 档中文定性
（`偏弱/一般/较稳定/较强/仍需观察`）。见 `models.py:333,964`。

---

## 2. 技术栈

| 层 | 选型 |
| --- | --- |
| 前端 | React 19 + TypeScript 7 + Vite 8 + react-router 7 + **zustand（3 个 store）** + Tailwind 4 + Radix UI + motion |
| 后端 | FastAPI + Python 3.12 + SQLAlchemy 2.0 async + asyncpg + Alembic + Pydantic 2 |
| 认证 | PyJWT HS256 + **bcrypt 直调**（刻意不经 passlib） |
| 数据库 | PostgreSQL 18 + **pgvector 0.8.6** |
| 缓存/锁 | Redis 7（不可用时**自动降级为进程内**，两种模式都强制限流） |
| 队列 | **自研 PostgreSQL 表队列**（`background_jobs` + `FOR UPDATE SKIP LOCKED`）。**没有 Celery/ARQ** |
| AI | **自研 httpx 适配器**。**没有 openai SDK、没有 LangChain、没有 pydantic-ai**（已裁定不引入） |
| 测试 | pytest 9 + Vitest 4 + Playwright 1.62 |
| 包管理 | 后端 `uv`，前端 `pnpm` |

---

## 3. 核心目录

```
backend/app/
├── main.py            入口：中间件 / 路由注册 / 异常信封 / /health /metrics
├── config.py          全部配置（pydantic-settings，单一来源）
├── api/               deps.py（鉴权依赖）· envelope.py（统一信封）
├── ai/                Provider 抽象：base / factory / mock / openai_compatible / embedding / voice
├── infrastructure/    database/models.py（★ 32 表的唯一枢纽，1465 行）
│                      cache/redis · rate_limit · metrics_registry · observability · storage/
├── jobs/              queue.py · worker.py · handlers/{knowledge,conversation,memory}
├── modules/           11 个领域模块（每个含 router/service/schemas）
│   ├── conversation  ★ 系统心脏：service.py 1319 行 + teacher_context.py + context_window.py
│   ├── quiz          skill.py（出题/判分）+ chapter_source.py + quiz_bank.py
│   ├── knowledge     ingestion.py + retrieval.py + service.py（pgvector SQL）
│   ├── memory        pipeline.py（规则式）+ agent_md.py
│   ├── codelab       ★ 在线编程教学工具（Phase 1）：
│   │                   sandbox.py（Docker 隔离边界）+ execution.py（确定性判题）
│   │                   scoring.py / validation.py / prompts.py / static_analysis.py
│   │                   sandbox_assets/{runner,sitecustomize,result_plugin}.py
│   └── content/learning/recommendation/identity/admin/voice
└── scripts/           seed / validate_library / import_library / import_assessments / …

frontend/src/
├── app/               router（唯一路由表）· providers/query.ts
├── pages/             10 个页面（home/library/book/reader/quizzes/profile/settings/login/admin）
├── features/          auth · conversation(SSE store) · companion · quiz · memory · learning · screen-context · voice · feedback
├── pages/codelab/     ★ CodeLab 工作台：CodeEditor(CodeMirror6) + CodeOutputPanel + AiReviewPanel
├── entities/          6 个纯类型文件
├── shared/
│   ├── services.ts    ★★ 唯一服务注册表：决定用真实 API 还是 mock
│   ├── api/           接口（*-service.ts）+ 实现（api-*.ts）+ http.ts + sse.ts + voice-client.ts
│   └── ui/            AppLayout · BottomNav · ResourceState · UserAvatar
└── mocks/             ⚠️ 全部是死代码，见 §9
```

---

## 4. 核心 Domain 与数据流

**32 张表**，按领域：身份（5）· 内容（4）· 学习（5）· 对话（3）· 记忆画像（5）· 测验（5）· 知识库（2）· 个性化（1）· 基础设施（2）。

**一次「带页面上下文的提问」的完整链路**（最重要的一条）：

```
ReaderPage 写 ScreenContext {bookId, chapterId, chapterTitle, visibleSection, selectedText}
  → ChatComposer.send(text, screenContext)
  → useConversationStore.send()            生成 Idempotency-Key + 乐观插入气泡
  → POST /api/v1/conversations/{id}/messages   (SSE)
  → ConversationService.send_message()      conversation/service.py:431-1056
       ├ 会话串行锁（Redis / asyncio 降级）
       ├ 幂等重放
       ├ 落库 STUDENT 消息
       ├ build_input_window()   摘要边界 + token 预算（3000）
       ├ quiz_intent 关键词判定   ← ⚠️ 含「题目」即劫持为出题
       ├ retrieve(query, screen_context)  ← RAG（真 pgvector）
       ├ build_teacher_context()  档案/偏好/记忆/画像/进度
       ├ 拼装 system_prompt（人格/摘要/上下文/RAG/证据/指令）
       └ provider.stream_chat()   ← ⚠️ 真实 LLM，但非真流式
  → 落库 TEACHER 消息 + LearningEvent + 入队 memory_consolidation
  → SSE: message.start → text.delta×N → message.done
```

---

## 5. 关键架构约定（**必须遵守**）

1. **没有 SQLAlchemy `relationship()`。** 全仓 0 处。跨表一律显式 `select().join()`。
   这是用血换来的：`worker.py:45-52` 记录了一次真实的 `MissingGreenlet` 事故
   （`rollback()` 后访问过期 ORM 属性会触发同步惰性加载）。
2. **Router 不写 SQL，Service 不碰 HTTP。** `content/service.py:79` 明示。
3. **统一响应信封**：`{"data":…, "meta":…}` / `{"error":{"code","message","details"}}`。
   错误一律 `HTTPException(detail={"code","message"})`。
4. **幂等靠唯一约束**：`reading_settlements.session_id`（主键）、
   `quiz_answers(session,question,attempt)`、`chapter_completions(student,chapter)`、
   `reviewed_questions.stable_key`、`idempotency_keys(actor,type,key)`。
5. **AI 失败不得中断主流程**：RAG / TeacherContext / evidence 三处全部 `try/except`
   （注释「must not break chat」）。
6. **前端页面永不直接 fetch**，一律经 `shared/services.ts` 的单例。
7. **内容可见性守卫放在 Service 层**（不是 Router），这样 Redis 缓存命中路径也绕不过。
8. **append-only 表**：`learning_events`、`messages`（应用层约定）。
9. **禁用账号即时失效**：`deps.py:41-45` 每次请求查 `users.status`。
10. **严格后台鉴权**：必须 `user_type=='ADMIN'` **且** `admins` 行 `enabled=true`。

---

## 6. 当前完成度（诚实版）

| 维度 | 评价 |
| --- | --- |
| 阶段 | **Prototype+ / MVP−**（不是 Beta，不是 Production Ready） |
| 产品功能 | ~60–70% |
| 前端 | ~75%（10 页面全接真实后端，tsc 0 错误，258 测试全绿） |
| 后端 | ~70%（71 HTTP + 1 WS，分层纪律好） |
| 数据层 | **~85%（最好的一环：三方对账几乎零漂移）** |
| AI 能力 | **~35–40%（最大短板）** |
| **CodeLab** | **闭环在 mock Provider 下已验证可用**（Phase 1）：真实 Docker 沙箱 + 确定性判题（F/R）+ A/Q 两个 LLM 维度的接线。⚠️ **真实 LLM Provider 的评分质量与 Prompt 配合尚待有效 Key 验收**，不得表述为「已完全验证」（见 `docs/17-codelab.md` §9）。未接入记忆/推荐/学习事件 |
| 测试 | ~45% |
| 部署 | **~10%** |
| 安全 | ~65% |
| 可维护性 | ~55% |
| 可观测性 | ~20% |

**「学生能走完一条学习闭环」是真的**；**「AI 数字教师」是半成品**。

---

## 7. 当前最大缺口（**先看这 5 条**）

| # | 缺口 | 一句话 |
| --- | --- | --- |
| **1** | **一整轮 T01–T26 工作未提交** | 96 改 + 46 新增；其中 **4 个迁移未提交而数据库已 stamped 到它们的 head** → `git clean` 后**任何 Alembic 命令都会失败** |
| **2** | **CI 的 backend job 在干净库上必然失败** | 测试顺序 bug：`TestChapterSourceVisibility` 不依赖 `client` fixture，造数发生在失败之后 |
| **3** | **开发库被测试夹具污染** | `conftest.py` 11 行、不设 `DATABASE_URL` → 测试直连开发库。学生书库 69 本中 **43 本是夹具**，32 本零章节 |
| **4** | **长对话摘要删除历史并谎报覆盖** | `jobs/handlers/conversation.py:86` 写 `message_covered_count = len(messages)`，而它只保留了首+关键+尾、每行截 160 字符；`context_window.py:61-65` 据此**丢弃**边界前的全部消息。**没有 LLM 摘要。** |
| **5** | **AI 内核名不符实** | 无 token 级流式（`stream:False` + 事后切片伪造）；无 Agent/工具调用；`student_episodes.embedding` 从不写入（239/0）；出题 89% 来自 8 题硬编码题库；审校题库**三重不通** |

---

## 8. 启动方式

```bash
# 一键（推荐）
bash scripts/start.sh                 # 默认只起 postgres；--with-minio 加 redis+minio

# 手动
docker compose up -d postgres redis
cd backend
cp .env.example .env                  # ★ JWT_SECRET 必填（无默认值）
uv run alembic upgrade head           # ★ 必须早于 seed
uv run python -m app.scripts.seed
uv run python -m app.scripts.validate_library --all
uv run python -m app.scripts.import_library --all
uv run uvicorn app.main:app --port 8002        # 终端 A
uv run python -m app.jobs.worker               # 终端 B（★ API 不会启动它！）
cd ../frontend && pnpm install
VITE_API_PROXY_TARGET=http://127.0.0.1:8002 pnpm dev --port 5174
```

- 后端固定 **:8002**（8000 被另一个项目占用）；前端 dev **:5174**；E2E 自起 **:5175**。
- 演示账号：学生 `xiaoming/demo123`（grade 8）；管理员 `admin/admin123`。
- 停止：`bash scripts/stop.sh`

**CodeLab 需要额外条件**：`CODELAB_ENABLED=true` + Docker 可用 +
`dai-kernel-python:latest`（运行，含 matplotlib）与 `dai-judge-python:latest`（判题，含 pytest）两个镜像。
新环境导入任务：`uv run python -m app.scripts.import_code_tasks`。详见 `docs/17-codelab.md`。

---

## 9. 测试方式

```bash
# 后端（⚠️ 见下方警告）
cd backend && uv run pytest -q

# 前端
cd frontend && npx vitest run          # 258 tests
npx tsc --noEmit                       # 0 errors
pnpm build

# 本地全量质量门禁（11 步）
bash scripts/ci.sh

# E2E（会自起后端 + Worker + seed）
bash scripts/ci-e2e.sh
```

### ⚠️ 三个必须知道的坑

1. **`uv run pytest` 会直连你的开发数据库。** `tests/conftest.py` 只有 11 行、
   **不设置 `DATABASE_URL`** → 用 `backend/.env` 的库。
   **跑之前请先 `export DATABASE_URL=...隔离库...`。**
2. **`scripts/ci.sh` 也会污染开发库**（它从 `backend/.env` 导出 `DATABASE_URL`）。
   `scripts/audit-check.sh` 有正确的守卫，但**没有任何脚本调用它**。
3. **前端有 11 个测试保护的是死代码**（`mocks/services/*.test.ts`、`ResourceState.test.tsx`），
   258 这个数字里有水分。

**当前真实测试结果**（2026-09-16 实测）：后端干净库 **1 failed / 383 passed**（CI 恒红）；
前端 **258 passed**；E2E **未验证**。

---

## 10. 不能轻易改变的设计

| 设计 | 原因 |
| --- | --- |
| **无 `relationship()`** | 规避 async 惰性加载事故 |
| **无 mastery/score/percent 数字列** | 产品硬约束 |
| **`VECTOR` 无维度列** | 兼容 mock(64) 与真实(1024) 共存 —— **但这是有代价的**（无法建索引、58% 知识不可达），改动前先读 `docs/16` R3 |
| **PG 表队列而非 Celery** | 已在生产验证（636 次 success），无必要引入新中间件 |
| **Service 层的可见性守卫位置** | 使缓存无法绕过 |
| **`shared/services.ts` 作为唯一服务切换点** | 前端 DI 的全部机制 |
| **`background_jobs` 的 `FOR UPDATE SKIP LOCKED` + TTL 回收** | 多消费者安全的核心 |
| **append-only 的 `learning_events` / `messages`** | 审计与可追溯性 |

---

## 11. 已知遗留问题（**不要重新"发现"它们**）

已经在 `docs/12-known-issues.md` 里分级登记（P0×3 / P1×8 / P2×20 / P3×16）。最容易误判的几条：

- ❌ **「前端还在用 mock」** → 已经彻底不用了。`shared/services.ts` 全绑 `Api*Service`，
  `src/mocks/` 是死代码，生产 bundle 里已验证不含任何 mock 标记。
- ❌ **「语音是断的」** → 语音输入（ASR）是**真实且可达的**（AudioWorklet + WS + 阿里云实时 ASR）。
  只有 **TTS** 未配置（**有意的诚实降级**，返回 `TTS_UNAVAILABLE` 而不是假音频）。
- ❌ **「ScreenContext 只在前端」** → 它的注释是错的，实际经 3 条通道发到后端。
- ❌ **「数据库有严重 schema 漂移」** → **几乎没有**。三方对账只有 1 个良性差异。
  问题在**库里的数据是脏的**，不在 schema。
- ❌ **「Worker 没实现」** → 实现完整且正在运行（636 次 success）。问题是**默认启动路径没有保证**。
- ❌ **「测验是纯 AI 生成的」** → 89% 来自 8 题硬编码题库；但**判分是真实且服务端权威的**。
- ❌ **「`.agent.md` 是后端产物」** → 前端自己合成了一份；后端那份（125 KB，真实）**没人调用**。

---

## 12. 下一步开发重点

按 `docs/16-roadmap-analysis.md`：

- **Phase A（止血，无讨论余地）**：提交未提交工作 → 确认迁移进 git →
  修 CI 顺序 bug → 给 `conftest.py` 加隔离守卫 → 清理开发库夹具 → CI 加 `alembic check`。
- **Phase B（打通闭环）**：修会话摘要 → 接真流式 → 修 `import_assessments` 并接入启动链路 →
  Worker 启动保证 → 情节记忆接向量 → 统一错误态 → 管理端补编辑 UI → 归档语义 → 清理死代码。
- **Phase C（结构）**：重建测试基础设施 → 补错误路径测试 → 覆盖率与 lint →
  向量索引决策 → 补 FK 与索引 → 拆分巨型文件 → React Query 二选一。
- **Phase D（产品）**：收敛出题策略 → 反馈/提示真实化 → 教学评测变门禁 → 最小可部署骨架。

**需要人类先拍板的 3 件事**（`docs/16` Reconsider）：
**R1** AI 能力叙事（收敛 vs 真上 Agent）、**R3** 向量列维度策略、**R5** 测试隔离方案。

---

## 13. 工作纪律（给下一个 Agent）

1. **代码是唯一事实源。** 本仓库的文档**确实有漂移**（已登记 20+ 处），
   尤其 `docs/plans/current-phase.md` 的测试数字与 `README.md` 的能力描述。
2. **不要相信 `docs/11-feature-status.md` 之外的「已完成」声明**，它逐项给了证据。
3. **改动前先读 `.audit/` 对应领域的报告**（A=AI / B=前端 / C=数据库 / D=测试，共 3600+ 行）。
4. **修 bug 前先确认它在干净环境可复现** —— 当前很多"问题"是脏数据造成的假象。
5. **跑测试前先设隔离 `DATABASE_URL`。**
6. 本项目的注释质量很高，且大量解释「为什么」——**改动时请保留这些解释**，
   它们记录了真实踩过的坑。
