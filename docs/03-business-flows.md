# 03 · 业务流程追踪

> 每条链路按 `用户操作 → 前端 → HTTP/SSE/WS → 后端 Route → Service → DB → Job/外部服务 → Response → UI` 逐步追踪，
> 并给出**真实性判断**：COMPLETE / PARTIAL / MOCK / STUB / DISCONNECTED / BROKEN。
>
> 判断依据是**实际调用关系**（已逐跳读代码 + 在运行实例上实测），不是文件名。

---

## 链路 1：登录与会话恢复 —— **COMPLETE**

```
[UI]  LoginPage 表单提交
  → AuthProvider.login()                         features/auth/AuthProvider.tsx:122-138
  → studentService.login()                       shared/api/api-student-service.ts:19
  → POST /api/v1/auth/login                      identity/router.py:23
  → IdentityService.login()                      identity/service.py
       ├ bcrypt.checkpw()                        identity/security.py:12-18
       ├ users.status == DISABLED → 401 ACCOUNT_DISABLED
       └ create_access_token() HS256             security.py:21-25
  → 若 user_type == 'ADMIN'：前端必须再通过 adminService.getAdminMe()
       （GET /me/admin），否则整段状态清除并抛 403 ADMIN_PROFILE_REQUIRED
       ── 这是「不信任 token 声明」的正确做法    AuthProvider.tsx:127-133
  → token 存 localStorage['shuangling-access-token']
[刷新恢复]  解码 JWT → ADMIN 时**再次**请求 /me/admin 复核   :63-107
```

**运行实测**：`POST /auth/login` 用 `xiaoming/demo123` 返回 200 + `access_token`（195 字符）+ `expires_at`。
返回体字段是 `access_token`（不是 `token`），前端已对齐。

**状态**：COMPLETE。测试覆盖：`AuthProvider.test.tsx`、`AuthProvider.admin.test.tsx`、`account-switch.test.tsx`、E2E `login-flow.spec.ts`。

---

## 链路 2：书库发现（分页 / 搜索 / 筛选 / 推荐）—— **COMPLETE**

```
[UI]  LibraryPage 挂载 / 筛选变化 / 搜索输入（防抖）
  → contentService.getBooksPage({cursor, limit, gradeMin, gradeMax, topic, search})
  → GET /api/v1/books?...                        content/router.py:25
  → ContentService.list_books()                  content/service.py:81-212
       ├ status != 'PUBLISHED' → 422 INVALID_CONTENT_STATUS    :94-103
       │    ★ 守卫在 Service 层，缓存命中路径也绕不过
       ├ Redis 缓存（键 = 全部过滤参数的 sha256 指纹）            :104-119
       ├ 年级区间相交：book.grade_max >= gmin AND book.grade_min <= gmax  :122-126
       ├ 后端全库 ILIKE 搜索（title/description/author）          :129-136
       ├ 游标 (created_at, book_id) 元组比较                      :137-141
       └ 附带每本书的 PUBLISHED 章节数                            :167-177
  → {data:[BookDTO], meta:{next_cursor, has_more, total}}
[UI]  书卡网格 + 「加载更多」游标翻页 + 推荐理由 + 继续学习入口
```

**状态**：COMPLETE。测试：`LibraryPage.test.tsx`（9，断言**后端**搜索而非本地过滤、游标翻页、错误重试）、`test_content_api.py`。

---

## 链路 3：阅读 → 页面感知对话 → RAG —— **COMPLETE（传输）/ PARTIAL（AI 质量）**

```
[UI]  ReaderPage 挂载
  → contentService.getChapters / getChapter / getBook / getBookProgress
  → ContentService.get_chapter_detail()          content/service.py:278-341
       ├ chapter.status != PUBLISHED → 404                       :282
       ├ ★ 父书 status != PUBLISHED → 404（越权防护）              :287-292
       └ 注入 is_completed（ChapterCompletion 事实表）
  → 渲染 ContentBlock（TITLE/PARAGRAPH/IMAGE/FIGURE/KNOWLEDGE_CARD/…）
       └ IMAGE/FIGURE 走 GET /library-assets/{book_slug}/{filename}
  → IntersectionObserver 更新 ScreenContext（visibleSection / contentBlockId / knowledgePoints）
[学习会话]  learningService.createSession() → POST /learning-sessions
[学生提问]  ChatComposer.send(text, screenContext)
  → useConversationStore.send()                  conversation-store.ts:336
  → POST /conversations/{id}/messages (SSE) + Idempotency-Key
  → ConversationService.send_message()           conversation/service.py:431-1056
       ├ 会话串行锁（Redis / asyncio 降级）                       :446-479
       ├ 幂等重放                                                :505-523
       ├ build_input_window()                                    context_window.py:45-88
       ├ ★ quiz_intent 关键词劫持（「题目」→ 出题）               :55, :612
       ├ ★ RAG retrieve(query, screen_context)                   :646 → retrieval.py:58
       │    └ KnowledgeService.search() pgvector `<=>`           knowledge/service.py:148-171
       ├ build_teacher_context() 档案/偏好/记忆/画像/进度/测验     teacher_context.py:204-452
       ├ system_prompt 拼装                                       :690-706
       └ provider.stream_chat()  ← **非真流式**（见 docs/08 §1.2）
[UI]  SSE message.start → text.delta×N → message.done → MessageList 渲染
```

