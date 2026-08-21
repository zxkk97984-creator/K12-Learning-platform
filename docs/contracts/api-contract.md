# 霜铃 · K12 AI 数字教师 V3 — API Contract（仅设计）

> 状态：Phase 0 契约基线（Task 0-D）
> 版本：v0.1
> 日期：2026-08-19
> 输入基线：domain-model.md（0-C，27 实体 + D1~D10）、执行总控（§11~§20 API 骨架、§13.5 SSE、§18.3 Voice 状态、§15.7 Quiz 幂等、§22~§24 协议）、project-architecture.md（§8 Screen Context、§11 Domain 划分）、page-map.md / ui-behavior.md（0-B 前端数据形状）
> 用途：Phase 2 起后端实现与前端接真实 API 的唯一契约。**本文只设计，不实现任何代码。**

---

## 1. 全局约定

### 1.1 Base URL 与版本

- 所有端点前缀：`/api/v1`（例如 `https://api.example.com/api/v1/books`）。
- 运行探针 `GET /health` 与 `GET /api/v1/ping` 由应用入口直接注册，仅用于健康检查，不计入下文业务 API 端点总数。
- 版本策略：路径版本 `v1`；不兼容变更必须升 `v2`，不破坏 v1 语义；同版本内只做向后兼容的字段追加（新增可选字段）。
- 开发环境 base URL 由前端配置项提供（Mock Service Layer 与 API 客户端同接口，总控 §27）。

### 1.2 认证方式

**选型：Bearer JWT（访问令牌）**，MVP 不做 refresh token 轮换。

理由：

1. SPA 无状态分发简单，避免 cookie/CSRF 配置面；
2. SSE 采用 `POST + fetch ReadableStream`（见 §8），可以在请求头携带 `Authorization`，不依赖 EventSource 的 cookie；
3. 后端 FastAPI 中间件统一校验 `Authorization: Bearer <token>`，`user_type` 与 `admin.role_level` 从 token claims 读取，Admin-only 路由直接拒绝。

约定：

- `POST /auth/login` 返回 `access_token`，有效期 7 天（MVP 常量，可配置）。
- 受保护端点均要求 `Authorization: Bearer <token>`；未携带或过期返回 `401`。
- 学生端点（`/me/**`、学习、对话、测验、记忆、推荐）要求 `user_type=STUDENT`；Admin-only 端点（`/admin/**`）额外要求 `user_type=ADMIN`。
- 登出为客户端丢弃令牌（MVP 无服务端黑名单；如需立即失效，后续加 Redis 黑名单，不影响本契约）。
- WebSocket 无法携带自定义头：语音连接用 `?token=<jwt>` 查询参数；生产建议换一次性 short-lived ticket（Phase 9 时定稿）。

### 1.3 统一响应信封

成功：

```json
{
  "data": {},
  "meta": { "next_cursor": null, "has_more": false }
}
```

- `data`：资源对象或数组；204 无响应体。
- `meta`：分页/计数等附加信息；单资源端点可省略或返回空对象。
- 创建类端点：`201 Created`，`Location` 指向新资源；重复幂等返回 `200` + 响应头 `Idempotency-Replayed: true`。

失败：

```json
{
  "error": {
    "code": "CONVERSATION_NOT_FOUND",
    "message": "conversation not found",
    "details": { "conversation_id": "..." }
  }
}
```

- `code`：稳定业务错误码（见 1.4），客户端按 code 分支，不解析 message。
- `message`：面向开发者/日志的英文摘要；面向学生的展示文案由前端生成。
- `details`：可选结构化详情（校验字段、资源 id 等）。

### 1.4 错误码体系

| HTTP | code | 场景 |
| --- | --- | --- |
| 400 | `BAD_REQUEST` | 请求语法/语义错误（非字段校验） |
| 401 | `UNAUTHENTICATED` | 未携带或无效令牌 |
| 401 | `TOKEN_EXPIRED` | 令牌过期 |
| 401 | `INVALID_CREDENTIALS` | 登录凭据错误 |
| 403 | `FORBIDDEN` | 已认证但无权访问该资源（非本人资源） |
| 403 | `ADMIN_ONLY` | 需要管理员身份 |
| 404 | `CONVERSATION_NOT_FOUND` | 会话不存在 |
| 404 | `BOOK_NOT_FOUND` / `CHAPTER_NOT_FOUND` / `KNOWLEDGE_POINT_NOT_FOUND` | 内容不存在 |
| 404 | `LEARNING_SESSION_NOT_FOUND` / `LEARNING_EVENT_NOT_FOUND` / `BOOK_PROGRESS_NOT_FOUND` | 学习记录不存在 |
| 404 | `QUIZ_NOT_FOUND` / `QUESTION_NOT_FOUND` / `ANSWER_NOT_FOUND` / `INTERACTION_NOT_FOUND` | 测验对象不存在 |
| 404 | `MEMORY_NOT_FOUND` / `INSIGHT_NOT_FOUND` / `EPISODE_NOT_FOUND` / `EVIDENCE_NOT_FOUND` | 记忆/画像不存在 |
| 404 | `RECOMMENDATION_NOT_FOUND` / `RESOURCE_NOT_FOUND` / `CHUNK_NOT_FOUND` | 推荐/知识不存在 |
| 404 | `TEACHER_ROLE_NOT_FOUND` | 教师角色不存在 |
| 409 | `IDEMPOTENCY_KEY_REUSED` | 同一 Idempotency-Key 被不同请求体复用 |
| 409 | `QUIZ_ALREADY_ANSWERED` | 该题该次尝试已提交（幂等重放除外） |
| 409 | `QUIZ_FINALIZED` | 测验/题目已完成，禁止再提交 |
| 409 | `QUIZ_NOT_ACTIVE` | 测验状态不是 ACTIVE（如 GENERATING/ABANDONED） |
| 409 | `QUIZ_HINT_LIMIT_REACHED` | 提示已达 max_hint_level |
| 409 | `MEMORY_INVALID_TRANSITION` | 记忆状态机不允许该动作 |
| 409 | `CONVERSATION_INVALID_STATUS` | 会话状态不允许该操作（如 DELETED） |
| 409 | `LEARNING_SESSION_INVALID_STATUS` | 学习时段状态不允许该操作（如已 ENDED） |
| 409 | `RECOMMENDATION_INVALID_STATUS` | 推荐状态不允许该操作（如已 DISMISSED） |
| 422 | `VALIDATION_ERROR` | 请求字段校验失败；details 含字段错误列表 |
| 422 | `SCREEN_CONTEXT_INVALID` | screen_context 不符合架构 §8 结构 |
| 422 | `QUIZ_INVALID_OUTPUT` | Quiz Skill 输出未通过 Pydantic/Rule 校验（AI 输出校验失败，业务可重试） |
| 422 | `AI_OUTPUT_VALIDATION_FAILED` | 其他 AI 结构化输出校验失败（记忆/推荐/画像） |
| 429 | `RATE_LIMITED` | 触发限流（AI 调用/登录尝试） |
| 500 | `INTERNAL_ERROR` | 未预期服务端错误 |
| 500 | `AI_PROVIDER_ERROR` | 模型供应商失败（详情含 provider，不泄露密钥） |
| 500 | `STREAM_NOT_RESUMABLE` | SSE 断线续传不可用（见 §8.4） |

### 1.5 分页与排序

