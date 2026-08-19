# 霜铃 · K12 AI 数字教师 V3 — Database Design（逻辑 Schema）

> 状态：Phase 0 契约基线（Task 0-E）
> 版本：v0.1
> 日期：2026-08-19
> 输入基线：domain-model.md（0-C，27 实体 + 关系/约束，**建表权威输入**）、api-contract.md（0-D，DTO/枚举/幂等约定）、project-architecture.md（PostgreSQL 18 + pgvector + Redis 分层）、执行总控 §9.2 Task 0-E
> 性质：**逻辑设计蓝图，不创建 Migration**；Phase 2 起 Alembic Migration 必须以此文件为唯一来源。本文不写 SQL、不建表、不写任何可执行代码。

---

## 1. 存储分层

### 1.1 PostgreSQL —— 唯一事实源（Source of Truth）

- 以下数据**只允许**持久化在 PostgreSQL（架构 §3.2）：
  - 全部 27 个业务实体（users → admins）；
  - 幂等映射表 `idempotency_keys`（0-D §1.7）；
  - 未来若引入 `background_jobs` 持久化状态，也归 PG（0-C §8 已排除出业务实体，本设计暂不建表，仅注明）。
- Redis 丢失不影响事实：Redis 里的一切都可以从 PG 重建或容忍丢失。
- 扩展：PostgreSQL 18 内置 `gen_random_uuid()`（无需 pgcrypto）；`vector` 扩展（pgvector）用于两个 embedding 列，**Phase 8 才启用**，维度由 Embedding Provider 决定（§1.4）。

### 1.2 Redis —— 临时/加速层（不建正式表）

| Key 模式 | 用途 | 生命周期 |
| --- | --- | --- |
| `cache:{resource}:{id}` | TanStack Query / API 响应缓存 | TTL 秒级~分钟级，可丢 |
| `rate_limit:{actor}:{action}` | 登录、LLM 调用限流 | 秒级窗口 |
| `lock:{job_type}:{entity_id}` | Memory Pipeline、Quiz Skill、推荐重算的分布式锁 | 任务期间 |
| `queue:jobs` / `queue:jobs:retry` | Worker Job Queue（PDF 解析、embedding、记忆合并、摘要） | 任务期间 |
| `stream:sse:{conversation_id}` | SSE 断线续传缓冲（0-D §15.4，Phase 4 启用 Redis 流缓冲；MVP 可不启用） | 会话活跃期 |
| `ws:{conversation_id}` | Voice WebSocket 连接元数据（Phase 9） | 连接生命周期 |
| `pubsub:*` | Worker/进程间通知 | 事件瞬态 |

规则：Redis 中**禁止**出现唯一保存的 Conversation / Quiz / Memory / Profile / LearningEvent（架构 §33）。

### 1.3 Object Storage —— 二进制资产（S3 兼容，MinIO/OSS 可替换）

| 前缀 | 内容 | 关联表 |
| --- | --- | --- |
| `covers/` | 书本封面 | `books.cover_url` |
| `avatars/` | 用户/角色头像 | `users`、`teacher_roles.avatar` |
| `knowledge/` | 上传的 PDF/Markdown/TXT/HTML 原始文件 | `knowledge_resources.storage_key` |
| `audio/` | TTS 音频缓存/语音记录（Phase 9） | `messages.metadata`（暂不建列） |
| `sprites/` | 桌虫 spritesheet 资产 | `teacher_roles.sprite_manifest` |

业务 Domain 不直接调用 MinIO SDK，统一走 ObjectStorage Adapter（架构 §34）；URL 用 presign 或公开 CDN 地址，不落库真实对象。

### 1.4 pgvector

- `student_episodes.embedding`、`knowledge_chunks.embedding` 两列使用 `vector` 类型。
- **维度不在本阶段定**：取决于 Embedding Provider（如 Qwen Embedding），Phase 8 启用 `CREATE EXTENSION vector` 时按 provider 参数确定维度。
- 索引策略：Phase 8 落地时使用 **HNSW（cosine）** 或 ivfflat 之一（按数据量测试决定）；本设计只标注「Phase 8」。
- 普通关系数据仍存 PG 普通列，向量只做检索增强（架构 §28）。

---

## 2. 命名与类型约定

| 项 | 约定 |
| --- | --- |
| 表名 | snake_case 复数：`student_profiles`、`quiz_sessions` |
| 列名 | snake_case；主键统一 `{table_singular}_id`（如 `student_id`） |
| 主键 | `uuid`，`DEFAULT gen_random_uuid()`，禁止客户端/LLM 生成 |
| 时间 | `timestamptz`（UTC 存储）；`created_at/updated_at` 由应用维护 |
| 枚举 | **`varchar(n)` + `CHECK`**（不用 PostgreSQL enum） |
| jsonb | 必须配套 Pydantic Schema（引用 0-C 对应实体字段），表设计中逐列注明 |
| 软删 | 用户数据表用 `status` 枚举软删；物理删除仅限 TTL 清理 |

**为什么枚举用 varchar + CHECK 而不是 PG enum**：

1. PG enum 的 `ALTER TYPE ... ADD VALUE` 在事务/旧版本上有坑，演进成本高；
2. CHECK 约束可通过普通 Migration 增删，与 Alembic 工作流一致；
3. 应用层已有 Pydantic 枚举校验（D10），DB CHECK 是第二道防线，不需要数据库级强类型；
4. 与 0-D 的字符串枚举 DTO 一致，避免类型转换噪音。

**软删策略**：

- 软删表：`users`（DISABLED）、`conversations`（DELETED）、`student_memories`（REMOVED）、`books/chapters/knowledge_points`（ARCHIVED）、`recommendations`（DISMISSED/EXPIRED）、`profile_insights`（SUPERSEDED）、`teacher_roles`（enabled=false）等——全部通过 status/布尔列，**不物理 DELETE**。
- 物理删除：仅 `idempotency_keys` 过期行由 Worker TTL 清理；无业务表物理删除。
- 隐私级联删除已裁定：审计链数据一律 `RESTRICT`，隐私删除走独立脱敏流程（见 §9）；涉及 LearningEvent/QuizSession/Messages 的外键一律 `RESTRICT`。

---

## 3. 表设计（27 实体 + 幂等映射表）

> 通用备注：所有 `jsonb` 数组引用（`*_ids`）不是物理外键，语义见 §6.2；所有 `updated_at` 由应用写入；`CHECK` 枚举取值与 domain-model 完全一致。

### 3.1 `users`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `user_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `username` | varchar(64) | 否 | — | 登录名 |
| `email` | varchar(255) | 是 | NULL | 邮箱 |
| `phone` | varchar(32) | 是 | NULL | 手机号 |
| `password_hash` | varchar(255) | 否 | — | 只存哈希 |
| `user_type` | varchar(16) | 否 | — | STUDENT / ADMIN |
| `status` | varchar(16) | 否 | 'ACTIVE' | ACTIVE / DISABLED |
| `last_login_at` | timestamptz | 是 | NULL | 最近登录 |
| `created_at` | timestamptz | 否 | now() | — |
| `updated_at` | timestamptz | 否 | now() | — |

- PK：`user_id`。
- UNIQUE：`username`；`email`（部分唯一，`WHERE email IS NOT NULL`）；`phone`（部分唯一）。
- CHECK：`user_type IN ('STUDENT','ADMIN')`；`status IN ('ACTIVE','DISABLED')`。
- 索引：唯一约束自带；`status` 低基数不加索引。
- 软删：`status=DISABLED`（账号停用，不物理删）。