**状态**：
- 阅读与图片渲染：**COMPLETE**（T11/T12 已交付真实图片资源）
- RAG 接线：**COMPLETE**（真的调用了 pgvector）
- AI 回答质量：**PARTIAL**（无真流式、无重试、记忆按时间而非相关性注入）
- ⚠️ **ReaderPage 无错误态**：所有内容请求 `catch {}` 吞掉，失败渲染「章节不存在。」（`ReaderPage.tsx:596`）→ 网络故障与 404 无法区分，且无重试按钮。**PARTIAL**

---

## 链路 4：完成章节 → 继续学习 —— **COMPLETE**

```
[UI]  阅读到章末 → ChapterCompletionCard「完成本章」
  → learningService.markChapterCompleted(chapterId)
  → PUT /api/v1/me/chapters/{chapter_id}/completion      learning/router.py:78
  → 写 chapter_completions (student_id, chapter_id) 唯一约束 → 幂等
  → 发 LearningEvent('CHAPTER_FINISHED')
  → 更新 book_progress / student_profiles.completed_chapters
[书「已完成」判定]  = 「本书全部 PUBLISHED 章节均在 chapter_completions 中」
  → 而非「滚动到末块」                                     models.py:517-523 注释明示
[继续学习]  首页 ContinueLearningCard 读 GET /me/learning-next
```

**状态**：COMPLETE（代码与迁移齐备）。
⚠️ **但数据面未激活**：实测开发库 `chapter_completions` 仅 2 行 —— 该能力刚落地，尚无真实使用量。

---

## 链路 5：随堂测验 → 判分 → 错题讲解 → 再练一道 —— **PARTIAL**

```
[触发 A] 对话中命中「出题/题目/测验/quiz/考考我」       conversation/service.py:55,612
    ⚠️ 副作用：问「这道题目我不会」会被劫持为出题
[触发 B] 章节页/首页入口（runIntent 走同一 send 路径）
  → SSE tool.start(tool="quiz") → QuizService.create_session()   :723-889
  → QuizSkill.generate()                                  quiz/skill.py:106-311
       来源优先级：审校题 > LLM > 章节确定性模板 > 通用题库   :123-199
       ★ 实测 89% 落到通用题库（8 题硬编码）
  → 落库 quiz_sessions + quiz_questions（正确答案只在服务端）
  → SSE tool.result(payload.quiz_session_id)
[UI]  QuizCard 渲染题目（多题型）
[作答]  POST /quiz-sessions/{id}/questions/{qid}/answers  (Idempotency-Key)
  → 服务端权威判分 QuizSkill.grade()                       skill.py:425-440
  → 记录 quiz_answers(attempt_no) / quiz_interactions(sequence)
  → 发 LearningEvent('QUIZ_ANSWERED'/'ANSWER_CORRECT'/'ANSWER_WRONG')
[讲解]  QuizDetailPage「讲解这道题」→ runIntent → 带题目快照的对话（T14 上下文契约）
[再练]  「再练一道」→ 新 quiz_session 带 source_quiz_session_id + source_question_id（T16）
[收尾]  result_summary + 复习事件 QUIZ_REVIEW_COMPLETED
```

**状态**：**PARTIAL**
- 判分、幂等、序号并发安全、答案隐藏：**COMPLETE**
- **AI 反馈是两句硬编码字符串**（`quiz/service.py:594-598`）
- **非题库题三个 hint level 返回同一句话**（`skill.py:451-457`）
- **审校题路径运行时 DISCONNECTED**（`reviewed_questions` 在 bootstrap 后恒为空，见 `docs/08` §5.3）
- 题量声明不一致（`skill.py:176-183` vs `:295-299`）

