# 05 · 后端

> FastAPI 模块化单体，Python 3.12，SQLAlchemy 2.0 async，Alembic。
> 代码量约 **33,245 行**（`backend/` 下 `.py`，含测试）。最大单文件：`infrastructure/database/models.py`（1465 行）。

---

## 1. 应用入口（`app/main.py`，161 行）

| 内容 | 位置 |
| --- | --- |
| `lifespan` | `:31-34` —— **空的**（注释「当前无任何外部依赖」已过时；实际依赖 DB/Redis/Worker） |
| 可观测性中间件 | `:43-94` —— `X-Request-ID` 生成/透传 + 全局限流 + 访问日志 + 指标采集 |
| 限流排除 | `:53-58` —— `/auth/login`（自带 ip+username 维度）、`/health`、`/metrics` 不计入全局 IP 限流 |
| 路由注册 | `:97-107` —— 11 个 router，业务全部挂 `/api/v1`；voice WS 不挂前缀（router 内部自带 `/api/v1/voice/ws`） |
| 异常处理 | `:110-141` —— `StarletteHTTPException` → 统一信封；`RequestValidationError` → 422 信封 |
| `/metrics` | `:144-149` —— 进程内 Prometheus 文本（`include_in_schema=False`） |
| `/health` | `:152-155` —— **不依赖数据库**（注释明示） |
| `/api/v1/ping` | `:158-161` |

---

## 2. 配置（`app/config.py`，104 行）

pydantic-settings，单一配置源。要点：

| 项 | 说明 |
| --- | --- |
| `jwt_secret` | **无默认值** → 必须通过 `.env`/环境变量显式提供（`config.py:23`） |
| `_reject_placeholder_secret_in_prod` | `ENVIRONMENT=prod` 且 secret 为 `dev-*`/`change-me` → **启动即失败**（`:82-91`） |
| Embedding key 回退 | `EMBEDDING_PROVIDER=openai_compatible` 且未设 `EMBEDDING_API_KEY` 时回退到 `ALIYUN_DASHSCOPE_API_KEY`（`:95-100`） |
| 数值约束 | 大量 `Field(ge=/le=/gt=)`，越界即启动失败 |
| Worker 调优 | `worker_poll_interval`、`worker_max_attempts`、`worker_running_ttl_seconds`(600)、`worker_backoff_base/max_seconds` |
| 上下文 | `context_window_token_budget`(3000)、`summary_message_threshold`(20) |
| 限流 | `rate_limit_enabled`(True)、`rate_limit_api_per_minute`(600)、`rate_limit_login_per_minute`(30) |
| 存储 | `storage_backend`(local\|s3) + S3 五要素 |
| Redis | `redis_url`、`redis_enabled`(True)、`redis_lock_ttl_seconds`(120)、`redis_cache_ttl_seconds`(60) |
| 语音 | `voice_provider`、`tts_provider`(默认 **`none`**)、`aliyun_asr_models`(4 个候选模型)、`speech_sample_rate`(16000) |

⚠️ **配置漂移**：根目录 `.env.example` 使用的是**旧变量名** `LLM_PROVIDER/LLM_API_KEY/LLM_BASE_URL/LLM_MODEL`，
与 `config.py` 的 `AI_*` **完全不匹配**，且无任何代码读取它。真正有效的是 `backend/.env.example`。

---

## 3. API 与鉴权层

| 文件 | 内容 |
| --- | --- |
| `app/api/envelope.py` | `ok(data, meta)` / `error_response(...)` —— 统一信封 |
| `app/api/deps.py` | `get_current_user`（每次请求查 `users.status`，**禁用账号即时失效**）<br>`require_student`（403 if not STUDENT）<br>`require_admin`（必须 ADMIN **且** `admins` 行 `enabled=true`，否则 403 `ADMIN_PROFILE_REQUIRED`；**已移除 legacy 放行路径**） |

详见 `docs/07-api.md`。

---

## 4. 领域模块（`app/modules/`）

### 4.1 `identity` —— 认证 / 档案 / 偏好

- `security.py`：bcrypt **直调**（注释说明是规避 passlib/bcrypt>=4 兼容问题）+ PyJWT HS256。
- `service.py`（261 行）：登录、`/me` 聚合、偏好自动建默认、头像上传（2 MB 上限）。
- `storage.py`：头像落盘 + `GET /files/avatars/{filename}`（**路径穿越防护已测**）。
- `router.py`：10 个端点。

### 4.2 `content` —— 书库 / 章节 / 内容块 / 图片资源

- `service.py`（355 行）：只读 Domain Service。**可见性守卫在 Service 层**（`list_books` 拒绝非 PUBLISHED、
  `get_chapter_detail` 校验父书状态），使缓存命中路径也无法绕过。
- 游标分页基于 `(created_at, entity_id)` 元组比较 + base64 JSON 游标。
- `assets.py`（**新增，未提交**）：`GET /library-assets/{book_slug}/{filename}` 教学图片服务。
- Redis 缓存键 = 全部过滤参数的 sha256 指纹（`_books_cache_key`，`:50-75`），避免不同查询互相污染。

