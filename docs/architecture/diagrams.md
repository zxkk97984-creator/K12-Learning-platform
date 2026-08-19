# 霜铃 · K12 AI 数字教师 V3 — Architecture Diagrams（8 张）

> 状态：Phase 0 契约基线（Task 0-F）
> 版本：v0.1
> 日期：2026-08-19
> 输入基线：project-architecture.md（§5/§6/§10/§31/§35，图表权威）、domain-model.md（0-C，27 实体）、database-design.md（0-E，存储分层）、api-contract.md（0-D，模块/SSE/WS）、执行总控 §9.2 Task 0-F 与 §32/§33（参考）
> 阶段声明：**当前是 Phase 0 设计蓝图，不是最终状态**。图中标注「Phase 8/9/10/11」的元素均为后续 Phase 才实现；参考总控 §32 最终架构，但本文件与 0-C/0-D/0-E 的最新边界（27 实体、10 模块、存储分层）保持一致。
> 阅读方式：每张图前 2-3 句说明「表达什么、供谁看」；mermaid 全部为 `flowchart`，可直接渲染。

---

## 1. Overall（系统总览）

表达系统端到端拓扑：学生浏览器 → React SPA（页面 + 桌虫 + 对话面板 + Screen Context）→ FastAPI Modular Monolith（10 个业务模块）→ Teacher Agent Runtime → AI Providers，底层为 PostgreSQL/pgvector + Redis + Object Storage。供架构评审、Phase 1 前端与 Phase 2 后端搭建者看全貌；与 0-D 的模块划分、0-E 的存储分层严格一致。

```mermaid
flowchart TB
    STUDENT["学生 / 浏览器（Grade 1–12）"]

    subgraph WEB["React 19 SPA（Phase 1 起）"]
        PAGES["页面：Home / Library / Reader / Quizzes / Quiz Detail / Profile"]
        COMPANION["全局桌虫 Companion（角色 + 位置 + 面板 + Context Actions）"]
        CHAT["Conversation Panel（Chat + Quiz Card + Voice 入口）"]
        SCREEN["ScreenContextProvider（当前页面感知）"]
        ADMINWEB["Admin Console（Phase 10）"]
        PAGES --> COMPANION
        SCREEN --> CHAT
        COMPANION --> CHAT
    end

    subgraph API["FastAPI Modular Monolith"]
        IDENTITY["Identity / Auth"]
        STUDENTMOD["Students"]
        CONTENT["Content"]
        LEARNING["Learning"]
        CONVERSATION["Conversation"]
        ASSESSMENT["Assessment"]
        MEMORY["Memory"]
        KNOWLEDGE["Knowledge"]
        PERSONAL["Personalization"]
        ADMIN["Admin（Phase 10）"]
    end

    subgraph TEACHER["Teacher Agent Runtime"]
        PERSONA["PersonaEngine"]
        CONTEXT["ContextBuilder"]
        CONVMGR["ConversationManager"]
        MEMRET["MemoryRetriever"]
        SKILLS["SkillRegistry / SkillExecutor"]
        GATEWAY["ModelGateway（PydanticAI Adapter）"]
    end

    subgraph PROVIDERS["AI Providers（Gateway 可替换）"]
        LLM["LLM：DeepSeek / Qwen / Mock"]
        EMB["Embedding（Phase 8）"]
        ASR["ASR（Phase 9）"]
        TTS["TTS（Phase 9）"]
    end

    subgraph DATA["Data Infrastructure"]
        PG[("PostgreSQL（27 表）")]
        VECTOR[("pgvector（Phase 8）")]
        REDIS[("Redis")]
        STORAGE[("Object Storage：MinIO / OSS / S3")]
    end

    STUDENT --> WEB
    WEB -->|"REST / SSE / WebSocket"| API
    ADMINWEB -->|"REST（Admin-only）"| ADMIN
    CONVERSATION --> TEACHER
    MEMORY --> TEACHER
    KNOWLEDGE --> TEACHER
    ASSESSMENT --> TEACHER
    TEACHER --> SKILLS
    TEACHER --> GATEWAY
    GATEWAY --> LLM
    GATEWAY --> EMB
    GATEWAY --> ASR
    GATEWAY --> TTS
    API --> PG
    KNOWLEDGE --> VECTOR
    API --> REDIS
    CONTENT --> STORAGE
    KNOWLEDGE --> STORAGE
    MEMORY --> VECTOR
```

