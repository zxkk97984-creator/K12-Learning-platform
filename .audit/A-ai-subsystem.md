# A — AI Subsystem Code Archaeology (霜铃 K12 backend)

**Scope:** `/home/zxk/Projects/K12-Learning-platform/backend` — `app/ai/`, `app/skills/`,
`app/modules/conversation/`, `app/modules/knowledge/`, `app/modules/memory/`,
`app/modules/quiz/`, `app/jobs/`.
**Method:** direct source reading (all claims cite file + line + symbol), plus *runtime* evidence from the
live dev stack (PostgreSQL `shuangling` DB, running API on :8002, running worker PID 40896, `/tmp/k12-*.log`).
No code was modified.

**Status legend**

| Label | Meaning |
|---|---|
| **REAL** | Works end-to-end; exercised in the running system (code path + runtime data). |
| **PARTIAL** | Works, but with material gaps/degradation versus what it appears to do. |
| **MOCK** | Deterministic placeholder returning canned data. |
| **STUB** | Contract/skeleton only; behaviour not implemented. |
| **HARDCODED** | Behaviour produced by literals in code rather than by model/data. |
| **DISCONNECTED** | Code exists but has no live caller / entrypoint. |
| **UNKNOWN** | Not determinable from available evidence. |

---

## 0. Environment snapshot: declared vs actually executed

| Item | Declared | Actually executed (evidence) |
|---|---|---|
| LLM provider | `app/config.py:25` default `ai_provider="mock"`; `.env.example:13` `AI_PROVIDER=mock` | **Live `.env` sets `AI_PROVIDER=openai_compatible`**, `AI_MODEL=deepseek-v4-flash`, `AI_BASE_URL=https://api.deepseek.com` → real vendor calls occur. DB: 33 TEACHER messages carry `{"provider":"openai_compatible"}` (`select model_info from messages`), e.g. `deepseek-v4-flash` 2026-09-07 06:23. |
| Embedding provider | `config.py:31` default `mock` (64-dim) | **Live `.env` sets `openai_compatible`, dim 1024** (dashscope compatible-mode, `qwen3.7-text-embedding`). DB: 467 chunks at 1024 dims — real embeddings were produced. |
| Voice ASR | `config.py:66` default `mock` | `.env` `VOICE_PROVIDER=aliyun` + dashscope key present → `AliyunASRProvider` is the active ASR. |
| Voice TTS | `config.py:70` default `tts_provider="none"`; **no `TTS_PROVIDER` in `.env`** | → `get_tts_provider()` raises `TTSUnavailableError` (`app/ai/voice.py:322-326`). **Voice replies are text-only in this deployment.** |
| Worker | `Dockerfile:20` CMD worker; `docker-compose.yml` `worker` service has `profiles: ["worker"]` → **not started by a plain `docker compose up`** | `scripts/start.sh` (section "4/7 启动后台 Worker") starts `uv run python -m app.jobs.worker`; PID file `backend/.worker.pid`=40896, and `ps -p 40896` confirms `uv run python -m app.jobs.worker` is running. |
| API startup | `app/main.py:31-34` `lifespan` only does `yield` | **The worker is NOT started by the API process.** A bare `uvicorn app.main:app` deployment has no consumer → jobs queue forever. |

DB counters used throughout (live): `conversations=156, messages=535, conversation_summaries=4,
student_memories=66, memory_candidates=50, profile_insights=931 (20 ACTIVE), quiz_sessions=89,
quiz_questions=107, reviewed_questions=5, knowledge_resources=497 (102 READY / 395 FAILED),
knowledge_chunks=1152 (1103 with embedding: 636×64-dim, 467×1024-dim), student_episodes=248
(0 with embedding)`.

---

## 1. `app/ai/` — provider gateway

### 1.1 Providers and selection

| File | Symbol | Finding |
|---|---|---|
| `app/ai/base.py:6-26` | `class AIProvider(ABC)` | **REAL contract, but minimal**: abstract surface is *only* `stream_chat(history, system_prompt)` + `model_info` + `last_usage`. No completion, no tools, no JSON mode, no cancellation token. |
| `app/ai/factory.py:7-23` | `get_ai_provider()` | **REAL env-driven factory.** `settings.ai_provider.strip().lower()`: `"mock"` → `MockAIProvider`, `"openai_compatible"` → `OpenAICompatibleProvider`, else `ValueError`. **Only 2 providers exist** (no Anthropic/OpenAI-SDK/Gemini/ollama). Note it does **not** pass `timeout_seconds`, so the 30 s default in `openai_compatible.py:39` is always used. |
| `app/ai/factory.py:7` | call frequency | A **new provider object is constructed per LLM call** (`conversation/service.py:634, 962`, `memory/pipeline.py:184`, `quiz/skill.py:359`). Consequence: a fresh `httpx.AsyncClient` per call (`openai_compatible.py:75`) → no connection pooling/TLS reuse; `last_usage` cannot race across requests but also cannot be aggregated. |

### 1.2 Streaming — there is no token streaming

**Finding: PARTIAL / mislabelled.** `OpenAICompatibleProvider.stream_chat` issues **one blocking
non-streaming POST** and then re-slices the finished string:

- `app/ai/openai_compatible.py:64-69` — payload contains `"stream": False`.
- `app/ai/openai_compatible.py:80-87` — a single `await client.post(f"{base_url}/chat/completions", ...)`.
- `app/ai/openai_compatible.py:103-104` — `for start in range(0, len(text), 16): yield text[start:start+16]` — a tight loop with **no delay**; all 16-char "deltas" are emitted at once after the full completion has already arrived.

`grep -rn '"stream"' app/` returns exactly one hit (`openai_compatible.py:68`, `False`). There is **no SSE
parser, no `httpx.stream`, no `iter_lines`, no partial-JSON decode** anywhere in the codebase.

The *transport* to the browser genuinely is SSE, but the token economy is fake:

- `app/modules/conversation/router.py:95-111` — returns `StreamingResponse(..., media_type="text/event-stream")` with `X-Accel-Buffering: no`.
- `app/modules/conversation/service.py:124-137` — `_sse_frame(event, data)` builds `id:/event:/data:` frames.
- `app/modules/conversation/service.py:1179-1216` — `_provider_chunks()` puts provider chunks through an `asyncio.Queue` and emits a `": ping\n\n"` heartbeat on a **15 s** timeout so the connection survives while the non-streaming call is in flight.
- `app/modules/conversation/service.py:962-983` — consumer loop yields one `text.delta` SSE frame per chunk.

Behaviour consequence: the user sees nothing until the whole completion returns, then a burst of deltas.
A 30 s hard timeout (`openai_compatible.py:39,48,76`) bounds the *entire* generation, so long answers
risk `AI_PROVIDER_ERROR` (`service.py:1047-1054`). Observed real completions max 951 chars / avg 308 chars
(`max(length(content))` over `openai_compatible` messages) — comfortably inside 30 s, so the defect is latent.

### 1.3 Exact request payloads

**Chat (`app/ai/openai_compatible.py:56-71`):**

```python
messages = [{"role": "system", "content": system_prompt}]
messages.extend({"role": "assistant" if m.get("role") == "assistant" else "user",
                 "content": str(m.get("content", ""))} for m in history)
payload = {"model": self.model, "messages": messages,
           "max_tokens": self.max_tokens, "stream": False}
if self.thinking_mode != "auto":
    payload["thinking"] = {"type": self.thinking_mode}   # .env: disabled
```