### 4.3 `learning` —— 会话 / 事件 / 进度 / 章节完成

- `learning_sessions` 有 **部分唯一索引** `uq_learning_sessions_one_active`（每学生最多一个 ACTIVE）。
- `reading_settlements` 以 `session_id` 为主键 → 时长结算**天然幂等**，重复 PATCH/自动关闭/Worker 重放都安全。
- `learning_events` 是 **append-only**（应用层约定，非 DB 强制）。
- `chapter_completions`（**新增，未提交**）：`(student_id, chapter_id)` 唯一 → 「完成本章」幂等；
  「书已完成」= 本书全部 PUBLISHED 章节都在该表中，而非滚动到末块。

### 4.4 `conversation` —— 系统心脏（`service.py` 1319 行，全仓最大业务文件）

- 会话级串行锁（Redis 分布式锁 + asyncio 本地降级，`:446-479`）。
- **幂等重放**：`Idempotency-Key` 命中时重放已存消息而非重复生成（`:505-523, 1058-1177`）。
- `teacher_context.py`（452 行）：从 DB 聚合完整学生上下文（档案/偏好/记忆/画像/最近学习/测验/阅读位置）。
  ⚠️ 存在 N+1：`:315-335` 按 quiz session 逐条查询。
- `context_window.py`（**新增，未提交**）：按字符启发式估算 token 的窗口裁剪。
- **AI 失败不阻塞主流程**：RAG / TeacherContext / evidence 三处全部 `try/except`（注释「must not break chat」）。
- ⚠️ 关键缺陷见 `docs/08` §2.4（摘要）与 §1.3（关键词劫持）。

### 4.5 `quiz` —— 出题 / 判分 / 提示 / 错题讲解

- `skill.py`（458 行）：`QuizSkill` —— 出题来源解析、判分、提示。**服务端权威判分**。
- `chapter_source.py`（325 行）：基于本章真实正文的确定性模板出题（5 种模板：单选/判断×2/填空/多选）。
- `quiz_bank.py`（239 行）：**8 题硬编码题库** + 审校题选择器 `select_reviewed_questions`。
- `service.py`（790 行）：会话生命周期、作答、提示、幂等、sequence 并发安全。
- ⚠️ 反馈与提示硬编码、审校题链路未接入 bootstrap、题量声明不一致（见 `docs/08` §5）。

### 4.6 `memory` —— 记忆 / 画像 / 情节 / 证据

- `pipeline.py`（593 行）：**规则式**事件分桶 + 计数 + 模板；LLM 仅润色单句（带数字接地校验）。
- 写入 5 张表：`memory_evidence`、`memory_candidates`、`student_memories`、`profile_insights`、`student_episodes`。
- `agent_md.py`（328 行）：`.agent.md` 渲染视图（明确声明「渲染视图，不是数据事实源」）。
  ⚠️ 标题硬编码 `# xiaoming.agent.md`（`:132,170`）。
- ⚠️ `student_episodes.embedding` **硬编码 `None`**（`pipeline.py:376`）。
- 「遗忘/否认不复活」约束：按内容对**全部状态**去重（T24）。

### 4.7 `knowledge` —— 资源 / 分块 / 向量检索

- `ingestion.py`（372 行）：PDF(pypdf)/Markdown/TXT 解析 → 500 字符固定窗口分块（**无重叠**）→ 逐块 embedding。
  ⚠️ HTML 在 `file_type` 枚举内但**无解析分支**。
- `retrieval.py`（129 行，**新增，未提交**）：`retrieve()` —— 融合用户提问 + ScreenContext，多级回退。
- `service.py`（231 行）：真实 pgvector SQL（`<=>` + `vector_dims` 维度过滤）+ ILIKE 关键词兜底。
- ⚠️ 无向量索引（HNSW 已移除）→ 顺序扫描；字面子串排序可压过余弦距离。

### 4.8 `recommendation` —— 规则推荐 + 下一步行动

- `service.py`（737 行）：基于 LearningEvent / QuizAnswer / BookProgress 的**规则式**推荐，
  带可解释 `reason` + `evidence_ids` + D9 溯源字段（`source_ids`/`license`/`source_url`/`model_info`/`skill_version`）。
- `GET /me/learning-next`（**新增，未提交**）：统一决定「继续练习 / 错题回顾 / 继续阅读」。

### 4.9 `admin` —— 内容运营

- `router.py` 454 行 + `service.py` 640 行，17 个端点。
- 上传资源 → 202 + 入队 `knowledge_ingest`（异步）。
- 复用 `Idempotency-Key`（`_reprocess` 键）。
- ⚠️ 内容块/知识点/资源元数据**只能创建，不能编辑**（后端有 PATCH，前端无 UI）。

### 4.10 `voice` —— 语音 WebSocket

- `ws.py`（310 行）：双向流式。ASR 走阿里云 DashScope 实时 WS（4 个候选模型名做兼容探测）。
- **复用 `ConversationService.send_message()`** 生成 AI 回复（`:119-129`）—— 不重复实现对话逻辑。
- 无 TTS 配置时返回明确 `TTS_UNAVAILABLE`（**不再返回静音假音频**）。

