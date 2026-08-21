# K12 AI 数字教师 V3——项目架构设计 v0.1

> 状态：架构基线  
> 适用阶段：V3 MVP → 比赛版本 → 后续可演进版本  
> 核心原则：**先产品体验，后服务扩展；成熟 Runtime + 自研教育 Domain；PostgreSQL 为事实源；Agent 不侵入业务核心。**

---

## 1. 文档目的

本文用于统一 K12 AI 数字教师 V3 的技术架构与开发边界，作为后续：

- 前端实现；
- 后端 API 设计；
- 数据库设计；
- Agent / Skill 开发；
- 长期记忆系统；
- Quiz Session；
- RAG / Knowledge；
- 语音交互；
- 测试与部署；

的共同基线。

本文不追求一次性设计完整的大型平台，而是优先保证：

1. V3 MVP 可以快速跑通；
2. AI Teacher 的核心能力可持续演进；
3. 业务 Domain 不被某个模型、Agent 框架、云厂商绑定；
4. 当前架构能够支撑未来增加教师角色、更多课程、更多 Skill 与更复杂的学习数据。

---

# 2. 产品架构目标

V3 的技术架构必须直接服务以下产品能力：

- Grade 1–12 学生体系；
- 可扩展 AI Teacher Role；
- 同一 Conversation 连续上下文；
- 长期 Student Memory；
- Screen Context 页面感知；
- AI 桌虫全局存在；
- 文本 AI 对话；
- 实时语音对话；
- AI 主动提问；
- 分层 Hint；
- Quiz Skill 生成结构化测验；
- Quiz Session 永久保存；
- 历史测验与互动记录；
- AI 学习画像；
- Knowledge / RAG；
- 管理端内容上传；
- 后台异步解析与索引。

系统本质不是“课程网站 + 聊天框”，而是：

```text
Learning Platform
        +
Context-aware AI Teacher
        +
Long-term Student Memory
        +
Structured Assessment
```

---

# 3. 总体架构原则

## 3.1 产品先于数据库

开发顺序保持：

```text
Product UX
↓
Frontend Domain Model
↓
API Contract
↓
Backend Domain
↓
Database Schema
```

避免：

```text
先设计大量表
↓
再反推产品
```

---

## 3.2 PostgreSQL 是 Source of Truth

核心业务数据必须持久化到 PostgreSQL。

包括：

- User；
- Student Profile；
- Conversation；
- Message；
- Quiz Session；
- Quiz Answer；
- Student Memory；
- Learning Event；
- Book / Chapter；
- Recommendation；
- Knowledge metadata。

Redis 不能成为唯一数据源。

原则：

```text
Redis 可以丢
PostgreSQL 不能丢
```

---

## 3.3 Agent Runtime 与教育业务解耦

不从零开发完整通用 Agent Framework。

采用：

```text
自研轻量 Teacher Agent Runtime
+
自研 Teacher Agent Domain
```

实际运行时由 `backend/app/ai/` 的 Provider 工厂、
`modules/conversation/service.py` 的 TeacherContext 组装，
以及 `modules/quiz/skill.py` 的结构化输出共同构成。
PydanticAI 保留为可选演进方向，不构成当前实现的缺失。

---

## 3.4 模型供应商必须可替换

业务代码不能直接依赖：

- DeepSeek；
- Qwen；
- 某个 ASR；
- 某个 TTS。

统一通过 Provider Gateway。

---

## 3.5 AI 结果必须经过 Schema 验证

涉及正式业务状态的 AI 输出不能直接使用自然语言。

例如：

- Quiz；
- Memory Update；
- Learning Insight；
- Recommendation；
- Structured Feedback。

必须：

```text
LLM
↓
Pydantic Schema
↓
Validation
↓
Domain Service
↓
Persistence
```

---

# 4. 技术栈总览