Defects: (a) **any non-assistant role is coerced to `user`** — a persisted `SYSTEM` message
(mapped at `service.py:573-577`) is sent to the model as a user turn; (b) `temperature`, `top_p`,
`stop`, `response_format`, `seed` are never sent; (c) `max_tokens` comes from `AI_MAX_TOKENS` (512 in
`.env.example`; unset in live `.env` → 512 default) with **no truncation/finish_reason check** — a
`finish_reason == "length"` answer is silently persisted as if complete.

**Embeddings (`app/ai/embedding.py:86-93`):** `POST {base_url}/embeddings` with
`{"model": ..., "input": text}` — **one chunk per HTTP request**, synchronous `httpx.Client`
(i.e. blocking I/O inside an async request/worker path, `embedding.py:79-85`), no batching.

**Headers:** `Authorization: Bearer {api_key}` + `Content-Type: application/json` in both
(`openai_compatible.py:82-85`, `embedding.py:88-91`). Proxy picked from `HTTPS_PROXY/HTTP_PROXY/ALL_PROXY`
with `trust_env=False` (`openai_compatible.py:12-25, 74-79`).

### 1.4 Does `openai_compatible.py` actually work?

**REAL (verified), with these caveats:**

| Aspect | Verdict | Evidence |
|---|---|---|
| URL construction | REAL | `base_url.rstrip("/") + "/chat/completions"` (`:43, :81`). Live base `https://api.deepseek.com` → `…/chat/completions`. |
| Auth | REAL | Bearer header `:83`. |
| Error handling | PARTIAL | HTTP ≥400 → `RuntimeError("AI_PROVIDER_ERROR: HTTP {code}: {detail[:500]}")` (`:88-92`); missing/odd JSON → `RuntimeError("unexpected chat completions response")` (`:98-101`). But these are swallowed upstream: `service.py:1047-1054` converts **every** exception into the constant user-facing string `"AI provider unavailable"`, discarding the code and the vendor detail (only logged locally). |
| Timeouts | PARTIAL | 30 s total (connect+read+write) hardcoded default; not configurable from settings; no per-request override; no connect/read split. |
| Retries | **ABSENT** | `grep -rn "retry\|retries\|tenacity\|backoff" app/ai/ app/modules/conversation/` → **0 hits**. A single transient 429/5xx/timeout fails the whole teacher turn (and, for quizzes, silently degrades the question source). |
| Streaming | **ABSENT** | see §1.2. |
| Real traffic proof | REAL | 33 TEACHER messages with `provider=openai_compatible` persisted; `grep -c "AI provider stream failed" /tmp/k12-backend.log` → **0**. |
| Constructor validation | REAL | Missing `base_url`/`api_key` raises `ValueError` (`:41-42`), surfaced as `AI_PROVIDER_ERROR` at request time. |

### 1.5 Is `mock` the default? What does mock return?

**Yes — the code default is mock; the live deployment overrides it.**
`config.py:25` `ai_provider: str = "mock"`, `config.py:26` `ai_model = "mock-model"`.

`app/ai/mock.py:8-92` `MockAIProvider`:
- `_reply_for(content)` (`:26-50`) is a **keyword → canned Chinese paragraph** lookup: `"训练数据"`,
  `("为什么出错","报错","错误","出错")`, `("出题","题目","练习")`, `("解释","讲给我听","怎么理解")`,
  else a generic "这是个很好的问题…" paragraph. **Purely HARDCODED.**
- `_reference_reply(system_prompt)` (`:52-75`) parses the `【知识库参考】` block the RAG path injects and
  echoes `根据知识库资料：{first 140 chars}（参考：{source}）`. This is the only "RAG-aware" mock behaviour and
  it is how `tests/test_ai_provider.py:60-83` proves retrieval→prompt wiring without a real model.
- `stream_chat` (`:77-92`) picks the **last user/student message**, truncates the reply to `max_tokens`
  **characters** (not tokens), and yields 8-char slices with a 30 ms `asyncio.sleep` — simulated streaming.

### 1.6 Agent / tool-calling loop

**There is none.** `grep -rn "tool_calls\|function_call\|\"tools\"\|tool_choice" app/` → **0 hits**.
Every LLM call site is a single-shot completion:

| Call site | Purpose | Shape |
|---|---|---|
| `conversation/service.py:1190` | teacher reply | 1 call, full history + system prompt |
| `conversation/service.py:634-637` | evidence Q&A re-phrasing | 1 call, **empty history** |
| `memory/pipeline.py:184` | rewrite one memory/insight sentence | 1 call, empty history |
| `quiz/skill.py:359` | generate N questions as JSON | 1 call, empty history |

The `tool.start` / `tool.result` SSE frames emitted for quizzes
(`conversation/service.py:738-748, 812-824`) look like an agent tool loop but are **HARDCODED**:
the branch is entered by substring keyword matching, not by a model decision —

- `service.py:55` `QUIZ_INTENT_KEYWORDS = ("出题", "题目", "测验", "quiz", "考考我")`
- `service.py:70-72` `_is_quiz_intent()` → `any(kw.casefold() in content.casefold())`
- `service.py:612` `quiz_intent = _is_quiz_intent(request.content)`

**Behavioural defect:** *any* message containing 「题目」/「测验」 triggers a brand-new quiz instead of an
answer — e.g. "这道题目我不会，讲讲吧" creates a 3-question quiz and never explains. The LLM never sees
that turn (`service.py:723-889` short-circuits before the provider branch).

### 1.7 Embedding providers

