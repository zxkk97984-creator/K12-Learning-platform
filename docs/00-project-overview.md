# 00 · 项目总览

> 本文件由 2026-09-16 的全量代码考古生成。**唯一事实源是当前工作区代码、数据库 Schema、配置与运行实测**，
> 不是旧的 README / 架构文档。凡代码无法证明的结论，均显式标注 `UNKNOWN` 或 `Hypothesis`。
>
> 证据规则：`文件:行号` 或 `函数/类名`。运行实测标注为「实测」。

---

## 1. 项目是什么

**霜铃（Shuangling）· K12 AI 数字教师 V3** —— 一个面向 K12 学生的「AI 通识教育」学习平台。

从代码反推的实际产品形态：

| 维度 | 代码证据支持的结论 |
| --- | --- |
| 产品形态 | Web 单页应用 + 后端 API。学生端 = 书库 → 阅读 → 页面感知 AI 对话 → 随堂测验 → 错题讲解 → 复习 → 继续学习 |
| 核心内容 | **AI / 编程 / 数据 / 机器人 / 计算思维 / 数字素养** 通识课程。`backend/data/library/books/` 下 25 本书 |
| 目标用户 | K12 学生（`grade` 1–12，`student_profiles.grade` CheckConstraint）。实测演示账号 `xiaoming` grade=8 |
| 核心隐喻 | 一位**可换风格的 AI 数字教师**（「霜铃」）+ 一只陪伴桌宠（Companion Dock） |
| 内容语言 | 中文（`language` 默认 `zh-CN`） |
| 当前阶段 | 受控小规模学生试用前的收敛期 |

**重要边界（代码证据）**：产品**不是**「全学科提分平台」。语料只有 AI 与计算通识（`backend/data/library/books/` 25 个 slug），
且代码中明确约束「禁止 mastery/score/percent 数字列」——`models.py:333` 注释
「knowledge_points（0-E §3.8；**禁止 mastery/score/percent 数字列**）」，
`profile_insights.level` 用 5 档定性的中文枚举（`偏弱/一般/较稳定/较强/仍需观察`，`models.py:964`）。
`tasks/plan.md:5`（第 4 条）也明确「保持『不引入主观知识掌握百分比』的原始产品约束」。

---

## 2. 用户角色

从 `users.user_type` 的 CheckConstraint（`models.py:47`）反推，**系统里只有两种角色**：

| 角色 | 判定 | 能力 |
| --- | --- | --- |
| `STUDENT` | `users.user_type='STUDENT'` + `student_profiles` 1:1 行 | 书库/阅读/对话/测验/记忆/画像/推荐 |
| `ADMIN` | `users.user_type='ADMIN'` + `admins` 1:1 行且 `enabled=true` | 书籍/章节/内容块/知识点/知识资源/教师风格管理 + 统计 |

`admins.role_level` 区分 `SUPERVISOR` / `CONTENT_EDITOR`（`models.py:1409`），
但**代码中未发现按 role_level 做差异化授权**——`require_admin`（`app/api/deps.py:68`）只校验「是 ADMIN 且 admins 行 enabled」，
不读取 `role_level` 做权限分级。→ **`role_level` 目前是无实效的字段（PARTIAL / 未接入授权）**。

> 代码中**不存在**：教师布置作业、班级、家长端、排行榜、支付、多租户。
> `tasks/plan.md:8` 明确将其排除在本轮范围外。

---

## 3. 技术栈（区分「声明」「实际使用」「接入运行链路」）

### 3.1 前端

| 类别 | 选型 | 状态 | 证据 |
| --- | --- | --- | --- |
| Framework | React 19.2 | 使用 | `frontend/package.json` |
| Language | TypeScript 7.0 | 使用 | `tsc --noEmit` 在 build 前置 |
| Build | Vite 8.2 | 使用 | `frontend/vite.config.ts` |
| Router | react-router-dom 7.18 | 使用 | `src/app/router/index.tsx` |
| Server State | TanStack Query 5.101 | 使用 | `src/app/providers/query.ts` |
| Client State | Zustand 5.0 | 使用 | `src/features/conversation/store/conversation-store.ts` |
| 动画 | motion 13 | 使用 | Companion 桌宠 |
| UI 基元 | Radix UI（dialog/popover/select） | 使用 | package.json |
| 样式 | Tailwind CSS 4.3（vite 插件） | 使用 | `@tailwindcss/vite` |
| 测试 | Vitest 4.1 + Testing Library | 使用 | `pnpm test` |
| E2E | Playwright 1.62 | 使用 | `frontend/e2e/` |
| HTTP Client | **原生 `fetch` 封装**（非 axios） | 使用 | `src/shared/api/http.ts` |
| 表单库 | **无**（受控组件手写） | — | 无 react-hook-form/formik 依赖 |

