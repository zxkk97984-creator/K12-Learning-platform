# 02 · 架构（以实际代码为准）

> 本文件描述**已经建成**的架构，不是设计意图。凡与 `docs/architecture/project-architecture.md` 不一致处，
> 以本文件为准，并在 `docs/12-known-issues.md` 记录偏差。

---

## 1. 整体形态

**前后端分离 + 模块化单体（Modular Monolith）+ 独立后台 Worker 进程。**

```
┌─────────────────────────────────────────────────────────────────────┐
│  浏览器  React 19 SPA  (:5174 dev / 静态产物)                         │
│  zustand(3 stores) · 手写 fetch 封装 · SSE · WebSocket(语音)          │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ /api/v1/**  (Vite proxy 规避 CORS)
                            │ /api/v1/conversations/{id}/messages  → SSE
                            │ /api/v1/voice/ws                     → WS
┌───────────────────────────▼─────────────────────────────────────────┐
│  FastAPI 应用  (uvicorn :8002)      backend/app/main.py              │
│   ├ 中间件：X-Request-ID / 全局限流 / 访问日志 / 进程内指标             │
│   ├ 异常处理：统一错误信封                                             │
│   └ 11 个业务 router（全部挂 /api/v1）+ voice WS                      │
│                                                                      │
│  modules/<domain>/{router,schemas,service}.py                        │
│      router  = 编排（鉴权依赖、DTO、信封），不写 SQL                    │
│      service = 业务规则 + 显式 SQL（无 ORM relationship 导航）          │
│      schemas = Pydantic DTO                                          │
└──────┬────────────────┬──────────────────┬───────────────────────────┘
       │                │                  │
┌──────▼──────┐  ┌──────▼───────┐  ┌───────▼────────────┐
│ infrastructure│ │   app/ai     │  │ modules/*/skill.py │
│ db/cache/     │ │ Provider 抽象 │  │ (quiz / memory)    │
│ storage/      │ │ LLM/Embed/   │  └────────────────────┘
│ metrics/      │ │ Voice        │
│ rate_limit    │ └──────┬───────┘
└──────┬────────┘        │ httpx
       │                 ▼
       │        ┌──────────────────────────┐
       │        │ DeepSeek / 阿里云百炼      │
       │        │ (openai-compatible 协议)   │
       │        └──────────────────────────┘
┌──────▼──────────────────────────────────────────────────────────────┐
│  PostgreSQL 18 + pgvector 0.8.6      Redis 7       本地磁盘 / S3     │
│  32 张表 · 唯一事实源                锁/缓存/限流    上传产物          │
└──────▲──────────────────────────────────────────────────────────────┘
       │ 同一套 session / service / 模型
┌──────┴──────────────────────────────────────────────────────────────┐
│  后台 Worker 进程   python -m app.jobs.worker                        │
│  background_jobs 表驱动 · FOR UPDATE SKIP LOCKED · 指数退避 · 孤儿回收 │
│  handlers: knowledge_ingest / conversation_summary / memory_consolidation │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. 分层与调用规则（代码强制）

### 2.1 后端分层

| 层 | 位置 | 职责 | 禁止 |
| --- | --- | --- | --- |
| Router | `modules/*/router.py` | 依赖注入鉴权、解析/校验 DTO、调用 service、返回信封 | 写 SQL、写业务规则 |
| Service | `modules/*/service.py` | 业务规则、事务边界、**全部 SQL 在此** | 直接读 `Request`、返回 `Response` |
| Schema | `modules/*/schemas.py` | Pydantic 请求/响应 DTO | 业务逻辑 |
| Skill | `modules/*/skill.py`、`app/skills/` | 领域能力边界（出题、判分、记忆抽取） | 持久化（由调用方事务负责） |
| Infrastructure | `app/infrastructure/` | DB/缓存/存储/指标/限流/日志 | 领域知识 |
| AI Provider | `app/ai/` | 外部模型适配 | 领域逻辑、DB 访问 |

**`content/service.py:79`** 明确注释：「Content 只读 Domain Service（Router 只做编排，SQL 在此层）」。

### 2.2 ⚠️ 最重要的隐含约定：**没有 SQLAlchemy `relationship()`**

`models.py`（1465 行、32 个模型）**通篇只有 `ForeignKey` 列，没有一处 `relationship(`**。
跨表访问一律显式 `select(...).join(...)` 或分步 `session.get()`。

**这条约定必须被新代码遵守**，理由（从代码可推断）：
1. 避免 async 下的隐式惰性加载（`MissingGreenlet`）。`worker.py:45-52` 的注释记载了
   一个真实缺陷（「缺陷 A 根因」）：`session.rollback()` 后访问过期 ORM 属性会触发同步惰性加载并抛 `MissingGreenlet`。
2. 显式 SQL 便于控制 N+1。

> **代价**：`teacher_context.py:315-335` 仍存在按 quiz session 逐条查询的 N+1 模式。

### 2.3 前端分层

| 层 | 位置 | 职责 |
| --- | --- | --- |
| 路由 | `app/router/` | 唯一路由表 + 守卫 |
| 页面 | `pages/<page>/` | 组合 feature + 调用 service |
| Feature | `features/<name>/` | 自洽的功能切片（组件 + store + hooks + lib） |
| 实体类型 | `entities/<name>/types.ts` | 纯类型，无逻辑 |
| 服务接口 | `shared/api/*-service.ts` | 接口契约 |
| 服务实现 | `shared/api/api-*.ts` | 真实 HTTP/SSE/WS 实现 |
| 服务注册 | **`shared/services.ts`（唯一切换点）** | 决定用哪个实现 |
| UI 基元 | `shared/ui/` | AppLayout / BottomNav 等 |

**约定**：页面永不直接 `fetch`，一律经 `shared/services.ts` 暴露的单例。

---

## 3. 横切关注点（实际实现）

| 关注点 | 实现 | 状态 |
| --- | --- | --- |
| **统一响应信封** | `{"data":…, "meta":…}` / `{"error":{"code","message","details"}}`（`app/api/envelope.py`） | REAL |
| **请求追踪** | `X-Request-ID` 生成/透传 + 回写响应头（`main.py:44-94`） | REAL |
| **鉴权** | JWT HS256 Bearer；`get_current_user` → `require_student` / `require_admin`（`app/api/deps.py`） | REAL |
| **账号禁用即时失效** | `deps.py:41-45` 每次请求查 `users.status` | REAL |
| **严格后台鉴权** | 必须 `user_type=ADMIN` **且** `admins` 行 `enabled=true`，否则 403 `ADMIN_PROFILE_REQUIRED`（`deps.py:68-103`） | REAL |
| **限流** | 全局限流按 client IP（600/min）+ 登录按 ip+username（30/min）；Redis 固定窗口，失败降级进程内（**两种模式都强制拒绝**） | REAL |
| **幂等** | `idempotency_keys` 表 + `Idempotency-Key` 头；对话/答题 | REAL |
| **可观测性** | 结构化访问日志（**明确不记录 Authorization/密码/正文**）+ 进程内 Prometheus 文本 | PARTIAL（无 LLM/DB/队列指标） |
| **错误处理** | `HTTPException(detail={code,message})` → 统一 handler；`RequestValidationError` → 422 信封 | REAL |
| **AI 失败不阻塞主流程** | RAG / TeacherContext / evidence 全部 `try/except` 包裹 | REAL（有意设计） |
| **后台任务** | PG 表队列 + 独立 Worker 进程 | REAL（但默认不随 API 启动，见 `docs/09`） |
| **并发控制** | 会话级串行锁（Redis 分布式锁 + asyncio 本地降级）；测验作答 sequence 唯一约束 | REAL |
| **时长结算幂等** | `reading_settlements.session_id` 主键 → 同一会话只结算一次 | REAL |

---

## 4. 数据流：一次「带页面上下文的提问」

```
[浏览器] 学生在阅读器第 3 章提问「这段是什么意思？」
   │  ReaderPage 已把 {bookId, chapterId, chapterTitle, visibleSection, selectedText} 写入 ScreenContext
   ▼
ChatComposer.send(text, screenContext)                       ChatComposer.tsx:201
   ▼
useConversationStore.send()                                  conversation-store.ts:336
   ├ 生成 Idempotency-Key
   ├ 乐观插入学生气泡
   ▼
ApiConversationService.sendMessage()  →  POST /conversations/{id}/messages (SSE)
   │    body = {content, screen_context: 白名单12字段}       api-conversation-service.ts:288-333
   ▼
[后端] conversation/router.py:80  →  ConversationService.send_message()
   ├ 会话串行锁（Redis / asyncio）                            service.py:446-479
   ├ 幂等校验（命中则重放已存消息）                            :505-523
   ├ 落库 STUDENT 消息                                        :540-560
   ├ 读历史 + 最新摘要                                        :564-594
   ├ build_input_window()  摘要边界 + token 预算              context_window.py:45-88
   ├ quiz_intent 关键词判定（「题目」会劫持为出题！）           :612
   ├ retrieve(query, screen_context)  ← RAG                  :646 → retrieval.py:58
   │     └ KnowledgeService.search()  pgvector `<=>` SQL      knowledge/service.py:148-171
   ├ build_teacher_context()  档案/偏好/记忆/画像/进度         teacher_context.py:204-452
   ├ 拼装 system_prompt（人格/摘要/上下文/RAG/证据/指令）       :690-706
   ├ provider.stream_chat()  ← 真实 LLM（非真流式，见 docs/08）
   └ 落库 TEACHER 消息 + LearningEvent + 入队 memory_consolidation
   ▼
[SSE]  message.start → text.delta × N → message.done
   ▼
[浏览器] conversation-store 逐帧追加 → MessageList 渲染 → 桌宠播动画
```

---

## 5. 架构层面的关键事实（易被误判）

| # | 事实 | 证据 |
| --- | --- | --- |
| 1 | **`docker-compose.yml` 里没有 api 服务。** 它是「依赖服务编排」，不是部署编排。后端与前端始终以宿主机进程运行。 | `docker-compose.yml` services: postgres / redis / minio / worker |
| 2 | **worker 容器服务被 profile 门控**，`docker compose up` 不会启动它。 | `profiles: ["worker"]` |
| 3 | **API 进程不启动 Worker。** `main.py:31-34` 的 lifespan 是空的（注释还写着「当前无任何外部依赖」，已过时）。 | `main.py:31-34` |
| 4 | **`infra/` 是空目录**（只有 `.gitkeep`），无 k8s / terraform / nginx。 | `ls infra/` |
| 5 | **`backend/Dockerfile` 存在但未被任何部署流程使用**（只被 compose 的 worker 服务引用，而该服务默认不启动）。 | `Dockerfile` CMD = `python -m app.jobs.worker` |
| 6 | **前端没有真实的端到端流式**：后端把完整回复切片成伪 delta（`docs/08` §1.2）。 | `openai_compatible.py:68,103-104` |
| 7 | **前端装了 React Query 但零使用**，所有数据获取是手写 `useState`+`useEffect`。 | `.audit/B-frontend.md` §6.2 |
| 8 | **`app/skills/` 注册表被绕过**：对话链路硬编码 `QuizService()`。 | `conversation/service.py:282-283` |

---

## 6. 与设计文档的关系

`docs/architecture/project-architecture.md`（2307 行）**整体仍与代码高度一致**，且已包含「落地状态」标注
（例如 §33 注明 Redis Cache/Lock 已实现、Worker 队列由 PostgreSQL 承载）。
经抽查，主要偏差集中在**新增能力未回写**与**少数注释/图示仍写 PydanticAI**：

| 设计文档处 | 偏差 |
| --- | --- |
| `diagrams.md:50,251` | 图中仍写「ModelGateway（PydanticAI Adapter）」，实际是自研 httpx 适配器（`project-architecture.md:529,2294` 已裁定不引入） |
| `project-architecture.md` 端点相关 | 未覆盖 T13/T16/T10 新增的 3 个端点（见 `docs/07-api.md`） |
| 全局 | 未记录「无 token 级流式」「会话摘要是规则式」等实现真相（见 `docs/12-known-issues.md`） |

> 完整漂移清单见 `docs/12-known-issues.md` 与 `docs/15-project-status.md` 的 Documentation Drift 章节。