| 层 | 技术 | 主要原因 |
|---|---|---|
| 前端框架 | React 19 + TypeScript | 高交互、组件化、类型安全 |
| 构建 | Vite | SPA 开发简单快速 |
| 路由 | React Router | 成熟、足够支撑学生端与管理端 |
| 样式 | Tailwind CSS | 快速建立自定义 Design System |
| UI Primitive | Radix UI | 行为与无障碍成熟，视觉完全自控 |
| 动画 | Motion + CSS | 桌虫、面板、交互动画 |
| Server State | TanStack Query | API 缓存、请求、Mutation |
| UI State | Zustand | 桌虫、聊天面板、语音 UI 等 |
| 后端 | FastAPI | Python AI 生态、SSE、WebSocket |
| Schema | Pydantic | API 与 LLM 结构化验证 |
| ORM | SQLAlchemy 2 | 清晰的数据访问层 |
| Migration | Alembic | 数据库 Schema 版本管理 |
| 主数据库 | PostgreSQL 18 | 核心关系业务事实源 |
| 向量 | pgvector | Knowledge + Memory 向量检索 |
| Cache / Ephemeral | Redis | Cache、Lock、Rate Limit、临时状态 |
| Object Storage | S3-Compatible Adapter | MinIO / OSS / S3 可替换 |
| Agent Runtime | 自研轻量 Teacher Agent Runtime | Provider 工厂、TeacherContext、Structured Output |
| Agent Domain | 自研 | Teacher / Memory / Quiz / Persona |
| AI Provider | Gateway Adapter | LLM / Embedding / ASR / TTS 解耦 |
| 文本流 | SSE / Event Stream | AI Chat 流式输出 |
| 语音流 | WebSocket | 实时双向音频 |
| Background Job | Worker + PostgreSQL Job Table | PDF、Embedding、Memory 等异步处理 |
| 前端测试 | Vitest + Playwright | 单元 + 浏览器真流程 |
| 后端测试 | Pytest | Domain / API / Agent |
| 部署 | Docker Compose | 开发与比赛环境简单稳定 |

---

# 5. 总体系统架构

```text
┌─────────────────────────────────────────────────────┐
│                  React Web Client                   │
│                                                     │
│  Home / Library / Learn / Quiz / Profile / Admin   │
│                                                     │
│  Floating AI Companion + Chat + Voice + Quiz UI    │
└───────────────┬────────────────┬────────────────────┘
                │                │
              REST          SSE / WebSocket
                │                │
                └───────┬────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│                    FastAPI API                      │
│                                                     │
│ Identity / Content / Learning / Conversation        │
│ Assessment / Memory / Knowledge / Personalization  │
└───────────────────────┬─────────────────────────────┘
                        │
         ┌──────────────┼─────────────────┐
         ↓              ↓                 ↓
  Domain Services   Teacher Agent      Job Service
                        │                 │
              ┌─────────┼─────────┐       ↓
              ↓         ↓         ↓     Worker
           Context    Skills   Provider   │
              │         │       Gateway   │
              └─────────┼─────────┘       │
                        ↓                 │
         ┌──────────────┼─────────────────┤
         ↓              ↓                 ↓
   PostgreSQL         Redis        Object Storage
       │
    pgvector
       │
 ┌─────┴────────┐
 ↓              ↓
Memory       Knowledge
```

---

# 6. 前端架构

## 6.1 前端定位

前端不是简单展示页面，而是整个 AI Teacher 体验的主要承载层。

必须优先跑通：

```text
登录
→ 首页
→ 书库
→ 章节学习
→ 桌虫
→ 连续聊天
→ 页面上下文
→ Quiz
→ 历史测验
→ 学习画像
→ Memory
→ Teacher Role 切换
```

---

## 6.2 前端职责

前端负责：

- 页面渲染；
- Screen Context 收集；
- 桌虫渲染与拖拽；
- AI Chat UI；
- SSE 事件消费；
- Voice WebSocket；
- Quiz Interactive UI；
- 本地交互状态；
- API 数据查询；
- 浏览器权限；
- 响应式布局。

前端不负责：

- 长期 Memory 判断；
- Quiz 正确答案可信保存；
- Agent Tool 业务执行；
- Knowledge 检索；
- Learning Profile 最终更新；
- 权限安全判定。

---

# 7. 前端状态边界

## 7.1 TanStack Query

用于所有 Server State：

```text
Student
Books
Chapters
Conversation History
Quiz History
Learning Profile
Memories
Recommendations
Admin Resources
```

---

## 7.2 Zustand

仅管理客户端 UI / Runtime State：

```text
Companion Position
Companion Animation State
Chat Panel Open / Close
Voice UI State
Selected Teacher Role UI
Current Temporary Interaction
Local Draft
```

禁止将所有 API 数据同步复制进 Zustand。

原则：

```text
服务器拥有的数据
→ TanStack Query

浏览器当前交互状态
→ Zustand
```

---

# 8. Screen Context System

AI 必须知道学生当前正在看什么。

前端每个重要页面提供统一结构：