---

## 2. Frontend（前端架构）

表达 React SPA 的分层：App Root → Providers（Auth / TanStack Query / ScreenContext / Zustand）→ Router 页面 + 全局 Companion Layer → Features → 数据层（Mock Service Layer 与 ApiClient 的替换边界，总控 §27）。供 Phase 1 前端工程师使用；目录结构对应 project-architecture §6.3（app / pages / features / entities / shared / mocks）。

```mermaid
flowchart TB
    ROOT["App Root"]

    subgraph PROVIDERS2["Providers"]
        AUTH["AuthProvider（JWT 上下文）"]
        QUERY["TanStack Query（Server State）"]
        SCREENCTX["ScreenContextProvider"]
        ZUSTAND["Zustand（UI Runtime State）"]
    end

    subgraph ROUTER["Router（React Router）"]
        PAGE_HOME["Home"]
        PAGE_LIB["Library"]
        PAGE_BOOK["Book Detail"]
        PAGE_READER["Reader / Learn"]
        PAGE_QUIZ["Quizzes / Quiz Detail"]
        PAGE_PROFILE["Profile / Memories / Settings"]
        PAGE_ADMIN["Admin（Phase 10）"]
    end

    subgraph COMPANION_LAYER["Companion Layer"]
        SPRITE["Character / Sprite 动画"]
        POSITION["Position / 拖拽 / localStorage 持久化"]
        PANEL["Chat Panel"]
        VOICE_UI["Voice UI（Phase 9）"]
        CONTEXT_ACTIONS["Context Actions / Quick Actions"]
        QUIZCARD["Quiz Card（互动测验）"]
    end

    subgraph FEATURES["Features"]
        FEAT_QUIZ["features/quiz"]
        FEAT_CHAT["features/chat"]
        FEAT_COMPANION["features/companion"]
        FEAT_SCREEN["features/screen-context"]
        FEAT_MEMORY["features/learning-profile + memory"]
    end

    subgraph DATA_LAYER["Data Layer（Mock ↔ API 替换边界）"]
        MOCK["Mock Service Layer（Phase 1 全量 Mock）"]
        APICLIENT["ApiClient（Phase 2+，REST / SSE / WS）"]
        SERVICES["Service Interfaces（与 0-D DTO 对齐）"]
        ENTITIES["entities / types（与 0-C 对齐）"]
    end

    ROOT --> PROVIDERS2
    PROVIDERS2 --> ROUTER
    PROVIDERS2 --> COMPANION_LAYER
    ROUTER --> FEATURES
    COMPANION_LAYER --> FEATURES
    FEATURES --> DATA_LAYER
    SCREENCTX --> COMPANION_LAYER
    SCREENCTX --> FEATURES
    SERVICES -->|"实现（Phase 1）"| MOCK
    SERVICES -->|"实现（Phase 2+ 逐个替换，总控 §27）"| APICLIENT
    ENTITIES --> SERVICES
    ENTITIES --> APICLIENT
```

---

## 3. Backend（后端模块化单体）

表达 FastAPI Modular Monolith：Router 只做校验与转发，业务进入 10 个 Domain Modules，Teacher 模块接入 AI Runtime；Worker 承担异步任务；Infrastructure 提供数据库/缓存/存储/可观测性。供 Phase 2 后端工程师与代码评审使用；D10 安全边界（Skill → Pydantic → Validator → Domain Service → Transaction）明确画在 AI 与 Domain 之间。