### 3.2 `student_profiles`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `student_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `user_id` | uuid | 否 | — | 登录账号（1:1） |
| `nickname` | varchar(32) | 否 | — | 昵称 |
| `avatar_url` | varchar(512) | 是 | NULL | 头像 |
| `grade` | integer | 否 | — | **CHECK 1<=grade<=12**；展示字符串不入库（D1） |
| `birth_date` | date | 是 | NULL | 出生日期（年龄派生） |
| `language` | varchar(16) | 否 | 'zh-CN' | 使用语言 |
| `learning_goal` | text | 是 | NULL | 学习目标 |
| `current_teacher_role_id` | uuid | 是 | NULL | 当前教师角色 |
| `learning_days` | integer | 否 | 0 | 统计摘要缓存，CHECK >=0 |
| `total_learning_minutes` | integer | 否 | 0 | 统计摘要缓存，CHECK >=0 |
| `completed_books` | integer | 否 | 0 | 统计摘要缓存，CHECK >=0 |
| `completed_chapters` | integer | 否 | 0 | 统计摘要缓存，CHECK >=0 |
| `quiz_count` | integer | 否 | 0 | 统计摘要缓存，CHECK >=0 |
| `created_at` | timestamptz | 否 | now() | — |
| `updated_at` | timestamptz | 否 | now() | — |

- PK：`student_id`。
- UNIQUE：`user_id`。
- FK：`user_id → users(user_id) ON DELETE CASCADE`（账号实体删除时档案随之删除；物理删除仅限隐私清除流程）；`current_teacher_role_id → teacher_roles(role_id) ON DELETE SET NULL`（角色下架不影响学生）。
- CHECK：`grade BETWEEN 1 AND 12`；各统计列 `>= 0`。
- 索引：`current_teacher_role_id`（FK）；`(grade)` 供书库筛选可加（MVP 可选）。

### 3.3 `student_preferences`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `preference_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `student_id` | uuid | 否 | — | 学生（1:1） |
| `preferred_explanation_style` | varchar(32) | 否 | — | 7 值枚举 |
| `preferred_difficulty` | varchar(16) | 否 | — | EASY/MEDIUM/HARD |
| `preferred_session_length` | varchar(16) | 否 | — | SHORT/MEDIUM/LONG |
| `voice_preference` | jsonb | 否 | '{}' | `{input_enabled,tts_enabled,volume,speed}`，Pydantic 校验 |
| `active_questioning_enabled` | boolean | 否 | true | 主动提问 |
| `daily_learning_minutes` | integer | 否 | 30 | CHECK >=0 |
| `evidence_ids` | jsonb | 否 | '[]' | 支撑证据（jsonb 引用） |
| `updated_at` | timestamptz | 否 | now() | — |

- PK：`preference_id`。
- UNIQUE：`student_id`（每学生一份当前偏好）。
- FK：`student_id → student_profiles(student_id) ON DELETE CASCADE`（强所属 1:1）。
- CHECK：`preferred_explanation_style IN ('EXAMPLE_BASED','VISUAL','STORY','DIRECT_DEFINITION','STEP_BY_STEP','CODE','INTERACTIVE')`；`preferred_difficulty IN ('EASY','MEDIUM','HARD')`；`preferred_session_length IN ('SHORT','MEDIUM','LONG')`；`daily_learning_minutes >= 0`。

### 3.4 `teacher_roles`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `role_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `name` | varchar(64) | 否 | — | 角色名 |
| `description` | text | 是 | NULL | 简介 |
| `persona` | jsonb | 否 | — | `{base_persona, character_persona}`，Pydantic 校验 |
| `tone` | varchar(128) | 否 | — | 语气 |
| `teaching_style` | varchar(128) | 否 | — | 教学风格 |
| `avatar` | varchar(512) | 是 | NULL | 头像 URL |
| `sprite_manifest` | jsonb | 否 | — | spritesheet 契约，Pydantic 校验 |
| `voice_id` | varchar(128) | 是 | NULL | TTS 语音 |
| `grade_rules` | jsonb | 否 | — | primary/junior/senior 规则，Pydantic 校验 |
| `prompt_profile` | jsonb | 是 | NULL | 带版本号 |
| `interaction_style` | varchar(128) | 是 | NULL | — |
| `enabled` | boolean | 否 | true | 是否可选 |
| `version` | integer | 否 | 1 | 配置版本，CHECK >=1 |
| `created_at` | timestamptz | 否 | now() | — |
| `updated_at` | timestamptz | 否 | now() | — |

- PK：`role_id`。
- UNIQUE：`name`。
- 备注：角色不持有任何学生数据（D2）；sprite_manifest 与 0-B spritesheet 契约一致。

### 3.5 `books`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `book_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `title` | varchar(255) | 否 | — | 书名 |
| `cover_url` | varchar(512) | 是 | NULL | 封面 |
| `description` | text | 是 | NULL | 简介 |
| `grade_min` | integer | 否 | — | **CHECK 1<=grade_min** |
| `grade_max` | integer | 否 | — | **CHECK grade_max<=12** |
| `difficulty` | varchar(16) | 否 | — | EASY/MEDIUM/HARD |
| `estimated_minutes` | integer | 否 | — | CHECK >0 |
| `author` | varchar(255) | 是 | NULL | 作者 |
| `source_ids` | jsonb | 否 | '[]' | 来源资源（jsonb 引用，D9） |
| `license` | varchar(128) | 是 | NULL | 许可 |
| `copyright_status` | varchar(128) | 是 | NULL | 版权状态 |
| `tags` | jsonb | 否 | '[]' | 主题标签，Pydantic 校验 |
| `status` | varchar(16) | 否 | 'DRAFT' | DRAFT/PUBLISHED/ARCHIVED |
| `created_by` | uuid | 否 | — | 管理员 |
| `published_at` | timestamptz | 是 | NULL | 发布时间 |
| `created_at` | timestamptz | 否 | now() | — |
| `updated_at` | timestamptz | 否 | now() | — |

- PK：`book_id`。
- FK：`created_by → admins(admin_id) ON DELETE RESTRICT`。
- CHECK：`grade_min BETWEEN 1 AND 12`；`grade_max BETWEEN 1 AND 12`；**`grade_min <= grade_max`**；`estimated_minutes > 0`；`difficulty IN ('EASY','MEDIUM','HARD')`；`status IN ('DRAFT','PUBLISHED','ARCHIVED')`。
- 索引：`(grade_min, grade_max)`（书库学段筛选）；`(status, created_at DESC)`（管理端列表，可加）。

### 3.6 `chapters`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `chapter_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `book_id` | uuid | 否 | — | 所属书 |
| `title` | varchar(255) | 否 | — | 章标题 |
| `chapter_order` | integer | 否 | — | 顺序 |
| `summary` | text | 是 | NULL | 摘要 |
| `estimated_minutes` | integer | 否 | — | CHECK >0 |
| `status` | varchar(16) | 否 | 'DRAFT' | DRAFT/PUBLISHED/ARCHIVED |
| `created_at` | timestamptz | 否 | now() | — |
| `updated_at` | timestamptz | 否 | now() | — |

- PK：`chapter_id`。
- UNIQUE：`(book_id, chapter_order)`。
- FK：`book_id → books(book_id) ON DELETE CASCADE`（内容强所属，非用户数据）。
- CHECK：`estimated_minutes > 0`；`status IN ('DRAFT','PUBLISHED','ARCHIVED')`。

### 3.7 `content_blocks`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `block_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `chapter_id` | uuid | 否 | — | 所属章 |
| `block_type` | varchar(32) | 否 | — | 8 值枚举 |
| `content` | jsonb | 否 | — | 按 block_type 校验 |
| `block_order` | integer | 否 | — | 顺序 |
| `section_key` | varchar(128) | 是 | NULL | data-read-section 锚点 |
| `knowledge_point_ids` | jsonb | 否 | '[]' | 知识点（jsonb 引用） |
| `created_at` | timestamptz | 否 | now() | — |
| `updated_at` | timestamptz | 否 | now() | — |