```ts
interface ScreenContext {
  route: string
  pageType: string

  bookId?: string
  chapterId?: string
  chapterTitle?: string

  visibleSection?: string
  selectedText?: string

  knowledgePoints?: string[]
  actions?: string[]
}
```

例如：

```json
{
  "route": "/learn/book/12/chapter/4",
  "pageType": "chapter_reader",
  "bookId": "12",
  "chapterId": "4",
  "chapterTitle": "什么是机器学习",
  "knowledgePoints": [
    "machine_learning",
    "training_data"
  ],
  "visibleSection": "监督学习",
  "selectedText": null
}
```

Screen Context 是 TeacherContext 的一个输入，不直接等于 Prompt。

---

# 9. AI 桌虫架构

桌虫分为两层。

## 9.1 Companion UI

负责：

- Sprite / PNG Sequence；
- CSS Animation；
- Motion 拖拽；
- 动作状态；
- 点击；
- 面板定位；
- 嘴型；
- 表情。

---

## 9.2 Teacher Interaction

负责：

- Chat；
- Voice；
- Context Action；
- Quiz UI；
- Hint；
- Recommendation；
- Learning State。

角色渲染与 Agent Runtime 必须解耦。

未来：

```text
Sprite
→ Live2D
→ Spine
→ 3D
```

不应该影响 Teacher Agent。

---

# 10. 后端架构原则

后端使用 Domain Service 架构。

Router 只负责：

```text
HTTP Input
↓
Validation
↓
调用 Domain Service
↓
HTTP Output
```

禁止：

```text
Router
├── 直接写复杂 SQL
├── 直接拼 Agent Prompt
├── 直接执行 Memory 规则
└── 直接处理 Knowledge Pipeline
```

---

# 11. 后端核心 Domain

建议划分：

```text
Identity
Content
Learning
Teacher
Conversation
Assessment
Memory
Personalization
Knowledge
Admin
Storage
Jobs
```

---

# 12. Teacher Agent 架构

正式采用路线图 §2.3 的自研轻量 Teacher Agent Runtime：

```text
backend/app/ai/ Provider Factory
+
ConversationService TeacherContext
+
QuizSkill Structured Output
```

项目自己负责：

- TeacherContext；
- Persona；
- Teacher Role；
- Student Memory；
- Quiz Skill；
- Hint；
- Knowledge Search；
- Learning Profile；
- Recommendation；
- Domain Persistence。

当前不引入 `pydantic-ai`。PydanticAI 仅作为可选演进方向，
不构成当前实现的缺失。

---

# 13. Teacher Agent 核心结构

```text
TeacherAgentService
│
├── TeacherContextBuilder
│
├── PersonaResolver
│
├── Teacher Agent Runtime
│   └── Provider Factory（`backend/app/ai/`）
│
├── ToolRegistry
│
├── SkillRegistry
│
├── AgentEventMapper
│
└── RunRecorder
```

---

# 14. TeacherContext

每次 Teacher Agent 调用前统一生成：

```text
TeacherContext
├── Student
│   ├── student_id
│   ├── grade
│   ├── age
│   └── preferences
│
├── TeacherRole
│   ├── role_id
│   ├── persona
│   ├── teaching_style
│   └── age_adaptation
│
├── CurrentScreen
│   ├── page
│   ├── book
│   ├── chapter
│   ├── visible_content
│   └── selected_content
│
├── LearningState
│   ├── recent_errors
│   ├── recent_quizzes
│   └── recent_progress
│
├── Memory
│   ├── profile
│   ├── preferences
│   └── relevant_episodes
│
└── Conversation
    ├── recent_messages
    └── summary
```

原则：

> 不允许由 Controller / Router 临时拼 Prompt。

所有 Agent 上下文通过 Context Builder 统一构造。

---

# 15. Persona 架构

Persona 分层：

```text
Teacher Base Persona
+
Teacher Character Persona
+
Student Grade Persona
+
Student Preference
+
Current Learning Context
```

Teacher Role 本身可以增加：

```text
TeacherRole
├── role_id
├── name
├── avatar
├── sprite_assets
├── voice
├── persona
├── tone
├── teaching_style
├── age_adaptation_rules
└── interaction_style
```

学生长期学习数据属于 Student，而不属于 TeacherRole。

切换 Teacher Role：

```text
只改变呈现 / Persona
不重置 Student Memory
```

---

# 16. Skills 架构

Skill 是带有明确业务规则与 Schema 的能力。

建议首版：

```text
skills/
├── quiz/
├── hint/
├── knowledge/
├── memory/
├── recommendation/
└── learning/
```