```mermaid
flowchart TB
    REQ["HTTP / SSE / WebSocket 请求"]

    subgraph API_ROUTER["API Router（FastAPI，仅校验与转发）"]
        R_ID["/auth /me"]
        R_CONTENT["/books /chapters"]
        R_LEARN["/learning-sessions /learning-events"]
        R_CONV["/conversations（SSE）"]
        R_QUIZ["/quiz-sessions（幂等提交）"]
        R_MEM["/me/memories /insights"]
        R_KNOW["/knowledge（Phase 8）"]
        R_RECO["/me/recommendations"]
        R_ADMIN["/admin（Phase 10）"]
    end

    subgraph DOMAINS["Domain Modules（Modular Monolith）"]
        D_ID["Identity"]
        D_STUDENT["Students"]
        D_CONTENT["Content"]
        D_LEARN["Learning"]
        D_CONV["Conversation"]
        D_TEACHER["Teacher"]
        D_MEM["Memory"]
        D_ASSESS["Assessment"]
        D_KNOW["Knowledge"]
        D_PERSONAL["Personalization"]
        D_ADMIN["Admin"]
    end

    subgraph AI_RUNTIME["AI Runtime（Teacher Agent）"]
        AGENT["TeacherAgentService"]
        SKILLS2["Skills：quiz / hint / memory / knowledge / recommendation"]
        VALID["Pydantic Schema"]
        SEC["D10 安全边界：禁止 LLM 直接写库"]
        GATEWAY2["ModelGateway"]
    end

    subgraph PROVIDERS3["AI Providers"]
        P_LLM["LLM / Embedding / ASR / TTS（Gateway 可替换）"]
    end

    subgraph WORKER["Worker（异步）"]
        W_QUEUE["Redis Job Queue"]
        W_JOBS["PDF Parse / Chunk / Embedding / Memory Consolidation / Summary"]
    end

    subgraph INFRA["Infrastructure"]
        DB[("PostgreSQL / pgvector")]
        CACHE[("Redis")]
        OBJ[("Object Storage")]
        OBS["Observability（logs / traces / metrics）"]
    end

    REQ --> API_ROUTER
    API_ROUTER --> DOMAINS
    D_CONV --> AGENT
    D_MEM --> AGENT
    D_ASSESS --> AGENT
    D_KNOW --> AGENT
    D_TEACHER --> AGENT
    AGENT --> SKILLS2
    SKILLS2 --> VALID
    VALID --> SEC
    SEC --> DOMAINS
    GATEWAY2 --> P_LLM
    D_KNOW --> WORKER
    D_MEM --> WORKER
    D_CONV --> WORKER
    WORKER --> W_QUEUE
    W_QUEUE --> W_JOBS
    W_JOBS --> INFRA
    DOMAINS --> INFRA
```

---

## 4. Teacher Agent Runtime

表达 TeacherAgentService 的七个组成（总控 §13.3）：PersonaEngine、ContextBuilder、ConversationManager、MemoryRetriever、SkillRegistry、SkillExecutor、ModelGateway，加上 RunRecorder；输入侧展示 TeacherContext 的六类数据来源，输出侧展示 Skill → Pydantic → Validator → Domain Service → Transaction 的落库路径（D10）。供 Phase 4 Teacher Agent 实现者与 Skill 开发者使用。

```mermaid
flowchart TB
    MSG["学生消息 / Context Action / Quiz 请求"]

    subgraph AGENT4["TeacherAgentService"]
        PERSONA4["PersonaEngine"]
        CTX4["ContextBuilder"]
        CONV4["ConversationManager"]
        MEMRET4["MemoryRetriever"]
        SKILLREG4["SkillRegistry"]
        SKILLEXEC4["SkillExecutor"]
        GATEWAY4["ModelGateway / AgentRuntimeAdapter（PydanticAI）"]
        RUN4["RunRecorder"]
    end

    subgraph INPUTS["TeacherContext 输入（架构 §14）"]
        S_STUDENT["Student（grade / preferences）"]
        S_ROLE["TeacherRole（persona / grade_rules / sprite_manifest）"]
        S_SCREEN["CurrentScreen（0-D ScreenContext）"]
        S_LEARN["LearningState（recent events / quizzes / progress）"]
        S_MEM["Memory（profile / preferences / episodes）"]
        S_CONV["Conversation（recent_messages + summary）"]
    end

    subgraph SKILLSET4["Skills"]
        SK_QUIZ["create_quiz"]
        SK_HINT["request_quiz_hint"]
        SK_KNOW["search_knowledge_base"]
        SK_MEM["update_memory_candidate"]
        SK_RECO["recommend_next_learning"]
    end

    subgraph BOUNDARY4["D10 安全边界"]
        PYD["Pydantic Schema 校验"]
        VAL4["Validator / RuleChecker"]
    end

    subgraph DOMAIN4["Domain Services + Transaction"]
        DS_CONV["ConversationService"]
        DS_QUIZ["AssessmentService"]
        DS_MEM["MemoryService"]
    end

    P_LLM4["LLM Provider（DeepSeek / Qwen / Mock）"]
    OBS4["可观测性：agent_run_id / skill_version / token_usage"]

    MSG --> CONV4
    CTX4 --> PERSONA4
    CTX4 --> CONV4
    CTX4 --> MEMRET4
    CTX4 --> S_STUDENT
    CTX4 --> S_ROLE
    CTX4 --> S_SCREEN
    CTX4 --> S_LEARN
    CTX4 --> S_MEM
    CTX4 --> S_CONV
    CONV4 --> SKILLREG4
    MEMRET4 --> SKILLREG4
    SKILLREG4 --> SKILLEXEC4
    SKILLEXEC4 --> SKILLSET4
    SKILLEXEC4 --> GATEWAY4
    SKILLSET4 --> PYD
    PYD --> VAL4
    VAL4 --> DOMAIN4
    DOMAIN4 --> DS_CONV
    DOMAIN4 --> DS_QUIZ
    DOMAIN4 --> DS_MEM
    GATEWAY4 --> P_LLM4
    RUN4 --> OBS4
```