### 3.2 后端

| 类别 | 选型 | 状态 | 证据 |
| --- | --- | --- | --- |
| Framework | FastAPI 0.141（Modular Monolith） | 使用 | `backend/pyproject.toml` |
| Language | Python 3.12（`>=3.12,<3.13`） | 使用 | pyproject |
| ORM | SQLAlchemy 2.0 async + asyncpg | 使用 | `app/infrastructure/database/` |
| Migration | Alembic 1.19 | 使用 | `backend/alembic/versions/` |
| Validation | Pydantic 2.13 + pydantic-settings | 使用 | `app/config.py` |
| Auth | PyJWT HS256 + bcrypt（直调，不经 passlib） | 使用 | `app/modules/identity/security.py` |
| Background Job | **自研 PostgreSQL 表驱动队列**（`background_jobs` + `FOR UPDATE SKIP LOCKED`） | 使用 | `app/jobs/queue.py`、`app/jobs/worker.py` |
| Cache / Lock | redis-py（分布式锁 + 可丢失缓存，不可用时进程内降级） | 使用 | `app/infrastructure/cache/redis.py`、`app/infrastructure/rate_limit.py` |
| 限流 | 自研固定窗口（Redis INCR 或进程内滑动窗口） | 使用 | `app/infrastructure/rate_limit.py` |
| 对象存储 | 自研抽象：`local` / `s3`（SigV4 手写） | 使用 | `app/infrastructure/storage/` |
| AI SDK | **无第三方 SDK**——自研 httpx 适配器 | 使用 | `app/ai/openai_compatible.py` |
| PDF 解析 | pypdf 6.1 | 使用 | `app/modules/knowledge/ingestion.py` |
| Logging | 标准库 logging + 自研 access log / metrics | 使用 | `app/infrastructure/observability.py`、`metrics_registry.py` |
| 测试 | pytest 9.1（dev group） | 使用 | `backend/tests/` |
| HTTP Client | httpx 0.28（**正式依赖**，非 dev） | 使用 | pyproject `dependencies` |

**明确不存在（不要臆测）**：Celery、ARQ、RQ、Kafka、RabbitMQ、Elasticsearch、LangChain、LlamaIndex、pydantic-ai、OpenAI SDK。
`docs/architecture/project-architecture.md:529` 已裁定「当前不引入 pydantic-ai，仅作为可选演进方向」，与代码一致。

### 3.3 基础设施

| 组件 | 声明 | 实际运行 | 接入运行链路 |
| --- | --- | --- | --- |
| PostgreSQL 18 + pgvector 0.8.6 | ✅ docker-compose | ✅ 容器 `shuangling-postgres` healthy | ✅ 唯一事实存储 |
| Redis 7 | ✅ docker-compose | ✅ 容器 `shuangling-redis` healthy | ⚠️ **部分**：`scripts/start.sh` 默认**不启动** redis（仅 `--with-minio` 时启动），此时限流自动降级为进程内 |
| MinIO | ✅ docker-compose | ✅ 容器 `shuangling-minio` healthy | ⚠️ **未接入**：`backend/.env` 中 `STORAGE_BACKEND=local`，S3 适配器仅本地联调 |
| Worker（docker） | ✅ compose `worker` 服务 | ❌ 未以容器运行 | ⚠️ 该服务带 `profiles: ["worker"]`，`docker compose up` 不会启动；实际由 `scripts/start.sh` 以**宿主机进程**运行 |
| API（docker） | ❌ **compose 中无 api 服务** | — | 后端始终以宿主机 uvicorn 运行 |
| 反向代理 / nginx | ❌ 不存在 | — | — |
| Kubernetes / Terraform | ❌ 不存在（`infra/` 只有 `.gitkeep`） | — | — |
| CI/CD | ✅ GitHub Actions（3 job） | ⚠️ **未在本机实际触发过** | `docs/plans/current-phase.md:34` 自述未验证 |
| 监控 / APM | ❌ 无（仅进程内 Prometheus 文本 `/metrics`） | — | 无 Prometheus/Grafana/Loki 部署 |