主要能力：

```text
create_quiz()
submit_quiz_answer()
request_quiz_hint()

search_knowledge_base()

get_student_profile()
get_learning_history()

update_student_memory()

get_quiz_history()
get_book_progress()

recommend_next_learning()
```

---

# 17. Quiz Skill

Quiz 是正式业务对象，不能只是 LLM 文本。

流程：

```text
Student / Teacher
↓
create_quiz
↓
Quiz Skill
↓
LLM Structured Output
↓
Pydantic Validation
↓
Assessment Domain
↓
Create QuizSession
↓
Persist Question Snapshot
↓
Return Quiz Event
↓
Frontend Quiz UI
```

---

# 18. Quiz Schema 原则

示例：

```python
class QuizQuestion(BaseModel):
    question_id: str
    type: str
    stem: str
    options: list
    answer: dict
    explanation: str
    source_context: dict
    interaction_policy: InteractionPolicy
```

正式 Quiz 创建后必须保存 Snapshot。

禁止在历史详情页重新让 AI 生成旧题。

---

# 19. Quiz Session

核心实体：

```text
QuizSession
├── quiz_id
├── student_id
├── conversation_id
├── teacher_role_id
├── book_id
├── chapter_id
├── generated_at
├── questions_snapshot
├── result_summary
├── duration
├── ai_feedback
├── model_info
└── skill_version
```

相关实体：

```text
QuizQuestion
QuizAnswer
QuizInteraction
```

---

# 20. Quiz Interaction

学生答题期间仍然可以和 AI 对话。

记录：

```text
quiz_session_id
question_id
student_answer
hint_level
hint_messages
teacher_messages
answer_result
```

这样实现：

```text
自然 AI 对话体验
+
正式 Assessment 数据
```

---

# 21. Hint Skill

Hint 必须与 Quiz Session 联动。

流程：

```text
request_quiz_hint
↓
读取当前 Quiz / Question
↓
读取已使用 hint_level
↓
Hint Skill
↓
生成下一级 Hint
↓
保存 Interaction
↓
返回 Agent Event
```

建议：

```text
Level 1
轻提示

Level 2
明显提示

Level 3
分步骤提示

必要时
完整讲解
```

---

# 22. Conversation 架构

Conversation 负责当前一段连续对话。

```text
Conversation
├── conversation_id
├── student_id
├── teacher_role_id
├── created_at
├── updated_at
└── status
```

```text
Message
├── message_id
├── conversation_id
├── role
├── content
├── message_type
├── metadata
└── created_at
```

---

# 23. Conversation Memory

短对话：

```text
最近完整 Messages
```

长对话：

```text
Recent Messages
+
Conversation Summary
+
必要的历史消息检索
```

Conversation Memory 解决：

> “刚刚聊了什么？”

不负责解决长期学生画像。

---

# 24. Long-term Memory 架构

首版正式定义：

```text
Conversation Memory
Profile Memory
Learning Memory
Preference Memory
Episodic Memory
```

---

# 25. Memory Update Pipeline

禁止每条聊天都直接写长期 Memory。

采用：

```text
Learning Event
↓
Memory Candidate
↓
Evidence Aggregation
↓
Confidence / Rule Check
↓
Memory Update
↓
Student Profile / Episode
```

原则：

```text
Temporary Signal
↓
Evidence Count
↓
Stable Profile
```

一次答错不能直接得出：

> 学生能力弱。

---

# 26. Memory 数据形态

## Profile Memory

稳定信息：

```text
grade
age
language
learning_goal
current_teacher_role
```

## Preference Memory

```text
preferred_explanation_style
preferred_difficulty
preferred_session_length
voice_preference
```

## Episodic Memory

例如：

```text
2026-08-20

学生学习“机器学习”
对训练数据产生疑惑
通过“小狗训练”的比喻后理解
```

---

# 27. Memory Retrieval

每次 TeacherContext 构建时：

```text
Current Query
+
Screen Context
+
Current Course
+
Recent Learning State
↓
Memory Retrieval
↓
Relevant Memories
```

禁止：

```text
把全部历史聊天
+
全部 Memory
+
全部测验
全部塞给 LLM
```

---

# 28. pgvector 使用边界

pgvector 用于：

```text
KnowledgeChunk Embedding
StudentEpisode Embedding
可检索 Memory
```

PostgreSQL 普通关系表继续保存：

```text
Student
Conversation
Quiz
Book
LearningEvent
```

MVP 不单独引入：

