# 霜铃 · K12 AI 数字教师 V3 — Traceability（全链路可追溯矩阵）

> 状态：Phase 0 契约基线（Task 0-G）
> 版本：v0.1
> 日期：2026-08-19
> 输入基线：产品需求总纲 v0.2（需求唯一来源）、page-map.md / ui-behavior.md（0-B）、domain-model.md（0-C）、api-contract.md（0-D）、database-design.md（0-E）、执行总控 §8 阶段划分与 §9.2 Task 0-G
> 用途：任何一条需求都能定位到原型交互、Domain 实体、API 端点、数据库表与落地 Phase；供 Hermes 验收、Phase 1 起各阶段排期与回归追溯使用。

---

## 1. 追溯模型与读取说明

### 1.1 六层追溯链

```text
Requirement（R-xx，产品需求总纲章节）
    ↓
Prototype（0-B：page-map 页面 / ui-behavior 交互条目）
    ↓
Domain（0-C：27 实体）
    ↓
API（0-D：端点，含 SSE / WebSocket 骨架）
    ↓
Database（0-E：27 表 + idempotency_keys 基础设施表）
    ↓
Phase（执行总控 §8：Phase 0~12）
```

### 1.2 维护规则

- **何时更新**：任何 0-B~0-E 契约文档发生变更（新增/删除/改名需求、实体、端点、表）时，必须同步更新本文矩阵；每个 Phase 验收前由 Hermes 抽查受影响行。
- **谁维护**：Implementation Agent 在执行涉及契约变更的任务时维护；Hermes 在验收时校验一致性（总控 §24 Git/Diff 检查）。
- **填满原则**：矩阵每行六列必须可填；纯客户端行为（如桌虫拖拽）也要追溯到其支撑实体（TeacherRole.sprite_manifest）与相关端点，禁止留空。
- **阶段原则**：后续 Phase 才落地的需求（语音/Admin/多角色/知识库）在 Phase 列写明确 Phase 编号，不写「未来」。

---

## 2. 需求条目清单（Requirement Inventory）

> 编号 R-01 ~ R-52，全部来自 `docs/requirements/产品需求总纲.md`，仅压缩表述、不改变语义；「来源章节」为原文标题编号。