- PK：`block_id`。
- UNIQUE：`(chapter_id, block_order)`。
- FK：`chapter_id → chapters(chapter_id) ON DELETE CASCADE`。
- CHECK：`block_type IN ('TITLE','PARAGRAPH','IMAGE','FIGURE','KNOWLEDGE_CARD','EXAMPLE','CALLOUT','HIGHLIGHT')`。

### 3.8 `knowledge_points`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `knowledge_point_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `name` | varchar(128) | 否 | — | 名称 |
| `slug` | varchar(128) | 否 | — | 唯一标识 |
| `description` | text | 是 | NULL | 定义 |
| `topic` | varchar(64) | 是 | NULL | 主题域 |
| `parent_id` | uuid | 是 | NULL | 父知识点 |
| `status` | varchar(16) | 否 | 'ACTIVE' | ACTIVE/ARCHIVED |
| `created_at` | timestamptz | 否 | now() | — |
| `updated_at` | timestamptz | 否 | now() | — |

- PK：`knowledge_point_id`。
- UNIQUE：`slug`。
- FK：`parent_id → knowledge_points(knowledge_point_id) ON DELETE SET NULL`（归档父节点不清子节点）。
- CHECK：`status IN ('ACTIVE','ARCHIVED')`。
- **禁止列**：本表（及全库）禁止任何 mastery/score/percent 数字列（D7、需求 §15）——设计评审必须检查无新增数字评分列。

### 3.9 `learning_sessions`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `session_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `student_id` | uuid | 否 | — | 学生 |
| `book_id` | uuid | 否 | — | 书 |
| `chapter_id` | uuid | 否 | — | 章 |
| `started_at` | timestamptz | 否 | — | 开始 |
| `ended_at` | timestamptz | 是 | NULL | 结束 |
| `duration_seconds` | integer | 否 | 0 | CHECK >=0 |
| `status` | varchar(16) | 否 | 'ACTIVE' | ACTIVE/ENDED/ABANDONED |
| `entry_route` | varchar(64) | 是 | NULL | 进入来源 |
| `created_at` | timestamptz | 否 | now() | — |

- PK：`session_id`。
- FK：`student_id → student_profiles(student_id) ON DELETE RESTRICT`（**已裁定：审计链 RESTRICT，隐私删除走脱敏**）；`book_id → books(book_id) ON DELETE RESTRICT`；`chapter_id → chapters(chapter_id) ON DELETE RESTRICT`。
- CHECK：`status IN ('ACTIVE','ENDED','ABANDONED')`；`duration_seconds >= 0`；`ended_at IS NULL OR ended_at >= started_at`。
- 部分唯一索引：`UNIQUE (student_id) WHERE status='ACTIVE'`（**数据库层落实「同一学生最多一个 ACTIVE 时段」不变量**）。
- 索引：`(student_id, started_at DESC)`。

### 3.10 `learning_events`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `event_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `student_id` | uuid | 否 | — | 学生 |
| `session_id` | uuid | 是 | NULL | 时段 |
| `event_type` | varchar(48) | 否 | — | 枚举见下 |
| `occurred_at` | timestamptz | 否 | — | 发生时间 |
| `book_id` | uuid | 是 | NULL | 定位 |
| `chapter_id` | uuid | 是 | NULL | 定位 |
| `block_id` | uuid | 是 | NULL | 定位 |
| `knowledge_point_ids` | jsonb | 否 | '[]' | 知识点（jsonb 引用） |
| `conversation_id` | uuid | 是 | NULL | 关联会话 |
| `quiz_session_id` | uuid | 是 | NULL | 关联测验 |
| `payload` | jsonb | 否 | — | 事件载荷，Pydantic 校验 |
| `created_at` | timestamptz | 否 | now() | 落库时间 |

- PK：`event_id`。
- FK（全部 `RESTRICT`，**已裁定：审计链 RESTRICT，隐私删除走脱敏**）：`student_id → student_profiles`；`session_id → learning_sessions`；`book_id → books`；`chapter_id → chapters`；`block_id → content_blocks`；`conversation_id → conversations`；`quiz_session_id → quiz_sessions`。
- CHECK：`event_type IN ('CHAPTER_STARTED','CHAPTER_FINISHED','SECTION_READ','KNOWLEDGE_CARD_VIEWED','HELP_REQUESTED','EXPLAIN_REQUESTED','SUMMARY_REQUESTED','QUIZ_CREATED','QUIZ_ANSWERED','ANSWER_CORRECT','ANSWER_WRONG','HINT_REQUESTED','QUESTION_ASKED','BOOK_STARTED','BOOK_FINISHED','VOICE_SESSION_STARTED','ROLE_SWITCHED','TEXT_SELECTED')`。`TEXT_SELECTED` 为 0-D 先行支持的待 0-C 补录项（§9 风险）。
- 索引：`(student_id, occurred_at DESC)`；`(student_id, event_type)`；`(quiz_session_id)`；`(conversation_id)`；`(session_id)`。
- 不可变性：**只 INSERT，不 UPDATE/DELETE**（应用层保证；审计与证据链依赖）。
- 预留：未来按月 RANGE 分区候选（§8）。

### 3.11 `book_progress`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `progress_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `student_id` | uuid | 否 | — | 学生 |
| `book_id` | uuid | 否 | — | 书 |
| `chapter_id` | uuid | 是 | NULL | 当前章 |
| `block_id` | uuid | 是 | NULL | 当前块 |
| `status` | varchar(16) | 否 | 'NOT_STARTED' | NOT_STARTED/READING/COMPLETED |
| `position_percent` | integer | 否 | 0 | 阅读位置 0~100（非掌握度） |
| `last_read_at` | timestamptz | 是 | NULL | 最近阅读 |
| `started_at` | timestamptz | 是 | NULL | — |
| `completed_at` | timestamptz | 是 | NULL | — |
| `total_seconds` | integer | 否 | 0 | CHECK >=0 |
| `updated_at` | timestamptz | 否 | now() | — |

- PK：`progress_id`。
- UNIQUE：**`(student_id, book_id)`**。
- FK：`student_id → student_profiles ON DELETE RESTRICT`（学生数据统一 RESTRICT，与审计链一致）；`book_id → books ON DELETE RESTRICT`；`chapter_id → chapters ON DELETE RESTRICT`；`block_id → content_blocks ON DELETE SET NULL`（位置指针）。
- CHECK：`status IN ('NOT_STARTED','READING','COMPLETED')`；`position_percent BETWEEN 0 AND 100`；`total_seconds >= 0`。
- 索引：唯一约束覆盖 `(student_id)` 前缀查询。

### 3.12 `conversations`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `conversation_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `student_id` | uuid | 否 | — | 学生 |
| `teacher_role_id` | uuid | 否 | — | 会话角色（创建时固定） |
| `title` | varchar(255) | 是 | NULL | 标题 |
| `status` | varchar(16) | 否 | 'ACTIVE' | ACTIVE/ARCHIVED/DELETED |
| `channel` | varchar(16) | 否 | 'TEXT' | TEXT/VOICE |
| `current_page_context` | jsonb | 否 | '{}' | 架构 §8 结构，Pydantic 校验 |
| `recent_messages` | jsonb | 否 | '[]' | 缓存窗口，事实源在 messages |
| `created_at` | timestamptz | 否 | now() | — |
| `updated_at` | timestamptz | 否 | now() | — |
| `last_message_at` | timestamptz | 是 | NULL | 最近消息 |