- Milvus；
- Qdrant；
- Elasticsearch Vector；
- 独立 Vector Service。

---

# 29. Knowledge / RAG 架构

知识来源：

```text
PDF
Markdown
TXT
整理后的网页资料
```

处理流程：

```text
Upload
↓
Object Storage
↓
KnowledgeResource
↓
Background Job
↓
Parse
↓
Chunk
↓
Metadata
↓
Embedding
↓
pgvector
↓
Ready
```

---

# 30. Knowledge Resource

建议：

```text
KnowledgeResource
├── id
├── source_name
├── source_url
├── author
├── license
├── copyright_status
├── storage_key
├── status
└── uploaded_at
```

```text
KnowledgeChunk
├── id
├── resource_id
├── content
├── metadata
├── knowledge_point_id
└── embedding
```

---

# 31. Worker 架构

Worker 是正式架构组件。

> 落地状态（P1-1）：已实现 PostgreSQL 表驱动的独立 Worker 与 Job 生命周期；知识资源 PDF/Markdown/TXT/HTML 处理、会话摘要和记忆合并均可由 Worker 执行。

不要在 HTTP Request 中执行重任务。

Worker 首版负责：

```text
PDF Parse
Content Chunk
Embedding
Knowledge Index
Conversation Summary
Memory Consolidation
```

学习画像刷新仍沿用现有记忆管线；推荐刷新当前采用学生端 GET 的惰性规则生成，暂不作为 Worker Job。

---

# 32. Job 生命周期

建议统一：

```text
queued
↓
running
↓
success
```

失败：

```text
running
↓
failed
```

建议记录：

```text
job_id
job_type
status
attempt
payload
error
created_at
started_at
finished_at
```

---

# 33. Redis 职责

> 落地状态（P1-2）：Redis Cache 与 Conversation Distributed Lock 已实现；Redis 不可用时保留本地锁降级。Worker Job Queue 当前由 PostgreSQL `background_jobs` 表承载。

Redis 负责：

```text
Cache
Distributed Lock
Rate Limit
Ephemeral Session
Temporary Agent State
WebSocket Connection Metadata
Pub/Sub
```

Redis 不负责长期唯一保存：

```text
Conversation
Quiz
Memory
Student Profile
Learning Event
```

---

# 34. Object Storage

统一定义：

```text
ObjectStorage
```

接口例如：

```text
put()
get()
delete()
copy()
presign()
```

Adapter：

```text
MinIOAdapter
S3Adapter
OSSAdapter
```

环境：

```text
Development
→ MinIO

Production
→ OSS / S3
```

业务 Domain 不允许直接调用 MinIO SDK。

---

# 35. AI Provider Gateway

拆成四类 Provider。

```text
AIProviderGateway
│
├── LLMProvider
├── EmbeddingProvider
├── ASRProvider
└── TTSProvider
```

例如：

```text
LLM
→ DeepSeek / Qwen

Embedding
→ Qwen Embedding

ASR
→ 阿里云

TTS
→ 阿里云
```

可以组合使用，不要求同一供应商。

---

# 36. LLM Provider

统一输入：

```text
ModelRequest
Messages
Tools
Structured Output Schema
Temperature / Config
```

统一输出：

```text
ModelResponse
Usage
ToolCall
StructuredData
ProviderMetadata
```

业务代码不得直接出现大量：

```text
if provider == "deepseek"
```

---

# 37. 文本 AI 流

文本交互：

```text
POST Message
↓
Teacher Agent
↓
Streaming
↓
SSE / Event Stream
↓
Frontend
```

事件建议：

```text
message_start
text_delta
tool_start
tool_result
quiz_created
hint_created
message_end
error
```

前端不要只按纯 token 字符串设计。

需要支持结构化 Agent Event。

---

# 38. Voice 架构

流程：

```text
Browser Microphone
↓
WebSocket
↓
ASR
↓
Student Text
↓
Teacher Agent
↓
LLM
↓
TTS
↓
Audio
↓
Browser
```

语音模式与文本模式共享：

```text
Conversation
TeacherContext
Memory
Quiz
Knowledge
```

语音不是独立 Chatbot。

---

# 39. API Contract

后端使用 Pydantic 作为 API Contract 来源。

建议：

```text
Pydantic
↓
FastAPI OpenAPI
↓
Generate TypeScript Client / Types
↓
React
```

目标：

```text
Backend Schema
=
OpenAPI Contract
=
Frontend API Types
```