| 编号 | 一句话描述 | 来源章节 |
| --- | --- | --- |
| R-01 | 产品定位：从小学到高中长期陪伴、记住并理解学生的 AI 数字教师 | §1 |
| R-02 | 用户范围：唯一核心用户是学生，grade=1~12 并自动映射小学/初中/高中 | §3.1 |
| R-03 | 管理角色：只保留轻量管理员端（平台维护），不做教师端 | §4 |
| R-04 | 可扩展 AI 教师角色：由统一 Role/Persona 配置驱动，切换角色不丢失学生数据 | §5、§20.2 |
| R-05 | 同一会话上下文记忆：Conversation 保留完整上下文（含字段清单） | §7、§7.1 |
| R-06 | 会话记忆与长期记忆必须区分，不得混用 | §7.3 |
| R-07 | AI 主动提问：检查理解、引导思考、进入结构化测验模式 | §8 |
| R-08 | 分层提示：轻提示→明显提示→分步骤解释→完整讲解 | §9、§53 |
| R-09 | 鼓励机制：基于真实答题行为的具体反馈，不空洞夸赞 | §10、§54 |
| R-10 | 年龄适配以 Persona 为核心：小学/初中/高中人格规则，不建 12 个 Agent | §11 |
| R-11 | 长期陪伴系统：分层记忆体系，不简单保存全部聊天 | §12 |
| R-12 | 用户基础记忆：昵称/年级/偏好/目标等稳定信息 | §13 |
| R-13 | 学习画像记忆：定性描述 + 证据，首版不生成能力百分比 | §14 |
| R-14 | 知识掌握画像：首版不做掌握度百分比，只保留真实学习证据 | §15 |
| R-15 | 学习偏好画像：解释方式/难度/学习节奏等结构化偏好 | §16 |
| R-16 | 行为画像：把原始统计转换为有教学意义的高层画像 | §17 |
| R-17 | 情节记忆 Episodic Memory：记录有意义学习事件 | §18 |
| R-18 | 长期记忆写入机制：Learning Event → 判断 → 提取 → 更新 Profile | §19、§91 |
| R-19 | 长期记忆读取机制：按当前问题检索相关记忆进 TeacherContext | §20、§27 |
| R-20 | 跨年级长期陪伴：年级变化保留记录并自动调整 Persona | §21 |
| R-21 | 全局自由悬浮桌虫：可拖拽、记录位置、自动防越界、多状态动画 | §22-24 |
| R-22 | 桌虫点击后的自适应聊天面板：右侧/左侧/上下/移动端底部 Sheet | §25 |
| R-23 | 桌虫快捷操作：按当前页面动态变化的 Context Actions | §26、§77 |
| R-24 | 当前界面感知 Screen Context：前端提供结构化页面上下文 | §27 |
| R-25 | 直接问当前页面与选中文字提问：AI 自动获得上下文 | §28-29 |
| R-26 | 当前页面总结：核心概念/重点/易错点/年级适配 | §30 |
| R-27 | 当前页面生成测验：AI 自动知道书本/章节/内容/近期记录 | §31 |
| R-28 | 首版多模态定义：文本 + 语音 + 当前页面上下文（输入/输出） | §32 |
| R-29 | AI 语音通话：ASR→Agent→LLM→TTS，语音与文本共享上下文 | §33-36 |
| R-30 | 内容体系与形态：书本→章节→知识点→学习内容（段落/图片/示例/知识卡等） | §37-38、§46 |
| R-31 | 书本数据结构与来源版权：书名/封面/年级/难度/来源/版权信息 | §40-41 |
| R-32 | 学习书库界面：搜索、适合你的书、学段/主题筛选、全部书籍 | §42 |
| R-33 | 个性化推荐：推荐理由可解释（为什么推荐） | §43 |
| R-34 | 书本详情页：封面/简介/进度/章节/知识点/预计时间/推荐 | §44 |
| R-35 | 阅读/学习页面与 AI 讲解按钮：目录 + 内容 + 桌虫 + 知识块讲解 | §45、§47 |
| R-36 | 自适应测验：Quiz Skill 生成结构化测验对象（Schema 化） | §48-50 |
| R-37 | 对话中发起正式测验：Quiz Session 创建 + 题目快照持久化 | §51、§55-56 |
| R-38 | 测验中的 AI 互动记录：答案/提示/追问/结果全部落库 | §52 |
| R-39 | 历史测验：列表筛选、详情（原题/答案/提示/解析/互动）、再次练习不覆盖旧记录 | §57-60 |
| R-40 | 学生个人中心与设置：账号/AI 教师/学习/语音/隐私 | §61、§67 |
| R-41 | AI 学习画像展示：优势/薄弱/编程思维/AI 基础/习惯/最近变化（定性） | §62-66 |
| R-42 | Memory 管理页面：学生有权查看/修改/忘记 AI 记忆 | §68 |
| R-43 | 首页学习驾驶舱与信息架构/导航：继续学习/今日学习/推荐/最近成长/测验入口 | §69-75、§85-86 |
| R-44 | 对话历史：按场景组织，可新建/继续/删除 | §78 |
| R-45 | 管理员端：首页统计/书本管理/内容管理/知识库管理/来源管理 | §79-84 |
| R-46 | TeacherContext 架构与 AI 工具/Skills：每次 AI 调用统一构造上下文，Skill 化工具 | §88-89 |
| R-47 | 五层记忆类型建议：Conversation/Profile/Learning/Preference/Episodic | §90 |
| R-48 | 画像必须可变化 + AI 解释画像：引用真实证据 | §92-93 |
| R-49 | 首页到学习主流程闭环：学→测→记→理解→推荐→再学 | §94-95 |
| R-50 | MVP 范围：必须有清单与暂不做清单 | §96-97 |
| R-51 | 二次元角色首版策略：Sprite/PNG 序列 + CSS/Canvas，渲染与 Agent 解耦 | §98 |
| R-52 | 知识库管理与 RAG 检索：上传解析切块嵌入索引，来源可溯源 | §41、§83 |

---

## 3. 追溯矩阵（核心交付物）

> 列说明：Prototype 引用 0-B 的 page-map 页面名或 ui-behavior 条目；Domain/API/DB 分别引用 0-C/0-D/0-E 的正式名称；Phase 引用总控 §8。API 端点列省略 `/api/v1` 前缀（如 `POST /quiz-sessions` = `POST /api/v1/quiz-sessions`），`{id}/{qid}` 为路径参数占位符。