- PK：`conversation_id`。
- FK：`student_id → student_profiles ON DELETE RESTRICT`（**已裁定：审计链 RESTRICT，隐私删除走脱敏**）；`teacher_role_id → teacher_roles ON DELETE RESTRICT`。
- CHECK：`status IN ('ACTIVE','ARCHIVED','DELETED')`；`channel IN ('TEXT','VOICE')`。
- 索引：`(student_id, updated_at DESC)`（会话列表）；`(teacher_role_id)`。
- 软删：`status='DELETED'`；会话摘要以 `conversation_summaries` 表为权威（§3.14），由 JOIN 提供。

### 3.13 `messages`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `message_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `conversation_id` | uuid | 否 | — | 会话 |
| `role` | varchar(16) | 否 | — | STUDENT/TEACHER/SYSTEM |
| `type` | varchar(32) | 否 | — | **7 值枚举（总控 §13.2）** |
| `content` | text | 否 | — | 正文 |
| `metadata` | jsonb | 否 | '{}' | quiz_session_id/hint_level/tool_state 等，Pydantic 校验 |
| `sequence` | integer | 否 | — | 会话内序号（应用生成） |
| `model_info` | jsonb | 是 | NULL | provider/model/skill_version |
| `created_at` | timestamptz | 否 | now() | — |

- PK：`message_id`。
- UNIQUE：**`(conversation_id, sequence)`**。
- FK：`conversation_id → conversations ON DELETE RESTRICT`（**已裁定：审计链 RESTRICT，隐私删除走脱敏**）。
- CHECK：`role IN ('STUDENT','TEACHER','SYSTEM')`；`type IN ('TEXT','QUIZ','TOOL_STATUS','HINT','RECOMMENDATION','SYSTEM','LEARNING_SUMMARY')`。
- 索引：唯一约束覆盖 `(conversation_id, sequence)` 正序；按需加 `(conversation_id, sequence DESC)` 供倒序分页。
- 不可变性：只追加（应用层保证）；`sequence` 在会话内唯一且递增。
- 预留：未来按月 RANGE 分区候选（§8）。

### 3.14 `conversation_summaries`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `summary_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `conversation_id` | uuid | 否 | — | 会话（1:1） |
| `summary` | text | 否 | — | 摘要 |
| `token_count` | integer | 否 | 0 | CHECK >=0 |
| `summary_version` | integer | 否 | 1 | 递增版本 |
| `source_message_ids` | jsonb | 否 | '[]' | 压缩范围 |
| `model_info` | jsonb | 是 | NULL | 生成模型 |
| `created_at` | timestamptz | 否 | now() | — |
| `updated_at` | timestamptz | 否 | now() | — |

- PK：`summary_id`。
- UNIQUE：`conversation_id`。
- FK：`conversation_id → conversations ON DELETE CASCADE`（派生数据，随会话物理删除；软删会话不影响）。

### 3.15 `quiz_sessions`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `quiz_session_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `student_id` | uuid | 否 | — | 学生 |
| `conversation_id` | uuid | 否 | — | 发起会话 |
| `teacher_role_id` | uuid | 否 | — | 生成时角色 |
| `book_id` | uuid | 是 | NULL | 内容定位 |
| `chapter_id` | uuid | 是 | NULL | 内容定位 |
| `title` | varchar(255) | 否 | — | 测验名 |
| `quiz_kind` | varchar(16) | 否 | — | CHAPTER_QUIZ/AI_QUIZ |
| `status` | varchar(16) | 否 | 'GENERATING' | GENERATING/ACTIVE/COMPLETED/ABANDONED |
| `questions_snapshot` | jsonb | 否 | — | **原题快照，创建后不可变（应用层保证，无触发器）** |
| `result_summary` | jsonb | 是 | NULL | `{correct,total,hints_used}`，无主观百分比 |
| `duration_seconds` | integer | 否 | 0 | CHECK >=0 |
| `ai_feedback` | text | 是 | NULL | 点评 |
| `model_info` | jsonb | 否 | — | provider/model |
| `skill_version` | varchar(64) | 否 | — | **必填（D5）** |
| `created_at` | timestamptz | 否 | now() | — |
| `updated_at` | timestamptz | 否 | now() | — |
| `completed_at` | timestamptz | 是 | NULL | — |

- PK：`quiz_session_id`。
- FK（全部 `RESTRICT`，**已裁定：审计链 RESTRICT，隐私删除走脱敏**）：`student_id → student_profiles`；`conversation_id → conversations`；`teacher_role_id → teacher_roles`；`book_id → books`；`chapter_id → chapters`。
- CHECK：`quiz_kind IN ('CHAPTER_QUIZ','AI_QUIZ')`；`status IN ('GENERATING','ACTIVE','COMPLETED','ABANDONED')`；`duration_seconds >= 0`；`completed_at IS NULL OR completed_at >= created_at`。
- 索引：`(student_id, created_at DESC)`（测验历史）；`(conversation_id)`；`(book_id, chapter_id)`。
- 不可变快照：`questions_snapshot` 只允许 INSERT 时写入；历史详情**只读快照，绝不触发 LLM**（D5，应用层+评审约束）。

### 3.16 `quiz_questions`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `question_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `quiz_session_id` | uuid | 否 | — | 测验 |
| `question_order` | integer | 否 | — | 题序 |
| `question_type` | varchar(24) | 否 | — | 4 值枚举 |
| `stem` | text | 否 | — | 题干 |
| `options` | jsonb | 否 | — | `[{key,text}]` |
| `correct_answer` | jsonb | 否 | — | 服务端权威 |
| `explanation` | text | 否 | — | AI 解析 |
| `source_context` | jsonb | 是 | NULL | 定位 |
| `interaction_policy` | jsonb | 否 | '{"allow_hint":true,"max_hint_level":3}' | 提示策略 |
| `knowledge_point_ids` | jsonb | 否 | '[]' | 知识点（jsonb 引用） |
| `created_at` | timestamptz | 否 | now() | — |

- PK：`question_id`。
- UNIQUE：**`(quiz_session_id, question_order)`**。
- FK：`quiz_session_id → quiz_sessions ON DELETE RESTRICT`（**已裁定：审计链 RESTRICT，隐私删除走脱敏**）。
- CHECK：`question_type IN ('SINGLE_CHOICE','MULTIPLE_CHOICE','TRUE_FALSE','FILL_BLANK')`。
- 索引：`(quiz_session_id)` 由唯一约束覆盖。

### 3.17 `quiz_answers`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `answer_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `quiz_session_id` | uuid | 否 | — | 测验 |
| `question_id` | uuid | 否 | — | 题目 |
| `student_id` | uuid | 否 | — | 学生 |
| `submitted_answer` | jsonb | 否 | — | 提交内容 |
| `is_correct` | boolean | 否 | — | 服务端判定 |
| `attempt_no` | integer | 否 | — | 尝试序号，CHECK >=1 |
| `hint_level_at_submit` | integer | 否 | 0 | CHECK >=0 |
| `is_final` | boolean | 否 | false | 最终答案 |
| `submitted_at` | timestamptz | 否 | — | 提交时间 |
| `created_at` | timestamptz | 否 | now() | — |

- PK：`answer_id`。
- UNIQUE：**`(quiz_session_id, question_id, attempt_no)`**（幂等兜底：同次尝试不重复落行，对应 0-D §10.5）。
- FK（全部 `RESTRICT`，**已裁定：审计链 RESTRICT，隐私删除走脱敏**）：`quiz_session_id → quiz_sessions`；`question_id → quiz_questions`；`student_id → student_profiles`。
- CHECK：`attempt_no >= 1`；`hint_level_at_submit >= 0`。
- 索引：`(quiz_session_id, question_id, created_at)`（由唯一约束部分覆盖，按需补时间索引）。