---

## 5. Quiz Skill Flow

表达一次正式测验从 Teacher Agent 到 QuizSession 落库的完整链路（总控 §15.2）：create_quiz → LLM 结构化输出 → QuizDraft → Schema 校验 → Rule 校验 → Reviewer → AssessmentService → 快照持久化 → quiz_created 事件 → 前端互动卡；并标注两条硬约束（提交幂等、历史只读快照）。供 Phase 6 Assessment/Quiz Skill 实现者与验收者使用。

```mermaid
flowchart TB
    AGENT5["Teacher Agent"]
    SKILL5["create_quiz Skill（InputSchema / Prompt / OutputSchema / Version）"]
    LLM5["LLM Structured Output"]
    DRAFT5["QuizDraft"]
    SCHEMA5["Pydantic Schema 校验"]
    RULE5["Rule Validation（题型 / 选项 / 难度 / 题数）"]
    REVIEW5["Reviewer"]
    ASSESS5["AssessmentService"]
    SESSION5["QuizSession + questions_snapshot 持久化"]
    EVENT5["quiz_created Agent Event / SSE"]
    UI5["前端 Interactive Quiz Card"]
    IDEM5["幂等：Idempotency-Key + (session, question, attempt_no) 唯一"]
    HISTORY5["历史详情：只读快照，不重新调用 LLM"]

    AGENT5 --> SKILL5
    SKILL5 --> LLM5
    LLM5 --> DRAFT5
    DRAFT5 --> SCHEMA5
    SCHEMA5 --> RULE5
    RULE5 --> REVIEW5
    REVIEW5 --> ASSESS5
    ASSESS5 --> SESSION5
    SESSION5 --> EVENT5
    EVENT5 --> UI5
    UI5 -->|"提交答案（幂等）"| ASSESS5
    SESSION5 --> IDEM5
    SESSION5 --> HISTORY5
```

---

## 6. Memory Pipeline

表达长期记忆的分层沉淀（总控 §16.2）：LearningEvent → MemoryEvidence → MemoryCandidate → 证据聚合/规则检查 → StudentMemory / ProfileInsight；强调「一次错误不得直接出结论」与 Conversation Memory 独立。供 Phase 7 Memory Pipeline 与画像实现者、产品验收者使用。

```mermaid
flowchart LR
    LE["LearningEvent（append-only 事实）"]
    EV["MemoryEvidence（证据聚合）"]
    MC["MemoryCandidate（LLM 提取候选，不直接可见）"]
    AGG["证据聚合 / 规则检查（证据量 + 置信）"]
    RULE["规则：一次错误不得直接得出「能力弱」"]
    SM["StudentMemory（稳定记忆，可被用户管理）"]
    PI["ProfileInsight（5 档定性，带证据）"]
    USERCTL["用户操作：确认 / 不完全正确 / 修改 / 忘记"]
    RETR["TeacherContext 检索"]
    CM["Conversation Memory（另一套系统）"]

    LE --> EV
    EV --> MC
    MC --> AGG
    AGG --> RULE
    RULE --> SM
    RULE --> PI
    USERCTL --> SM
    SM --> RETR
    PI --> RETR
    CM -->|"独立，不混入长期记忆"| RETR
```

---

## 7. RAG / Knowledge