| 需求(R-xx) | Prototype | Domain 实体 | API 端点 | DB 表 | Phase |
| --- | --- | --- | --- | --- | --- |
| R-01 | page-map 全局层（companion 常驻）+ ui-behavior §2.1 | StudentProfile、StudentMemory、ProfileInsight | GET /me、GET /me/memories、GET /me/insights | student_profiles、student_memories、profile_insights | Phase 1（体验）→ Phase 7（记忆落地） |
| R-02 | page-map topnav（grade-badge「初二·8年级」）+ library grade-filter | StudentProfile | GET /me、PATCH /me | student_profiles（grade CHECK 1~12） | Phase 2 |
| R-03 | 原型无管理端页面（0-D §14 骨架） | Admin、User | GET /admin/stats、POST /admin/books、POST /admin/knowledge/resources | admins | Phase 10 |
| R-04 | page-map user-menu（学段/演示）+ ui-behavior §1.2 | TeacherRole、StudentProfile | GET /teacher-roles（骨架）、PATCH /me | teacher_roles、student_profiles | Phase 2（数据结构）/ Phase 11（完整 UX） |
| R-05 | page-map companion-panel + ui-behavior §2.5（流式/上下文） | Conversation、Message、ConversationSummary | POST /conversations、POST /conversations/{id}/messages、GET /conversations/{id}/summary | conversations、messages、conversation_summaries | Phase 4 |
| R-06 | ui-behavior §3.7（画像与对话数据分离） | Conversation vs StudentMemory | GET /conversations vs GET /me/memories | conversations vs student_memories | Phase 4 / Phase 7 |
| R-07 | ui-behavior §2.1 showSuggestion + §2.6 quick actions | Conversation、Message、StudentPreference | POST /conversations/{id}/messages、PATCH /me/preferences | conversations、messages、student_preferences | Phase 4 |
| R-08 | ui-behavior §2.6 三级 hint + §2.7 quiz 提示/修正 | QuizSession、QuizQuestion、QuizInteraction、QuizAnswer | POST /quiz-sessions/{id}/questions/{qid}/hints、POST .../answers | quiz_interactions、quiz_answers | Phase 6 |
| R-09 | ui-behavior §2.7 答对/答错反馈 + aiState happy | QuizAnswer、LearningEvent | POST .../answers、POST /learning-events | quiz_answers、learning_events | Phase 6 |
| R-10 | page-map user-menu（学段切换）+ ui-behavior §1.2 学段主题 | TeacherRole（grade_rules）、StudentProfile（grade） | PATCH /me、GET /teacher-roles | teacher_roles、student_profiles | Phase 11（Persona 引擎）/ Phase 2（grade 数据） |
| R-11 | page-map profile（memory-list）+ ui-behavior §2.11 | StudentMemory、MemoryCandidate、MemoryEvidence、StudentEpisode、ProfileInsight | GET /me/memories、GET /me/insights、GET /me/episodes | student_memories、memory_candidates、memory_evidence、student_episodes、profile_insights | Phase 7 |
| R-12 | page-map profile（student-intro）+ topnav badge | StudentProfile、StudentPreference | GET /me、GET /me/preferences | student_profiles、student_preferences | Phase 2 |
| R-13 | page-map profile（画像 + level-tag）+ ui-behavior §1.4 | ProfileInsight、MemoryEvidence | GET /me/insights、GET /me/evidence/{id} | profile_insights、memory_evidence | Phase 7 |
| R-14 | page-map profile（定性档位，无数字）+ ui-behavior §1.2 | ProfileInsight、KnowledgePoint | GET /me/insights | profile_insights、knowledge_points | Phase 7（0-C/0-E 已落实禁止百分比） |
| R-15 | page-map profile（学习方式）+ ui-behavior §3.7 frontmatter | StudentPreference | GET /me/preferences、PATCH /me/preferences | student_preferences | Phase 2（数据）/ Phase 7（Pipeline 更新） |
| R-16 | page-map home（最近变化 timeline）+ profile 表现 | LearningEvent、ProfileInsight | POST /learning-events、GET /me/insights | learning_events、profile_insights | Phase 3（事件）/ Phase 7（画像） |
| R-17 | page-map home（tnode 时间线） | StudentEpisode | GET /me/episodes | student_episodes | Phase 7 |
| R-18 | page-map profile（changelog/memory 操作，0-B 无真实 Pipeline） | LearningEvent、MemoryEvidence、MemoryCandidate、StudentMemory | POST /learning-events、GET /me/memories | learning_events、memory_evidence、memory_candidates、student_memories | Phase 7 |
| R-19 | ui-behavior §2.4（memory intent 响应引用画像） | StudentMemory、ProfileInsight、StudentEpisode | GET /me/memories、GET /me/insights、GET /me/episodes | student_memories、profile_insights、student_episodes | Phase 7 |
| R-20 | 无独立原型页（数据保留语义） | StudentProfile、StudentMemory、StudentEpisode | PATCH /me（grade） | student_profiles、student_memories、student_episodes | Phase 2 / Phase 7 |
| R-21 | page-map companion-dock + ui-behavior §2.1（拖拽/持久化/suggest） | TeacherRole（sprite_manifest） | GET /teacher-roles（骨架，供 sprite 资产） | teacher_roles | Phase 1（UI）/ Phase 11（多角色） |
| R-22 | page-map companion-panel + ui-behavior §2.2（placePanel 定位） | Conversation、Message | GET /conversations/{id}/messages、POST /conversations/{id}/messages | conversations、messages | Phase 4 |
| R-23 | ui-behavior §2.6 QUICK_ACTIONS + page-map 各页快捷操作 | Conversation、Message | POST /conversations/{id}/messages | conversations、messages | Phase 4 |
| R-24 | page-map reader（context-rail）+ ui-behavior §2.13 IntersectionObserver | Conversation（current_page_context） | POST /conversations/{id}/messages（screen_context 字段） | conversations | Phase 5 |
| R-25 | page-map selection-popover + ui-behavior §2.3 | Conversation、Message、ContentBlock | POST /conversations/{id}/messages、GET /chapters/{chapter_id} | conversations、messages、content_blocks | Phase 5 |
| R-26 | page-map reader（总结本页按钮）+ ui-behavior §2.4 summary | Message（LEARNING_SUMMARY） | POST /conversations/{id}/messages（SSE） | messages | Phase 4 |
| R-27 | page-map reader（给我出题）+ ui-behavior §2.5 Quiz Skill 生成 | QuizSession | POST /quiz-sessions | quiz_sessions | Phase 6 |
| R-28 | page-map voice-overlay + ui-behavior §2.12 | Conversation（channel）、Message | POST /conversations/{id}/messages、WS /api/v1/voice/ws（Phase 9 骨架） | conversations、messages | Phase 1（文本）/ Phase 9（语音） |
| R-29 | page-map voice-overlay + ui-behavior §2.12（startVoice/toggle） | Conversation（channel=VOICE）、Message | WS /api/v1/voice/ws（骨架） | conversations、messages | Phase 9 |
| R-30 | page-map reader（knowledge-card/example/callout/figure/mark） | Book、Chapter、ContentBlock、KnowledgePoint | GET /books、GET /chapters/{chapter_id} | books、chapters、content_blocks、knowledge_points | Phase 3 |
| R-31 | page-map library（卡片 meta） | Book、KnowledgeResource | GET /books/{book_id}、POST /admin/knowledge/resources | books、knowledge_resources | Phase 3（结构）/ Phase 8/10（来源管理） |
| R-32 | page-map library（toolbar/筛选/empty）+ ui-behavior §2.8 | Book | GET /books | books | Phase 3 |
| R-33 | page-map home（recommend-card/evidence）+ library 推荐卡 + ui-behavior §2.4 book-why | Recommendation | GET /me/recommendations、POST /me/recommendations/{id}/dismiss | recommendations | Phase 1（Mock）/ Phase 7（Skill） |
| R-34 | 原型无独立详情页（page-map library 卡片承载进度） | Book、BookProgress | GET /books/{book_id}、GET /me/progress/{book_id} | books、book_progress | Phase 3 |
| R-35 | page-map reader + knowledge-card「让霜铃讲给我听」 | Chapter、ContentBlock、Message | GET /chapters/{chapter_id}、POST /conversations/{id}/messages（explain） | chapters、content_blocks、messages | Phase 3 / Phase 4 |
| R-36 | ui-behavior §2.7 quiz-card + §3.5 QUIZZES 结构 | QuizSession、QuizQuestion | POST /quiz-sessions、GET /quiz-sessions/{id}/questions | quiz_sessions、quiz_questions | Phase 6 |
| R-37 | ui-behavior §2.5 tool 消息（Quiz Skill 生成中） | QuizSession、Message（QUIZ） | POST /quiz-sessions、GET /quiz-sessions | quiz_sessions、messages | Phase 6 |
| R-38 | ui-behavior §2.7 选择/提交/提示/修正 | QuizAnswer、QuizInteraction | POST .../answers、POST .../hints、GET .../interactions | quiz_answers、quiz_interactions | Phase 6 |
| R-39 | page-map quizzes + quiz-detail + ui-behavior §2.7/§3.5 | QuizSession、QuizQuestion、QuizAnswer、QuizInteraction | GET /quiz-sessions、GET /quiz-sessions/{id}、GET .../answers、GET .../interactions | quiz_sessions、quiz_questions、quiz_answers、quiz_interactions | Phase 6 |
| R-40 | page-map user-menu（学段/演示）+ profile | StudentProfile、StudentPreference | GET /me、PATCH /me、GET/PATCH /me/preferences | student_profiles、student_preferences | Phase 2 |
| R-41 | page-map profile（student-view + archive + doc-mode）+ ui-behavior §2.10 | ProfileInsight、StudentMemory | GET /me/insights、GET /me/memories | profile_insights、student_memories | Phase 7 |
| R-42 | page-map profile（memory-list）+ ui-behavior §2.11 | StudentMemory | GET /me/memories、PATCH /me/memories/{memory_id} | student_memories | Phase 7 |
| R-43 | page-map home（hero/section-grid/home-lower）+ topnav | BookProgress、Recommendation、QuizSession、StudentMemory | GET /me/progress、GET /me/recommendations、GET /quiz-sessions | book_progress、recommendations、quiz_sessions、student_memories | Phase 1（Mock）/ Phase 3/6/7（各数据源） |
| R-44 | 原型无对话历史页（chat 面板为当前会话） | Conversation | GET /conversations、POST /conversations、PATCH /conversations/{id} | conversations | Phase 4 |
| R-45 | 原型无管理端页面（0-D §14 骨架） | Admin、Book、Chapter、ContentBlock、KnowledgeResource | GET /admin/stats、/admin/books、/admin/chapters、/admin/knowledge/resources | admins、books、chapters、content_blocks、knowledge_resources | Phase 10 |
| R-46 | ui-behavior §2.4 intent 映射 + chat-context-label | Conversation、Message、TeacherRole | POST /conversations/{id}/messages（SSE tool 事件）、GET /teacher-roles | conversations、messages、teacher_roles | Phase 4 / Phase 8（search_knowledge） |
| R-47 | page-map profile（画像/偏好/情节/对话分区展示） | StudentMemory、Conversation | GET /me/memories、GET /conversations | student_memories、conversations | Phase 7 |
| R-48 | page-map profile（level-tag + md-ask「问霜铃」） | ProfileInsight、MemoryEvidence | GET /me/insights/{id}、GET /me/evidence/{id} | profile_insights、memory_evidence | Phase 7 |
| R-49 | 0-B 全流程（home→reader→quiz→quizzes→profile） | 全部核心实体 | 主链路端点（GET /books、POST messages、POST /quiz-sessions、GET /quiz-sessions、GET /me/insights） | 主链路表 | Phase 1（前端全 Mock 跑通） |
| R-50 | 0-B 全部原型（MVP 体验边界） | 27 实体 | 0-D 66 端点 | 27 + idempotency_keys | Phase 0（定义范围）/ Phase 12（质量门禁） |
| R-51 | page-map companion-sprite + ui-behavior §2.13 spritesheet | TeacherRole（sprite_manifest） | GET /teacher-roles（骨架） | teacher_roles | Phase 1（渲染策略）/ Phase 11（角色管理） |
| R-52 | 原型无知识库页面（0-D §12 骨架） | KnowledgeResource、KnowledgeChunk、KnowledgePoint | GET /knowledge/resources、POST /knowledge/search、POST /admin/knowledge/resources | knowledge_resources、knowledge_chunks、knowledge_points | Phase 8（RAG）/ Phase 10（管理上传） |