- **统一 cursor 分页**：所有列表端点接受 `?limit=<1..100>&cursor=<opaque>`；默认 `limit=20`。
- `meta`：`{ next_cursor: string|null, has_more: boolean }`；无更多数据时 `next_cursor=null`。
- cursor 由服务端生成（编码上一页最后一条的排序键 `(created_at, <id>)`），客户端不得自行拼接。
- 排序：默认 `created_at DESC, <id> DESC` 稳定排序；可选 `sort` 参数仅允许端点文档列出的白名单字段（如 `title`, `updated_at`），非法值返回 422。

### 1.6 时间与 ID

- 时间：ISO 8601 / RFC 3339 UTC（如 `2026-08-19T12:34:56Z`）；客户端本地展示自行转换时区。
- ID：全部为 uuid v4 字符串（小写规范形式），由服务端生成；客户端只传引用，不自造 ID（总控 §28）。
- 枚举值：大写 SCREAMING_SNAKE_CASE（中文业务枚举如画像档位除外，按 domain-model 固定值）。

### 1.7 幂等约定

- 适用端点（文档中标注「幂等：是」的 POST）：请求头 `Idempotency-Key: <uuid 或 ≤64 字符字符串>`。
- 服务端按 `(actor_id, actor_type, key)` 保存映射 24 小时：
  - 同 key + 同规范化请求体 → 重放原始成功响应，响应头 `Idempotency-Replayed: true`；
  - 同 key + 不同请求体 → `409 IDEMPOTENCY_KEY_REUSED`；
  - 缺少 key → 按普通请求处理（不保证去重）。
- **Quiz 答案提交（总控 §15.7）与对话消息发送强制要求 Idempotency-Key**；其余标记为「建议」。

### 1.8 通用头

- 请求：`Content-Type: application/json`、`Authorization`、`Idempotency-Key`（按端点）。
- 响应：`X-Request-Id`（便于日志关联，客户端透传 `X-Request-Id` 可被采纳）；`Idempotency-Replayed`（幂等重放）。

---

## 2. DTO 与 Domain 一致性原则

1. 每个响应 DTO 字段必须能映射回 `domain-model.md` 的实体字段；**禁止发明实体中没有的字段**。
2. 派生/组合字段必须显式标注 `(derived)`，例如 `stage`（由 grade 派生）、`chapter_count`（由 Chapter 计数）、`progress`（来自 BookProgress）、`recommended`（来自 ACTIVE Recommendation）。
3. 展示字符串（如 `"初二 · 8 年级"`、`"8 / 10"`）只存在于前端渲染层，**任何 DTO 不返回**；分数用结构化 `{correct, total}`。
4. 前端需要的视图字段（book.status/started/recommend/tint 等，0-B）由后端按上述 DTO 组装，前端不再维护业务判定。
5. AI 相关写入端点（消息、Quiz、Hint、Memory、Recommendation）**只接受结构化请求、只返回结构化响应**；任何 LLM 输出在落库前必须通过 Pydantic 校验（D10）。

---

## 3. DTO 目录（响应体字段定义）

> 端点章节引用以下 DTO；字段名与 domain-model 实体字段一一对应，`(derived)` 为派生字段。

### 3.1 Auth / Identity

**AuthDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `access_token` | string | JWT |
| `token_type` | string | 固定 `Bearer` |
| `expires_at` | datetime | 过期时间 |
| `user` | object | `{ user_id, username, user_type }` |

**StudentProfileDTO**（映射 StudentProfile）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `student_id` | uuid | PK |
| `nickname` / `avatar_url` | string | 昵称/头像 |
| `grade` | int | 1~12 |
| `stage` | enum `PRIMARY/JUNIOR/SENIOR` | (derived) 1-6/7-9/10-12 |
| `birth_date` / `language` / `learning_goal` | date/string/string | 基础资料 |
| `current_teacher_role_id` | uuid? | 当前角色 |
| `learning_days` / `total_learning_minutes` / `completed_books` / `completed_chapters` / `quiz_count` | int | 统计摘要（Worker 重算缓存） |
| `created_at` / `updated_at` | datetime | 时间 |

**TeacherRoleSummaryDTO**（映射 TeacherRole 子集）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `role_id` / `name` / `description` | uuid/string/text | 基础 |
| `avatar` | string? | 头像 |
| `voice_id` | string? | 语音 |
| `enabled` | bool | 是否可选 |

### 3.2 Students

**StudentPreferenceDTO**（映射 StudentPreference）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `preference_id` | uuid | PK |
| `student_id` | uuid | 学生 |
| `preferred_explanation_style` | enum | EXAMPLE_BASED/VISUAL/STORY/DIRECT_DEFINITION/STEP_BY_STEP/CODE/INTERACTIVE |
| `preferred_difficulty` | enum | EASY/MEDIUM/HARD |
| `preferred_session_length` | enum | SHORT/MEDIUM/LONG |
| `voice_preference` | jsonb | `{input_enabled,tts_enabled,volume,speed}` |
| `active_questioning_enabled` | bool | 主动提问开关 |
| `daily_learning_minutes` | int | 学习时长目标 |
| `evidence_ids` | jsonb | 支撑证据 |
| `updated_at` | datetime | 时间 |

### 3.3 Content

**BookSummaryDTO**（映射 Book + 派生）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `book_id` / `title` / `cover_url` / `description` | uuid/string | 基础 |
| `grade_min` / `grade_max` | int | 适用年级 |
| `difficulty` | enum | EASY/MEDIUM/HARD |
| `estimated_minutes` | int | 预计时长 |
| `tags` | jsonb | 主题标签 |
| `chapter_count` | int | (derived) 章数 |
| `progress` | BookProgressDTO? | (derived) 当前进度；无记录时 null |
| `recommended` | bool | (derived) 是否存在 ACTIVE 推荐 |

**BookDetailDTO** = BookSummaryDTO + `author/license/copyright_status/source_ids/created_by/published_at`。

**ChapterSummaryDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `chapter_id` / `title` / `summary` / `estimated_minutes` | uuid/string/text/int | 基础 |
| `chapter_order` | int | 顺序 |
| `status` | enum | DRAFT/PUBLISHED/ARCHIVED |
| `content_block_count` | int | (derived) |
| `is_completed` | bool | (derived) 当前学生是否完成（来自 BookProgress/事件） |

**ChapterDetailDTO** = ChapterSummaryDTO + `content_blocks: ContentBlockDTO[]` + `knowledge_points: KnowledgePointDTO[]`。

**ContentBlockDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `block_id` / `block_type` / `content` / `block_order` / `section_key` / `knowledge_point_ids` | uuid/enum/jsonb/int/string?/jsonb | 实体字段原样 |

**KnowledgePointDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `knowledge_point_id` / `name` / `slug` / `description` / `topic` / `parent_id` / `status` | uuid/string/string/text?/string?/uuid?/enum | 实体字段原样 |

### 3.4 Learning

**LearningSessionDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session_id` / `book_id` / `chapter_id` / `started_at` / `ended_at?` / `duration_seconds` / `status` / `entry_route?` | 按实体 | 实体字段原样 |

**LearningEventDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `event_id` / `session_id?` / `event_type` / `occurred_at` / `book_id?` / `chapter_id?` / `block_id?` / `knowledge_point_ids?` / `conversation_id?` / `quiz_session_id?` / `payload` | 按实体 | 实体字段原样；created_at 隐含 |

**BookProgressDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `progress_id` / `book_id` / `chapter_id?` / `block_id?` / `status` / `position_percent` / `last_read_at?` / `started_at?` / `completed_at?` / `total_seconds` | 按实体 | 实体字段原样 |

### 3.5 Conversations

**ConversationListItemDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `conversation_id` / `title?` / `status` / `channel` | 按实体 | 基础 |
| `teacher_role` | TeacherRoleSummaryDTO? | (derived) 关联角色 |
| `last_message_at` / `updated_at` | datetime | 排序/展示 |

**ConversationDTO** = ConversationListItemDTO + `student_id` + `current_page_context`（jsonb，架构 §8 结构）+ `recent_messages`（jsonb 缓存窗口）+ `conversation_summary`（text?）。

**MessageDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `message_id` / `conversation_id` / `role` / `type` / `content` / `metadata` / `sequence` / `model_info?` / `created_at` | 按实体 | 实体字段原样 |

**ConversationSummaryDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `summary_id` / `summary` / `token_count` / `summary_version` / `source_message_ids?` / `model_info?` / `updated_at` | 按实体 | 实体字段原样 |

### 3.6 Assessment

**QuizSessionListItemDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `quiz_session_id` / `title` / `quiz_kind` / `status` / `book_id?` / `chapter_id?` / `created_at` / `completed_at?` | 按实体 | 基础 |
| `result_summary` | jsonb? | `{correct,total,hints_used}` |
| `ai_feedback` | text? | 点评 |
| `skill_version` | string | Skill 版本 |

**QuizSessionDetailDTO** = QuizSessionListItemDTO + `student_id` + `conversation_id` + `teacher_role_id` + `questions_snapshot`（jsonb，只读快照）+ `duration_seconds` + `model_info`。

**QuizQuestionDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `question_id` / `question_order` / `question_type` / `stem` / `options` / `interaction_policy` / `knowledge_point_ids?` / `source_context?` | 按实体 | 实体字段原样 |
| `correct_answer` / `explanation` | jsonb/text? | **条件可见**：ACTIVE 会话中仅在该题已提交后返回；历史/COMPLETED 详情始终返回 |

**QuizAnswerDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `answer_id` / `question_id` / `submitted_answer` / `is_correct` / `attempt_no` / `hint_level_at_submit` / `is_final` / `submitted_at` | 按实体 | 实体字段原样 |

**QuizInteractionDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `interaction_id` / `question_id?` / `interaction_type` / `payload` / `message_id?` / `answer_id?` / `sequence` / `created_at` | 按实体 | 实体字段原样 |

### 3.7 Memory

**StudentMemoryDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `memory_id` / `memory_type` / `content` / `tags?` / `confidence` / `status` / `evidence_ids` / `origin_candidate_id?` / `user_confirmed` / `created_at` / `updated_at` / `confirmed_at?` | 按实体 | 实体字段原样；`confidence` 只返回 LOW/MEDIUM/HIGH 定性值 |

**ProfileInsightDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `insight_id` / `insight_type` / `dimension` / `level` / `description` / `evidence_ids` / `status` / `valid_from` / `valid_until?` / `rule_version` / `updated_at` | 按实体 | 实体字段原样；level 仅 5 档 |

**MemoryEvidenceDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `evidence_id` / `source_type` / `event_ids` / `payload` / `count` / `first_occurred_at?` / `last_occurred_at?` / `derived_at` / `rule_version` | 按实体 | 实体字段原样 |

**StudentEpisodeDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `episode_id` / `title` / `summary` / `occurred_at` / `event_ids` / `book_id?` / `chapter_id?` / `knowledge_point_ids?` / `importance` / `tags?` / `created_at` | 按实体 | 实体字段原样；**embedding 永不返回** |

### 3.8 Personalization

**RecommendationDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `recommendation_id` / `student_id` / `recommendation_type` / `title` / `description` / `reason` / `evidence_ids` / `related_book_id?` / `status` / `created_at` / `updated_at` | 按实体 | 实体字段原样；`reason` 与 `evidence_ids` 用于解释推荐依据 |

### 3.9 Knowledge（骨架）

**KnowledgeResourceDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `resource_id` / `source_name` / `source_url` / `author?` / `license` / `copyright_status` / `file_type` / `status` / `error?` / `uploaded_by` / `uploaded_at` / `updated_at` | 按实体 | 实体字段原样；`storage_key` 不返回 |

**KnowledgeChunkDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `chunk_id` / `resource_id` / `chunk_index` / `content` / `content_type?` / `metadata` / `knowledge_point_ids?` / `token_count` / `status` | 按实体 | 实体字段原样；**embedding 永不返回** |

### 3.10 Admin

**AdminStatsDTO**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `book_count` / `chapter_count` / `knowledge_point_count` / `resource_count` / `resource_processing` | int | (derived) 管理首页统计 |

---

## 4. 端点总览

| 模块 | 端点数 | 说明 |
| --- | --- | --- |
| Identity / Auth | 5 | 登录/登出/me/教师角色 |
| Students | 2 | 偏好读写 |
| Content | 5 | 书/章/块/知识点读取 |
| Learning | 7 | 时段、事件、进度 |
| Conversations | 7 | CRUD + 消息 + SSE + 摘要 |
| Assessment | 8 | 测验生成/历史/答题/提示/互动 |
| Memory | 8 | 记忆/画像/情节/证据/agent.md |
| Knowledge | 4 | 骨架（资源/块/检索） |
| Personalization | 2 | 推荐列表/忽略 |
| Admin | 17 | 统计 1 / 书 4 / 章·块·知识点 6 / 知识资源 3 / 教师角色 3 |
| **HTTP 业务端点合计** | **65** | |
| Voice WebSocket | 1 | `/api/v1/voice/ws` |
| **API 路由合计** | **66** | |

> **实现核对（2026-08-21）**：以 `backend/app/main.py` 注册的业务 router 及其 `@router` 装饰器为事实源，当前实际为 Identity 7、Admin 17、Content 5、Knowledge 4、Learning 7、Conversation 7、Memory 8、Quiz 8、Recommendation 2 个 HTTP 端点，合计 65 个 HTTP；Voice 另有 1 个 WebSocket。契约总表按 Identity/Auth 与 Students 拆分，因此两行合计仍与 router 计数一致。`GET /health` 与 `GET /api/v1/ping` 是运行探针，不计入业务 API 契约总数。

---

## 5. Identity / Auth

### 5.1 POST `/api/v1/auth/login`

- 用途：学生或管理员登录，获取 JWT。
- 鉴权：公开。
- 幂等：否（每次登录签发新令牌）。
- 请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `username` | string | 是 | 登录名（或邮箱，由服务端判定） |
| `password` | string | 是 | 密码 |

- 响应 `200`：`data: AuthDTO`。
- 错误：`422 VALIDATION_ERROR`、`401 INVALID_CREDENTIALS`、`429 RATE_LIMITED`。

```json
{
  "data": {
    "access_token": "eyJ...",
    "token_type": "Bearer",
    "expires_at": "2026-08-26T12:00:00Z",
    "user": { "user_id": "uuid", "username": "xiaoming", "user_type": "STUDENT" }
  }
}
```

### 5.2 POST `/api/v1/auth/logout`

- 用途：登出（客户端丢弃令牌；MVP 服务端无状态）。
- 鉴权：已登录。
- 幂等：是（重复登出仍返回 204）。
- 响应 `204`；错误：`401 UNAUTHENTICATED`。

### 5.3 GET `/api/v1/me`

- 用途：当前学生档案（STUDENT 返回 StudentProfileDTO；ADMIN 返回 AdminDTO 骨架）。
- 鉴权：已登录。
- 幂等：N/A（GET）。
- 响应 `200` `data: StudentProfileDTO`；错误：`401`、`404 STUDENT_PROFILE_NOT_FOUND`。

### 5.4 PATCH `/api/v1/me`

- 用途：更新当前学生档案。
- 鉴权：STUDENT。
- 幂等：N/A。
- 请求体（部分更新）：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `nickname` / `avatar_url` | string | 否 | 资料 |
| `grade` | int | 否 | 1~12；变更触发异步画像/事件重算 |
| `birth_date` / `language` / `learning_goal` | date/string/string | 否 | 基础资料 |
| `current_teacher_role_id` | uuid | 否 | 必须是 enabled 的 TeacherRole |

- 响应 `200` `data: StudentProfileDTO`。
- 错误：`422 VALIDATION_ERROR`（含 grade 范围）、`404 TEACHER_ROLE_NOT_FOUND`、`403 FORBIDDEN`（角色未启用按 403 或 422，见 §11 歧义）。

### 5.5 GET `/api/v1/teacher-roles`

- 用途：读取当前可用的 AI 教师角色列表，供学生端设置页切换。
- 鉴权：STUDENT。
- 查询：`enabled`（默认 `true`）。
- 响应 `200` `data: TeacherRoleDTO[]`；错误：`401`。

---

## 6. Students

### 6.1 GET `/api/v1/me/preferences`

- 用途：读取当前学生偏好。
- 鉴权：STUDENT。
- 响应 `200` `data: StudentPreferenceDTO`；错误：`401`。

### 6.2 PATCH `/api/v1/me/preferences`

- 用途：更新偏好（用户设置覆盖；`preferred_explanation_style` 等来自设置页，不走 LLM）。
- 鉴权：STUDENT。
- 幂等：N/A。
- 请求体（部分更新）：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `preferred_explanation_style` | enum | 否 | 枚举校验 |
| `preferred_difficulty` | enum | 否 | 枚举校验 |
| `preferred_session_length` | enum | 否 | 枚举校验 |
| `voice_preference` | jsonb | 否 | Schema 校验 |
| `active_questioning_enabled` | bool | 否 | — |
| `daily_learning_minutes` | int | 否 | 非负 |

- 响应 `200` `data: StudentPreferenceDTO`；错误：`422 VALIDATION_ERROR`。

---

## 7. Content

> Phase 3 骨架：全部为只读；发布状态由服务端过滤（仅 PUBLISHED 对学生可见）。

### 7.1 GET `/api/v1/books`

- 用途：书库列表（搜索/学段/主题筛选，分页）。
- 鉴权：STUDENT。
- 查询参数：

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `stage` | enum | PRIMARY/JUNIOR/SENIOR（可选） |
| `topic` | string | 主题标签（可选，多值用逗号） |
| `search` | string | 匹配 title/keywords/description |
| `cursor` / `limit` | string/int | 分页 |

- 响应 `200` `data: BookSummaryDTO[]` + `meta`。
- 错误：`422 VALIDATION_ERROR`（非法 stage/topic）、`401`。

### 7.2 GET `/api/v1/books/{book_id}`

- 用途：书本详情（含派生进度）。
- 鉴权：STUDENT。
- 响应 `200` `data: BookDetailDTO`；错误：`404 BOOK_NOT_FOUND`。

### 7.3 GET `/api/v1/books/{book_id}/chapters`

- 用途：章节列表（含完成标记）。
- 鉴权：STUDENT。
- 响应 `200` `data: ChapterSummaryDTO[]` + `meta`（chapter_order 升序）；错误：`404 BOOK_NOT_FOUND`。

### 7.4 GET `/api/v1/chapters/{chapter_id}`

- 用途：章节详情 + 有序 ContentBlock + 知识点（阅读器数据源）。
- 鉴权：STUDENT。
- 响应 `200` `data: ChapterDetailDTO`；错误：`404 CHAPTER_NOT_FOUND`。

### 7.5 GET `/api/v1/knowledge-points/{knowledge_point_id}`

- 用途：知识点读取。
- 鉴权：STUDENT。
- 响应 `200` `data: KnowledgePointDTO`；错误：`404 KNOWLEDGE_POINT_NOT_FOUND`。

---

## 8. Learning

### 8.1 POST `/api/v1/learning-sessions`

- 用途：开始一次学习时段（进入某书/章）。
- 鉴权：STUDENT。
- 幂等：建议。
- 请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `book_id` | uuid | 是 | 书 |
| `chapter_id` | uuid | 是 | 章（必须属于该书） |
| `entry_route` | string | 否 | 进入来源 |

- 服务端行为：关闭该学生其他 ACTIVE 会话（domain 不变量），创建 ACTIVE 会话。
- 响应 `201` `data: LearningSessionDTO` + `Location`；错误：`404 BOOK_NOT_FOUND/CHAPTER_NOT_FOUND`、`422 VALIDATION_ERROR`、`409 IDEMPOTENCY_KEY_REUSED`。

### 8.2 PATCH `/api/v1/learning-sessions/{session_id}`

- 用途：结束/放弃学习时段。
- 鉴权：STUDENT（仅本人）。
- 请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `status` | enum | 是 | `ENDED / ABANDONED`；仅允许从 ACTIVE 流转 |

- 响应 `200` `data: LearningSessionDTO`（duration_seconds 已结算）；错误：`404 LEARNING_SESSION_NOT_FOUND`、`403 FORBIDDEN`、`409 LEARNING_SESSION_INVALID_STATUS`（已补录 §1.4）。

### 8.3 POST `/api/v1/learning-events`

- 用途：记录一次学习事件（append-only）。
- 鉴权：STUDENT。
- 幂等：建议（客户端重试防重复）。
- 请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `session_id` | uuid | 否 | 所属时段 |
| `event_type` | enum | 是 | domain-model 枚举（见 8.4 兼容表） |
| `occurred_at` | datetime | 是 | 事件发生时间 |
| `book_id` / `chapter_id` / `block_id` | uuid | 按类型 | 定位 |
| `knowledge_point_ids` | jsonb | 否 | 知识点 |
| `conversation_id` / `quiz_session_id` | uuid | 否 | 关联 |
| `payload` | jsonb | 是 | 事件载荷（按类型 Schema） |

- 响应 `201` `data: LearningEventDTO`；错误：`422 VALIDATION_ERROR`、`404 LEARNING_SESSION_NOT_FOUND`、`409 IDEMPOTENCY_KEY_REUSED`。

### 8.4 事件类型兼容表

> domain-model 枚举为权威；总控 §12.5 首版事件名做别名映射，`TEXT_SELECTED` 为待补录项（见 §11 风险）。

| 本契约（= domain-model） | 总控 §12.5 别名 | 说明 |
| --- | --- | --- |
| `BOOK_STARTED` | `BOOK_OPENED` | 打开书 |
| `CHAPTER_STARTED` | `CHAPTER_OPENED` | 进入章 |
| `SECTION_READ` | `CONTENT_VIEWED` | 内容可见 |
| `CHAPTER_FINISHED` | `CHAPTER_COMPLETED` | 完成章 |
| `EXPLAIN_REQUESTED` | `AI_EXPLAIN_REQUESTED` | 请求讲解 |
| `TEXT_SELECTED` | `TEXT_SELECTED` | 选中文字（**需 0-C 补录枚举**，本契约先行支持） |

### 8.5 GET `/api/v1/me/progress`

- 用途：当前学生的全部书本进度列表。
- 鉴权：STUDENT。
- 响应 `200` `data: BookProgressDTO[]`（无记录的书返回空列表，不自动创建行）；错误：`401`。

### 8.6 GET `/api/v1/me/progress/{book_id}`

- 用途：单书进度。
- 鉴权：STUDENT。
- 响应 `200` `data: BookProgressDTO | null`（无行返回 null，不报 404）；错误：`404 BOOK_NOT_FOUND`。

### 8.7 GET `/api/v1/me/learning-events`

- 用途：最近学习事件（首页「最近学习」/审计）。
- 鉴权：STUDENT。
- 查询：`cursor/limit`、`event_type`（可选）。
- 响应 `200` `data: LearningEventDTO[]` + `meta`；错误：`401`。

### 8.8 PUT `/api/v1/me/progress/{book_id}`

- 用途：创建或更新当前学生的单书学习进度。
- 鉴权：STUDENT。
- 请求体：`chapter_id?`、`block_id?`、`status?`（`NOT_STARTED/READING/COMPLETED`）、`position_percent?`（0~100）。
- 响应 `200` `data: BookProgressDTO`；错误：`404 BOOK_NOT_FOUND`、`422 VALIDATION_ERROR`。

---

## 9. Conversations

### 9.1 GET `/api/v1/conversations`

- 用途：会话列表。
- 鉴权：STUDENT。
- 查询：`cursor/limit`、`status`（默认 ACTIVE）、`channel`。
- 响应 `200` `data: ConversationListItemDTO[]` + `meta`；错误：`401`、`422 VALIDATION_ERROR`。

### 9.2 POST `/api/v1/conversations`

- 用途：创建新会话。
- 鉴权：STUDENT。
- 幂等：建议。
- 请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `teacher_role_id` | uuid | 否 | 缺省用学生当前角色 |
| `channel` | enum | 否 | TEXT（默认）/ VOICE |
| `title` | string | 否 | 可空 |

- 响应 `201` `data: ConversationDTO`；错误：`404 TEACHER_ROLE_NOT_FOUND`、`409 IDEMPOTENCY_KEY_REUSED`。

### 9.3 GET `/api/v1/conversations/{conversation_id}`

- 用途：会话详情（含 current_page_context、recent_messages、summary）。
- 鉴权：STUDENT（仅本人）。
- 响应 `200` `data: ConversationDTO`；错误：`404 CONVERSATION_NOT_FOUND`、`403 FORBIDDEN`。

### 9.4 PATCH `/api/v1/conversations/{conversation_id}`

- 用途：更新标题 / 归档 / 软删。
- 鉴权：STUDENT（仅本人）。
- 请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `title` | string | 否 | 新标题 |
| `status` | enum | 否 | `ARCHIVED / DELETED`；DELETED 为软删，隐私级联策略见 §11 风险 |

- 响应 `200` `data: ConversationDTO`；错误：`404`、`403`、`409 CONVERSATION_INVALID_STATUS`（非法流转，如 DELETED→ACTIVE）。

### 9.5 GET `/api/v1/conversations/{conversation_id}/messages`

- 用途：分页读取消息历史（断线重连后补全）。
- 鉴权：STUDENT（仅本人）。
- 查询：`cursor/limit`（sequence 升序或降序由 sort 决定，默认升序）。
- 响应 `200` `data: MessageDTO[]` + `meta`；错误：`404 CONVERSATION_NOT_FOUND`、`403 FORBIDDEN`。

### 9.6 POST `/api/v1/conversations/{conversation_id}/messages`

- 用途：发送学生消息并触发 Teacher Agent，**返回 SSE 流**（契约见 §15）。
- 鉴权：STUDENT（仅本人）。
- 幂等：**必须**（Idempotency-Key 防重复 Agent Run）。
- 请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `content` | text | 是 | 学生消息正文 |
| `type` | enum | 否 | 学生侧仅允许 `TEXT`（缺省 TEXT） |
| `screen_context` | jsonb | 否 | 架构 §8 ScreenContext：`{ route, page_type, book_id?, chapter_id?, chapter_title?, content_block_id?, visible_section?, selected_text?, knowledge_points?, actions? }`；服务端校验并更新 Conversation.current_page_context |
| `selected_text` | string | 否 | 兼容字段：并入 screen_context.selected_text（二选一，见 §11） |

- 响应：`200`（`Content-Type: text/event-stream`），事件见 §15；`202` 不适用（流式首包即 `message.start`）。
- 错误（非流式错误用信封；流内错误用 `error` 事件）：`404 CONVERSATION_NOT_FOUND`、`403 FORBIDDEN`、`422 VALIDATION_ERROR / SCREEN_CONTEXT_INVALID`、`409 CONVERSATION_INVALID_STATUS`（DELETED）、`409 IDEMPOTENCY_KEY_REUSED`、`500 AI_PROVIDER_ERROR`。

### 9.7 GET `/api/v1/conversations/{conversation_id}/summary`

- 用途：读取会话摘要（长会话）。
- 鉴权：STUDENT（仅本人）。
- 响应 `200` `data: ConversationSummaryDTO | null`；错误：`404 CONVERSATION_NOT_FOUND`。

---

## 10. Assessment

> 硬约束：历史详情只读快照，**绝不触发 LLM**（D5）；答案提交幂等（总控 §15.7）。

### 10.1 POST `/api/v1/quiz-sessions`

- 用途：请求生成正式测验（走 Quiz Skill）。
- 鉴权：STUDENT。
- 幂等：建议。
- 请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `conversation_id` | uuid | 是 | 发起对话 |
| `book_id` / `chapter_id` | uuid | 否 | 内容定位 |
| `quiz_kind` | enum | 否 | CHAPTER_QUIZ / AI_QUIZ |
| `question_count` | int | 否 | 1~10，默认 3 |
| `difficulty` | enum | 否 | EASY/MEDIUM/HARD，缺省用偏好 |

- 响应 `202 Accepted`：`data: { quiz_session_id, status: "GENERATING" }` + `Location: /api/v1/quiz-sessions/{id}`；生成完成由前端轮询 10.3 或等待会话 SSE `tool.result`。
- 错误：`404 CONVERSATION_NOT_FOUND`、`422 QUIZ_INVALID_OUTPUT`（Skill 输出校验失败）、`500 AI_PROVIDER_ERROR`、`409 IDEMPOTENCY_KEY_REUSED`。

### 10.2 GET `/api/v1/quiz-sessions`

- 用途：测验历史列表（筛选/分页）。
- 鉴权：STUDENT。
- 查询：`cursor/limit`、`quiz_kind`、`status`、`book_id`、`date_from/date_to`（「更早」等前端筛选由参数组合实现）。
- 响应 `200` `data: QuizSessionListItemDTO[]` + `meta`；错误：`401`、`422 VALIDATION_ERROR`。

### 10.3 GET `/api/v1/quiz-sessions/{quiz_session_id}`

- 用途：测验详情（**只读快照**；含 questions_snapshot、result_summary、ai_feedback、skill_version）。
- 鉴权：STUDENT（仅本人）。
- 响应 `200` `data: QuizSessionDetailDTO`；错误：`404 QUIZ_NOT_FOUND`、`403 FORBIDDEN`。
- 明确：本端点及其子资源端点**不调用任何 LLM**；生成中（GENERATING）可返回 200 + status=GENERATING 供轮询。

### 10.4 GET `/api/v1/quiz-sessions/{quiz_session_id}/questions`

- 用途：题目列表（答题时与历史回顾共用；correct_answer/explanation 按 §3.6 条件可见）。
- 鉴权：STUDENT（仅本人）。
- 响应 `200` `data: QuizQuestionDTO[]`（question_order 升序）；错误：`404 QUIZ_NOT_FOUND`、`403 FORBIDDEN`。

### 10.5 POST `/api/v1/quiz-sessions/{quiz_session_id}/questions/{question_id}/answers`

- 用途：提交答案（服务端判定正确性）。
- 鉴权：STUDENT（仅本人）。
- 幂等：**必须**（Idempotency-Key）。
- 请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `answer` | jsonb | 是 | 学生提交内容（单选题 `{"key":"B"}`） |
| `hint_level_at_submit` | int | 否 | 客户端上报当前提示级数，服务端以 Interaction 记录为准校正 |

- 服务端行为：校验测验 ACTIVE、题目存在；按 (session, question, attempt_no) 判重；生成 QuizAnswer + ANSWER_SUBMIT/ANSWER_RESULT Interaction；写 LearningEvent（ANSWER_CORRECT/ANSWER_WRONG）且按 attempt 幂等。
- 响应 `201` `data: QuizAnswerDTO`；重放 `200` + `Idempotency-Replayed: true`。
- 错误：`404 QUIZ_NOT_FOUND/QUESTION_NOT_FOUND`、`403 FORBIDDEN`、`409 QUIZ_NOT_ACTIVE`、`409 QUIZ_ALREADY_ANSWERED`（同 attempt 重复且无幂等键）、`409 QUIZ_FINALIZED`、`409 IDEMPOTENCY_KEY_REUSED`、`422 VALIDATION_ERROR`。

```json
{
  "data": {
    "answer_id": "uuid",
    "question_id": "uuid",
    "submitted_answer": { "key": "B" },
    "is_correct": true,
    "attempt_no": 1,
    "hint_level_at_submit": 0,
    "is_final": true,
    "submitted_at": "2026-08-19T12:00:00Z"
  }
}
```

### 10.6 POST `/api/v1/quiz-sessions/{quiz_session_id}/questions/{question_id}/hints`

- 用途：请求下一级提示（Hint Skill 联动）。
- 鉴权：STUDENT（仅本人）。
- 幂等：**必须**（同一 hint level 重放不重复生成）。
- 请求体：无（空 body）。
- 服务端行为：校验当前题未完成且 hint_level < max；生成 HINT_REQUEST + HINT_RESPONSE Interaction；向 Conversation 写入 type=HINT 消息。
- 响应 `201` `data: { hint_level, hint_text, max_hint_level, interaction_id }`；错误：`404`、`403`、`409 QUIZ_NOT_ACTIVE`、`409 QUIZ_HINT_LIMIT_REACHED`、`409 QUIZ_FINALIZED`、`409 IDEMPOTENCY_KEY_REUSED`。

### 10.7 GET `/api/v1/quiz-sessions/{quiz_session_id}/answers`

- 用途：答卷答案列表（历史详情页）。
- 鉴权：STUDENT（仅本人）。
- 响应 `200` `data: QuizAnswerDTO[]`；错误：`404 QUIZ_NOT_FOUND`、`403 FORBIDDEN`。

### 10.8 GET `/api/v1/quiz-sessions/{quiz_session_id}/interactions`

- 用途：互动审计日志（当时提示/追问/回答/结果，不可变）。
- 鉴权：STUDENT（仅本人）。
- 响应 `200` `data: QuizInteractionDTO[]`（sequence 升序）；错误：`404 QUIZ_NOT_FOUND`、`403 FORBIDDEN`。

---

## 11. Memory

### 11.1 GET `/api/v1/me/memories`

- 用途：记忆管理页（用户可查看 AI 记住了什么）。
- 鉴权：STUDENT。
- 查询：`status`（默认 ACTIVE；REMOVED 供管理页展示）、`memory_type`。
- 响应 `200` `data: StudentMemoryDTO[]`；错误：`401`。

### 11.2 PATCH `/api/v1/me/memories/{memory_id}`

- 用途：记忆状态机（正确/不完全正确/修改/忘记）。
- 鉴权：STUDENT（仅本人）。
- 请求体：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `action` | enum | 是 | `CONFIRM / DISPUTE / FORGET / EDIT` |
| `content` | text | EDIT 时必填 | 修改后的记忆内容 |

- 状态机：
  - `CONFIRM`：ACTIVE/DISPUTED → ACTIVE + user_confirmed=true
  - `DISPUTE`：ACTIVE → DISPUTED
  - `FORGET`：任意 → REMOVED（软删，保留审计）
  - `EDIT`：任意非 REMOVED → 新版本（旧版 SUPERSEDED）+ user_confirmed=true
- 响应 `200` `data: StudentMemoryDTO`；错误：`404 MEMORY_NOT_FOUND`、`403 FORBIDDEN`、`409 MEMORY_INVALID_TRANSITION`。

### 11.3 GET `/api/v1/me/insights`

- 用途：AI 学习画像列表（含 ACTIVE 与 SUPERSEDED 历史，对应原型 changelog）。
- 鉴权：STUDENT。
- 查询：`status`、`insight_type`、`cursor/limit`。
- 响应 `200` `data: ProfileInsightDTO[]` + `meta`；错误：`401`。

### 11.4 GET `/api/v1/me/insights/{insight_id}`

- 用途：画像条目详情（「为什么这样判断」入口，含 evidence 摘要）。
- 鉴权：STUDENT。
- 响应 `200` `data: ProfileInsightDTO` + `meta.evidence: MemoryEvidenceDTO[]`（由 evidence_ids 展开）；错误：`404 INSIGHT_NOT_FOUND`、`403 FORBIDDEN`。

### 11.5 GET `/api/v1/me/evidence/{evidence_id}`

- 用途：证据详情（引证真实学习记录）。
- 鉴权：STUDENT（仅本人）。
- 响应 `200` `data: MemoryEvidenceDTO`；错误：`404 EVIDENCE_NOT_FOUND`、`403 FORBIDDEN`。

### 11.6 GET `/api/v1/me/episodes`

- 用途：情节记忆列表。
- 鉴权：STUDENT。
- 查询：`cursor/limit`、`importance`。
- 响应 `200` `data: StudentEpisodeDTO[]` + `meta`；错误：`401`。

### 11.7 GET `/api/v1/me/episodes/{episode_id}`

- 用途：情节详情。
- 鉴权：STUDENT（仅本人）。
- 响应 `200` `data: StudentEpisodeDTO`；错误：`404 EPISODE_NOT_FOUND`、`403 FORBIDDEN`。

### 11.8 GET `/api/v1/me/agent.md`

- 用途：读取当前学生的可供 Agent 使用的 Markdown 画像摘要。
- 鉴权：STUDENT。
- 响应 `200` `text/markdown`；错误：`401`。

> MemoryCandidate 是 Pipeline 内部产物，无学生端点；管理端调试端点属 Admin 骨架（§14），不在本轮展开。

---

## 12. Knowledge（Phase 8 骨架，只定契约不展开细节）

### 12.1 GET `/api/v1/knowledge/resources`

- 用途：资源列表（管理端查看处理状态）。
- 鉴权：ADMIN。
- 查询：`status`（UPLOADED/PARSING/CHUNKING/INDEXING/READY/FAILED）、`cursor/limit`。
- 响应 `200` `data: KnowledgeResourceDTO[]` + `meta`；错误：`403 ADMIN_ONLY`、`401`。

### 12.2 GET `/api/v1/knowledge/resources/{resource_id}`

- 用途：资源详情。
- 鉴权：ADMIN。
- 响应 `200` `data: KnowledgeResourceDTO`；错误：`404 RESOURCE_NOT_FOUND`、`403 ADMIN_ONLY`。

### 12.3 GET `/api/v1/knowledge/resources/{resource_id}/chunks`

- 用途：资源切块列表（仅 READY）。
- 鉴权：ADMIN。
- 响应 `200` `data: KnowledgeChunkDTO[]`；错误：`404 RESOURCE_NOT_FOUND`、`403 ADMIN_ONLY`。

### 12.4 POST `/api/v1/knowledge/search`

- 用途：知识检索（Teacher Agent/内部 Skill 使用；Phase 8 实现）。
- 鉴权：STUDENT（经 Agent 调用）或内部服务凭证（后续定稿）。
- 请求体：`{ query, knowledge_point_ids?, limit? }`。
- 响应 `200` `data: KnowledgeChunkDTO[]`（含 metadata.source_url/license，满足 D9）；错误：`422 VALIDATION_ERROR`、`500 AI_PROVIDER_ERROR`（embedding 失败）。

---

## 13. Personalization

### 13.1 GET `/api/v1/me/recommendations`

- 用途：惰性生成并读取当前学生的 ACTIVE 推荐列表（首页「霜铃的下一步建议」「为你精选」）。
- 鉴权：STUDENT。
- 响应 `200` `data: RecommendationDTO[]`；无推荐时返回空数组；错误：`401`。

### 13.2 POST `/api/v1/me/recommendations/{recommendation_id}/dismiss`

- 用途：忽略推荐（ACTIVE→DISMISSED）。
- 鉴权：STUDENT（仅本人）。
- 响应 `200` `data: RecommendationDTO`；错误：`404 RECOMMENDATION_NOT_FOUND`、`403 FORBIDDEN`、`409 RECOMMENDATION_INVALID_STATUS`。

> 当前实现未提供推荐详情 GET 或独立 refresh 端点；GET 列表会基于学习数据惰性重算并写入推荐实体。

---

## 14. Admin（Phase 10 骨架，全部 Admin-only）

> 本节仅定骨架与字段范围，不做完整 CRUD 细节展开；实现细节 Phase 10 定稿。全部端点要求 `user_type=ADMIN`，否则 `403 ADMIN_ONLY`。

### 14.1 GET `/api/v1/admin/stats`

- 用途：管理首页统计（书本/章节/知识点/资源数量与处理状态）。
- 响应 `200` `data: AdminStatsDTO`。

### 14.2 Books

| 端点 | 用途 | 幂等 |
| --- | --- | --- |
| `GET /api/v1/admin/books` | 全部状态的书列表（含 DRAFT/ARCHIVED） | N/A |
| `POST /api/v1/admin/books` | 创建书（Book 字段；source_ids/license/copyright_status） | 建议 |
| `GET /api/v1/admin/books/{book_id}` | 书管理详情 | N/A |
| `PATCH /api/v1/admin/books/{book_id}` | 更新书（含 status DRAFT/PUBLISHED/ARCHIVED 发布/下架） | N/A |

### 14.3 Chapters / ContentBlocks / KnowledgePoints

| 端点 | 用途 | 幂等 |
| --- | --- | --- |
| `POST /api/v1/admin/books/{book_id}/chapters` | 创建章（chapter_order 由服务端排定） | 建议 |
| `PATCH /api/v1/admin/chapters/{chapter_id}` | 更新章 | N/A |
| `POST /api/v1/admin/chapters/{chapter_id}/content-blocks` | 追加 ContentBlock（block_type/content/block_order/section_key/knowledge_point_ids） | 建议 |
| `PATCH /api/v1/admin/content-blocks/{block_id}` | 更新内容块 | N/A |
| `POST /api/v1/admin/knowledge-points` | 创建知识点 | 建议 |
| `PATCH /api/v1/admin/knowledge-points/{knowledge_point_id}` | 更新知识点 | N/A |

### 14.4 Knowledge Resources

| 端点 | 用途 | 幂等 |
| --- | --- | --- |
| `POST /api/v1/admin/knowledge/resources` | 上传（multipart：文件 + source_name/source_url/author/license/copyright_status）；创建 KnowledgeResource + Worker Job | 建议 |
| `PATCH /api/v1/admin/knowledge/resources/{resource_id}` | 更新元数据（license/status 等） | N/A |
| `POST /api/v1/admin/knowledge/resources/{resource_id}/reprocess` | 触发重处理 | 建议 |

> 资源列表、详情与 chunks 读取实际注册在 Knowledge router（§12），路径为 `/api/v1/knowledge/resources...`；本 Admin router 仅提供上传、元数据更新和重处理 3 个端点。

### 14.5 TeacherRoles（Phase 11 骨架）

| 端点 | 用途 | 幂等 |
| --- | --- | --- |
| `GET /api/v1/admin/teacher-roles` | 角色列表（含 enabled=false） | N/A |
| `POST /api/v1/admin/teacher-roles` | 创建角色（persona/sprite_manifest/grade_rules 等 Schema 校验） | 建议 |
| `PATCH /api/v1/admin/teacher-roles/{role_id}` | 更新角色 / 启停 | N/A |

> 学生端角色切换：`PATCH /me.current_teacher_role_id`（§5.4）；角色列表（仅 enabled）供设置页：`GET /api/v1/teacher-roles?enabled=true`（归属 Identity 模块，详见 §5.5）。

---

## 15. SSE 契约（Conversation 流式）

### 15.1 传输方式

- 端点：`POST /api/v1/conversations/{conversation_id}/messages`（§9.6）。
- 响应：`Content-Type: text/event-stream`，UTF-8。
- **客户端实现要求**：原生 `EventSource` 不支持 POST 与自定义头，因此客户端必须用 `fetch` + `ReadableStream` 解析 SSE 帧；`Authorization` 走请求头。
- 帧格式（标准 SSE）：

```text
id: <message_id>
event: <event_type>
data: <json>