### 3.18 `quiz_interactions`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `interaction_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `quiz_session_id` | uuid | 否 | — | 测验 |
| `question_id` | uuid | 是 | NULL | 题目（非题目级互动可空） |
| `interaction_type` | varchar(24) | 否 | — | **6 值枚举（D6）** |
| `payload` | jsonb | 否 | — | hint/问答载荷，Pydantic 校验 |
| `message_id` | uuid | 是 | NULL | 关联消息 |
| `answer_id` | uuid | 是 | NULL | 关联答案 |
| `sequence` | integer | 否 | — | 会话内互动序号 |
| `created_at` | timestamptz | 否 | now() | — |

- PK：`interaction_id`。
- UNIQUE：`(quiz_session_id, sequence)`。
- FK（全部 `RESTRICT`，**已裁定：审计链 RESTRICT，隐私删除走脱敏**）：`quiz_session_id → quiz_sessions`；`question_id → quiz_questions`；`message_id → messages`；`answer_id → quiz_answers`。
- CHECK：`interaction_type IN ('HINT_REQUEST','HINT_RESPONSE','QUESTION_ASK','TEACHER_REPLY','ANSWER_SUBMIT','ANSWER_RESULT')`。
- 索引：`(quiz_session_id, question_id, created_at)`；`(message_id)`；`(answer_id)`。
- 不可变性：只追加（审计日志）。
- 预留：未来按月 RANGE 分区候选（§8）。

### 3.19 `student_memories`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `memory_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `student_id` | uuid | 否 | — | 学生 |
| `memory_type` | varchar(16) | 否 | — | PROFILE/PREFERENCE/LEARNING/EPISODIC |
| `content` | text | 否 | — | 记忆内容 |
| `tags` | jsonb | 否 | '[]' | 标签 |
| `confidence` | varchar(8) | 否 | — | LOW/MEDIUM/HIGH（定性，不展示为数字） |
| `status` | varchar(16) | 否 | 'ACTIVE' | ACTIVE/DISPUTED/SUPERSEDED/REMOVED |
| `evidence_ids` | jsonb | 否 | '[]' | 支撑证据（jsonb 引用） |
| `origin_candidate_id` | uuid | 是 | NULL | 来源候选 |
| `user_confirmed` | boolean | 否 | false | 用户确认 |
| `created_at` | timestamptz | 否 | now() | — |
| `updated_at` | timestamptz | 否 | now() | — |
| `confirmed_at` | timestamptz | 是 | NULL | — |

- PK：`memory_id`。
- FK：`student_id → student_profiles ON DELETE RESTRICT`（**已裁定：审计链 RESTRICT，隐私删除走脱敏**）；`origin_candidate_id → memory_candidates(candidate_id) ON DELETE SET NULL`。
- CHECK：`memory_type IN ('PROFILE','PREFERENCE','LEARNING','EPISODIC')`；`confidence IN ('LOW','MEDIUM','HIGH')`；`status IN ('ACTIVE','DISPUTED','SUPERSEDED','REMOVED')`。
- 索引：`(student_id, status)`；`(student_id, updated_at DESC)`（记忆管理页）。
- 软删：`status='REMOVED'`；DISPUTED/REMOVED 不参与检索（应用层）。

### 3.20 `memory_candidates`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `candidate_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `student_id` | uuid | 否 | — | 学生 |
| `candidate_type` | varchar(16) | 否 | — | PROFILE/PREFERENCE/LEARNING/EPISODIC |
| `content` | text | 否 | — | 候选内容 |
| `proposed_memory` | jsonb | 否 | — | 结构化建议 |
| `evidence_ids` | jsonb | 否 | '[]' | 证据（jsonb 引用） |
| `confidence` | varchar(8) | 否 | — | LOW/MEDIUM/HIGH |
| `status` | varchar(16) | 否 | 'PENDING' | PENDING/APPROVED/REJECTED/MERGED |
| `rule_version` | varchar(64) | 否 | — | Memory 规则版本 |
| `model_info` | jsonb | 否 | — | 生成模型 |
| `created_at` | timestamptz | 否 | now() | — |
| `resolved_at` | timestamptz | 是 | NULL | 处理时间 |

- PK：`candidate_id`。
- FK：`student_id → student_profiles ON DELETE RESTRICT`（**已裁定：审计链 RESTRICT，隐私删除走脱敏**）。
- CHECK：`candidate_type IN ('PROFILE','PREFERENCE','LEARNING','EPISODIC')`；`confidence IN ('LOW','MEDIUM','HIGH')`；`status IN ('PENDING','APPROVED','REJECTED','MERGED')`。
- 索引：`(student_id, status)`；`(status, created_at)`（Pipeline 扫描）。

### 3.21 `memory_evidence`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `evidence_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `student_id` | uuid | 否 | — | 学生 |
| `source_type` | varchar(24) | 否 | — | QUIZ/LEARNING_SESSION/CONVERSATION/BOOK_PROGRESS |
| `event_ids` | jsonb | 否 | '[]' | 归并的 LearningEvent id（jsonb 引用） |
| `payload` | jsonb | 否 | — | 聚合事实，Pydantic 校验 |
| `count` | integer | 否 | 1 | 事件数，CHECK >=1 |
| `first_occurred_at` | timestamptz | 是 | NULL | — |
| `last_occurred_at` | timestamptz | 是 | NULL | — |
| `derived_at` | timestamptz | 否 | — | 聚合时间 |
| `rule_version` | varchar(64) | 否 | — | 聚合规则版本 |

- PK：`evidence_id`。
- FK：`student_id → student_profiles ON DELETE RESTRICT`（**已裁定：审计链 RESTRICT，隐私删除走脱敏**）。
- CHECK：`source_type IN ('QUIZ','LEARNING_SESSION','CONVERSATION','BOOK_PROGRESS')`；`count >= 1`。
- 索引：`(student_id, derived_at DESC)`。
- 不可变性：聚合后不修改（新证据产生新聚合）。
- 备注：`event_ids` 为 jsonb 引用而非 FK（理由见 §6.2）。

### 3.22 `student_episodes`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `episode_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `student_id` | uuid | 否 | — | 学生 |
| `title` | varchar(255) | 否 | — | 情节标题 |
| `summary` | text | 否 | — | 叙事 |
| `occurred_at` | timestamptz | 否 | — | 发生时间 |
| `event_ids` | jsonb | 否 | '[]' | 支撑事件（jsonb 引用） |
| `book_id` | uuid | 是 | NULL | 定位 |
| `chapter_id` | uuid | 是 | NULL | 定位 |
| `knowledge_point_ids` | jsonb | 否 | '[]' | 知识点（jsonb 引用） |
| `embedding` | vector | 是 | NULL | **pgvector，维度 Phase 8 定** |
| `importance` | varchar(8) | 否 | — | LOW/MEDIUM/HIGH |
| `tags` | jsonb | 否 | '[]' | 标签 |
| `created_at` | timestamptz | 否 | now() | — |

- PK：`episode_id`。
- FK：`student_id → student_profiles ON DELETE RESTRICT`（**已裁定：审计链 RESTRICT，隐私删除走脱敏**）；`book_id → books ON DELETE RESTRICT`；`chapter_id → chapters ON DELETE RESTRICT`。
- CHECK：`importance IN ('LOW','MEDIUM','HIGH')`。
- 索引：`(student_id, occurred_at DESC)`；`embedding` 的 **HNSW 向量索引 Phase 8** 落地。