---

## 4. 反向覆盖检查（Coverage）

### 4.1 Domain → 需求（27 实体逐一确认）

| # | Domain 实体 | 指向它的需求（R-xx） | 支撑性说明 |
| --- | --- | --- | --- |
| 1 | User | R-03、R-40 | 直接：登录账号主体 |
| 2 | StudentProfile | R-01、R-02、R-12、R-20、R-40 | 直接 |
| 3 | StudentPreference | R-07、R-15、R-40 | 直接 |
| 4 | TeacherRole | R-04、R-10、R-21、R-46、R-51 | 直接 |
| 5 | Book | R-30、R-31、R-32、R-33、R-34 | 直接 |
| 6 | Chapter | R-30、R-34、R-35 | 直接 |
| 7 | ContentBlock | R-25、R-30、R-35 | 直接 |
| 8 | KnowledgePoint | R-25、R-30、R-52 | 直接 |
| 9 | LearningSession | R-16、R-18、R-43 | 直接（学习时段聚合） |
| 10 | LearningEvent | R-09、R-16、R-17、R-18 | 直接（Memory Pipeline 输入） |
| 11 | BookProgress | R-34、R-35、R-43 | 直接 |
| 12 | Conversation | R-05、R-06、R-22、R-24、R-44、R-46、R-47 | 直接（一等 Domain） |
| 13 | Message | R-05、R-26、R-28、R-37、R-38、R-46 | 直接 |
| 14 | ConversationSummary | R-05、R-06 | **支撑性**：无独立 UI 需求，支撑长会话上下文（R-05 字段清单） |
| 15 | QuizSession | R-27、R-36、R-37、R-39 | 直接 |
| 16 | QuizQuestion | R-36、R-38、R-39 | 直接 |
| 17 | QuizAnswer | R-09、R-38、R-39 | 直接 |
| 18 | QuizInteraction | R-08、R-38、R-39 | 直接 |
| 19 | StudentMemory | R-01、R-06、R-11、R-12、R-13、R-18、R-19、R-42、R-47 | 直接 |
| 20 | MemoryCandidate | R-18 | **纯支撑性**：Pipeline 中间产物，无直接 UI/API 需求（0-D 亦无学生端点） |
| 21 | MemoryEvidence | R-13、R-18、R-19、R-48 | 直接（证据引证） |
| 22 | StudentEpisode | R-17、R-19、R-47 | 直接 |
| 23 | ProfileInsight | R-01、R-13、R-14、R-16、R-41、R-47、R-48 | 直接 |
| 24 | Recommendation | R-33、R-43 | 直接 |
| 25 | KnowledgeResource | R-31、R-45、R-52 | 直接 |
| 26 | KnowledgeChunk | R-52 | 直接 |
| 27 | Admin | R-03、R-45 | 直接 |
| — | （idempotency_keys） | R-50（基础设施） | 非 Domain，0-D §1.7 要求，0-E 标注基础设施表 |

