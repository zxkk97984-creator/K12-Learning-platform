# 08 · AI / Agent / RAG / Memory 系统

> 本文件追踪完整链路：**用户请求 → 调用入口 → Context 构建 → Model → Tool → Persistence → Response**，
> 并对每个环节标注真实性。凡「代码存在但未接入」一律标注 `DISCONNECTED`，不写成 COMPLETE。
>
> 主要证据来自 `.audit/A-ai-subsystem.md`（738 行完整代码考古）+ 运行中的开发库实测。

---

## 0. 一句话结论

**AI 子系统是「真实的 Rust 骨架 + 若干空心梁」**：
Provider 适配、SSE 传输、pgvector 检索、任务队列、记忆/画像落库都是真的、在跑的；
但**没有 token 级流式**、**没有 Agent/Tool Calling**、**会话摘要是破坏性的伪摘要**、
**情节记忆向量从不写入**、**出题 89% 来自 8 题硬编码题库**。

---

## 1. Provider 层（`app/ai/`）

### 1.1 抽象的 Provider

`AIProvider` 契约（`app/ai/base.py:6-26`）只有 `stream_chat()` + `model_info` + `last_usage`。
**没有** tools / JSON mode / 取消 / 温度等参数面。

工厂 `get_ai_provider()`（`app/ai/factory.py:7-23`）按 `settings.ai_provider` 二选一，**每次调用新建实例**：

| provider | 类 | 状态 |
| --- | --- | --- |
| `mock` | `MockAIProvider`（`mock.py:26-50`） | MOCK：关键词 → 固定段落；RAG 回显（`:52-75`） |
| `openai_compatible` | `OpenAICompatibleProvider`（`openai_compatible.py`） | **REAL**：httpx + Bearer，实测 33 条真实回复落库，API 日志 0 错误 |

**默认值 vs 实际**：`config.py:25` 默认 `AI_PROVIDER="mock"`；
但工作区 `backend/.env` 设为 `openai_compatible`（`https://api.deepseek.com`，`deepseek-v4-flash`）。
→ **当前运行实例真的在调用外部付费模型**（`messages.model_info->>'provider'` 中有 33 条 `openai_compatible`）。

### 1.2 ⚠️ 最反直觉的发现：**没有 token 级流式**

| 证据 | 内容 |
| --- | --- |
| `openai_compatible.py:68` | 请求体写死 `"stream": False` |
| `openai_compatible.py:103-104` | 拿到**完整**字符串后，用切片循环把它切成 16 字符的「伪 delta」逐块 yield |
| 全仓检索 | `httpx.stream` / `iter_lines` / SSE 解析在 `app/ai/` 中 **0 命中** |

**后果**：
1. 用户看到的「打字机效果」是**服务端伪造的**——模型早已生成完毕，只是一块块喂给前端。
2. 首字节延迟 = 整段生成延迟。整段生成被 `openai_compatible.py:39,76` 的 **30 秒固定超时**（不可配置）硬性限制。
3. **没有任何重试**（`grep retry/tenacity/backoff app/ai/` = 0 命中）。超时即失败。

**要修的方向**：把 `stream: True` + 真实 SSE 解析接上——前端 SSE 传输层（见 §3.3）本来就是对的，改造成本集中在这一个 adapter。

### 1.3 没有 Agent、没有 Tool Calling

- 全仓 `tool_calls` / `function_call` / `"tools"` 检索 = **0 命中**。
- 对话中的 `tool.start` / `tool.result` SSE 帧（前端据此渲染题卡）**不是工具调用**，
  而是 `service.py:612` 的关键词子串匹配：`QUIZ_INTENT_KEYWORDS = ("出题","题目","测验","quiz","考考我")`（`service.py:55`）。
- **副作用（真实缺陷）**：学生问「**这道题目我不会**」→ 命中「题目」→ **不回答问题，直接生成一份 3 题测验**。

`app/skills/` 的 Skill 抽象也基本空心：
- `skills/base.py:4-8` 是**只有元数据的 Protocol**（元数据型 STUB）。
- `skills/registry.py:5-7` 只注册一项 `{"quiz": QuizSkill()}`。
- **对话链路完全绕过注册表**：`conversation/service.py:282-283` 直接 `QuizService()` 硬编码 → `DISCONNECTED`。

### 1.4 Embedding