### 3.23 `profile_insights`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `insight_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `student_id` | uuid | 否 | — | 学生 |
| `insight_type` | varchar(24) | 否 | — | STRENGTH/WEAKNESS/UNDERSTANDING/HABIT/CHANGE/INTEREST |
| `dimension` | varchar(64) | 否 | — | 维度 slug |
| `level` | varchar(8) | 否 | — | **5 档定性（D7）** |
| `description` | text | 否 | — | 定性描述 |
| `evidence_ids` | jsonb | 否 | '[]' | 支撑证据（jsonb 引用） |
| `status` | varchar(16) | 否 | 'ACTIVE' | ACTIVE/SUPERSEDED |
| `valid_from` | timestamptz | 否 | — | 生效时间 |
| `valid_until` | timestamptz | 是 | NULL | 失效时间 |
| `rule_version` | varchar(64) | 否 | — | 画像规则版本 |
| `model_info` | jsonb | 是 | NULL | 生成模型 |
| `created_at` | timestamptz | 否 | now() | — |
| `updated_at` | timestamptz | 否 | now() | — |

- PK：`insight_id`。
- FK：`student_id → student_profiles ON DELETE RESTRICT`（**已裁定：审计链 RESTRICT，隐私删除走脱敏**）。
- CHECK：`insight_type IN ('STRENGTH','WEAKNESS','UNDERSTANDING','HABIT','CHANGE','INTEREST')`；**`level IN ('偏弱','一般','较稳定','较强','仍需观察')`**；`status IN ('ACTIVE','SUPERSEDED')`；`valid_until IS NULL OR valid_until >= valid_from`。
- 索引：`(student_id, status, valid_from DESC)`（画像页 + changelog）。
- **禁止任何数字评分列**（与 D7 同规）。

### 3.24 `recommendations`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `recommendation_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `student_id` | uuid | 否 | — | 学生 |
| `recommendation_type` | varchar(16) | 否 | — | BOOK/CHAPTER/REVIEW/QUIZ/DAILY_PLAN |
| `book_id` | uuid | 是 | NULL | 目标书 |
| `chapter_id` | uuid | 是 | NULL | 目标章 |
| `title` | varchar(255) | 否 | — | 标题 |
| `reason` | text | 否 | — | 推荐理由（可解释） |
| `evidence_ids` | jsonb | 否 | '[]' | 依据（jsonb 引用） |
| `source_ids` | jsonb | 否 | '[]' | 来源资源（jsonb 引用，D9） |
| `license` | varchar(128) | 是 | NULL | 引用许可 |
| `source_url` | varchar(512) | 是 | NULL | 引用 URL |
| `status` | varchar(16) | 否 | 'ACTIVE' | ACTIVE/DISMISSED/EXPIRED |
| `expires_at` | timestamptz | 是 | NULL | 过期时间 |
| `model_info` | jsonb | 是 | NULL | 生成模型 |
| `skill_version` | varchar(64) | 否 | — | 推荐 Skill 版本 |
| `created_at` | timestamptz | 否 | now() | — |

- PK：`recommendation_id`。
- FK：`student_id → student_profiles ON DELETE RESTRICT`（**已裁定：审计链 RESTRICT，隐私删除走脱敏**）；`book_id → books ON DELETE RESTRICT`；`chapter_id → chapters ON DELETE RESTRICT`。
- CHECK：`recommendation_type IN ('BOOK','CHAPTER','REVIEW','QUIZ','DAILY_PLAN')`；`status IN ('ACTIVE','DISMISSED','EXPIRED')`。
- 索引：`(student_id, status, created_at DESC)`（首页推荐）；`(book_id)`；`(chapter_id)`。

### 3.25 `knowledge_resources`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `resource_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `source_name` | varchar(255) | 否 | — | 来源名称 |
| `source_url` | varchar(512) | 否 | — | 来源 URL（D9） |
| `author` | varchar(255) | 是 | NULL | 作者 |
| `license` | varchar(128) | 否 | — | **非空** |
| `copyright_status` | varchar(128) | 否 | — | **非空** |
| `storage_key` | varchar(512) | 否 | — | Object Storage 键 |
| `file_type` | varchar(16) | 否 | — | PDF/MARKDOWN/TXT/HTML |
| `status` | varchar(16) | 否 | 'UPLOADED' | UPLOADED/PARSING/CHUNKING/INDEXING/READY/FAILED |
| `uploaded_by` | uuid | 否 | — | 管理员 |
| `error` | text | 是 | NULL | 失败原因 |
| `uploaded_at` | timestamptz | 否 | now() | — |
| `created_at` | timestamptz | 否 | now() | — |
| `updated_at` | timestamptz | 否 | now() | — |

- PK：`resource_id`。
- FK：`uploaded_by → admins(admin_id) ON DELETE RESTRICT`。
- CHECK：`file_type IN ('PDF','MARKDOWN','TXT','HTML')`；`status IN ('UPLOADED','PARSING','CHUNKING','INDEXING','READY','FAILED')`。
- 索引：`(status, created_at)`；`(uploaded_by)`。

### 3.26 `knowledge_chunks`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `chunk_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `resource_id` | uuid | 否 | — | 所属资源 |
| `chunk_index` | integer | 否 | — | 块序号 |
| `content` | text | 否 | — | 切块文本 |
| `content_type` | varchar(64) | 是 | NULL | 类型/标题 |
| `metadata` | jsonb | 否 | '{}' | source_url/license/page/heading |
| `knowledge_point_ids` | jsonb | 否 | '[]' | 知识点（jsonb 引用） |
| `embedding` | vector | 是 | NULL | **pgvector，维度 Phase 8 定** |
| `token_count` | integer | 否 | 0 | CHECK >=0 |
| `status` | varchar(16) | 否 | 'PENDING' | PENDING/READY/FAILED |
| `created_at` | timestamptz | 否 | now() | — |

- PK：`chunk_id`。
- UNIQUE：`(resource_id, chunk_index)`。
- FK：`resource_id → knowledge_resources ON DELETE CASCADE`（内容强所属，管理端内容）。
- CHECK：`token_count >= 0`；`status IN ('PENDING','READY','FAILED')`。
- 索引：`(resource_id)` 由唯一约束覆盖；`embedding` 的 **HNSW 向量索引 Phase 8** 落地。