| Symbol | Verdict | Evidence |
|---|---|---|
| `MockEmbeddingProvider` (`embedding.py:32-47`) | **MOCK** | Per-dimension SHA-256 of `f"{text}::segment::{i}"` → uniform noise, L2-normalised. **No semantic similarity whatsoever**; nearest-neighbour results are arbitrary. Dimension from `settings.embedding_dimension` (default 64). |
| `OpenAICompatibleEmbeddingProvider` (`embedding.py:50-126`) | **REAL** | `POST /embeddings`, bearer auth; validates finite numeric list, **enforces `len == configured dimension`** (`:121-125`) and L2-normalises. Live proof: 467 knowledge chunks stored at 1024 dims. |
| `get_embedding_provider()/get_embedding()` (`:129-144`) | **REAL but wasteful** | Factory called **per `embed()` call** → new `httpx.Client` per text; blocking sync I/O in async paths (`ingestion.py:199` inside the worker's async session, `service.py:132` inside an HTTP request). |
| Dimension coupling | **PARTIAL / operational trap** | Live DB mixes **636×64-dim (legacy mock) + 467×1024-dim**. Vector SQL filters `vector_dims(kc.embedding) = :embedding_dimension` (`knowledge/service.py:165`), so **58 % of embedded chunks are invisible to retrieval** under the current 1024-dim provider. This is documented as intentional in `alembic/versions/c7d8e9f0a1b2_allow_variable_embedding_dimensions.py` and `app/scripts/reindex_embeddings.py:1-20`, but it is a live recall hole until `reindex_embeddings` is run. |

### 1.8 Voice

| Symbol | Verdict | Evidence |
|---|---|---|
| `MockASR` (`voice.py:32-43`) | **MOCK** | Any non-empty audio → the fixed string `"这里是什么意思"`. |
| `AliyunASRProvider` + `AliyunASRSession` (`voice.py:55-235`) | **REAL** | Full duplex DashScope WebSocket protocol: `run-task` frame (`:189-207`), `task-started` gating with 10 s timeout (`:107-108`), partial/final sentence events (`:83-87`), free-tier-exhausted model rotation (`:213-217`), PCM framing (`:224-227`). Active because `.env VOICE_PROVIDER=aliyun`. |
| `MockTTS` (`voice.py:237-255`) | **MOCK** | Returns a **1-second silent 8 kHz WAV** regardless of text. |
| `OpenAICompatibleTTS` (`voice.py:274-314`) | **REAL code, currently off** | `POST /audio/speech`; raises `TTSUnavailableError` on HTTP/network failure. **Not selected**: no `TTS_PROVIDER` in `.env` → `get_tts_provider()` (`:317-329`) hits the `("", "none")` branch and raises. The voice WS then emits `{"type":"error","code":"TTS_UNAVAILABLE"}` (`voice/ws.py:142-155`). Deliberate (no fake audio) but means the voice feature has **no audio output** in this deployment. |
| Voice loop (`modules/voice/ws.py:84-180`) | **REAL** | ASR → `ConversationService.send_message()` **in-process** (`ws.py:119-129`), scrapes `text.done` out of the SSE stream (`_parse_sse_text_done`, `:58-72`) → then TTS. Barge-in/state machine real (`:263-295`). |

---

## 2. `app/skills/` — the "Skills" abstraction

**Finding: REAL but vestigial — a 1-entry name→object map around the quiz generator.**

- `app/skills/base.py:4-8` `class Skill(Protocol)` — **STUB-level contract**: only `name: str` and
  `skill_version: str`. No `invoke()`, no input/output schema, no prompt template, no tool declaration.
- `app/skills/registry.py:5-7` — `_SKILLS = {"quiz": QuizSkill()}`. **Exactly one skill is registered.**
- `app/skills/registry.py:10-15` `get_skill(name)` — dict lookup, `ValueError` on miss.
- **Invocation:** `app/modules/quiz/service.py:38` imports it and `:122`
  `self.skill = skill or cast(QuizSkill, get_skill("quiz"))`. That is the *only* production caller
  (`grep -rn "get_skill" app/` → `quiz/service.py:122`, plus `app/skills/__init__.py` re-export and 4 tests).
  There is **no generic "skill dispatch"** from the conversation agent; `ConversationService` hardcodes
  `self.quiz_service = QuizService()` (`conversation/service.py:282-283`) and calls it directly.
- **Rule-based or LLM-prompt-based?** QuizSkill is **primarily rule/deterministic**, with an *optional*
  LLM branch — see §6.

**End-to-end trace of the only registered skill (`QuizSkill.generate`, `quiz/skill.py:106-311`):**

1. `POST /api/v1/conversations/{id}/messages` with content containing 「出题」 → `service.py:612` sets `quiz_intent`.
2. `service.py:752-771` reads `bookId`/`chapterId` from the client screen-context snapshot and calls
   `QuizService.create_session(..., question_count=3, difficulty="MEDIUM", allow_bank_fallback=False)`.
3. `quiz/service.py:171-237` re-validates ownership/PUBLISHED status, builds `QuizGenerationContext`.
4. `quiz/service.py:238` → `get_skill("quiz").generate(session, context)`.
5. `quiz/skill.py:130-151` `load_chapter_source()` (`chapter_source.py:64-162`) reads real
   `Chapter`/`Book`/`ContentBlock`/`KnowledgePoint` rows (PUBLISHED-only).
6. Source priority (`skill.py:153-198`):
   `reviewed_questions` (APPROVED, chapter+grade) → `_try_llm_generate` (real provider only,
   `skill.py:323-324`) → `generate_chapter_questions` (deterministic templates,
   `chapter_source.py:186-217` with builders at `:220-316`) → static `QUIZ_BANK`
   (`quiz_bank.py:17-166`).
7. Rows + immutable snapshot written (`skill.py:253-311`), `LearningEvent("QUIZ_CREATED")` added by
   `quiz/service.py:247-259`, committed.
8. SSE: `tool.start` → `tool.result{quiz_session_id}` → `text.delta` ×2 → `text.done` → `message.done`
   (`service.py:738-888`), TEACHER message persisted with `metadata_={"tool":"quiz", ...}`.

---

## 3. `app/modules/conversation/` — message flow, context, SSE

### 3.1 Full send flow (HTTP → service → context → LLM → persistence → SSE)

`POST /api/v1/conversations/{conversation_id}/messages`
(`router.py:80-111`, student auth via `api/deps.py:51-57`)

1. **Lock** — `service.py:431-480` `send_message()`: Redis `acquire_lock("lock:conversation:{id}", 120s)`
   with in-process `asyncio.Lock` fallback (`_conversation_lock`, `:66-67`); lock released in the SSE
   generator's `finally` (`:470-479`).
2. **Preflight before the stream** (`_send_message_locked`, `:482-559`): profile → `SELECT … FOR UPDATE`
   on the conversation row → idempotency-key replay check (`:505-523`) → ownership/DELETED checks →
   `screen_context` replace-or-inherit (`:536-541`) → allocate `sequence = max+1` (`:543-545,
   395-404`) → **persist + commit the STUDENT message** (`:547-560`).
3. **History build** (`:564-578`): all messages for the conversation, ascending, role-mapped
   `STUDENT→user / TEACHER→assistant / SYSTEM→system`.
4. **Summary + window** (`:580-606`): latest `ConversationSummary` (`:256-262`), then
   `build_input_window(...)` with `settings.context_window_token_budget` (default 3000).
5. **Evidence branch** (`:613-642`): `is_evidence_question()` (`memory/agent_md.py:58-70`) regex/router;
   rule-based citation reply from `build_evidence_reply`; if the provider is real, an **extra** LLM call
   re-phrases the evidence (`:626-642`).
6. **RAG retrieval** (`:643-662`): `retrieve(session, request.content, screen_context=current_context, limit=3)`
   — **skipped** when quiz intent or an evidence reply already exists.
7. **Persona** (`:663-674`) from `TeacherRole` (persona/tone/teaching_style), then
   **TeacherContext** (`:677-689`) from `build_teacher_context`, then `teacher_usage_note()`.
8. **System prompt assembly** (`:690-706`) — see §3.2.
9. **Three mutually exclusive generation branches**, each with its own persistence + SSE tail:
   - **quiz intent** (`:723-889`) — no LLM; canned `intro`/`outro`, quiz tool frames.
   - **evidence reply** (`:891-958`) — pre-computed text sliced into 8-char deltas.
   - **provider stream** (`:960-1054`) — `get_ai_provider()` → `_provider_chunks()` → `text.delta`* →
     `text.done{usage}` → insert TEACHER `Message` → commit → `_enqueue_summary_if_needed` → `message.done`.
   Error tails: `EmptyAIResponseError` → `AI_EMPTY_RESPONSE`; any exception → `AI_PROVIDER_ERROR`
   (`:1039-1054`), with `session.rollback()`.
10. **Summary job** (`:406-429`): if total messages ≥ `SUMMARY_MESSAGE_THRESHOLD` (20) and no pending job
    with the same payload, `enqueue(session, "conversation_summary", {...})` + commit.

**Idempotent replay** (`_replay_stream`, `:1058-1177`): re-emits the stored teacher content as
`text.delta` 16-char frames plus a reconstructed `tool.start/tool.result` pair for quiz turns, with
`"replay": True`. `router.py:108-110` sets `Idempotency-Replayed`.

### 3.2 What actually goes into the prompt

`service.py:695-706` concatenates, in order, only the non-empty parts:

1. `persona_block` — `【教师人格】base_persona/tone/teaching_style` (`:663-674`).
2. `summary_context` — `【本会话长对话摘要（v{n}）】` (`:590-594`) or the "earlier context may be
   unavailable" notice (`:605-606`).
3. `teacher_context_block` + `teacher_usage_note()` (`:677-689`, `teacher_context.py:204-452`) —
   eight DB-backed sections: 学生档案 / 学习偏好 / 长期记忆 (top 5 ACTIVE `StudentMemory`) /
   画像洞察 (top 5 ACTIVE `ProfileInsight`) / 最近学习事件 (10) / 最近测验 (5, with **N+1 queries per
   quiz session**, `teacher_context.py:315-335`) / 当前阅读位置 (chapter, visible section, up to 3
   `ContentBlock` excerpts of 160 chars, knowledge points, selected text) / 正在讲解的题目
   (server-authoritative quiz review snapshot, `teacher_context.py:128-201`).
4. `reference_block` — **RAG**: `【知识库参考】` with `- 内容：/- 来源：/- 链接：` per chunk (`:654-662`).
5. `evidence_context` (only if non-empty).
6. `instruction_block` — fixed persona line + `当前页面上下文：{json}` (the *raw* client snapshot).

**Notes / defects:** memory & insight injection is **not** similarity-based (recency only,
`ORDER BY updated_at/valid_from DESC LIMIT 5`); there is no token budgeting for these sections beyond
hard-coded char/row caps (`teacher_context.py:40-46`); the whole block is rebuilt from ~10–20 queries on
every single message.

### 3.3 SSE semantics

Event vocabulary in `service.py`: `message.start`, `text.delta`, `text.done`, `message.done`,
`tool.start`, `tool.result`, `error` (`_sse_error`, `:140-156`, `fatal: True`), plus comment heartbeats
`": ping\n\n"` (`:968`). Envelope helpers at `:124-137`; ids are `message_id`s. Verified by
`tests/test_conversation_sse.py:217-234` (`names[0]=="message.start"`,
`names[-2:]==["text.done","message.done"]`, `text.delta>1`) and consumed by the frontend
(`frontend/src/shared/api/api-conversation-service.ts`, `sse.test.ts`).

**Streaming authenticity caveat:** with the real provider, deltas arrive only after the full completion
(§1.2). The only *genuine* incremental behaviour is the mock provider's 30 ms-per-8-chars pacing.

### 3.4 `context_window.py` — what the token budget really does

- `estimate_tokens()` (`:23-27`) = `int(len(text) * 0.6)` — a **character heuristic**, honestly documented.
- `build_input_window()` (`:45-88`): if a summary exists **and** `summary_message_count > 0`, take
  `history[summary_message_count:]`; otherwise take everything. Then accumulate from **oldest to newest**
  until the budget is exceeded (`:67-75`), and if anything was dropped, **keep only the newest message**
  (`:76-78`) — a latent bug: even when e.g. 8 of 10 recent messages would fit, a single over-budget item
  discards *all* older ones, so the "window" collapses to one turn. `early_context_unavailable` is set
  only when there is no summary (`:87`).
- **Semantic trap:** `message_covered_count` is set to `len(messages)` by the summary handler
  (`jobs/handlers/conversation.py:77,86`) while the stored summary is *not* a summary of all those
  messages — see §7. Everything before that index is **dropped from the model's input**.
- Real DB sample: one summary has `message_covered_count=22`, `token_count=38`,
  body `"会话摘要：\nSTUDENT: 长对话消息 1…\nTEACHER: 上下文已收到"` → 22 messages of context compressed
  into 38 characters.

---

## 4. `app/modules/knowledge/` — ingestion, retrieval, RAG wiring

### 4.1 Ingestion pipeline (upload → parse → chunk → embed → store)

**Entrypoint:** `POST /api/v1/admin/knowledge/resources` (`admin/router.py:292-345`) → idempotency
wrapper (`admin/service.py:98-146`) → `AdminService.upload_knowledge_resource` (`admin/service.py:439-501`):
size check, extension→`MARKDOWN|TXT|HTML|PDF`, `%PDF-` magic check, `storage_key = knowledge/{admin_id}/{uuid}.{ext}`,
`get_storage().put(...)`, insert `KnowledgeResource(status="UPLOADED")`, `enqueue(session,"knowledge_ingest",
{"resource_id": ...})`.

**Worker side:** `jobs/handlers/knowledge.py:11-25` → `ingest_stored_resource`
(`knowledge/ingestion.py:312-372`): read bytes via storage abstraction (`load_resource_bytes`, `:86-104`),
then `parse_pdf` for PDF else UTF-8 decode, `parse_markdown`, then `ingest_text` (`:209-309`).

**Is parsing real?**
- `parse_markdown` (`:24-49`) — REAL but trivial: heading-prefix detection (`#`), accumulates lines into
  blocks. Applied **uniformly to TXT/HTML/PDF text**, so HTML is *not* parsed — raw tags flow into chunks;
  section keys are heading text only.
- `parse_pdf` (`:169-195`) — PARTIAL/dual: tries `pypdf` if importable, else a hand-rolled
  content-stream literal-string extractor (`_pdf_content_streams:152-166`, `_pdf_literal_strings:107-149`)
  with FlateDecode support; raises if nothing extractable. `pypdf` **is** a declared dependency
  (`pyproject.toml`), so the real path is used.

**Is chunking real? YES, but naive:** `chunk_blocks` (`:52-70`) keeps blocks ≤ 500 chars intact and
otherwise slices by **fixed 500-char windows with no overlap, no sentence boundary awareness**
(`MAX_CHUNK_CHARS=500`, `:20`). `token_count` is stored as `len(content)` characters (`:295`).

**Is embedding real? YES (provider-dependent):** `_embedding_value` (`:198-200`) calls `get_embedding()`
and serialises to a pgvector literal `"[v1,v2,…]"`. Live: 467 chunks at 1024 dims prove real vendor
embeddings; 395 resources `FAILED` (382 `archived: test data`, 7 `embedding failed`,
6 `embedding provider down`) show the pipeline is failure-prone and that failures are recorded, not hidden.

**Status machine is real:** `UPLOADED→PARSING→CHUNKING→INDEXING→READY`, `FAILED` with `error` text
(`:252, 271-275, 299-309`); re-ingest deletes old chunks (`:262-266`) and is idempotent for `READY`
resources (`:234-239`).

### 4.2 Is vector search actually performed in SQL? — **YES**

`KnowledgeService.search` (`knowledge/service.py:127-202`) builds raw SQLAlchemy `text()` SQL with pgvector:

```sql
SELECT kc.chunk_id, …, CASE WHEN vector_dims(kc.embedding) = :embedding_dimension
       THEN kc.embedding <=> CAST(:query_embedding AS vector) END AS distance
FROM knowledge_chunks kc
JOIN knowledge_resources kr ON kr.resource_id = kc.resource_id
WHERE kc.status='READY' AND kr.status='READY' AND kc.embedding IS NOT NULL
  AND vector_dims(kc.embedding) = :embedding_dimension
  [AND EXISTS (SELECT 1 FROM jsonb_array_elements_text(kc.knowledge_point_ids) kp WHERE kp = ANY(:kp_ids))]
  [AND (<distance>) <= :max_distance]
ORDER BY <distance> LIMIT :limit
```
(`:148-171`.) Cosine distance operator `<=>`, dimension-guarded. Extension confirmed live:
`pg_extension.vector 0.8.6`; HNSW indexes were **dropped** in migration
`c7d8e9f0a1b2_allow_variable_embedding_dimensions.py:33-44`, so this is a **sequential scan** over all
chunks on every message — fine at 1 152 rows, not at scale.

**It is not purely vector search, though** — the vector result set is then post-filtered and re-ranked by
**literal substring tests**, and keyword `ILIKE` takes over whenever the raw query string is not found:

- `:173-174` no rows → `_keyword_fallback` (`:204-231`, `content ILIKE '%{query}%'`).
- `:175-180` rows exist but no row contains the raw query → keyword results are returned **instead**.
- `:181-187` re-sorts by `(0 if query in content else 1, distance)` — a raw-substring match **outranks**
  semantic similarity.

**Trap:** because `_keyword_fallback` interpolates the user's text into `ilike(f"%{query}%")` via SQLAlchemy
(parameterised, so not injectable) but treats `%`/`_` as wildcards, a query containing `%` degrades to a
match-all scan (bounded by `LIMIT`, so a recall bug rather than a DoS).

### 4.3 Is RAG wired into the conversation? — **YES, exact call site**

`app/modules/conversation/service.py:643-653`:

```python
retrieved_chunks = []
try:
    if not quiz_intent and evidence_reply is None:
        retrieved_chunks = await retrieve(session, request.content,
                                          screen_context=current_context, limit=3)
except Exception:
    retrieved_chunks = []
```

`retrieve()` (`knowledge/retrieval.py:58-129`) augments the query with
`screen_context["selected_text"]` + `chapter_title` (`:21-31, 67-72`), searches, then applies
substring/5-gram overlap filters and up to 5 successive n-gram retries (`:90-110`), and finally resolves
`source_name` from `knowledge_resources` (`:112-122`). The chunks are injected as `reference_block`
(`service.py:654-662`) into the system prompt (`:695-706`) with instructions to cite sources.

**Assessment: REAL, but recall-limited in this deployment** — 58 % of embedded chunks (64-dim legacy)
cannot be matched by the 1024-dim query filter, and the `_keyword_fallback`/substring re-ranking means
"semantic" retrieval is often literal matching. The knowledge `POST /knowledge/search` endpoint
(`knowledge/router.py:56-62`) exposes the same service to students.

---

## 5. `app/modules/memory/`

### 5.1 Pipeline: rule-based spine, optional LLM cosmetic layer

`app/modules/memory/pipeline.py` — module docstring says *"Rule-based Memory Pipeline"* and the code
matches: **the extraction logic is HARDCODED/RULE-BASED; the LLM only rewrites the sentence.**

Flow (`MemoryPipeline.process_student`, `:553-593`):

1. Load all `LearningEvent`s; subtract event ids already referenced by `MemoryEvidence` (`:560-571`);
   return early if nothing pending (`:572-573`).
2. `classify_event` (`:62-71`) maps event types to 4 buckets via **literal sets**:
   `QUIZ_EVENT_TYPES`/`CONVERSATION_EVENT_TYPES`/`LEARNING_EVENT_TYPES`/`BOOK_EVENT_TYPES` (`:37-59`).
3. Per `(source_type, dimension)` group → `_aggregate_group` (`:215-380`):
   `_apply_event_facts`/`_merge_facts` (`:74-119`) increment **hardcoded counters**
   (`correct_count`, `explain_requested_count`, …); write `MemoryEvidence` with
   `payload={"dimension":…, **facts}`, `count`, first/last occurred (`:238-251`).
4. **Optional LLM rewrite** (`:256-267`): if `settings.ai_provider == "openai_compatible"`, prompt
   *"请用一句中文描述这位学生的稳定学习表现…禁止编造…"*; output is rejected if it contains a ≥5-digit
   number not present in the facts (`_text_numbers_grounded`, `:196-201`; regex `:35`). On any failure it
   falls through to the template `_candidate_content` (`:122-131`).
5. `MemoryCandidate` upsert (`:270-307`): identical content → merge evidence ids and flip
   `PENDING→APPROVED` at `total_count>=2`; else insert with `rule_version="memory-rule-v1"`.
6. `StudentMemory` write **only when `total_count >= 2`** (`:309-347`), with explicit anti-resurrection
   logic: a DISPUTED/REMOVED/SUPERSEDED row with identical content is never reactivated (`:311-347`).
7. `StudentEpisode` insert (`:349-380`) — **`embedding=None` hardcoded at `:376`.**
8. `_rebuild_insights` (`:476-551`): supersede all ACTIVE `ProfileInsight`s, recompute 4 rule-based
   qualitative insights with **hardcoded thresholds** (`_quiz_insight:382-407`, `_conversation_insight:409-432`,
   `_reading_insight:434-453`, `_book_insight:455-474`), optionally LLM-rewrite each description
   (`:509-522`), insert as ACTIVE.

**Runtime proof of "rule spine":** `profile_insights` = 931 rows, 911 SUPERSEDED / 20 ACTIVE; memory
types present: PREFERENCE 32, EPISODIC 21, LEARNING 7, PROFILE 6; statuses ACTIVE 53, REMOVED 9,
DISPUTED 3, SUPERSEDED 1 — i.e. user-controlled state transitions really happen.

### 5.2 Which memory types/tables are actually written

| Table | Written by | Live count |
|---|---|---|
| `memory_evidence` | `pipeline.py:238-251` | (drives all others) |
| `memory_candidates` | `pipeline.py:290-307` | 50 |
| `student_memories` (`LEARNING`/`PREFERENCE`/`EPISODIC`/`PROFILE`) | `pipeline.py:326-339` | 66 |
| `student_episodes` | `pipeline.py:359-380` | 248 |
| `profile_insights` | `pipeline.py:536-551` | 931 |

**Consolidation job trace:** `LearningEvent` write (`learning/service.py:325-341`) and quiz answer
(`quiz/service.py:602`) call `enqueue_memory_consolidation(session, student_id)` **inside the same
transaction** (`jobs/queue.py:203-218`, dedup via `has_pending_job`) → worker `resolve_handler("memory_consolidation")`
(`jobs/worker.py:38-41`) → `jobs/handlers/memory.py:11-21` → `MemoryPipeline().process_student`.
Live: 259 `memory_consolidation` jobs `success`, 1 stuck in `running` (will be recycled by
`recover_stale_running`, `jobs/worker.py:87`).

### 5.3 `agent_md.py`

- **What it is:** a **rendered Markdown view** of DB memory (docstring `:1-4`: "database is the single
  source of truth; .agent.md is only a rendered view"). `render_agent_md` (`:122-221`) reads
  `StudentProfile`, `StudentPreference`, ACTIVE `StudentMemory`, ACTIVE `ProfileInsight`, `StudentEpisode`
  and inlines evidence summaries (`_evidence_summary`, `:102-119`).
- **Is it exposed via API?** **YES — REAL:** `GET /api/v1/me/agent.md` (`memory/router.py:122-128`) returns
  `text/markdown`. Covered by `tests/test_agent_md.py`.
- **Is it real?** **REAL content, HARDCODED identity.** The title is the literal `"# xiaoming.agent.md"`
  for *every* student (`:132` and `:170`) — the file is never per-student named, and the empty-profile
  branch still emits the xiaoming filename. There is **no physical `.agent.md` file** written anywhere
  (`grep` finds no writer); it is generated on read only.

### 5.4 Is `student_episodes.embedding` ever populated? — **NO**

- Only writer: `pipeline.py:359-380`, and `embedding=None` is passed literally at `:376`.
- Column exists and is a real `VECTOR` (`infrastructure/database/models.py:944-945`), created by
  `f0e1d2c3b4a5_create_episodes_and_insights.py`, re-typed by `c7d8e9f0a1b2`.
- **DB proof: `student_episodes` = 248 rows, `count(embedding)` = 0.**
- Consequence: episodic memory is **write-only** for the AI — episodes appear in `.agent.md` and
  `/me/episodes`, but are never retrieved by similarity and never injected into any prompt.
  **DISCONNECTED.**

---

## 6. `app/modules/quiz/`

### 6.1 Where questions actually come from

`QuizSkill.generate` (`quiz/skill.py:106-311`) resolves sources in this strict order (`:153-198`):

| # | Source | Condition | model_info | Live count |
|---|---|---|---|---|
| 0 | `reviewed_questions` (human-reviewed, APPROVED, chapter+grade match) | `chapter_id` set and rows exist (`:156-168`, `quiz_bank.py:193-239`) | `{"provider":"reviewed","model":"reviewed-question-v1"}` | **0** sessions (only 1 APPROVED row in DB, covering 1 chapter) |
| 1 | **LLM JSON generation** | `ai_provider == "openai_compatible"` and no `bank_fallback_reason` (`_try_llm_generate`, `:313-380`) | `{"provider":"openai_compatible","model":settings.ai_model}` | **3** sessions |
| 2 | **Deterministic chapter templates** | `chapter_source` loaded | `{"provider":"quiz-skill","model":"chapter-content-v2"}` | **3** sessions |
| 3 | **Static `QUIZ_BANK`** (8 hardcoded questions) | default / no chapter | `{"provider":"quiz-bank","model":"quiz-bank-v1"}` | **79** sessions |

DB ground truth (`select model_info->>'provider', count(*) from quiz_sessions group by 1`):
`quiz-bank 79`, `quiz-skill 3`, `openai_compatible 3`, `(null) 4`. **≈89 % of all quizzes ever created in
this deployment came from the 8-question hardcoded bank** (`quiz_bank.py:17-158`), including the
chapter-less "AI_QUIZ" path triggered by chat keywords.

**LLM path details:** `_try_llm_generate` (`:313-380`) builds a Chinese prompt demanding a strict JSON array
of `question_type/stem/options/correct_answer/explanation/knowledge_point_ids`; for chapter quizzes it
injects up to 8 real content excerpts + KP names (`:328-349`). Output is parsed tolerantly
(markdown fences, first `[`…last `]`, `_parse_llm_questions`, `:382-415`), each item structurally
validated by `_is_valid_question` (`:49-72`), and **rejected wholesale unless `len(data) >= question_count`**
(`:368-379`). Every failure logs and falls back **silently to the caller** (model_info records the truth,
so it is auditable).

**Deterministic chapter path** (`chapter_source.py:186-217` + builders `:220-316`) is genuinely
content-derived: single choice from chapter KPs vs 12 "foreign" KP names, true/false from real chapter
text (always TRUE) and from other chapters' text (always FALSE), fill-in-the-blank by blanking a KP name
inside real text, multi-select from chapter KPs + foreign distractors. Reproducible, gradable,
auditable — but **template-shaped** ("以下哪一项是《X》这一章的核心知识点？").

**Known gap in the reviewed path:** `if reviewed_items:` (`:176`) accepts **any** number, even below
`question_count`, while `result_summary` at creation is hardcoded to `{"total": context.question_count}`
(`:295-299`) — a 1-row reviewed chapter would yield a quiz claiming 3 questions with only 1.
(The same mismatch is explicitly guarded for the LLM path at `:368-379`, but not here.)

### 6.2 Quiz lifecycle trace

**Create** — `POST /api/v1/quiz-sessions` (`quiz/router.py:24-30`) → `QuizService.create_session`
(`quiz/service.py:171-262`): ownership + PUBLISHED book/chapter validation, optional "similar practice"
source validation (`:201-215`), `QuizGenerationContext` with `allow_bank_fallback` from the request
(default `True`, `quiz/schemas.py:29`; the **chat path forces `False`**, `conversation/service.py:769`),
`skill.generate(...)`, `LearningEvent("QUIZ_CREATED")`, commit.

**Question selection** — see the table above.

**Answer grading** — `QuizService.submit_answer` (`:439-605`):
row-lock on the session (`:453-455`) → idempotency replay (`:456-464`, `_find_answer_replay:370-416`) →
status gate → `attempt_no = max+1` → **`_is_answer_correct` → `QuizSkill.grade`**
(`:417-421`, `skill.py:425-440`): `MULTIPLE_CHOICE` sorted-keys equality; `FILL_BLANK` casefolded
`strip()` equality; otherwise key equality — **against the server-side `correct_answer`, never the
client's** (the client field is ignored, `:472-474`). `is_final = correct or attempt_no >= MAX_ATTEMPTS`.
Persists `QuizAnswer`, two `QuizInteraction`s (SUBMIT/RESULT), `LearningEvent("ANSWER_CORRECT"/"ANSWER_WRONG")`,
recomputes `result_summary` from actual rows (`:550-579`), flips to `COMPLETED` and increments
`profile.quiz_count` exactly once (`:580-593`), then `enqueue_memory_consolidation` in the same
transaction (`:602`).

**Feedback: HARDCODED.** `quiz_session.ai_feedback` is one of **two literal strings**
(`:594-598`): `"答对了，概念和例子连得很好。"` if the last answer was correct else
`"这次完成了尝试，可以回看解析并总结规律。"`. There is **no LLM feedback call anywhere** — despite the
column name and the `ai_feedback` field in `QuizSessionDTO` (`quiz/schemas.py:57`).

**Answer reveal policy: REAL and correctly gated** — `_question_dto(..., reveal_answer=...)`
(`:85-107`) omits `correct_answer`/`explanation` unless the session is `COMPLETED|ABANDONED` or that
question has been answered (`:337-344`).

**Hints: HARDCODED for non-bank questions.** `QuizSkill.hint` (`skill.py:451-457`) returns the bank
question's 3 authored hints if the question maps to `QUIZ_BANK` (via `source_context["bank_id"]`,
`_find_bank_question:442-449`); otherwise it returns the identical canned sentence
`f"先回到题干，找出它要求你判断的关键规律（提示 {level}）。"` for levels 1–3 — i.e. **level differences are
purely cosmetic for LLM/chapter-generated questions**. Hint governance (max level, idempotency,
`HINT_REQUEST`/`HINT_RESPONSE` interactions, TEACHER `HINT` message persisted into the conversation,
`LearningEvent("HINT_REQUESTED")`) is real (`:650-764`).

---

## 7. `app/jobs/`

### 7.1 The queue

**REAL, PostgreSQL-table-backed** (`d6e7f8a9b0c1_create_background_jobs.py`).
`PostgresJobQueue` (`jobs/queue.py:48-148`): `enqueue` inserts `status="queued", attempt=0`
(`:51-67`); `claim_next` does `SELECT … WHERE status='queued' AND (next_attempt_at IS NULL OR
next_attempt_at <= now) ORDER BY created_at, job_id LIMIT 1 FOR UPDATE SKIP LOCKED`, then flips to
`running`, `attempt += 1`, sets `started_at` (`:69-97`) — correct multi-worker-safe claim;
`recover_stale_running` requeues `running` jobs older than `worker_running_ttl_seconds`
(`:99-124`); `mark_success` (`:126-132`); `mark_failed` retries with **exponential backoff**
`base*2^(attempt-1)` capped (`:134-148`, `_backoff_for:19-24`) until `worker_max_attempts`,
then terminal `failed`. `has_pending_job` dedupes by payload subset (`:185-200`).
**Redis is not used for the queue** (connector module `JobQueue` Protocol at `:26-45` documents the
intended swap). No priority, no scheduling, no per-type concurrency — single-loop FIFO.

### 7.2 Job types and handlers — registered?

Three types, dispatched by an **explicit if-chain** in `resolve_handler` (`jobs/worker.py:29-42`) —
registered and reachable (not a plugin registry, but functional):

| `job_type` | Handler | Enqueued by |
|---|---|---|
| `knowledge_ingest` | `jobs/handlers/knowledge.py:11-25` → `ingest_stored_resource` | `admin/service.py:497` (upload), `:535` (reprocess) |
| `conversation_summary` | `jobs/handlers/conversation.py:39-91` | `conversation/service.py:425` |
| `memory_consolidation` | `jobs/handlers/memory.py:11-21` → `MemoryPipeline.process_student` | `learning/service.py:341`, `quiz/service.py:602` via `queue.py:203-218` |

Unknown type → `UnknownJobTypeError` (`:25-26, 42`) → job marked failed/retried. `process_claimed_job`
(`:45-69`) handles the MissingGreenlet pitfall by re-fetching the job after rollback (documented at
`:47-51`) — this is real, tested hardening.

### 7.3 Is the worker actually started? Entrypoints

- `app/worker.py:1-7` — `python -m app.worker` → `app.jobs.worker.main()`.
- `app/jobs/worker.py:110-118` — `main()` → `asyncio.run(run_worker())`; loop at `:72-107` polls
  `worker_poll_interval` (1 s), commits after claim/recovery even on empty polls, and never lets an
  exception kill the loop.
- `scripts/start.sh` (section "4/7 启动后台 Worker") — `nohup setsid uv run python -m app.jobs.worker &`,
  PID → `backend/.worker.pid`. **This is the real entrypoint in this deployment.**
- `backend/Dockerfile:20` — `CMD ["python", "-m", "app.jobs.worker"]`.
- `docker-compose.yml` `worker:` service — **`profiles: ["worker"]`**, so a plain `docker compose up`
  does **not** start it (comment in the file states this is intentional, to avoid double instances).
- `app/main.py:31-34` — **the API lifespan does not start the worker** (empty `yield`).

**Runtime proof jobs are consumed:** process PID 40896 `uv run python -m app.jobs.worker`;
`background_jobs` = `knowledge_ingest` 272 success / 60 failed, `memory_consolidation` 259 success / 1 running,
`conversation_summary` 105 success, plus one synthetic `rollback_poison_*` 1 failed. The 60
`knowledge_ingest` failures are `"knowledge resource not found: <uuid>"` — jobs enqueued for later-deleted
resources.

### 7.4 The conversation-summary handler is *not* a summarizer (**important**)

`jobs/handlers/conversation.py`:
- `_summary_messages` (`:16-27`) keeps **the first message, only messages whose `type` is in
  `{"QUIZ","HINT","RECOMMENDATION","LEARNING_SUMMARY","SYSTEM"}` (`:12`), and the last message** —
  every ordinary TEXT turn in between is **discarded**.
- `_summary_text` (`:30-36`) prefixes `"会话摘要：\n"` and truncates each retained line to **160 chars**.
- `message_covered_count = len(messages)` (`:77, 86`) claims the summary covers **all** messages, and
  `model_info = {"provider":"rule","model":"conversation-summary-v1"}` (`:78, 87`) proves it is
  **rule-based, not LLM-based** (no `get_ai_provider` call in this file).

**Combined effect with §3.4:** once a conversation crosses the 20-message threshold, the model's input
for subsequent turns is `[summary of first+key+last] + [messages after the boundary]`. Because
`message_covered_count` = total count, **all non-key messages are dropped from context forever** and the
"summary" that replaces them is a 160-char-capped excerpt. Live sample: a real summary with
`message_covered_count=22` and `token_count=38`. This is the single most consequential AI-behaviour
defect found: the assistant silently loses conversation history and the artifact claims otherwise.

Also note the handler is re-run on **every** message after the threshold (new job each time, `:57-58`),
re-reading and rewriting the whole summary; version counter increments (`:84`).

---

## 8. Cross-cutting runtime evidence

| Observation | Command/source | Result |
|---|---|---|
| Real teacher replies persisted | `select role, model_info->>'provider', count(*) from messages group by 1,2` | TEACHER: mock 87, quiz-bank 53, **(none) 35**, openai_compatible 33, quiz-skill 27, rule 13, capturing 2, capture 1 |
| Real LLM latency headroom | `max(length(content))` for `openai_compatible` | max 951, avg 308 chars |
| Provider errors in API log | `grep -c "AI provider stream failed" /tmp/k12-backend.log` | 0 |
| Embedding dimension split | `select vector_dims(embedding), count(*) … group by 1` | 64 → 636, **1024 → 467** |
| Episode embeddings | `select count(*), count(embedding) from student_episodes` | 248 / **0** |
| Knowledge corpus health | `select status, count(*) from knowledge_resources` | READY 102, FAILED 395 (382 `archived: test data`, 7 `embedding failed`, 6 `embedding provider down`) |
| pgvector present | `select extname, extversion from pg_extension` | `vector 0.8.6` |
| Worker alive | `ps -p 40896`, `cat backend/.worker.pid` | running `uv run python -m app.jobs.worker` |
| Metrics endpoint | `GET /metrics` | only HTTP counters/uptime — **no AI/LLM/RAG/token metrics at all** |
| Eval harness | `evals/run_teaching_eval.py:33-40, 79-102` | offline mode **only judges protocol** with canned `"observed"` dims; real mode requires explicit env and is not part of CI → **no automated teaching-quality gate** |

---

## 9. Summary table — component × status × evidence

| # | Component | Status | Key evidence (file:line / symbol) |
|---|---|---|---|
| 1.1 | `AIProvider` contract | PARTIAL | `ai/base.py:6-26` — only `stream_chat`; no tools/JSON/cancel |
| 1.2 | Provider factory (env-driven) | REAL | `ai/factory.py:7-23`; 2 providers only; new instance per call |
| 1.3 | `OpenAICompatibleProvider` HTTP | REAL | `ai/openai_compatible.py:75-101`; 33 real messages, 0 errors |
| 1.4 | Streaming (token-level) | **MOCK** | `openai_compatible.py:68` `stream:False`, `:103-104` post-hoc 16-char slicing; no SSE parse anywhere |
| 1.5 | SSE transport to browser | REAL | `conversation/router.py:95-111`, `service.py:124-137, 708-1056`, `_provider_chunks:1179-1216` |
| 1.6 | Timeouts | PARTIAL | `openai_compatible.py:39,76` — 30 s total, not configurable |
| 1.7 | Retries/backoff on LLM | **ABSENT** | `grep retry/tenacity/backoff app/ai/` → 0 hits |
| 1.8 | Tool/function calling | **ABSENT** | `grep tool_calls/function_call/"tools"` → 0 hits |
| 1.9 | "Agent" quiz tool loop | **HARDCODED** | `service.py:55, 70-72, 612, 723-889` keyword hijack (「题目」 triggers a quiz) |
| 1.10 | `MockAIProvider` | MOCK | `ai/mock.py:26-50` keyword→canned paragraph; `:52-75` RAG echo |
| 1.11 | Mock as default | REAL (default) / overridden live | `config.py:25`; `.env` `AI_PROVIDER=openai_compatible` |
| 1.12 | Mock embedding (hash noise) | MOCK | `ai/embedding.py:32-47` |
| 1.13 | Real embedding adapter | REAL | `embedding.py:50-126`; 467 chunks @1024 |
| 1.14 | Embedding dimension migration | PARTIAL | `c7d8e9f0a1b2…py:33-44`; **636 legacy 64-dim chunks unreachable** |
| 1.15 | Aliyun ASR (duplex WS) | REAL | `ai/voice.py:55-235`; `.env VOICE_PROVIDER=aliyun` |
| 1.16 | Mock ASR | MOCK | `voice.py:32-43` fixed phrase |
| 1.17 | TTS | DISCONNECTED in this deployment | `voice.py:317-329` + no `TTS_PROVIDER` → `TTS_UNAVAILABLE` (`voice/ws.py:142-155`) |
| 1.18 | Usage/token accounting | PARTIAL | `service.py:163-186` real usage in provider branch; `:845-850` and `:914-919` report **character counts as `input_tokens`/`output_tokens`** |
| 2.1 | `Skill` protocol | STUB | `skills/base.py:4-8` — metadata only |
| 2.2 | Skill registry | REAL (1 entry) | `skills/registry.py:5-7` `{"quiz": QuizSkill()}`; caller `quiz/service.py:122` |
| 2.3 | Skill dispatch from agent | **DISCONNECTED** | conversation hardcodes `QuizService()` (`conversation/service.py:282-283`) |
| 3.1 | Message send flow | REAL | `router.py:80-111` → `service.py:431-1056` |
| 3.2 | Per-conversation turn lock | REAL | `service.py:446-479` Redis + asyncio fallback |
| 3.3 | Idempotent replay SSE | REAL | `service.py:505-523, 1058-1177`; `router.py:108-110` |
| 3.4 | System prompt assembly | REAL | `service.py:690-706` (persona/summary/teacher-context/RAG/evidence/instruction) |
| 3.5 | TeacherContext from DB | REAL | `teacher_context.py:204-452`; N+1 per quiz session `:315-335` |
| 3.6 | Memory/insight injection | PARTIAL | recency-only `LIMIT 5` (`teacher_context.py:246-285`), not similarity |
| 3.7 | `context_window` budget | PARTIAL | `context_window.py:45-88`; char heuristic; `:76-78` collapses window to 1 turn |
| 3.8 | Conversation summary quality | **HARDCODED / misleading** | `jobs/handlers/conversation.py:12, 16-36, 77, 86` — first+key+last, 160-char cap, claims full coverage |
| 3.9 | Voice → conversation reuse | REAL | `voice/ws.py:119-129` reuses `ConversationService.send_message` |
| 4.1 | Upload → job enqueue | REAL | `admin/router.py:292-345`, `admin/service.py:439-501` |
| 4.2 | PDF/Markdown parsing | REAL (PARTIAL for HTML) | `ingestion.py:169-195`, `:24-49`; HTML not parsed |
| 4.3 | Chunking | REAL (naive) | `ingestion.py:52-70` — 500-char fixed windows, no overlap |
| 4.4 | Embedding on ingest | REAL | `ingestion.py:198-200, 278`; 467 real vectors |
| 4.5 | Vector SQL search | REAL | `knowledge/service.py:148-171` (`<=>` + `vector_dims`); seq-scan (HNSW dropped) |
| 4.6 | Keyword/substring re-rank | PARTIAL | `service.py:173-187, 204-231` — substring can outrank semantics |
| 4.7 | RAG wired into chat | REAL | `conversation/service.py:643-662` → `retrieval.py:58-129` |
| 5.1 | Memory extraction | RULE-BASED | `memory/pipeline.py:37-173` hardcoded buckets/counters/templates |
| 5.2 | LLM in memory pipeline | PARTIAL (cosmetic) | `pipeline.py:179-194, 256-267, 509-522` — rewrites sentences only, with number-grounding guard |
| 5.3 | Evidence + insight writes | REAL | `pipeline.py:238-251, 290-307, 326-347, 536-551`; 931 insights / 66 memories live |
| 5.4 | Consolidation job | REAL | `queue.py:203-218`, `worker.py:38-41`, `handlers/memory.py`; 259 successes |
| 5.5 | `student_episodes.embedding` | **DISCONNECTED** | `pipeline.py:376` `embedding=None`; DB 0 / 248 populated |
| 5.6 | `.agent.md` rendering | REAL (hardcoded name) | `agent_md.py:122-221`; API `memory/router.py:122-128`; literal `"# xiaoming.agent.md"` at `:132, :170` |
| 6.1 | Question source | **HARDCODED bank dominant** | `quiz_bank.py:17-158` 8 Qs; DB: 79/89 sessions `quiz-bank` |
| 6.2 | LLM question generation | REAL (rare) | `skill.py:313-380`; DB 3 sessions; strict structural validation |
| 6.3 | Deterministic chapter questions | REAL (templated) | `chapter_source.py:186-316`; DB 3 sessions |
| 6.4 | Reviewed question source | PARTIAL / near-unused | `quiz_bank.py:193-239`; DB 1 APPROVED row → 0 sessions; **count bug** `skill.py:176-183` vs `:295-299` |
| 6.5 | Grading | REAL (server-side) | `skill.py:425-440`, `quiz/service.py:417-421, 484-499`; answer hidden until answered (`:337-344`) |
| 6.6 | Feedback | **HARDCODED** | `quiz/service.py:594-598` two literal strings; no LLM call |
| 6.7 | Hints | HARDCODED for non-bank | `skill.py:451-457` one identical sentence for all 3 levels |
| 6.8 | Quiz via chat keywords | PARTIAL (over-triggers) | `conversation/service.py:55, 612, 723-889` — 「题目」 always creates a quiz |
| 7.1 | PG job queue | REAL | `jobs/queue.py:48-148` `FOR UPDATE SKIP LOCKED`, backoff, stale recovery |
| 7.2 | Handler registration | REAL | `jobs/worker.py:29-42` (3 types) |
| 7.3 | Worker entrypoint | REAL but external | `scripts/start.sh`; `Dockerfile:20`; **not** in `main.py:31-34` lifespan; compose profile-gated |
| 7.4 | Live consumption | REAL | PID 40896; 272+259+105 jobs success |
| 7.5 | AI observability | **ABSENT** | `main.py:144-149` + `infrastructure/metrics_registry.py` — no LLM/token/latency/RAG metrics |
| 7.6 | Teaching-quality eval gate | PARTIAL | `evals/run_teaching_eval.py:33-40` canned judgments; real mode manual, not in CI |

---

## 10. Most consequential defects (ranked)

1. **The conversation "summary" deletes history and claims to cover it** — `jobs/handlers/conversation.py:12,16-36,86`
   + `context_window.py:61-65`. After 20 messages the model loses every non-key TEXT turn, replaced by a
   ≤160-chars-per-line excerpt, while `message_covered_count = len(messages)` tells the window builder to
   drop everything before that index. No LLM summarization exists anywhere.
2. **There is no streaming** — `openai_compatible.py:68,103-104`. The SSE layer is honest transport over a
   fake token stream; the entire completion must arrive inside a non-configurable 30 s budget, and there
   are **no retries**.
3. **`student_episodes.embedding` is never written** (`pipeline.py:376`; DB 0/248) — episodic memory is
   unreachable by the AI, making `/me/episodes` a UI-only feature.
4. **58 % of embedded knowledge is invisible to RAG** in this deployment (636 × 64-dim legacy vs 467 ×
   1024-dim active; `knowledge/service.py:165`), and what remains is re-ranked by raw substring matching
   (`:175-187`).
5. **Quiz "AI generation" is 89 % the 8-question hardcoded bank** (`quiz_bank.py`; DB 79/89), with
   **hardcoded two-string feedback** (`quiz/service.py:594-598`) and **one identical hint sentence** for
   every non-bank question (`skill.py:451-457`).
6. **Keyword intent detection hijacks normal questions** — any message containing 「题目」/「测验」
   creates a quiz instead of answering (`conversation/service.py:55, 612`).
7. **Memory is rule-based with an LLM veneer** — the model only rewrites one sentence
   (`pipeline.py:179-194, 256-267`); all extraction thresholds are literals. `.agent.md` is real but
   hardcodes the filename `xiaoming.agent.md` for every student (`agent_md.py:132, 170`).
8. **No agent loop, no tool calling, no retries, no LLM observability** — `tool.start/tool.result` is a
   hardcoded branch, `/metrics` has no AI counters, and the teaching eval gate is protocol-only in CI.
9. **Queue is fine; the worker's startup is fragile** — `main.py` lifespan does nothing and the compose
   worker service is `profiles:["worker"]`; a deployment that forgets `scripts/start.sh` silently stops
   consolidating memory and summarizing conversations.