---

## 5. AI Provider 层（`app/ai/`）

| 文件 | 内容 | 状态 |
| --- | --- | --- |
| `base.py` | `AIProvider` ABC（`stream_chat`/`model_info`/`last_usage`） | 契约偏窄 |
| `factory.py` | `get_ai_provider()` 按配置选择 | REAL |
| `mock.py` | 关键词→固定段落；RAG 回显 | MOCK |
| `openai_compatible.py` | httpx 适配器 | REAL，但 **`stream:False` + 事后切片伪造 delta**；30s 固定超时；**无重试** |
| `embedding.py` | mock（64 维 SHA256）/ openai_compatible（维度强校验） | REAL |
| `voice.py` | ASR（mock/aliyun）/ TTS（none/mock/openai_compatible） | ASR REAL，TTS 未配置 |

详见 `docs/08-ai-system.md`。

---

## 6. 基础设施（`app/infrastructure/`）

| 文件 | 内容 | 备注 |
| --- | --- | --- |
| `database/models.py` | **32 张表全部 ORM 定义（1465 行）** | 无 `relationship()`；`VECTOR` 自定义类型无维度 |
| `database/engine.py` | async engine；测试环境用 NullPool | |
| `database/session.py` | `async_session` / `get_session` | |
| `cache/redis.py` | 分布式锁 + 缓存，带本地降级 | |
| `rate_limit.py` | Redis 固定窗口 / 进程内滑动窗口（含键清扫与 10k 上限） | **两种模式都强制拒绝**，不静默放行 |
| `metrics_registry.py` | 进程内 Prometheus 文本 | **无 LLM/DB/队列指标** |
| `observability.py` | 结构化访问日志 | **明确不记录 Authorization/密码/正文** |
| `storage/base.py`+`local.py`+`s3.py` | 存储抽象；S3 为手写 SigV4 | 生产用 local |

---

## 7. 后台任务（`app/jobs/`）

| 文件 | 内容 |
| --- | --- |
| `queue.py`（218 行） | `enqueue` / `claim_next`（`FOR UPDATE SKIP LOCKED`）/ `mark_success` / `mark_failed`（指数退避 `next_attempt_at`）/ `recover_stale_running` |
| `worker.py`（118 行） | 主循环 + `resolve_handler`（3 类任务）；**循环体整体兜底**，单任务异常不终止 Worker |
| `handlers/knowledge.py` | `knowledge_ingest` → `ingest_stored_resource` |
| `handlers/conversation.py` | `conversation_summary` → ⚠️ **非 LLM 摘要，且谎报覆盖范围** |
| `handlers/memory.py` | `memory_consolidation` → MemoryPipeline |

**`worker.py:45-52` 的注释记载了一个真实缺陷的根因**：「缺陷 A」——
handler 失败后 `session.rollback()` 会使 ORM 实例属性过期，再访问 `job.job_id` 会触发同步惰性加载并抛
`MissingGreenlet`。因此收尾一律通过局部 `job_id` 重新查询。**这是理解本项目 async ORM 陷阱的最好例子。**

---

## 8. 运维脚本（`app/scripts/`，11 个）

| 脚本 | 幂等 | 是否接入启动/CI |
| --- | --- | --- |
| `seed.py`（230 行） | ✅ | ✅ `start.sh` / `ci.sh` / `ci-e2e.sh` / GitHub CI |
| `validate_library.py`（661 行，语料结构校验 R1–R?） | ✅ | ✅ 同上（作为导入前置门禁） |
| `import_library.py`（422 行） | ✅ | ✅ 同上 |
| `import_assessments.py`（142 行，**未提交**） | ✅（按 `stable_key` upsert） | ❌ **仅测试调用** → 审校题库链路断在这里 |
| `ingest_knowledge.py` | — | 手动 |
| `reindex_embeddings.py`（166 行） | — | 手动（`--dry-run`/`--limit`） |
| `rebuild_memory.py` | — | 手动 |
| `archive_noncorpus.py` | — | 手动（一次性） |
| `preview_data_governance.py` | — | 手动 |
| `verify_s3.py`（138 行） | — | 手动 |

---

## 9. 后端总体评价

**做得好的**：分层纪律（Router 不写 SQL）、统一信封与错误码、幂等机制（会话/答题/结算/导入四层）、
并发安全（会话锁 + sequence 唯一约束 + 部分唯一索引）、安全基线（账号禁用即时失效、
严格后台鉴权、路径穿越防护、日志不记敏感信息）、限流双模式强制、
「AI 失败不阻塞主流程」的降级设计、可见性守卫放在 Service 层使缓存无法绕过。

**主要问题**：AI 层空心化（无流式/无工具调用/摘要破坏性）、
测试直连开发库、Worker 启动无保证、可观测性缺 LLM 与队列维度、
内容运营只能创建不能编辑、遗留脚手架未清理。