避免前后端手工维护两套互相漂移的 Model。

---

# 40. 核心数据库对象

首版建议：

```text
User

StudentProfile
StudentPreference
StudentMemory
StudentEpisode

TeacherRole

Conversation
Message
ConversationSummary

Book
Chapter
ContentBlock
KnowledgePoint

LearningSession
LearningEvent
BookProgress

QuizSession
QuizQuestion
QuizAnswer
QuizInteraction

Recommendation

KnowledgeResource
KnowledgeChunk

BackgroundJob
```

---

# 41. 数据库边界

数据库层：

```text
SQLAlchemy Model
Repository
Unit of Work / Session
```

Domain Service 不直接依赖 HTTP。

Router 不直接编写复杂 ORM 流程。

---

# 42. SQLAlchemy Async 原则

使用：

```text
SQLAlchemy 2 AsyncSession
```

遵守：

```text
1 Request / Task
=
1 AsyncSession
```

不跨并发 Task 共享 Session。

---

# 43. 推荐后端目录

```text
backend/
├── app/
│   ├── main.py
│   │
│   ├── api/
│   │   ├── auth.py
│   │   ├── books.py
│   │   ├── learning.py
│   │   ├── conversations.py
│   │   ├── quizzes.py
│   │   ├── profile.py
│   │   ├── memories.py
│   │   └── admin.py
│   │
│   ├── domains/
│   │   ├── identity/
│   │   ├── content/
│   │   ├── learning/
│   │   ├── conversation/
│   │   ├── assessment/
│   │   ├── memory/
│   │   ├── personalization/
│   │   └── knowledge/
│   │
│   ├── ai/
│   │   ├── teacher/
│   │   │   ├── service.py
│   │   │   ├── context.py
│   │   │   └── persona.py
│   │   │
│   │   ├── runtime/
│   │   │   ├── teacher_runtime.py
│   │   │   └── events.py
│   │   │
│   │   ├── skills/
│   │   │   ├── quiz/
│   │   │   ├── hint/
│   │   │   ├── memory/
│   │   │   ├── knowledge/
│   │   │   └── recommendation/
│   │   │
│   │   └── providers/
│   │       ├── llm/
│   │       ├── embedding/
│   │       ├── asr/
│   │       └── tts/
│   │
│   ├── storage/
│   │   ├── service.py
│   │   └── adapters/
│   │
│   ├── jobs/
│   │   ├── service.py
│   │   ├── worker.py
│   │   └── handlers/
│   │
│   ├── db/
│   │   ├── models/
│   │   ├── repositories/
│   │   └── session.py
│   │
│   ├── schemas/
│   ├── config/
│   └── common/
│
├── alembic/
└── tests/
```

---

# 44. 推荐前端目录

```text
frontend/
├── src/
│   ├── app/
│   │   ├── router/
│   │   ├── providers/
│   │   └── layouts/
│   │
│   ├── pages/
│   │   ├── home/
│   │   ├── library/
│   │   ├── book/
│   │   ├── learn/
│   │   ├── quizzes/
│   │   ├── profile/
│   │   ├── settings/
│   │   └── admin/
│   │
│   ├── features/
│   │   ├── companion/
│   │   ├── chat/
│   │   ├── voice/
│   │   ├── quiz/
│   │   ├── screen-context/
│   │   ├── learning-profile/
│   │   └── memory/
│   │
│   ├── entities/
│   │   ├── student/
│   │   ├── teacher-role/
│   │   ├── book/
│   │   ├── conversation/
│   │   └── quiz/
│   │
│   ├── api/
│   │   ├── client/
│   │   └── generated/
│   │
│   ├── stores/
│   ├── components/
│   │   ├── ui/
│   │   └── shared/
│   │
│   ├── styles/
│   └── types/
│
└── tests/
```

---

# 45. 前端组件层次

建议：

```text
components/ui
```

只放 Design System 基础组件：

```text
Button
Dialog
Popover
Sheet
Tooltip
Tabs
Input
Card
```

业务组件：

```text
features/quiz
features/chat
features/companion
```

避免 UI Primitive 和业务逻辑混在一起。

---

# 46. 测试策略

## 前端

Vitest：

- Utility；
- Store；
- Hook；
- Quiz State；
- Context Builder。

Playwright：

```text
登录
→ 首页
→ 进入课程
→ 打开桌虫
→ 多轮聊天
→ 创建 Quiz
→ 回答
→ 查看 History
```

---

## 后端

Pytest：