表达两套内容体系（总控 §17.1）：Curriculum Content（Book → Chapter → ContentBlock ↔ KnowledgePoint）与 Reference Knowledge（KnowledgeResource → 解析/切块/Embedding → KnowledgeChunk/pgvector）；检索输入为 Question + ScreenContext + Grade，输出 RelevantKnowledge（带 source_ids/license/source_url）进入 TeacherContext。供 Phase 8 Knowledge/RAG 实现者使用。

```mermaid
flowchart TB
    subgraph CURRICULUM["Curriculum Content（课程内容）"]
        B["Book"]
        CH["Chapter"]
        CB["ContentBlock"]
        KP["KnowledgePoint"]
        B --> CH
        CH --> CB
        CB -->|"jsonb 引用"| KP
    end

    subgraph REFERENCE["Reference Knowledge（Phase 8）"]
        RES["KnowledgeResource"]
        ING["Ingestion：Upload → Parser → Chunk → Metadata → Embedding"]
        CHUNK["KnowledgeChunk + embedding（pgvector）"]
        KP2["KnowledgePoint"]
        RES --> ING
        ING --> CHUNK
        CHUNK -->|"jsonb 引用"| KP2
    end

    Q["Question"]
    SC["ScreenContext"]
    GRADE["Grade"]
    RETR2["Retrieve（pgvector 相似度检索）"]
    RELEVANT["RelevantKnowledge（含 source_ids / license / source_url）"]
    TC["TeacherContext"]
    LLM2["LLM"]

    Q --> RETR2
    SC --> RETR2
    GRADE --> RETR2
    CURRICULUM --> RETR2
    CHUNK --> RETR2
    RETR2 --> RELEVANT
    RELEVANT --> TC
    TC --> LLM2
```

---

## 8. Data（数据架构）

表达存储分层（严格对齐 0-E §1）：PostgreSQL 27 张实体表按域分组（Identity/Content/Learning/Conversation/Assessment/Memory/Personalization/Knowledge）+ 1 张幂等基础设施表；pgvector 两个 embedding 列（Phase 8）；Redis 与 Object Storage 的角色。供 Phase 2 起数据库实现与运维参考。

```mermaid
flowchart TB
    APPS8["FastAPI / Worker"]

    subgraph PG8["PostgreSQL（唯一事实源，27 张实体表）"]
        subgraph ID8["Identity（5）"]
            T_USERS["users"]
            T_PROFILES["student_profiles"]
            T_PREFS["student_preferences"]
            T_ROLES["teacher_roles"]
            T_ADMINS["admins"]
        end
        subgraph CONTENT8["Content（4）"]
            T_BOOKS["books"]
            T_CHAPTERS["chapters"]
            T_BLOCKS["content_blocks"]
            T_KPS["knowledge_points"]
        end
        subgraph LEARN8["Learning（3）"]
            T_SESSIONS["learning_sessions"]
            T_EVENTS["learning_events"]
            T_PROGRESS["book_progress"]
        end
        subgraph CONV8["Conversation（3）"]
            T_CONV["conversations"]
            T_MSGS["messages"]
            T_SUMMARIES["conversation_summaries"]
        end
        subgraph ASSESS8["Assessment（4）"]
            T_QUIZ["quiz_sessions"]
            T_QUESTIONS["quiz_questions"]
            T_ANSWERS["quiz_answers"]
            T_INTERACTIONS["quiz_interactions"]
        end
        subgraph MEM8["Memory（5）"]
            T_MEM["student_memories"]
            T_CAND["memory_candidates"]
            T_EVID["memory_evidence"]
            T_EPISODES["student_episodes"]
            T_INSIGHTS["profile_insights"]
        end
        subgraph PERSON8["Personalization（1）"]
            T_RECO["recommendations"]
        end
        subgraph KNOW8["Knowledge（2）"]
            T_RES["knowledge_resources"]
            T_CHUNKS["knowledge_chunks"]
        end
        subgraph INFRA8["Application Infrastructure（非 Domain）"]
            T_IDEM["idempotency_keys"]
        end
    end

    VEC8["pgvector：student_episodes.embedding / knowledge_chunks.embedding（Phase 8，维度由 Provider 定）"]
    REDIS8["Redis：cache / rate_limit / lock / queue / sse temp / ws metadata"]
    OBJ8["Object Storage：covers / avatars / knowledge / audio / sprites"]

    APPS8 --> PG8
    APPS8 --> REDIS8
    APPS8 --> OBJ8
    PG8 -->|"vector 扩展（Phase 8）"| VEC8
```