| Provider | 实现 | 状态 |
| --- | --- | --- |
| `mock` | 64 维 SHA256 确定性哈希 + L2 归一（`embedding.py:32-47`） | MOCK |
| `openai_compatible` | 真实 `/embeddings` 调用 + 维度校验（`embedding.py:50-126`） | **REAL**，实测 467 个 1024 维向量 |

### 1.5 Voice（ASR/TTS）

| 能力 | 实现 | 当前部署状态 |
| --- | --- | --- |
| ASR（阿里云 DashScope 双向 WS） | `ai/voice.py:55-235` | **REAL**，`.env VOICE_PROVIDER=aliyun` |
| ASR（mock） | `voice.py:32-43` 固定短语 | MOCK |
| TTS | `voice.py:317-329` | **DISCONNECTED**：`TTS_PROVIDER` 未设置 → `get_tts_provider()` 抛错 → WS 返回 `TTS_UNAVAILABLE`（`voice/ws.py:142-155`） |

> 这是**有意的诚实降级**（不再返回静音假音频），不是 bug。语音链路当前为「学生说 → AI 文字回」。

### 1.6 LLM 可观测性 —— **缺失**

`/metrics`（`main.py:144-149` + `infrastructure/metrics_registry.py`）只有 HTTP 计数与 uptime。
**没有任何 LLM 指标**：调用次数、token 用量、延迟、失败率、RAG 命中率、检索延迟。

token 计量本身也是部分失真：`conversation/service.py:163-186` 在 provider 分支取真实 usage，
但 `quiz/service.py:845-850` 与 `:914-919` 两个分支把**字符数**当作 `input_tokens`/`output_tokens` 上报。

---

## 2. 对话链路（`app/modules/conversation/`）—— 系统的心脏

### 2.1 完整调用链（REAL）

```
POST /api/v1/conversations/{id}/messages        conversation/router.py:80-111
  └─ ConversationService.send_message()          conversation/service.py:431-1056
       ├─ 会话级串行锁（Redis 分布式锁 + asyncio 本地降级）  :446-479      REAL
       ├─ 幂等键校验 / 冲突重放（Idempotency-Key）        :505-523,1058-1177  REAL
       ├─ 落库 STUDENT 消息（sequence 唯一约束）          :540-560
       ├─ 读取历史 + 最新 ConversationSummary           :564-594
       ├─ build_input_window(摘要边界 + token 预算)      conversation/context_window.py:45-88  PARTIAL
       ├─ 证据问答分支（规则）                          :617-625              REAL(规则)
       ├─ RAG 检索 retrieve(query, screen_context)      :643-653 → knowledge/retrieval.py:58  REAL
       ├─ 教师人格 TeacherRole 注入                     :663-674              REAL
       ├─ build_teacher_context()  档案/偏好/记忆/画像/进度  teacher_context.py:204-452   REAL
       ├─ system_prompt 拼装                            :690-706              REAL
       ├─ SSE 流式输出                                  :708-1056             REAL(传输)
       │    ├─ quiz_intent 分支 → QuizService.create_session()  :723-889
       │    └─ 普通分支 → provider.stream_chat()                :1179-1216
       └─ 落库 TEACHER 消息 + LearningEvent + 入队 memory_consolidation
```

### 2.2 system_prompt 实际内容（`service.py:690-706`，顺序即优先级）

```
[教师人格 persona_block]        ← teacher_roles.persona / tone / teaching_style
[长对话摘要 summary_context]     ← conversation_summaries（见 §2.4 警告）
[TeacherContext 学生上下文块]    ← teacher_context.py 从 DB 聚合
[知识库参考 reference_block]     ← RAG top-3 chunk（含 source_name / source_url）
[证据上下文 evidence_context]    ← 证据问答分支
[instruction_block]             ← 固定人设 + 当前页面上下文 JSON
```

**注入内容真实、来源可溯**。但注意：记忆注入是**按时间取最近 5 条**（`teacher_context.py:246-285`），
**不是按相关性检索** → PARTIAL。

### 2.3 SSE 传输层（REAL，且质量高）

`router.py:95-111` + `service.py:708-1056` 实现了一套完整事件协议：
`message.start` / `text.delta` / `tool.start` / `tool.result` / `message.done` / `error`，
带 `event_id`、幂等重放、`X-Request-ID`、AbortSignal 取消、生成纪元（epoch）隔离。
前端 `shared/api/sse.ts` 正确处理 CRLF、跨 chunk 的多字节 UTF-8、心跳注释行。