**结论**：27 个实体全部有至少一条需求指向；纯支撑性实体 = `MemoryCandidate`（Pipeline 中间产物）；支撑性实体 = `ConversationSummary`（无独立交互需求）。`idempotency_keys` 为非 Domain 基础设施表，由 R-50 与 0-D 幂等约定覆盖。

### 4.2 API → Domain（无孤儿端点）

| API 模块（0-D） | 端点数 | 映射实体 |
| --- | --- | --- |
| Identity / Auth | 4 | User、StudentProfile、Admin |
| Students | 2 | StudentPreference |
| Content | 5 | Book、Chapter、ContentBlock、KnowledgePoint |
| Learning | 6 | LearningSession、LearningEvent、BookProgress |
| Conversations | 7 | Conversation、Message、ConversationSummary、TeacherRole |
| Assessment | 8 | QuizSession、QuizQuestion、QuizAnswer、QuizInteraction |
| Memory | 7 | StudentMemory、ProfileInsight、MemoryEvidence、StudentEpisode |
| Knowledge | 4 | KnowledgeResource、KnowledgeChunk、KnowledgePoint |
| Personalization | 4 | Recommendation |
| Admin | 19 | Admin、Book、Chapter、ContentBlock、KnowledgePoint、KnowledgeResource、TeacherRole |