---

## 链路 6：学习事件 → 记忆/画像 → 推荐 —— **PARTIAL**

```
[UI]  ReaderPage / ChatComposer 发学习事件
  → POST /learning-events                                learning/router.py:42
  → learning_events (append-only)
  → ★ 入队 background_jobs('memory_consolidation')        （不在 HTTP 请求内同步执行）
[Worker 独立进程]  python -m app.jobs.worker
  → claim_next() FOR UPDATE SKIP LOCKED                  jobs/queue.py:48-148
  → handlers/memory.handle_memory_consolidation()
  → MemoryPipeline.run()                                 memory/pipeline.py:37-173
       ├ 规则式事件分桶/计数/模板（硬编码）
       ├ LLM 仅改写句子（带数字接地校验）                    :179-194,256-267
       ├ 写 memory_evidence / memory_candidates /
       │    student_memories / profile_insights
       └ ★ student_episodes.embedding 硬编码 None           :376
  → GET /me/memories | /me/insights | /me/episodes | /me/agent.md
  → 首页/书库 Recommendation（规则式 + reason + evidence_ids）
```

**状态**：
- 事件 → 队列 → Worker → 落库：**COMPLETE**（实测 259 次 success）
- 记忆抽取智能度：**RULE-BASED**（LLM 仅润色）
- 情节记忆检索：**DISCONNECTED**（239 行 / 0 向量 → AI 永远看不到情节）
- 记忆注入对话：**PARTIAL**（按时间取最近 5 条，非相关性）
- 画像：**COMPLETE**（5 档定性，无百分比 —— 符合产品约束）

---

## 链路 7：长对话摘要 —— **BROKEN（破坏性）**

```
消息数 > SUMMARY_MESSAGE_THRESHOLD(20)
  → 入队 background_jobs('conversation_summary')          （每条新消息都重新入队一次）
  → handlers/conversation.handle_conversation_summary()
       ├ 只保留：第 1 条 + type∈{QUIZ,HINT,RECOMMENDATION,LEARNING_SUMMARY,SYSTEM} + 最后 1 条
       ├ 每行截断到 160 字符
       ├ ★ 无任何 LLM 调用（model_info={"provider":"rule"}）
       └ ★ 写入 message_covered_count = len(messages)  ← 谎报覆盖全部
  → 下一轮 build_input_window() 据此丢弃该索引之前的全部消息  context_window.py:61-65
```

**状态**：**BROKEN**。超过 20 条后，AI **永久丢失**所有非关键 TEXT 轮次，
而系统对外声称上下文完整。实测样本：`message_covered_count=22`、`token_count=38`。
→ `docs/08` §2.4、`docs/12-known-issues.md` P1-1。

---

## 链路 8：语音对话 —— **PARTIAL（有意的能力降级）**

```
[UI]  ChatComposer 🎤（受 voicePrefs.input_enabled 控制，默认 true）
  → audio-capture.ts：getUserMedia + AudioWorklet（非 MediaRecorder）
       48kHz → 16kHz 线性插值降采样 → Int16 PCM → 100ms/1600 样本定长帧
       public/audio-worklet-processor.js（1602 字节，真实存在）
  → base64 → WS /api/v1/voice/ws {type:'audio', ...}
       ├ 连接时与路由变化时推送 screen_context（避免陈旧章节上下文）
  → voice/ws.py：阿里云 DashScope 双向流式 ASR（REAL，.env VOICE_PROVIDER=aliyun）
  → 复用 ConversationService.send_message() 得到 AI 回复     voice/ws.py:119-129
  → TTS：get_tts_provider() 抛错（TTS_PROVIDER 未设置）
       → WS 返回明确的 TTS_UNAVAILABLE                      voice/ws.py:142-155
[UI]  以文字形式展示 AI 回复 + 桌宠动画
```

**状态**：PARTIAL —— 学生说 → AI 文字回（**无语音合成**）。
这是**有意的诚实降级**（不再返回静音假音频），不是 bug。
⚠️ `QuickActions.tsx:38-44` 有一个「语音聊天」按钮**没有 onClick**（死 UI）。

---

## 链路 9：管理后台内容运营 —— **PARTIAL**