> **判断**：传输层是**这套系统里工程质量最高的部分之一**；问题在于它承载的「token 流」是伪造的（§1.2）。

### 2.4 ⚠️ 最严重的 AI 缺陷：会话摘要会**删除历史**并**谎报覆盖范围**

| 环节 | 代码 | 事实 |
| --- | --- | --- |
| 触发 | `service.py` 消息数 > `SUMMARY_MESSAGE_THRESHOLD`(20) 时入队 | REAL |
| 生成 | `jobs/handlers/conversation.py:16-27` `_summary_messages` | **只保留：第 1 条 + `type ∈ {QUIZ,HINT,RECOMMENDATION,LEARNING_SUMMARY,SYSTEM}` 的消息 + 最后 1 条** |
| 截断 | `:30-36` `_summary_text` | 每行截到 **160 字符**，前缀 `"会话摘要：\n"` |
| **谎报** | `:77,86` | 写入 `message_covered_count = len(messages)` —— **声称覆盖了全部消息** |
| 后果 | `context_window.py:61-65` | 窗口构建器据此**丢弃该索引之前的全部消息** |

- `model_info = {"provider":"rule","model":"conversation-summary-v1"}`（`:78,87`）→ **本文件根本没有 `get_ai_provider()` 调用，没有 LLM 摘要**。
- 真实库样本：`message_covered_count=22`，`token_count=38`。
- 且**每条新消息都会重新入队一次**摘要任务（`:57-58`），反复重写。

**净效果**：一段超过 20 条的对话，AI 会**永久丢失**所有非关键 TEXT 轮次，
取而代之的是每行 ≤160 字符的摘录，而系统对外声称「上下文完整」。

> 这是本次审计发现的**单个影响最大的 AI 行为缺陷**。修复方向见 `docs/16-roadmap-analysis.md`。

### 2.5 上下文窗口（`context_window.py`，新文件）

按**字符**启发式估算 token（`context_window.py:45-88`），非真实分词。
`:76-78` 存在把窗口压缩到只剩 1 轮的退化路径。
`context_window_token_budget` 默认 3000（`config.py:45`）。

---

## 3. RAG / 知识库（`app/modules/knowledge/`）

### 3.1 入库管线（REAL）

```
POST /admin/knowledge/resources            admin/router.py:292-345 → 入队 knowledge_ingest
  └─ Worker: handle_knowledge_ingest        jobs/handlers/knowledge.py
       └─ ingest_stored_resource()          knowledge/ingestion.py
            ├─ 解析：PDF(pypdf) / Markdown / TXT      :169-195   REAL
            │    ⚠️ HTML 声明支持但未解析
            ├─ 分块：固定 500 字符窗口，无重叠         :52-70     REAL(朴素)
            └─ 嵌入：每块调 embedding provider         :198-200,278  REAL
```

### 3.2 向量检索是真 SQL（REAL）

`knowledge/service.py:148-171` 构造原生 SQL：

```sql
SELECT ... , CASE WHEN vector_dims(kc.embedding) = :embedding_dimension
                  THEN kc.embedding <=> CAST(:query_embedding AS vector) END AS distance
FROM knowledge_chunks kc JOIN knowledge_resources kr USING(resource_id)
WHERE kc.status='READY' AND kr.status='READY'
  AND kc.embedding IS NOT NULL
  AND vector_dims(kc.embedding) = :embedding_dimension
ORDER BY distance LIMIT :limit
```

- pgvector 扩展 **0.8.6 已安装**。
- **无向量索引**：迁移 `c7d8e9f0a1b2` 移除了 HNSW（pgvector 索引要求固定维度，而列是无维度 `vector`）→ **全表顺序扫描**。

### 3.3 ⚠️ RAG 已接入，但**在本部署中 58% 的知识不可达**

`conversation/service.py:646` 确实调用了 `retrieve()`（**RAG 是真接上的**，不是摆设）。但是：

| 维度 | chunk 数 | 是否可达 |
| --- | --- | --- |
| 64 维（早期 mock embedding 遗留） | **636** | ❌ 被 `vector_dims = :embedding_dimension` 过滤掉 |
| 1024 维（当前真实 embedding） | **467** | ✅ 可达 |