---

## 4. 核心价值链（代码可证明的闭环）

```
登录(xiaoming)
  → 书库 /library          GET /books                 （仅 PUBLISHED，分页+搜索+筛选）
  → 书本详情 /books/:id     GET /books/{id}, /chapters
  → 阅读器 /learn/:b/:c     GET /chapters/{id}         （ContentBlock 渲染 + 图片资源）
       ├─ 开学习会话        POST /learning-sessions
       ├─ 页面感知对话      POST /conversations/{id}/messages  (SSE)
       │     └─ TeacherContext(档案/偏好/记忆/画像/进度) + RAG(知识库) + 教师人格
       ├─ 完成本章          PUT /me/chapters/{id}/completion
       └─ 结算时长          PATCH /learning-sessions/{id} → reading_settlements
  → 随堂测验 /quizzes       POST /quiz-sessions          （审校题 > LLM > 章节确定性 > 通用题库）
       ├─ 答题              POST .../questions/{qid}/answers
       └─ 提示 / 讲解        POST .../hints, 错题讲解上下文
  → 学习事件               POST /learning-events   → 入队 memory_consolidation（Worker）
  → 记忆/画像 /profile      GET /me/memories,/insights,/episodes,/agent.md
  → 推荐/下一步             GET /me/recommendations,/me/learning-next
  → 回到阅读/练习
```

这条链路的**每一环在代码中都有真实实现**，并已在运行中的实例上逐点实测通过（见 `docs/15-project-status.md` §运行实测）。

---

## 5. 当前产品边界（代码事实）

**在边界内**：学生端 9 个页面 + 管理端 5 个页面；AI 对话（SSE 流式）；RAG 知识库检索；随堂测验与错题讲解；
长期记忆与学习画像（定性 5 档）；规则式推荐；多 AI 教师风格；语音 ASR/TTS（Provider 化）；
内容管理后台；后台任务 Worker。

**边界外 / 未完成**：
- 真实对象存储（MinIO 已起但未被应用使用；`STORAGE_BACKEND=local`）
- 生产部署形态（无 compose api 服务、无反代、无 k8s）
- 真实 ASR/TTS 的外部质量验证（`.env` 已配 `VOICE_PROVIDER=aliyun`，但无自动化验证）
- 人工审校签署（`reviewed_questions` 表在开发库中 **0 行**）
- 多副本部署下的 `/metrics` 聚合（`docs/plans/current-phase.md:38` 自述待定）

---

## 6. 命名与术语表

| 术语 | 含义 | 代码位置 |
| --- | --- | --- |
| 霜铃 / Shuangling | 产品名 & AI 教师人设名 | `app_name`、system prompt |
| TeacherContext | 每轮对话注入的完整学生上下文块 | `app/modules/conversation/teacher_context.py` |
| ScreenContext | 前端当前页面/选中文本/章节上下文 | `app/modules/conversation/schemas.py`、`frontend/src/features/screen-context/` |
| Memory | 长期记忆（PROFILE/PREFERENCE/LEARNING/EPISODIC） | `student_memories` |
| Episode | 情节记忆（一次学习经历） | `student_episodes` |
| Insight | 画像洞察（5 档定性） | `profile_insights` |
| Skill | 领域能力边界（quiz / memory 等） | `app/skills/`、`app/modules/quiz/skill.py` |
| D9 溯源 | 内容来源/许可/版权字段族 | `source_ids`/`license`/`copyright_status` 平铺列 |
| Companion | 桌宠（Dock + Panel） | `frontend/src/features/companion/` |
| T01–T26 | 2026-09 优化任务编号 | `tasks/plan.md` |
| 0-E / 0-D | 历史规格文档编号（domain model / API contract） | 仅存于注释，**原文档已不在仓库** |

> ⚠️ 代码注释大量引用 `0-E §3.x`、`0-D §1.2` 等编号。经检索，**这些编号对应的原始文档不在本仓库**
> （`docs/` 下无 0-D/0-E 文件）。它们现在只能通过 `models.py` 的列定义与 `docs/contracts/api-contract.md` 间接还原。
> 这是新维护者理解代码时的一个真实摩擦点（见 `docs/13-technical-debt.md` DX 部分）。