```
[UI]  /admin/books      创建/编辑书、状态切换（DRAFT/PUBLISHED/ARCHIVED）
      /admin/chapters   创建章节、创建内容块、创建知识点
      /admin/knowledge  上传资源（PDF/MD/TXT）→ 202 → 轮询状态 → 失败重试
      /admin/styles     教师风格 CRUD
      /admin            平台统计
  → POST /admin/knowledge/resources                     admin/router.py:292-345
  → 入队 background_jobs('knowledge_ingest')
  → Worker：解析（pypdf/Markdown）→ 500 字符固定窗口分块 → 逐块 embedding → READY
[UI]  AdminKnowledge 3 秒轮询 UPLOADED→…→READY；FAILED 可重试
```

**状态**：PARTIAL
- 上传→解析→索引→状态可见：**COMPLETE**（实测 272 次 `knowledge_ingest` success）
- ⚠️ **只能创建，不能编辑**：`PATCH /admin/content-blocks/{id}`、`PATCH /admin/knowledge-points/{id}`、
  `PATCH /admin/knowledge/resources/{id}` 三个端点**有实现有测试但前端无 UI**
- ⚠️ **「归档」用 `status='FAILED'` + `error='archived: test data'` 表达**，
  导致后台把 382 条归档资源显示为「失败」（`docs/08` §3.5）
- ⚠️ **HTML 类型声明支持但未解析**（`knowledge_resources.file_type` 允许 HTML，`ingestion.py` 无 HTML 分支）

---

## 链路 10：账号切换隔离 —— **COMPLETE（前端）/ 有残留**

```
[登出]  AuthProvider → clearAuthState()
  → reset-user-state.ts:12-18
       ├ clearToken()
       ├ useConversationStore.reset()   ← 中止在途 SSE、bump epoch、清 per-user 键、aiState→idle
       └ queryClient.clear()
  → ★ 但**未重置**：companion store（桌宠 id + Dock 位置）、toast store、
       ScreenContextProvider 的 React state（它在 AuthProvider 内层，登出时不卸载）
```

**状态**：COMPLETE（对话/请求隔离严格），但有 3 处状态残留 → PARTIAL。
E2E `account-switch.spec.ts` + 单测 `account-switch.test.tsx` 覆盖主路径。

---

## 链路 11：后台任务（Worker）—— **COMPLETE（进程内）/ DISCONNECTED（默认启动路径）**

```
生产者：admin 上传资源 / 消息超阈值 / 学习事件
  → queue.enqueue(session, job_type, payload)     jobs/queue.py
  → background_jobs(status='queued')
消费者：python -m app.jobs.worker
  → recover_stale_running()（running 超 TTL 600s 视为崩溃遗留 → 重排）
  → claim_next()  FOR UPDATE SKIP LOCKED
  → resolve_handler()  3 类：knowledge_ingest / conversation_summary / memory_consolidation
  → mark_success / mark_failed(指数退避 next_attempt_at)
```

**状态**：
- 队列与消费逻辑：**COMPLETE**（实测 272 + 259 + 105 次 success；当前 Worker 进程在运行）
- ⚠️ **启动路径脆弱**：`main.py` lifespan 为空；compose 的 worker 服务被 `profiles:["worker"]` 门控
  → `docker compose up` **不会**启动 Worker。任何绕过 `scripts/start.sh` 的部署都会静默失去异步能力（无告警）。

---

## 汇总表

| # | 链路 | 状态 | 关键缺口 |
| --- | --- | --- | --- |
| 1 | 登录与会话恢复 | **COMPLETE** | — |
| 2 | 书库发现（分页/搜索/筛选） | **COMPLETE** | — |
| 3 | 阅读 → 页面感知对话 → RAG | COMPLETE(传输) / **PARTIAL**(质量) | 无真流式；ReaderPage 无错误态 |
| 4 | 章节完成 → 继续学习 | **COMPLETE** | 数据面刚落地（2 行） |
| 5 | 测验 → 判分 → 讲解 → 再练 | **PARTIAL** | 反馈/提示硬编码；审校题库未接入 bootstrap |
| 6 | 事件 → 记忆/画像 → 推荐 | **PARTIAL** | 情节记忆向量全空；记忆按时间非相关性注入 |
| 7 | 长对话摘要 | **BROKEN** | 删除历史 + 谎报覆盖范围 |
| 8 | 语音对话 | **PARTIAL** | 无 TTS（有意）；死按钮 |
| 9 | 管理后台内容运营 | **PARTIAL** | 只能创建不能编辑；归档语义错误 |
| 10 | 账号切换隔离 | **COMPLETE** / 有残留 | 桌宠/toast/ScreenContext 未重置 |
| 11 | 后台任务 Worker | **COMPLETE** / 默认不启动 | 无启动保证、无队列积压告警 |