`backend/.env` 中 `EMBEDDING_DIMENSION=1024` → 查询向量 1024 维 → **636 个 64 维 chunk 永远不会被检索到**。
这些是历史遗留数据，需要用 `app/scripts/reindex_embeddings.py` 重索引（该脚本存在，但未被执行到这个库上）。

### 3.4 排序启发式会压过语义相似度（PARTIAL）

`knowledge/service.py:173-187`：
1. 若无向量结果 → 退回 `ILIKE '%整句查询%'` 关键词兜底（`:204-231`）。
2. 若**没有任何向量结果的字面包含用户查询**，先尝试关键词兜底，命中则**整体丢弃向量结果**。
3. 最终排序键是 `(0 if request.query in row.content else 1, distance)` —— **字面子串匹配优先级高于余弦距离**。

对自然语言提问，第 2/3 步基本不会触发（因为整句不会字面出现），所以向量结果通常仍然生效；
但这是一套脆弱的启发式，语义排序会被偶然的字面命中劫持。

### 3.5 `knowledge_resources` 健康度（实测）

| status | 数量 | 说明 |
| --- | --- | --- |
| READY | 102 | 可用 |
| FAILED | 395 | 其中 **382 条 error = `archived: test data`** |

> ⚠️ **设计异味**：项目用 `status='FAILED'` + `error='archived: test data'` 来表达「已归档」，
> 而不是新增一个 `ARCHIVED` 状态（`KnowledgeResource.status` 的 CheckConstraint 里确实没有 ARCHIVED）。
> 这导致「归档」与「真失败」在数据上不可区分，`/admin/knowledge` 会把 382 条归档内容当作失败资源展示。
> 另有 7 条 `embedding failed`、6 条 `embedding provider down` —— 真实失败。

---

## 4. Memory / 画像（`app/modules/memory/`）

### 4.1 抽取是**规则驱动**，LLM 只是「润色层」

`memory/pipeline.py:37-173` 是硬编码的事件分桶 + 计数器 + 模板；
LLM 只在 `:179-194, 256-267, 509-522` 被用来**改写一个句子**，并带「数字必须出现在证据里」的防幻觉校验。

→ 标注 **RULE-BASED with LLM veneer**（真实、可解释、但谈不上智能）。

### 4.2 真实写入的表（实测）

| 表 | 行数 | 状态 |
| --- | --- | --- |
| `memory_evidence` | 378 | REAL |
| `memory_candidates` | 43 | REAL |
| `student_memories` | 48 | REAL |
| `profile_insights` | 921 | REAL（5 档定性，无百分比） |
| `student_episodes` | 239 | REAL（**但 embedding 全空**，见 §4.3） |

### 4.3 ⚠️ `student_episodes.embedding` **从不写入** → `DISCONNECTED`

- `memory/pipeline.py:376` 硬编码 `embedding=None`。
- 实测：`student_episodes` **239 行 / 0 个 embedding**。

**后果**：情节记忆是**只写的**——存进去了，但**从不被检索、从不注入 prompt**。
`/me/episodes` 因此是一个**纯 UI 功能**：学生能看到，AI 永远看不到。
（按钮「点击后前端调用 `read_episode` 触发 `EPISODE_READ` 事件」这类交互也不影响这一点。）

### 4.4 `.agent.md` 渲染（REAL，但有一处硬编码）

`agent_md.py:122-221` 真实渲染结构化记忆视图，通过 `GET /api/v1/me/agent.md` 暴露
（实测返回 **125 KB** Markdown，内容为真实数据）。
⚠️ 但标题在 `agent_md.py:132,170` 硬编码为 `"# xiaoming.agent.md"`——**所有学生的文件名都是 xiaoming**。

**并且前端根本不用它**：`ArchiveDocCard.tsx:47` 在浏览器里用 `buildMarkdown()` 自己合成了一份 `.agent.md`
（见 `docs/04-frontend.md` §4）。→ 后端能力 `DISCONNECTED`（无消费者）。

### 4.5 记忆合并任务（REAL）

`queue.py:203-218` 入队 → `worker.py:38-41` 分发 → `handlers/memory.py` 执行。实测 **259 次 success**。

---

## 5. Quiz（`app/modules/quiz/`）

### 5.1 题目来源优先级（`skill.py:123-199`）