```

- 心跳：服务端每 15s 发送注释行 `: ping`，避免代理超时。

### 15.2 事件清单（严格 7 种，总控 §13.5）

| 事件 | 方向 | 语义 |
| --- | --- | --- |
| `message.start` | server→client | 教师消息开始（含 message_id，可提前占位） |
| `text.delta` | server→client | 文本增量 |
| `tool.start` | server→client | 工具/Skill 开始（如 Quiz Skill） |
| `tool.result` | server→client | 工具/Skill 完成或失败 |
| `text.done` | server→client | 文本输出完成（含全文与 model_info） |
| `message.done` | server→client | 消息持久化完成（最终 message_id/sequence） |
| `error` | server→client | 流内错误（非 fatal 可继续，fatal 终止） |

### 15.3 事件 payload

**message.start**

```json
{
  "message_id": "uuid",
  "conversation_id": "uuid",
  "role": "TEACHER",
  "type": "TEXT",
  "sequence": 12,
  "created_at": "2026-08-19T12:00:00Z",
  "request_id": "uuid"
}
```

**text.delta**

```json
{
  "message_id": "uuid",
  "delta": "训练数据不是",
  "index": 3,
  "sequence": 12
}
```

**tool.start**

```json
{
  "tool_run_id": "uuid",
  "tool": "quiz",
  "state": "running",
  "message_id": "uuid",
  "payload": { "quiz_session_id": null }
}
```

`tool` 枚举：`quiz / hint / knowledge / memory / recommendation / learning`。

**tool.result**

```json
{
  "tool_run_id": "uuid",
  "tool": "quiz",
  "status": "success",
  "payload": { "quiz_session_id": "uuid", "skill_version": "quiz-v1" }
}
```

`status`：`success / error`；失败时 payload 含 `{ code, message }`，前端可渲染 TOOL_STATUS 错误。

**text.done**

```json
{
  "message_id": "uuid",
  "content": "训练数据不是机器背下来的答案……",
  "model_info": { "provider": "mock", "model": "mock-model" },
  "usage": { "input_tokens": 120, "output_tokens": 80 }
}
```

**message.done**

```json
{
  "message_id": "uuid",
  "conversation_id": "uuid",
  "sequence": 12,
  "created_at": "2026-08-19T12:00:10Z",
  "metadata": {}
}
```

**error**

```json
{
  "request_id": "uuid",
  "code": "AI_PROVIDER_ERROR",
  "message": "provider unavailable",
  "details": {},
  "fatal": true
}
```

### 15.4 客户端消费与断线重连

- 客户端按 `message_id` 聚合：`text.delta` 追加到当前 message 缓冲；`tool.start/result` 渲染 TOOL_STATUS 消息（不打断文本缓冲）；`message.done` 后消息正式可见（此时 GET messages 可读到）。
- 每个事件的 `id` 字段 = `message_id`（非逐 delta），用于 `Last-Event-ID` 续传。
- 断线重连语义（MVP）：
  1. 客户端断开后先 `GET /conversations/{id}/messages` 拉取已持久化消息（含 message.done 之前的文本则无）；
  2. 若原请求仍在服务端执行（未 message.done），用**相同 Idempotency-Key** 重发 `POST messages`；服务端命中运行中状态返回 `error { code: "STREAM_NOT_RESUMABLE" }` 或重放已缓冲流（MVP 不保证 delta 级续传，仅保证不产生重复用户消息与重复 Agent Run）；
  3. 若原请求已结束，重发同 key 直接重放持久化结果（`message.done` 重放 + `Idempotency-Replayed: true`）。
- 服务端保证：Idempotency-Key 在 24h 内记录 Agent Run 状态（running/done），杜绝双跑；`error(fatal=true)` 后客户端不得自动重发同一 key，需用户显式重试（对应原型 error 消息「重试/稍后再问」）。

---

## 16. WebSocket 契约（Voice，Phase 9 骨架）

> **Phase 9 才实现，此处仅定契约骨架**；细节（音频编码、采样率、barge-in 策略、ticket 鉴权）Phase 9 定稿。

### 16.1 连接

- 路径：`/api/v1/voice/ws?conversation_id={id}&token={jwt}`（WS 无法带自定义头；MVP 用 token 查询参数，生产建议一次性 ticket）。
- 协议：JSON 文本帧；音频数据 base64 内嵌。

### 16.2 消息类型

client→server：

| type | 说明 |
| --- | --- |
| `audio_chunk` | `{ type, data(base64), sample_rate? }` |
| `audio_end` | 本段语音结束（触发 ASR finalize） |
| `cancel` | 取消当前轮 |
| `ping` | 保活 |

server→client：

| type | 说明 |
| --- | --- |
| `state` | `{ type:"state", state }` |
| `partial` | `{ type:"partial", text, transcript_id }` ASR 中间结果 |
| `final` | `{ type:"final", text, message_id?, conversation_id }` final 作为普通 Conversation Message（总控 §18.1） |
| `error` | `{ type:"error", code, message }` |
| `pong` | 保活响应 |

### 16.3 状态机（总控 §18.3）

```text
IDLE ──connect/audio──▶ LISTENING
LISTENING ──final──▶ THINKING
THINKING ──TTS ready──▶ SPEAKING
SPEAKING ──barge-in/audio──▶ LISTENING
SPEAKING ──done──▶ IDLE
任意 ──fatal──▶ ERROR ──reset──▶ IDLE
```

- `state` 事件在每次迁移时下发；前端角色动画与语音 UI 跟随（对应 0-B voice-overlay 与 sprite 状态）。
- `final` 文本由服务端写入 Conversation（type=TEXT）并进入同一 SSE/Agent 流程；语音与文本共享 Conversation/TeacherContext/Memory/Quiz（架构 §38）。

---

## 17. 硬约束落实清单

| 约束 | 落实位置 |
| --- | --- |
| Quiz 提交幂等（总控 §15.7） | §1.7 + §10.5：Idempotency-Key 必填；同 (session, question, attempt_no) 判重；重放返回原结果；同 key 异 body → 409 |
| 历史测验只读快照、不触发 LLM（D5） | §10.3/§10.4/§10.7/§10.8 全部为纯读端点；返回 questions_snapshot/skill_version；文档明令禁止任何 LLM 调用 |
| Screen Context 作为消息请求字段 | §9.6 body.screen_context，结构 = 架构 §8 + §14.2（含 content_block_id）；服务端校验后更新 Conversation.current_page_context |
| DTO 不发明字段 | §2 + §3：所有字段映射 domain-model 实体，派生字段显式标注 (derived) |
| LLM 不直接写库（D10） | §1.2/§2.5/§10/§13：所有 AI 触发端点返回结构化 DTO；Side Effect 走 Skill→Pydantic→Validator→Domain Service→Transaction |
| Message 类型固定 7 值 | §3.5 MessageDTO.type + §15 tool 枚举分离（工具状态走 TOOL_STATUS，不污染 Message 类型） |
| Conversation 一等 Domain + 双记忆分离 | §9 端点；ConversationDTO 只承载会话上下文，长期记忆走 §11 模块 |
| 画像定性档位 | §3.7 ProfileInsightDTO.level 仅 5 档；无任何百分比字段 |

---

## 18. 本轮不设计细节（占位/骨架）

1. **Voice WebSocket**：§16 只给连接路径、消息类型与状态机；音频格式、ASR/TTS Provider 参数、barge-in 细节 Phase 9 定稿。
2. **Knowledge 检索**：§12.4 只给请求/响应形状；RAG 相关性、embedding 维度、检索策略 Phase 8 定稿。
3. **Admin 完整 CRUD**：§14 只给端点与字段范围；校验规则、批量操作、权限细分 Phase 10 定稿。
4. **多 TeacherRole 管理**：§14.5 只给列表/创建/更新骨架；Persona 预览、sprite 上传校验、版本 diff Phase 11 定稿。
5. **Auth refresh/黑名单**：MVP 无 refresh token 与服务端登出黑名单；如需再补。
6. **ConversationSummary 手动重算 / Message 编辑**：不在本轮（Summary 由 Worker 自动；消息只追加）。
7. **MemoryCandidate 管理端点**：Pipeline 内部对象，本轮无端点。

---

## 19. 歧义裁决记录（已全部裁决）

1. **认证选型**（已裁决）：采用 JWT Bearer（§1.2 定稿）；如后续改为 cookie session，需同步改 SSE/WS 鉴权方式。
2. **Quiz 重新作答语义**（已裁决）：同 attempt 幂等重放不重复；答错后再提交 = 新 attempt（新 QuizAnswer 行，证据按 attempt 幂等），维持 §10.5 与 QuizAnswer.attempt_no 用法。
3. **学习事件枚举缺口**（已裁决）：`TEXT_SELECTED` 已由 0-C 补录，与本契约一致；`BOOK_OPENED/CHAPTER_OPENED/CHAPTER_COMPLETED/AI_EXPLAIN_REQUESTED` 以 domain-model 命名为准做别名映射。
4. **409 专用错误码**（已裁决）：`LEARNING_SESSION_INVALID_STATUS`、`RECOMMENDATION_INVALID_STATUS` 已补录进 §1.4 错误码表，正文端点直接使用。
5. **PATCH /me.current_teacher_role_id 与 GET /teacher-roles**（已裁决）：`GET /api/v1/teacher-roles`（仅 enabled）归 Identity 模块，Phase 11 实现。
6. **隐私删除级联**（已裁决）：审计链数据一律 RESTRICT，不物理级联；隐私删除走独立脱敏流程（0-E 已落实），PATCH conversations status=DELETED 与 memory FORGET 只做软删。
7. **SSE 续传能力**（已裁决）：Phase 4 落地 Redis 流缓冲（30s），MVP 仍不保证 delta 级续传；本契约已预留 `STREAM_NOT_RESUMABLE`。