**结论**：66 个端点全部可映射回 domain-model 实体，无孤儿端点；`GET /teacher-roles`（骨架）映射 TeacherRole，不视为孤儿。

### 4.3 DB → Domain（27 ↔ 27）

- 27 张实体表与 27 个实体一一对应，逐表核对结论直接引用 0-E §7 自查表（无遗漏、无多余业务表）。
- 额外 1 张 `idempotency_keys` 基础设施表（非 Domain），由 0-D §1.7 幂等约定与 R-50 覆盖。

### 4.4 孤儿报告

**有需求、原型缺失（原型覆盖缺口，非实现孤儿）**：

| 需求 | 缺口 | 建议 |
| --- | --- | --- |
| R-03 / R-45 | 管理员端无原型页面 | Phase 10 按 0-D §14 骨架新建；当前以骨架文档承接 |
| R-34 | 书本详情页无独立原型 | Phase 1 按需求 §44 + 0-D GET /books/{id} 新建页面 |
| R-40 | 设置页无独立原型（user-menu 只承载学段/演示） | Phase 1 补 Settings 页或与 Hermes 确认合并承载 |
| R-44 | 对话历史页无原型 | Phase 4 按 0-D GET /conversations 新建 |
| R-52 | 知识库管理无原型 | Phase 8/10 按 0-D §12/§14 骨架实现 |