```text
Domain Unit Test
API Test
Repository Test
Agent Contract Test
Skill Test
Memory Rule Test
Quiz Snapshot Test
Knowledge Pipeline Test
```

---

# 47. Agent 测试原则

不要只测试：

> “模型回答好不好”。

重点测试：

```text
Tool 是否正确触发
Schema 是否正确
Quiz 是否落库
Hint Level 是否正确
Memory 是否满足证据规则
Context 是否包含正确页面信息
Provider Failover 是否正确
```

对于 LLM：

```text
Mock Provider
+
少量真实模型 E2E
```

---

# 48. Docker Compose

MVP 开发环境：

```text
frontend
backend
worker
postgres
redis
minio
```

可选：

```text
nginx
```

---

# 49. 部署拓扑

比赛阶段：

```text
Docker Compose
```

即可。

不要提前引入：

- Kubernetes；
- Service Mesh；
- Kafka；
- 多 Region；
- 大型微服务。

---

# 50. MVP 服务边界

首版建议仍然：

```text
Modular Monolith
```

而不是：

```text
Identity Service
Content Service
Memory Service
Quiz Service
...
每个都独立容器
```

Domain 可以逻辑隔离，但运行时暂时保持：

```text
FastAPI API
+
Worker
```

两个主要进程。

---

# 51. 为什么不做微服务

当前用户量、团队规模、比赛阶段都不需要微服务成本。

优先：

```text
清晰 Domain Boundary
>
物理服务拆分
```

未来真正需要时再按 Domain 抽出服务。

---

# 52. MVP 明确不做

架构阶段不要提前建设：

```text
复杂 Multi-Agent
通用 Agent Framework
Kubernetes
Kafka
独立 Vector DB
Event Sourcing
CQRS
GraphQL
完整 Live2D Runtime
重型 Workflow Engine
全学科知识图谱
复杂微服务
```

除非后续出现明确业务需求。

---

# 53. Agent 演进路线

## Phase 1

```text
Single Teacher Agent
+
Tools
+
Skills
```

## Phase 2

增加：

```text
Background Memory Jobs
Recommendation
Reviewer
```

## Phase 3

只有当真正出现复杂长流程时，再评估：

```text
LangGraph
Workflow Engine
Multi-Agent
```

---

# 54. 数据架构演进

Phase 1：

```text
PostgreSQL
+
pgvector
+
Redis
```

Phase 2：

数据量明显增长后评估：

- 向量索引优化；
- Search Service；
- 分离 Analytics；
- Object Storage CDN。

不要提前拆。

---

# 55. Agent Framework 替换原则

业务层不得直接高度绑定任何具体 Agent Runtime（包括未来可选的 PydanticAI）。

通过：

```text
AgentRuntimeAdapter
```

隔离。

当前：

```text
TeacherContext + QuizSkill
↓
Provider Factory（`backend/app/ai/`）
↓
LLM / Embedding / ASR / TTS Provider
```

未来可以替换或引入：

```text
PydanticAI
OpenAI Agents SDK
LangGraph
Custom Runtime
```

而不用重写：

```text
QuizService
MemoryService
ConversationService
KnowledgeService
TeacherContext
```

---

# 56. Provider 替换原则

同样：

```text
LLMProvider
EmbeddingProvider
ASRProvider
TTSProvider
```

全部通过 Interface。

避免 Agent Domain 直接依赖厂商 SDK。

---

# 57. 关键请求链路：普通 AI 对话

```text
Student Message
↓
Conversation API
↓
Persist User Message
↓
TeacherContextBuilder
↓
Memory Retrieval
↓
Screen Context
↓
自研 Teacher Agent Runtime
↓
LLM
↓
Tool Calls
↓
Agent Events
↓
SSE
↓
Frontend
↓
Persist Assistant Message
```

---

# 58. 关键请求链路：Quiz

```text
Student:
“给我出三道题”
↓
Teacher Agent
↓
create_quiz Skill
↓
Quiz Structured Output
↓
Pydantic Validate
↓
AssessmentService
↓
QuizSession + Snapshot
↓
quiz_created Event
↓
Frontend Interactive Quiz
```

---

# 59. 关键请求链路：上传知识资料

```text
Admin Upload PDF
↓
StorageService
↓
Object Storage
↓
KnowledgeResource
↓
Create Job
↓
Worker
↓
Parse
↓
Chunk
↓
Embedding
↓
pgvector
↓
Resource = ready
```

---

# 60. 关键请求链路：长期 Memory