### 3.27 `admins`

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `admin_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `user_id` | uuid | 否 | — | 登录账号（1:1） |
| `display_name` | varchar(128) | 否 | — | 显示名 |
| `role_level` | varchar(24) | 否 | 'SUPERVISOR' | SUPERVISOR/CONTENT_EDITOR |
| `permissions` | jsonb | 是 | NULL | 权限列表 |
| `enabled` | boolean | 否 | true | 启用 |
| `created_at` | timestamptz | 否 | now() | — |
| `updated_at` | timestamptz | 否 | now() | — |

- PK：`admin_id`。
- UNIQUE：`user_id`。
- FK：`user_id → users(user_id) ON DELETE CASCADE`。
- CHECK：`role_level IN ('SUPERVISOR','CONTENT_EDITOR')`。

### 3.28 `idempotency_keys`（应用基础设施表，非 Domain 实体）

| 列 | 类型 | 可空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `idempotency_id` | uuid | 否 | gen_random_uuid() | 主键 |
| `actor_id` | uuid | 否 | — | 幂等作用域主体（student 或 admin 的 id） |
| `actor_type` | varchar(16) | 否 | — | STUDENT / ADMIN |
| `key` | varchar(64) | 否 | — | Idempotency-Key |
| `request_hash` | varchar(64) | 否 | — | 规范化请求体 sha256 |
| `response` | jsonb | 否 | — | 原始成功响应（供重放） |
| `created_at` | timestamptz | 否 | now() | — |
| `expires_at` | timestamptz | 否 | — | TTL（24h） |

- PK：`idempotency_id`。
- UNIQUE：**`(actor_id, actor_type, key)`**。
- FK：`actor_id` 不设物理 FK（可能指向 users 或统一 actor；应用层按 `actor_type` 校验归属）。
- CHECK：`actor_type IN ('STUDENT','ADMIN')`。
- 索引：`(actor_id, expires_at)`（TTL 清理 Worker）。
- 物理删除：过期行由 Worker 定期清理（**唯一允许物理删除的表**）。
- 备注：0-D §1.7 按 `(actor_id, actor_type, key)` 作用域；`actor_id` 不设物理 FK，应用层按 `actor_type` 校验归属。

---

## 4. 索引策略

### 4.1 外键列索引

| 表 | 外键列 | 说明 |
| --- | --- | --- |
| `student_profiles` | `current_teacher_role_id` | 角色筛选/Join |
| `books` | `created_by` | 管理端 |
| `learning_sessions` | `book_id` / `chapter_id` | Join 与筛选 |
| `learning_events` | `session_id` / `book_id` / `chapter_id` / `block_id` / `conversation_id` / `quiz_session_id` | 事件反查 |
| `conversations` | `teacher_role_id` | 角色维度 |
| `quiz_sessions` | `conversation_id` / `teacher_role_id` / `book_id` / `chapter_id` | 反查 |
| `quiz_answers` | `question_id`（含在唯一约束前缀） | — |
| `quiz_interactions` | `message_id` / `answer_id` / `question_id` | 互动审计 |
| `recommendations` | `book_id` / `chapter_id` | 目标反查 |
| `student_episodes` | `book_id` / `chapter_id` | 定位反查 |
| `knowledge_resources` | `uploaded_by` | 管理端 |

（`content_blocks.chapter_id`、`chapters.book_id`、`messages.conversation_id`、`quiz_questions.quiz_session_id`、`knowledge_chunks.resource_id` 已被各自唯一约束的前缀列覆盖，无需单独索引。）

### 4.2 高频查询路径索引

| 查询路径 | 索引 |
| --- | --- |
| 会话列表：按学生 + 最近更新 | `conversations (student_id, updated_at DESC)` |
| 消息历史：按会话 + 序号 | `messages UNIQUE (conversation_id, sequence)`；倒序分页按需 `(conversation_id, sequence DESC)` |
| 测验历史：按学生 + 时间 | `quiz_sessions (student_id, created_at DESC)` |
| 学习事件：按学生 + 时间 | `learning_events (student_id, occurred_at DESC)` |
| 书本进度：按学生 | `book_progress UNIQUE (student_id, book_id)`（前缀覆盖） |
| 记忆管理：按学生 + 状态 | `student_memories (student_id, status)` |
| 画像：按学生 + 状态 + 时间 | `profile_insights (student_id, status, valid_from DESC)` |
| 推荐：按学生 + 状态 + 时间 | `recommendations (student_id, status, created_at DESC)` |
| 单一 ACTIVE 学习时段 | `learning_sessions UNIQUE (student_id) WHERE status='ACTIVE'` |

### 4.3 pgvector 索引（Phase 8）

- `student_episodes.embedding`、`knowledge_chunks.embedding`：启用 `vector` 扩展后建 HNSW（cosine）索引；维度与索引参数（m/ef_construction）由 Phase 8 数据量与 Provider 决定。
- MVP 阶段不建向量索引、不装扩展。

### 4.4 写多读少的谨慎项

- `learning_events` / `messages` / `quiz_interactions` 是 append-only 高频写表：**不加覆盖索引、不加低选择性索引**（如单列 status），避免写放大。
- `idempotency_keys` 高频写 + TTL 删：只保留唯一约束与 `(student_id, expires_at)` 清理索引。
- 所有唯一约束/部分索引优先满足业务不变量，性能索引在 Phase 2+ 用 EXPLAIN 实测后再补。

---

## 5. 关系与完整性

### 5.1 物理外键关系表（on delete 行为）

| 子表 | 外键列 | 目标 | on delete | 说明 |
| --- | --- | --- | --- | --- |
| student_profiles | user_id | users | CASCADE | 账号→档案（仅隐私清除物理删） |
| student_profiles | current_teacher_role_id | teacher_roles | SET NULL | 角色下架不伤学生 |
| student_preferences | student_id | student_profiles | CASCADE | 强所属 1:1 |
| chapters | book_id | books | CASCADE | 内容强所属 |
| content_blocks | chapter_id | chapters | CASCADE | 内容强所属 |
| knowledge_points | parent_id | knowledge_points | SET NULL | 层级指针 |
| learning_sessions | student_id | student_profiles | RESTRICT | 已裁定：审计链 RESTRICT |
| learning_sessions | book_id / chapter_id | books / chapters | RESTRICT | 内容软删保护 |
| learning_events | student_id / session_id / book_id / chapter_id / block_id / conversation_id / quiz_session_id | 各目标 | RESTRICT | 已裁定：审计链 RESTRICT |
| book_progress | student_id | student_profiles | RESTRICT | 学生数据统一 RESTRICT（原 CASCADE 已移除） |
| book_progress | book_id / chapter_id | books / chapters | RESTRICT | — |
| book_progress | block_id | content_blocks | SET NULL | 位置指针 |
| conversations | student_id | student_profiles | RESTRICT | 已裁定：审计链 RESTRICT |
| conversations | teacher_role_id | teacher_roles | RESTRICT | — |
| messages | conversation_id | conversations | RESTRICT | 已裁定：审计链 RESTRICT |
| conversation_summaries | conversation_id | conversations | CASCADE | 派生数据 |
| quiz_sessions | student_id / conversation_id / teacher_role_id / book_id / chapter_id | 各目标 | RESTRICT | 已裁定：审计链 RESTRICT |
| quiz_questions | quiz_session_id | quiz_sessions | RESTRICT | 已裁定：审计链 RESTRICT |
| quiz_answers | quiz_session_id / question_id / student_id | 各目标 | RESTRICT | 已裁定：审计链 RESTRICT |
| quiz_interactions | quiz_session_id / question_id / message_id / answer_id | 各目标 | RESTRICT | 已裁定：审计链 RESTRICT |
| student_memories | student_id | student_profiles | RESTRICT | 已裁定：审计链 RESTRICT |
| student_memories | origin_candidate_id | memory_candidates | SET NULL | 候选删除不清记忆 |
| memory_candidates | student_id | student_profiles | RESTRICT | 已裁定：审计链 RESTRICT |
| memory_evidence | student_id | student_profiles | RESTRICT | 已裁定：审计链 RESTRICT |
| student_episodes | student_id / book_id / chapter_id | 各目标 | RESTRICT | 已裁定：审计链 RESTRICT |
| profile_insights | student_id | student_profiles | RESTRICT | 已裁定：审计链 RESTRICT |
| recommendations | student_id / book_id / chapter_id | 各目标 | RESTRICT | 已裁定：审计链 RESTRICT |
| knowledge_resources | uploaded_by | admins | RESTRICT | — |
| knowledge_chunks | resource_id | knowledge_resources | CASCADE | 内容强所属 |
| admins | user_id | users | CASCADE | 账号→管理员 |
| idempotency_keys | actor_id | —（不设物理 FK） | — | actor_type=STUDENT/ADMIN，应用层校验归属 |
| books | created_by | admins | RESTRICT | — |

### 5.2 物理 FK vs jsonb 引用

| 引用形式 | 字段 | 原因 |
| --- | --- | --- |
| **物理 FK** | 上表全部 | 1:1 / 1:N 强所属与核心链路（ownership + 生命周期） |
| **jsonb 数组引用** | `evidence_ids`（student_memories / profile_insights / memory_candidates / recommendations / student_preferences）、`event_ids`（memory_evidence / student_episodes）、`knowledge_point_ids`（content_blocks / learning_events / quiz_questions / knowledge_chunks / student_episodes / recommendations 等）、`source_ids`（books / recommendations） | ① 聚合快照：证据/事件集在派生时刻固化，事后删除历史事件不应破坏已沉淀结论；② 避免环形 FK（memory_candidates ↔ student_memories ↔ memory_evidence 互相引用）；③ N:M 知识关联读多写少，MVP 无需查询反链 |

风险与缓解：

- jsonb 引用无数据库级完整性；由应用层 Pydantic/Service 校验 + 定期一致性巡检（Phase 2+ 可加离线脚本）兜底。
- Phase 8 若出现「按知识点反查题目/章节」的高频查询，再评估把 `knowledge_point_ids` 提升为物理关联表（`chapter_knowledge_points` 等，与总控 §12.3 对齐——见 §9 风险）。

---

## 6. 分区 / 归档 / 大数据量预留

- **标注候选（只标注，不设计细节）**：
  - `learning_events`：按 `occurred_at` 月 RANGE 分区候选（append-only、时间查询为主）；
  - `messages`：按 `created_at` 月 RANGE 分区候选；
  - `quiz_interactions`：按 `created_at` 月 RANGE 分区候选；
  - 归档策略：`conversations.status=DELETED` 或 ARCHIVED 达到阈值后可归档到冷存储（Phase 后期评估）。
- **MVP 明确不做**：不分区、不引入归档中间件、不引入独立时序库/分析库（架构 §52/§54）；表全部按普通堆表设计，索引按 §4。
- 扩容触发条件：单表超千万行或慢查询出现后再做，迁移路径由 0-E 后续版本补充。

---

## 7. 与 Domain Model 一致性自查表（27 ↔ 27）

| # | Domain 实体 | 表名 | 覆盖要素 | 备注 |
| --- | --- | --- | --- | --- |
| 1 | User | `users` | 列/唯一/CHECK/软删 | 无 FK |
| 2 | StudentProfile | `student_profiles` | grade CHECK / 统计缓存 | 1:1 user |
| 3 | StudentPreference | `student_preferences` | 3 组偏好 CHECK | 1:1 student |
| 4 | TeacherRole | `teacher_roles` | jsonb 配置校验 | 无学生数据 |
| 5 | Book | `books` | grade_min/max CHECK | source_ids jsonb |
| 6 | Chapter | `chapters` | (book_id, chapter_order) 唯一 | — |
| 7 | ContentBlock | `content_blocks` | block_type CHECK / 顺序唯一 | section_key |
| 8 | KnowledgePoint | `knowledge_points` | slug 唯一 / 无评分列 | parent 自引用 |
| 9 | LearningSession | `learning_sessions` | 部分唯一 ACTIVE | RESTRICT（已裁定） |
| 10 | LearningEvent | `learning_events` | 事件枚举 / 不可变 | 审计链 |
| 11 | BookProgress | `book_progress` | (student_id, book_id) 唯一 | position 0~100 |
| 12 | Conversation | `conversations` | 状态/频道 CHECK | current_page_context |
| 13 | Message | `messages` | type 7 值 / (conversation_id, sequence) 唯一 | 只追加 |
| 14 | ConversationSummary | `conversation_summaries` | conversation_id 唯一 | 1:1 |
| 15 | QuizSession | `quiz_sessions` | snapshot 不可变 / skill_version 必填 | RESTRICT（已裁定） |
| 16 | QuizQuestion | `quiz_questions` | (quiz_session_id, question_order) 唯一 | correct_answer 权威 |
| 17 | QuizAnswer | `quiz_answers` | (quiz_session_id, question_id, attempt_no) 唯一 | 幂等兜底 |
| 18 | QuizInteraction | `quiz_interactions` | 6 值枚举 / (quiz_session_id, sequence) 唯一 | 审计 |
| 19 | StudentMemory | `student_memories` | 状态机 CHECK / 软删 | evidence jsonb |
| 20 | MemoryCandidate | `memory_candidates` | 状态机 CHECK | Pipeline 内部 |
| 21 | MemoryEvidence | `memory_evidence` | count>=1 / 不可变 | event_ids jsonb |
| 22 | StudentEpisode | `student_episodes` | embedding 列（Phase 8） | 向量 |
| 23 | ProfileInsight | `profile_insights` | **level 5 档 CHECK** / 无数字列 | 版本化 |
| 24 | Recommendation | `recommendations` | source_ids/license/source_url（D9） | 可解释 |
| 25 | KnowledgeResource | `knowledge_resources` | license/copyright 非空 | storage_key |
| 26 | KnowledgeChunk | `knowledge_chunks` | (resource_id, chunk_index) 唯一 / embedding | 向量 |
| 27 | Admin | `admins` | role_level CHECK | 1:1 user |
| — | （基础设施） | `idempotency_keys` | (actor_id, actor_type, key) 唯一 / TTL | **非 Domain，0-D §1.7 要求** |

结论：**27 个 Domain 实体 ↔ 27 张表，无遗漏、无多余业务表**；额外仅有 1 张幂等映射基础设施表（任务要求）。

---

## 8. 与 API Contract 的枚举对齐

| 枚举 | domain-model / api-contract 取值 | 落库位置 |
| --- | --- | --- |
| Message.type | TEXT / QUIZ / TOOL_STATUS / HINT / RECOMMENDATION / SYSTEM / LEARNING_SUMMARY | `messages.type` CHECK |
| QuizInteraction.type | HINT_REQUEST / HINT_RESPONSE / QUESTION_ASK / TEACHER_REPLY / ANSWER_SUBMIT / ANSWER_RESULT | `quiz_interactions.interaction_type` CHECK |
| ProfileInsight.level | 偏弱 / 一般 / 较稳定 / 较强 / 仍需观察 | `profile_insights.level` CHECK |
| QuizQuestion.type | SINGLE_CHOICE / MULTIPLE_CHOICE / TRUE_FALSE / FILL_BLANK | `quiz_questions.question_type` CHECK |
| grade | int 1~12（展示字符串不入库） | `student_profiles.grade` CHECK |
| 幂等 | Idempotency-Key (actor_id, actor_type, key) 24h | `idempotency_keys` |

---

## 9. 风险与歧义记录（已裁决 / 仍待定）

1. **级联删除策略**（已裁决）：审计链相关 FK（LearningEvent / QuizSession / Messages 等）一律 `RESTRICT`，隐私删除走独立脱敏流程，不物理级联；脱敏流程细节于 Phase 12 隐私专项再定稿。
2. **jsonb 引用 vs 物理关联表**（仍待定）：`knowledge_point_ids` 等 N:M 当前维持 jsonb 方案；Phase 8 依据查询模式再裁决是否提升为物理关联表（如 `chapter_knowledge_points`）。
3. **`TEXT_SELECTED` 事件枚举**（已裁决）：0-C 已补录，0-D/0-E CHECK 与本表一致。
4. **部分唯一索引 `learning_sessions UNIQUE(student_id) WHERE status='ACTIVE'`**（已裁决：采纳）：保留该部分唯一索引，数据库层落实「同一学生最多一个 ACTIVE 时段」。
5. **`idempotency_keys` 作用域**（已裁决）：已扩展为 `(actor_id, actor_type, key)`，覆盖 STUDENT/ADMIN 两类端点幂等（0-D §1.7 已同步）。
6. **分区时机**（仍待定）：learning_events/messages/quiz_interactions 月分区仅标注；Phase 2 依据数据量评估后再定分区键与归档流程，MVP 不分区。
7. **`conversations.conversation_summary` 冗余列**（已裁决）：冗余列已移除，摘要由 JOIN `conversation_summaries` 提供。
8. **`book_progress.student_id` CASCADE → RESTRICT**（已裁决）：已统一为 RESTRICT，§3.11 与 §5.1 同步。