```
chapter_id 存在？
 ├─ 是 → 1) 审校题库 reviewed_questions (APPROVED + 年级匹配)
 │        2) LLM 生成（严格结构校验，失败即弃）
 │        3) 章节确定性模板生成（chapter_source.py，基于本章真实正文）
 │        4) （仅 allow_bank_fallback 时）通用题库
 └─ 否 → 通用题库 quiz_bank
```

### 5.2 ⚠️ 实际生产中 89% 是**硬编码的 8 题题库**

实测 `quiz_sessions.model_info->>'provider'` 分布：

| provider | 会话数 | 说明 |
| --- | --- | --- |
| `quiz-bank` / `quiz-bank-v1` | **79** | 8 题硬编码题库（`quiz_bank.py:17-158`） |
| `quiz-skill` / `chapter-content-v2` | 4 | 章节确定性模板 |
| `openai_compatible` / deepseek | 3 | 真实 LLM 出题 |
| `reviewed` | **0** | 见 §5.3 |

### 5.3 ⚠️ 审校题库链路 **DISCONNECTED**（运行时）

代码、迁移、数据文件、测试**全都在**：
- 迁移 `a7b8c9d0e1f2`（`reviewed_questions` 表，未提交）
- 导入器 `app/scripts/import_assessments.py`（未提交）
- 数据 `backend/data/library/assessments/{ai-not-magic-junior,ai-primary-fun,ml-how-machines-learn}/ch01.json`
- 选择器 `quiz_bank.py:193-239`、集成 `quiz/skill.py:154-183`
- 测试 `tests/test_reviewed_assessments.py`

**但是**：`import_assessments.py` **没有被 `scripts/start.sh` / `ci.sh` / `ci-e2e.sh` / `.github/workflows/ci.yml` 中的任何一处调用**
（全仓检索确认：只有测试文件调用它）。→ 全新环境 bootstrap 后 `reviewed_questions` 恒为空 → 审校题路径**永不触发**。

### 5.4 判分是真的；反馈与提示是假的

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| 服务端权威判分 | **REAL** | `skill.py:425-440`、`quiz/service.py:417-421, 484-499` |
| 答案在作答前不下发 | **REAL** | `quiz/service.py:337-344` |
| AI 反馈文本 | **HARDCODED** | `quiz/service.py:594-598` 两句字面量字符串，无 LLM 调用 |
| 非题库题的提示 | **HARDCODED** | `skill.py:451-457` 三个 hint level 返回**同一句话** |

### 5.5 已知计数缺陷

`skill.py:176-183`：审校题来源可能返回**少于** `question_count` 的题目，
但 `result_summary`（`:295-299`）仍按 `question_count` 声称题量 → 前后不一致（PARTIAL）。

---

## 6. 后台任务（`app/jobs/`）

### 6.1 队列（REAL，设计正确）

`jobs/queue.py:48-148`：
- `FOR UPDATE SKIP LOCKED` 认领 → 多消费者安全
- 指数退避 `next_attempt_at`（`config.py:42-43`）
- `recover_stale_running`：`running` 超 TTL（默认 600s）视为崩溃遗留并回收
- 3 个 handler 全部注册（`worker.py:29-42`）

实测成功数：`knowledge_ingest` 272、`memory_consolidation` 259、`conversation_summary` 105。

### 6.2 ⚠️ Worker 的启动是**脆弱的**（DISCONNECTED by default）

- `main.py:31-34` 的 `lifespan` **不做任何事**（注释还写着「当前无任何外部依赖」，已过时）。
- `docker-compose.yml` 的 `worker` 服务带 `profiles: ["worker"]` → **`docker compose up` 不会启动它**。
- 实际启动路径只有两条：`scripts/start.sh`（宿主机进程）与 `Dockerfile` 的 `CMD`。

**风险**：任何忘记用 `scripts/start.sh` 的部署方式，都会得到一个「API 正常但任务永不消费」的系统——
记忆不再合并、摘要不再生成、知识资源永远停在 `UPLOADED`，而且**没有任何告警**。

---

## 7. 教学评测（`backend/evals/`）

`evals/teaching_cases.jsonl`（37 例）+ `run_teaching_eval.py`。
但 `run_teaching_eval.py:33-40` 的离线模式输出的是**预置的 `"observed"` 判定**，只校验协议格式；
真实模式需要显式环境变量、**不在 CI 中**。

→ **没有自动化教学质量门禁**（PARTIAL）。`docs/plans/current-phase.md:36` 也自述「真实付费模型教学评测待授权与预算」。