```text
Student Learning
↓
LearningEvent
↓
Memory Candidate
↓
Worker / MemoryService
↓
Evidence Check
↓
Structured Memory Update
↓
StudentMemory / StudentEpisode
↓
后续 TeacherContext 可检索
```

---

# 61. 安全边界

AI 不直接拥有数据库任意写权限。

Tool：

```text
update_student_memory()
```

不应该：

```text
LLM
↓
直接执行任意 SQL
```

所有写操作必须经过 Domain Service。

同样：

```text
create_quiz()
```

必须进入 Assessment Domain。

---

# 62. 可观测性

至少记录：

```text
request_id
conversation_id
agent_run_id
provider
model
tool_calls
skill_version
latency
token_usage
error
```

Quiz 额外保存：

```text
model_info
skill_version
```

方便比赛演示、Bug 定位、AI 行为复核。

---

# 63. 版本化原则

以下内容需要版本号：

```text
Quiz Skill
Memory Rule
Prompt Profile
Teacher Persona
AI Provider Config
Knowledge Processing Pipeline
```

目的：

> 历史 Quiz 必须知道当时由哪一版规则生成。

---

# 64. 开发阶段建议

## Phase 0：Domain Contract

先定义：

```text
Student
TeacherRole
ScreenContext
Conversation
QuizSession
QuizQuestion
StudentMemory
LearningEvent
Recommendation
```

---

## Phase 1：纯前端体验

Mock API 跑通：

```text
首页
书库
学习页
桌虫
聊天
Quiz
历史记录
画像
Memory
Role 切换
```

---

## Phase 2：核心后端

实现：

```text
Auth
Student
Book
Conversation
Quiz Persistence
TeacherRole
```

---

## Phase 3：Teacher Agent

接入：

```text
自研轻量 Teacher Agent Runtime
Provider Gateway
TeacherContext
Streaming
Tools
```

---

## Phase 4：Quiz / Memory

实现：

```text
Quiz Skill
Hint Skill
Quiz History
LearningEvent
Memory Pipeline
```

---

## Phase 5：Knowledge / Voice

实现：

```text
Knowledge Pipeline
pgvector
RAG
ASR
TTS
WebSocket Voice
```

---

## Phase 6：比赛收尾

重点：

```text
稳定性
演示数据
E2E
UI
动画
错误恢复
日志
Docker Compose
```

---

# 65. 最终架构基线

V3 当前正式推荐：

```text
Frontend
React 19
TypeScript
Vite
React Router
Tailwind
Radix UI
Motion
TanStack Query
Zustand

Backend
FastAPI
Pydantic
SQLAlchemy 2
Alembic

Data
PostgreSQL 18
pgvector
Redis
S3-Compatible Object Storage

AI
自研轻量 Teacher Agent Runtime
Custom Teacher Domain
Custom Skills
TeacherContext
Persona
Memory
Provider Gateway

Streaming
SSE / Event Stream
WebSocket Voice

Async
Worker
PostgreSQL Job Table

Test
Vitest
Playwright
Pytest

Deploy
Docker Compose
```

---

# 66. 最重要的架构决策

最终只需要记住以下十条：

1. **前端优先，先把完整学习体验跑通。**
2. **PostgreSQL 是业务事实源，Redis 只是辅助层。**
3. **采用自研轻量 Teacher Agent Runtime，PydanticAI 仅作为可选演进方向。**
4. **Teacher / Quiz / Memory / Persona / Context 是我们自己的核心 Domain。**
5. **正式 AI 业务输出必须经过 Pydantic Schema。**
6. **Agent 不能直接操作数据库，必须调用 Domain Tool / Service。**
7. **Memory 与 Knowledge 都可使用 pgvector，但关系数据仍归 PostgreSQL。**
8. **重任务交给 Worker，不占用 FastAPI 请求。**
9. **LLM / Embedding / ASR / TTS 必须通过 Provider Gateway 解耦。**
10. **MVP 保持 Modular Monolith，不提前微服务化。**

---

# 67. 一句话总结

> **K12 AI 数字教师 V3 采用 React + FastAPI + PostgreSQL/pgvector 为核心技术底座，以自研轻量 Teacher Agent Runtime 连接 Provider Gateway，并在其上实现 Teacher Context、Persona、Memory、Quiz Skills 与学习 Domain，通过 Worker、SSE/WebSocket 和统一数据契约构建一个可扩展、可测试、可长期演进的 AI 教育平台；PydanticAI 保留为可选演进方向。**