**有实现、无需求（孤儿实现）**：无。27 实体、66 端点、27+1 表均有需求或基础设施说明支撑。

---

## 5. Phase 落地映射

> 阶段划分按总控 §8（Phase 0~12）；跨阶段需求在多个 Phase 集合中出现（如 R-04 数据结构在 Phase 2、完整 UX 在 Phase 11）。

| Phase | 落地的需求编号集合 | 说明 |
| --- | --- | --- |
| Phase 0 | R-50 | 本阶段定义 MVP 范围与全部契约（0-A~0-G），不实现功能 |
| Phase 1 | R-01、R-21、R-22、R-23、R-26、R-28、R-33、R-35、R-37、R-43、R-49、R-51 | React 生产 UI + 全 Mock 跑通完整闭环 |
| Phase 2 | R-02、R-04、R-10、R-12、R-15、R-20、R-40 | 学生身份、档案、偏好、grade、角色数据结构 |
| Phase 3 | R-16、R-30、R-31、R-32、R-34、R-35 | 书库、章节、阅读器、进度、学习事件 |
| Phase 4 | R-05、R-06、R-07、R-09、R-22、R-23、R-26、R-44、R-46 | Conversation 一等 Domain + Teacher Agent Runtime |
| Phase 5 | R-24、R-25 | Screen Context 界面感知 |
| Phase 6 | R-08、R-09、R-27、R-36、R-37、R-38、R-39 | Quiz Skill、结构化测验、历史答卷 |
| Phase 7 | R-11、R-13、R-14、R-15、R-16、R-17、R-18、R-19、R-20、R-33、R-41、R-42、R-47、R-48 | 长期记忆 Pipeline、画像、记忆管理、推荐 Skill |
| Phase 8 | R-46、R-52 | Knowledge / RAG / pgvector / 检索 Skill |
| Phase 9 | R-28、R-29 | 语音：ASR / TTS / WebSocket |
| Phase 10 | R-03、R-31、R-45、R-52 | 管理员端：内容/知识库/来源管理 |
| Phase 11 | R-04、R-10、R-51 | 多 AI 教师角色与 Persona 管理 |
| Phase 12 | R-50 | 无新需求；对 R-01~R-52 做 CI / E2E / 稳定性 / 比赛质量门禁 |

**覆盖确认**：R-01 ~ R-52 全部出现在至少一个 Phase 集合中，无未分配需求。

---

## 6. 本轮明确不做

1. 不展开每条需求的详细验收标准（由各 Phase 验收时按总控 §24 单独定义）。
2. 不重新定义需求：R-xx 只引用产品需求总纲原文章节，不新增/不篡改语义。
3. 不设计 API/DB 细节：端点与表以 0-D / 0-E 为权威，本文只做映射。
4. 不修改任何已有文档（0-B~0-E 如需修订，走独立任务）。
