# 12 · 已知问题登记（P0–P3）

> 分级标准：
> - **P0** 系统无法正确运行 / 数据安全 / 严重架构错误
> - **P1** 核心业务链路缺失或无法正常使用
> - **P2** 明显影响维护性、稳定性或产品体验
> - **P3** 优化项
>
> 每条给出：现象 → 代码证据 → 影响 → 根因 → 推荐修复方向。
> **本阶段不修改任何业务代码。**
>
> 所有「实测」均指在 2026-09-16 运行中的实例（API :8002、postgres `shuangling`、Worker pid 40896）上观测到的结果。

---

# P0

## P0-1 · CI 的 backend job 在全新环境上**必然失败**（测试顺序 bug）

**现象**
按 `.github/workflows/ci.yml` 的**完全相同**顺序在全新数据库上执行
（`alembic upgrade head` → `validate_library --all` → `import_library --all` → `pytest -q`），
结果稳定为 **`1 failed, 383 passed`**。→ **CI 目前是红的**，不是偶发。

失败用例：`tests/test_content_ai_visibility.py::TestChapterSourceVisibility::test_published_chapter_loads_source`
（`assert source is not None`，该文件 `:169`）。

**代码证据**
- `TestChapterSourceVisibility` 是该文件的**第一个类**（`:159`），它的 4 个方法**不接收 `client` fixture**。
- 造数据的 `_ensure()` 只在**模块级 `client` fixture** 里被调用（`:129-133`），
  而该 fixture 直到后面的 `TestQuizApiVisibility`（`:185+`）才第一次被实例化。
- 已用行时间戳证明：夹具书 `b3000000-…-0001` 创建于运行**期间**、**失败之后**。
- 在同一（现已变脏的）库上重跑该用例 → 通过。→ 典型的**顺序依赖**缺陷。

**影响**
质量门禁失效。任何人推 PR 都会看到红色 CI；「384 passed / 0 failed」的基线
（`docs/plans/current-phase.md:14`）只在**已被污染的库上第二次运行**时才成立。

**推荐修复方向**
让 `TestChapterSourceVisibility` 自己依赖 `client` fixture（或在自己的 setup 中造数据）。
这是让 CI 变绿的前置条件。

---

## P0-2 · 测试与 E2E 直连开发数据库，测试夹具已泄漏进学生可见内容

**现象**
学生书库（`GET /books`，强制 `status='PUBLISHED'`）中**69 本书里有 43 本是 pytest 夹具**，
其中 32 本**零章节**。夹具标题包括 `分页测试书00`…`分页测试书24独有关键词绿松石`、
`可见性·已发布书`、`AI 可见性测试书`、`完成闭环测试书`、`审校测试书`、`测验测试书`、
`错题讲解测试书`、`P3 测试书 0001/0002`、`Phase2 测试书`、`发布测试书-<uuid>`、`书-b70000`。
全部 `created_at::date = current_date`（2026-09-16）。另有 47 本已归档的同名夹具残留。

实测数据：

| 指标 | 数值 |
| --- | --- |
| `books` 总数 | 130（PUBLISHED 69 / ARCHIVED 63 / DRAFT 6 → 实际 132） |
| PUBLISHED 中测试夹具 | **43** |
| PUBLISHED 中真实语料 | 26 |
| PUBLISHED 但零章节 | **32** |
| `users` | 159（48 ADMIN / 106 STUDENT / 5 其他） |
| `admins` | 3 |
| `idempotency_keys` | **8442** |
| `background_jobs` | 691（含一条伪造 job_type `rollback_poison_d44d11bd-…`） |

**代码证据**
- `backend/tests/conftest.py`（全文 11 行）只设置了 `ENVIRONMENT/AI_PROVIDER/AI_MODEL/EMBEDDING_PROVIDER/
  VOICE_PROVIDER/REDIS_ENABLED/JWT_SECRET`，**没有覆盖 `DATABASE_URL`** → engine 使用 `backend/.env` 中的
  `postgresql+asyncpg://…@localhost:5432/shuangling`，即开发者真实开发库。
- `scripts/ci.sh` 的 `prepare_backend_env()`：当 `DATABASE_URL` 未设置时，从 `backend/.env` 解析并
  **export** 该值，随后执行 `uv run pytest -q` → 本地跑 `ci.sh` 必然污染开发库。
- 反过来，`scripts/audit-check.sh:24-49` **已经实现了正确的守卫**（拒绝与开发库同名、拒绝默认 `shuangling`），
  但**没有任何脚本调用它**。
- `scripts/test-db.sh` 也有保护（`PROTECTED_DB="shuangling"` 拒绝 restore），同样未被 CI 链路调用。
- 测试本身**不做** `drop_all`/`create_all`（全仓 0 匹配），因此**不是破坏性的**——
  但它们创建的用户/书/任务/事件会长期残留，且部分测试按 `book_id` 做定向 `delete`。

**影响**
1. **产品面**：学生打开书库，前几屏全是「分页测试书00」；32 本空书点进去没有任何内容。
2. **数据可信度**：真实学习数据（159 用户中可能混有测试账号）与夹具混杂，无法据此判断试用效果。
3. **回归可信度**：在一个已被 43 本同名/近似书污染的库上跑测试，测试之间可能互相干扰，
   `docs/plans/current-phase.md` 声称的「384 passed」是在**隔离库 `shuangling_audit`** 上取得的——
   说明作者知道要隔离，但**工具链没有强制**。

**根因**
隔离是「文档约定 + 人工纪律」，而非「工具强制」。`conftest.py` 缺一道 fail-fast 断言；
`ci.sh` 缺一次 `audit-check` 调用。

**第二个症状（2026-09-16 固化提交时实测确认）**
本机若**同时运行着开发 Worker**（`scripts/start.sh` 会启动它），它会持续轮询同一个
`background_jobs` 表并**抢走测试刚入队的任务**，导致
`tests/test_worker_queue.py::test_worker_loop_survives_bad_job_and_processes_next`
间歇性失败。实测对照：

| 条件 | 全仓结果 |
| --- | --- |
| Worker 运行中 | `2 failed / 460 passed` |
| Worker 停止后 | `1 failed / 461 passed`（只剩下面这条既有失败） |

→ 这不只是"数据脏"，还会让**队列类测试失去确定性**。跑全量回归前应先停 Worker
（或按上面的方向做测试库隔离）。

**推荐修复方向**
1. `backend/tests/conftest.py` 在导入 `app.*` 之前强制校验 `DATABASE_URL`：未设置 → 直接 `pytest.exit`；
   库名等于开发库名 → 拒绝运行（复用 `audit-check.sh` 的判定逻辑）。
2. `scripts/ci.sh` 在 pytest 之前调用 `bash scripts/audit-check.sh`。
3. 补一个一次性清理脚本，把 `title` 匹配测试夹具模式且 `created_at` 集中的书归档/删除。
4. 长期：让测试自己创建/销毁 schema（或使用 per-run 临时库），而不是依赖共享的可变库。

---

## P0-3 · 长对话摘要删除历史，并谎报「已覆盖全部消息」

**现象**
一段对话超过 20 条消息后，AI 会**永久丢失**所有普通 TEXT 轮次；
系统对外（以及对自己）声称上下文完整。

**代码证据**
- `app/jobs/handlers/conversation.py:12` —— 保留类型白名单 `{QUIZ, HINT, RECOMMENDATION, LEARNING_SUMMARY, SYSTEM}`
- `:16-27` `_summary_messages` —— 只保留 **第 1 条 + 上述白名单消息 + 最后 1 条**
- `:30-36` `_summary_text` —— 每行截断到 **160 字符**，前缀 `"会话摘要：\n"`
- `:77, :86` —— 写入 **`message_covered_count = len(messages)`**（声称覆盖全部）
- `:78, :87` —— `model_info = {"provider":"rule","model":"conversation-summary-v1"}`，
  **本文件没有 `get_ai_provider()` 调用 → 不存在 LLM 摘要**
- `app/modules/conversation/context_window.py:61-65` —— 窗口构建器依据 `message_covered_count`
  **丢弃该索引之前的全部消息**
- 实测样本：`message_covered_count=22`、`token_count=38`

**影响**
核心教学链路的质量缺陷：学生在长对话中追问早期内容时，AI 无法看到那些内容，
却因为拿到了一份「摘要」而不会承认自己不知道 → **既回答不了，也不说回答不了**。
这是本次审计发现的单个影响最大的 AI 行为缺陷。

**根因**
`message_covered_count` 的语义被误用：它本应表示「摘要**真正吸收**了多少条消息」，
却被写成「摘要生成时共有多少条消息」。加上摘要器本身是「首+关键+尾」的规则截断，
两者叠加等于**静默丢弃历史**。

**推荐修复方向**
1. 立即：把 `message_covered_count` 改为**实际被摘要吸收的消息索引**（真正连续的边界），
   使未被吸收的消息仍进入窗口。
2. 其次：把规则摘要换成 LLM 摘要（或至少对全部 TEXT 轮次做压缩而非丢弃）。
3. 加一条回归测试：构造 30 轮对话，断言**第 25 轮的内容仍能被回答引用**。

---

# P1

## P1-0 · 4 个迁移未提交，而线上库已 stamped 到它们的 head（fresh clone 会让 Alembic 完全不可用）

**现象**
`a4b5c6d7e8f9`、`a5b6c7d8e9f1`、`a6b7c8d9e0f1`、`a7b8c9d0e1f2` 四个迁移文件处于
**untracked**（`git status` 的 `??`）状态，而开发库 `alembic_version` 已经是 **`a7b8c9d0e1f2`**。

**代码证据**
- `git status --porcelain` 显示这 4 个文件为 `??`
- 实测 `SELECT version_num FROM alembic_version` → `a7b8c9d0e1f2`
- 22 个已提交迁移构成链，其 head 是 `b2c3d4e6f789` —— **落后于数据库当前版本**

**影响**
`git clean -fd`、或任何全新 clone，都会得到一个「迁移链 head 落后于数据库」的仓库：
**任何 Alembic 命令都会以 "unknown revision" 失败**（`upgrade`/`downgrade`/`current`/`history` 全部）。
仓库**无法复现它正在运行的数据库**。这是本次审计中最紧急的单点风险。

**推荐修复方向**
立即提交这 4 个迁移（连同其余 T 轮改动）。

---

## P1-1 · 没有 token 级流式；30 秒硬超时；零重试

**现象**
用户看到的「打字机」是服务端伪造的；长回答一旦超过 30 秒直接失败，且不会重试。

**代码证据**
- `app/ai/openai_compatible.py:68` —— 请求体写死 `"stream": False`
- `:103-104` —— 拿到完整字符串后切成 16 字符的伪 delta 逐块 yield
- 全仓 `httpx.stream` / `iter_lines` / SSE 解析在 `app/ai/` 中 **0 命中**
- `:39, :76` —— 30 秒超时，**不可配置**
- `grep retry/tenacity/backoff app/ai/` → **0 命中**

**影响**
- 首字节延迟 = 整段生成延迟（教学解释类回答很容易 > 10 s）。
- 超过 30 s 必然失败，且无退避重试 → 学生看到报错。
- 「流式体验」是假的：网络中断也不会节省任何算力。
- 前端 SSE 传输层（`sse.ts`、`conversation/router.py:95-111`）本身**是对的**，
  即问题被隔离在这一个 adapter 内。

**根因**
Provider 适配器是「先做完再切片」的最简实现，未接真实 SSE 解析。

**推荐修复方向**
`stream: True` + `httpx.stream("POST", …, )` + `iter_lines()` 解析 `data: ` 帧，
直接 yield 真实 delta；超时改为「连接超时 + 读取间隔超时」两个可配置值；加一次幂等重试。

---

## P1-2 · Worker 默认启动路径无保证，且队列积压不可观测

**现象**
`docker compose up` 启动的系统**没有 Worker**。任何绕过 `scripts/start.sh` 的启动方式
都会得到一个「API 正常、任务永不消费」的系统，且没有任何告警。

**代码证据**
- `app/main.py:31-34` —— `lifespan` 是空的（注释「当前无任何外部依赖」已过时）
- `docker-compose.yml` 的 `worker` 服务带 `profiles: ["worker"]`
  → 实测 `docker compose config --services` 只输出 `redis/minio/postgres`；
  加 `--profile worker` 才出现 `worker`
- `docker-compose.yml` **没有 api 服务**（它是依赖编排，不是部署编排）
- 实际启动只发生在 `scripts/start.sh`（宿主机进程）与 `Dockerfile` 的 `CMD`
- 实测 Worker 正在运行（pid 40896），累计 272 + 259 + 105 次 success —— **能力是真的，保障不是**

**影响**
静默降级：知识资源永远停在 `UPLOADED`、记忆不再合并、摘要不再生成。
用户与运维都看不到（`/metrics` 无队列指标）。

**推荐修复方向**
1. 去掉 `worker` 的 profile 门控（或在 README/部署文档中显式要求 `--profile worker`）。
2. 增加队列健康探针：`GET /health` 或独立端点暴露 `queued` 数量与**最老 queued 任务年龄**。
3. 在 `background_jobs` 积压超阈值时告警。

---

## P1-3 · 审校题库链路**三重不通**：未接入 bootstrap + 导入器有 bug + 数据格式不匹配

**现象**
`reviewed_questions` 表在全新环境 bootstrap 后**恒为空**；**即使接上导入器，13 道出厂审校题也永远选不出来**。

**代码证据（三个独立层面的问题）**

1. **未接入运行链路**：以下四处**都没有**调用 `import_assessments` ——
   `scripts/start.sh`、`scripts/ci.sh`、`scripts/ci-e2e.sh`、`.github/workflows/ci.yml`（已逐一核对）。
   全仓调用方**只有** `backend/tests/test_reviewed_assessments.py:114,141-142`。
   对照：`validate_library --all` → `import_library --all` 这条链路在四处**都有**。

2. **导入器读错字段层级**：
   - `import_assessments.py:96` 按**每题**读 `question.get("review_status", "DRAFT")`
   - 而出厂的 3 个 JSON（共 13 题）把 `review_status` 写在**文件顶层**，没有一题写在题内
     （实测：0/4、0/4、0/5）
   - → **13 题全部以 `DRAFT` 导入**，而选择器要求 `review_status == 'APPROVED'`
     （`quiz_bank.py:206-209`）→ **一题都不可能被选中**

3. **章节解析同样失败**：导入器只从**顶层** `chapter_id` 键推导章节（`import_assessments.py:87-90`），
   而 JSON 用的是 `slug` + `chapter` → 13 题**同时**落到 `chapter_id = NULL`，
   **在第二个独立维度上也不可选**。
   （`skipped_no_chapter` 计数器在 `:72` 初始化、`:128` 返回，但**从未自增** —— docstring 承诺的
   「找不到时跳过该题并告警」未实现，是死代码。）

**存在的资产（都是真的，只是不通）**
表与迁移 `a7b8c9d0e1f2`（未提交）、导入器 `app/scripts/import_assessments.py`（142 行，未提交）、
数据 `backend/data/library/assessments/*/ch01.json`、选择器 `quiz_bank.py:193-239`、
集成 `quiz/skill.py:154-183`、测试 `tests/test_reviewed_assessments.py`。

**影响**
T22b（三学段样板章节与题目审校）在代码层、数据层、运行时层**三个层面都不通**。
实测 quiz 来源分布：`quiz-bank` 79 / `chapter-content-v2` 4 / `openai_compatible` 3 / **`reviewed` 0**；
线上 `reviewed_questions` 的 5 行**全是测试夹具**（`cap-approved` 等），真实词库从未被导入。

**推荐修复方向**
① 修导入器读顶层 `review_status`；② 从 `slug` + `chapter` 解析章节；
③ 把 `import_assessments` 接入 `ci.sh` / `ci-e2e.sh` / `start.sh` / CI（紧随 `import_library --all`）；
④ 在 `validate_library` 中校验 assessments 结构。

---

## P1-4 · 情节记忆的向量从不写入 → AI 永远看不到情节

**现象**
`student_episodes` 有 239 行，**0 行有 embedding**。

**代码证据**
- `app/modules/memory/pipeline.py:376` —— 硬编码 `embedding=None`
- 实测 `SELECT count(*), count(embedding) FROM student_episodes` → `239 / 0`

**影响**
情节记忆是**只写的**：学生能在 `/me/episodes` 看到，AI **从不检索、从不注入 prompt**。
这是一个纯 UI 功能，与「AI 数字教师记得你」的产品承诺不符。

**推荐修复方向**
在 `pipeline` 写入 episode 时调用 `get_embedding(title + summary)`；
在 `teacher_context` 中按相似度检索 top-k episode 注入（而非当前的时间序）。

---

## P1-5 · RAG 中 58% 的已嵌入知识不可达；无向量索引

**现象**
向量检索 SQL 带 `vector_dims(kc.embedding) = :embedding_dimension` 过滤。
当前查询向量 1024 维（`EMBEDDING_DIMENSION=1024`），而库中：

| 维度 | chunk 数 | 可达 |
| --- | --- | --- |
| 64（早期 mock embedding 遗留） | **636** | ❌ |
| 1024（当前真实 embedding） | 467 | ✅ |

**代码证据**
- `app/modules/knowledge/service.py:148-171`（`<=>` 距离 + `vector_dims` 过滤）
- 迁移 `c7d8e9f0a1b2_allow_variable_embedding_dimensions.py` 移除了 HNSW 索引
  （pgvector 索引要求固定维度）→ 现状是**全表顺序扫描**
- `app/infrastructure/database/models.py:25-39` `VECTOR` 无维度 + 注释说明不建索引

**影响**
可用知识量被腰斩；且随语料增长，顺序扫描会线性变慢。

**推荐修复方向**
1. 执行 `app/scripts/reindex_embeddings.py`（已存在，未被运行到该库）把 64 维 chunk 重嵌入为 1024 维，
   或直接把这批历史 chunk 标记为不可用并清理。
2. 中期：固定 embedding 维度后重建 HNSW 索引（需要一次维度锁定的迁移）。

---

## P1-6 · ReaderPage 无错误态；失败被渲染成「安心的空态」

**现象**
后端故障与「章节不存在」在 UI 上**无法区分**，且没有重试入口。

**代码证据**
- `frontend/src/pages/reader/ReaderPage.tsx:169,175,182` —— 内容请求全部 `catch {}` 吞掉；
  全文件 grep `error` = 0
- `:176-189` —— `getChapter` 失败时**伪造** `{...chapter, content_blocks: []}` → 显示「本章暂无内容」
- `:596` —— 否则显示「章节不存在。」
- 同类问题：`LibraryPage.tsx:183-185`（进度失败 → 每本书显示「未开始」）、
  `QuizDetailPage.tsx:98`（失败 → 「答卷不存在。」）、
  `use-home-data.ts:209,218`（`statsError`/`memoriesError` 未被消费 → 显示「我还没有记住…」）

**影响**
学生在后端抖动时看到的是「没有内容」而不是「加载失败，请重试」，
会误以为课程缺失；也无法自助恢复。这是 T07「统一错误/重试/空态」任务的**未完成部分**。

**推荐修复方向**
按首页 `use-home-data.ts` 的 per-section error flag 模式改造；
把已经写好但零引用的 `shared/ui/ResourceState.tsx` 用起来。

---

## P1-7 · SettingsPage 加载失败导致软锁

**现象**
设置页加载失败时表单静默显示空昵称，保存必然失败且只给通用错误提示。

**代码证据**
`frontend/src/pages/settings/SettingsPage.tsx`
- `:96-99` `Promise.all([getPreferences(), getTeacherRoles()])`
- `:100-112` **整个成功分支（含全部 `currentUser` 派生字段初始化）都在 `await` 之后**
- `:113-115` **空 `catch`**
- 后端拒绝：`backend/app/modules/identity/schemas.py:55` `nickname` 有 `min_length=1`

**影响**
Medium-High。**是软锁，不是数据损坏** —— 经核对，`updatePreferences` 不会被触达，
因此不会静默覆盖真实偏好。（仅读前端代码容易误判为数据丢失，故此处明确澄清。）

**推荐修复方向**
把字段初始化移到 `await` 之前（或使用 `currentUser` 的同步初值），
`catch` 中设置错误态并渲染重试。

---

## P1-8 · 关键词意图劫持：「题目」触发测验而不是回答问题

**现象**
学生问「**这道题目我不会**」，系统不回答问题，而是直接生成一份 3 题测验。

**代码证据**
- `app/modules/conversation/service.py:55` —— `QUIZ_INTENT_KEYWORDS = ("出题","题目","测验","quiz","考考我")`
- `:612` —— `quiz_intent = _is_quiz_intent(request.content)`（子串匹配）
- `:723-889` —— 命中即走 `tool.start/tool.result` 出题分支，**不再走 LLM 回答分支**

**影响**
高频教学场景下的错误行为，且用户无法阻止。

**推荐修复方向**
改为显式意图（前端按钮/命令前缀）或让 LLM 做意图判定，
并把关键词匹配降级为「仅当整句是祈使出题时才触发」。

---

# P2

## P2-1 · 出题 89% 来自 8 题硬编码题库；AI 反馈与提示是硬编码

**证据**
- 实测 `quiz_sessions.model_info->>'provider'`：`quiz-bank` **79** / `chapter-content-v2` 4 /
  `openai_compatible` 3 / `reviewed` 0（共 89 个有 model_info 的会话）
- `app/modules/quiz/quiz_bank.py:17-158` —— 8 道硬编码题
- `app/modules/quiz/service.py:594-598` —— `ai_feedback` 是**两句字面量字符串**，无 LLM 调用
- `app/modules/quiz/skill.py:451-457` —— 非题库题的 3 个 hint level 返回**同一句话**

**影响**
「AI 随堂测验」的产品承诺与实现不符；学生反复看到同样 8 道题。
（判分本身是真实且服务端权威的，不要一并否定。）

**推荐修复方向**
把 `import_assessments` 接入 bootstrap（P1-3）优先解决审校题源；
再考虑扩大章节确定性模板覆盖率；反馈与提示接入 LLM（并保留规则兜底）。

---

## P2-2 · 管理后台只能创建，不能编辑

**证据**（后端有实现有测试，前端无 UI）
`PATCH /admin/content-blocks/{id}`、`PATCH /admin/knowledge-points/{id}`、
`PATCH /admin/knowledge/resources/{id}`、`GET /admin/books/{id}` —— 见 `docs/07-api.md` §2。

**影响**
内容块/知识点创建后不可修正；知识资源的许可/版权/来源字段上传后不可更正
（而这些正是 D9 溯源合规字段）。

---

## P2-3 · React Query 装了、配了、完全没用

**证据**
`frontend/src/app/providers/query.ts` 定义了完整的重试策略（401/403 不重试、429 尊重 `retryAfterMs`）
与 `staleTime: 60_000`；但全仓 `useQuery` = 0、`useMutation` = 0、`invalidateQueries` = 0。
`shared/api/query-keys.ts`（含防跨账号缓存污染的 `userScopedKey` 约定）零引用。
每个页面手写 `useState` + `useEffect` 拉取并在变更后手动重取。

**影响**
无查询缓存、无失效策略、跨页面数据不一致（例如在设置页改了昵称，首页不会自动更新）。
T07 建立的两套约定（query keys + retry policy）实际上都成了死代码。

---

## P2-4 · 没有 LLM / 队列 / 数据库可观测性

**证据**
`GET /metrics` 实测只输出 HTTP 计数与 uptime。无 LLM 调用数、token 用量、延迟、失败率、
RAG 命中率、队列深度、最老任务年龄、DB 连接池指标。
另：`quiz/service.py:845-850, 914-919` 把**字符数**当 `input_tokens`/`output_tokens` 上报。

**影响**
线上问题无法定位；成本无法核算；队列积压不可见（与 P1-2 叠加）。

---

## P2-5 · 内容「归档」用 `status='FAILED'` + 错误字符串表达

**证据**
实测 `knowledge_resources`：READY 102 / FAILED 395，其中 **382 条 `error = 'archived: test data'`**。
`KnowledgeResource.status` 的 CheckConstraint 只有 `UPLOADED/PARSING/CHUNKING/INDEXING/READY/FAILED`，
**没有 ARCHIVED**。

**影响**
归档与真失败在数据上不可区分；`/admin/knowledge` 把 382 条归档内容显示为「失败资源」，
真正的失败（7 条 `embedding failed`、6 条 `embedding provider down`）被淹没。

---

## P2-6 · 前端死代码堆积（约 1700 行 mock + 若干抽象）

**证据**（全部零引用，已验证不在生产 bundle 中）
- 6 个 `src/mocks/services/*.ts`（`MockContentService`/`MockConversationService`/`MockMemoryService`/
  `MockQuizService`/`MockRecommendationService`/`MockStudentService`）
- 5 个 `src/mocks/data/*.ts`（仅 `QUICK_ACTIONS` 被生产引用、`mockBooks` 被一个测试引用）
- `shared/ui/ResourceState.tsx`（62 行，含自己的 4 个测试）
- `shared/api/query-keys.ts`（19 行）
- `conversation-store.ts:639-667` `pushStreaming` + `:123` `streamTimer`（伪造 22ms/字符打字机）
- `api-quiz-service.ts:205 createQuizSession`、`api-content-service.ts:197 getKnowledgePoint`、
  `api-memory-service.ts:236 getInsight`、`api-quiz-service.ts:272 getHints`
- `QuickActions.tsx:38-44` 「语音聊天」按钮（无 `onClick`）
- 测试死代码：`mocks/services/content-service.test.ts`（5）、`quiz-service.test.ts`（2）、
  `ResourceState.test.tsx`（4）

**影响**
新维护者会被 `src/mocks/` 误导（见 `docs/01-repository-map.md` §3.2）；
测试数量虚高（12 个测试保护的是不可达代码）。

---

## P2-7 · `.agent.md`：前端自造，后端能力闲置且标题硬编码

**证据**
- 前端：`pages/profile/components/ArchiveDocCard.tsx:47` 调用 `buildMarkdown(profile, prefs, insights)`
  在浏览器里合成 `.agent.md`，标题 `:63` 为 `{nickname}.agent.md`
- 后端：`GET /api/v1/me/agent.md` **真实存在**（实测返回 125 KB 真实 Markdown），前端**从不调用**
- 后端标题硬编码：`app/modules/memory/agent_md.py:132,170` 写死 `"# xiaoming.agent.md"`

**影响**
同一个概念有两份实现且都不是「对的那份」；后端那份对所有学生都叫 xiaoming。

---

## P2-8 · 桌宠「主动建议」是硬编码定时器

**证据**
`frontend/src/features/companion/hooks/useCompanionDock.ts:66-78` —— `setTimeout` 6 秒显示
「有一个新建议」徽标、13 秒隐藏，**不由任何真实建议驱动**。注释写「7s 恢复」，代码是 13000ms。

**影响**
生产环境中**唯一用户可见的伪造行为**（其余 fabrications 都不可见）。

---

## P2-9 · 401 处理不一致

**证据**
`shared/api/http.ts:91-93` 与 `sse.ts` 均派发全局 `shuangling:unauthorized`；
但 `api-student-service.ts:58-77`（`uploadAvatar`）与 `learning-service.ts:102-130` 使用**原生 fetch**，
**未派发** → 这两条路径遇到会话过期时不会清理登录态。

---

## P2-10 · 账号切换有 3 处状态残留

**证据**
`frontend/src/features/auth/reset-user-state.ts:12-18` 清了 token、conversation store、queryClient；
但**未重置**：companion store（`selectedPetId` + Dock 位置）、toast store、
`ScreenContextProvider` 的 React state（它在 `AuthProvider` 内层，登出时不卸载）。

**影响**
切换账号后可能短暂看到上一账号的桌宠选择与页面上下文。

---

## P2-11 · HTML 文件类型声明支持但未实现解析

**证据**
`KnowledgeResource.file_type` CheckConstraint 允许 `HTML`（`models.py:1288`），
但 `app/modules/knowledge/ingestion.py` 只有 PDF/Markdown/TXT 分支。

---

## P2-12 · 记忆注入按时间而非相关性

**证据**
`app/modules/conversation/teacher_context.py:246-285` —— 取最近 5 条记忆（`LIMIT 5`），
不做相似度检索。叠加 P1-4（情节无向量），「AI 记得你」的能力显著弱于产品表述。

---

## P2-13 · TeacherContext 构建存在 N+1

**证据**
`app/modules/conversation/teacher_context.py:315-335` —— 按 quiz session 逐条查询。
每轮对话都会执行。

---

## P2-14 · `admins.role_level` 无任何授权实效

**证据**
`admins.role_level` 枚举 `SUPERVISOR` / `CONTENT_EDITOR`（`models.py:1409`），
但 `app/api/deps.py:68-103` 的 `require_admin` **不读取该字段**
（全仓检索 `role_level` 仅出现在模型定义与 admin 的读写 DTO 中）。
→ 两个等级目前权限完全相同。

---

---

## P2-15 · `archive_noncorpus.py` 会把**合法内容**当作测试数据归档（HIGH，仅因是手动脚本而未触发）

**证据**
`app/scripts/archive_noncorpus.py:58,70-73` 的保留规则**只有** `source_url LIKE 'local://library/knowledge/%'`，
其余一律设为 `status='FAILED', error='archived: test data'`。但：
- `ingest_knowledge.py:76` 写入的是 `https://demo.shuangling.local/knowledge/<stem>` → **会被归档**
- **任何真实的后台上传**（管理员在 `/admin/knowledge` 上传的文档）→ **会被归档**

在活库上运行它，会**静默关闭这些文档的 RAG**。
另：该 UPDATE **没有 status 谓词**（不同于 books 分支的 `status != 'ARCHIVED'` 守卫）→ 严格来说不幂等，
每次运行都重写全部匹配行的 `status`/`error`/`updated_at`。

**现状**：尚未造成损害，唯一保护是「它被标记为手动/一次性」。
**推荐**：在执行前放宽保留规则；补一份 break-glass 说明。

---

## P2-16 · `alembic downgrade` 跨过 `c7d8e9f0a1b2` 会静默清空全部真实向量

**证据**
`alembic/versions/c7d8e9f0a1b2_allow_variable_embedding_dimensions.py:50-57` —— downgrade 会把
**所有维度 ≠ 64 的 embedding 置为 NULL**。在本库上，这就是全部 **467 个真实的 1024 维向量**
（外加 `student_episodes` 的向量，虽然它们本来就是空的）。

**含义**：这是一条**单向门**。未先导出 `knowledge_chunks.embedding` 之前，绝不能 downgrade 跨过它。
**推荐**：在迁移文件顶部加显式警告注释；在 README/开发指南中记录。

---

## P2-17 · 迁移被「回溯修改」，破坏可复现性

**证据**
`b1c2d3e4f5a6_create_teacher_roles.py` 在**已被应用之后**又被 commit `bce24e9` 修改
（种子数据从 `shuangling`/`strict-mentor` 改为 `温暖鼓励`/`严谨清晰`；可用 `git show 364aba6:…` 对比）。
后果：`b2c3d4e5f6a7`（重命名迁移）在全新重放时成为 no-op，不同环境重放同一条链会得到不同数据。

**推荐**：迁移一旦合并即视为不可变；数据修正走新迁移。

---

## P2-18 · 测试基础设施缺失 + 「测试剧场」

**证据（`conftest.py` 只有 11 行、零 fixture）**
- **零 fixture**；从不设置 `DATABASE_URL` → 直连开发库
- **无 schema 重建、无事务回滚、无 truncate**；隔离靠各模块手写的 `_ensure*()`（create-if-absent）
- `tests/test_learning_api.py:207-208` 的注释自己承认：「共享开发库中可能残留其它测试模块的进度行」
- `scripts/test-db.sh` **不是**测试库搭建脚本（我最初误判了）—— 它只是一个手动 `shuangling_audit` 库的
  backup/restore 工具，**没有任何东西调用它**
- 三个 `_ensure*()` 造数器是 create-if-absent 且**不修复 status** → 一旦夹具被归档就永久失败
  （这正是 P0-1 第 2 个失败的原因）

**「测试剧场」（测试通过但不验证生产路径）**
| 位置 | 问题 |
| --- | --- |
| `test_ai_provider.py:159,206` | monkeypatch 手写 `FakeClient`；`_http_proxy_url()`（测试中 0 引用）与 HTTP ≥400 分支（`:88-92`）**从未执行** |
| 全套测试 | 唯一出现过的假状态码是 **200**（`test_ai_provider.py:138,184`、`test_embedding.py:38,96`）→ **没有任何错误路径的 HTTP 测试** |
| `test_redis_lock.py:1` | docstring 自认「in-memory fake」；而 CI **真的起了 Redis**（`ci.yml:25-33`）却被绕过 |
| `test_phase4_platform.py:55-95` | `S3ObjectStorage.put/get/exists` 从未被调用，工厂测试只断言「返回了实例」 |
| `test_content_cache.py:1` | 「database and Redis are both replaced with fakes」 |
| `AdminPages.test.ts:33` | mock 掉**整个** `@/shared/api/admin-service` 模块，然后断言组件调用了这个 mock —— 删掉/改名/改错 URL 都照样通过 |
| `test_smoke.py:22` | `test_validation_error_uses_envelope` 根本没有测 422：它断言 200 并检查 404 信封 |

**无任何覆盖率工具**：没有 pytest-cov、没有 vitest coverage、CI 中**没有 ruff/mypy**。

---

## P2-19 · CI 声明的失败诊断产物**永远不会产生**

**证据**
- `ci.yml:219-227` 在失败时上传 `/tmp/shuangling-backend.*.log` 与 `/tmp/shuangling-worker.*.log`，
  但 `scripts/ci-e2e.sh` 的 `cleanup()` EXIT trap 里有 `rm -f "$BACKEND_LOG" "$WORKER_LOG"`
  → **日志在上传前就被删掉**，而 `if-no-files-found: ignore` 把这件事藏了起来
- `ci.yml:217` 上传 `frontend/playwright-report/**/*.html`，但 `playwright.config.ts:11` 设的是
  `reporter: [['list']]` —— **根本没有 HTML reporter**，该路径从不产生（已确认目录不存在）

**影响**：CI 红的时候拿不到它承诺的排障材料 —— 正好与 P0-1（CI 恒红）叠加，形成最坏的组合。

---

## P2-20 · 本地 `scripts/ci.sh` 与 GitHub CI 跑在**不同的数据**上

**证据**
`scripts/ci.sh:70-98` 只在 `DATABASE_URL` **未设置**时才设它，否则回退到 `backend/.env`（开发库）；
而 GitHub CI 用 service container（全新库）。
→ **同一套测试，不同的数据**，于是「本地绿 / CI 红」（或反之）。

---

# P3

| # | 问题 | 证据 | 影响 |
| --- | --- | --- | --- |
| P3-1 | 根目录 `.env.example` 变量名与代码不匹配且无人读取 | 用 `LLM_PROVIDER/LLM_API_KEY/LLM_BASE_URL/LLM_MODEL`；`config.py` 用 `AI_*`；全仓无引用 | 误导新环境搭建 |
| P3-2 | `backend/空` 垃圾文件（4 字节，内容 `117`） | 未跟踪 | 噪音 |
| P3-3 | `.playwright-mcp/` 36 个调试快照未清理 | 未跟踪 | 噪音 |
| P3-4 | `app/worker.py` 是重复入口 shim，无调用方 | 所有脚本用 `python -m app.jobs.worker` | 两套入口文档 |
| P3-5 | `start.sh` 容器名守卫永不匹配 | `grep -q '^k12.*postgres\|-postgres-1$'` vs 实际容器名 `shuangling-postgres`（实测：守卫不匹配） | 死逻辑（当前无害，因后续 `docker compose up` 幂等） |
| P3-6 | `stop.sh` 不停 redis/minio | 只 `docker compose stop postgres`，而 `start.sh --with-minio` 会启动它们 | 残留容器 |
| P3-7 | 死测试 12 个（mock 服务 7 + ResourceState 4 + …） | 见 P2-6 | 覆盖率虚高 |
| P3-8 | 文档漂移：3 个端点未记录；端点总数写 68 实际 71 | `docs/contracts/api-contract.md:390` | 契约不可信 |
| P3-9 | 4 个新迁移 + 19 个后端新文件 + 19 个前端新文件未提交 | `git status` | 一次崩溃即丢失 |
| P3-10 | 5 处前端注释与实现不符 | 见 `docs/04-frontend.md` §10 | 误导维护者 |
| P3-11 | `infra/` 空、无任何部署配置 | 只有 `.gitkeep` | 无生产化路径 |
| P3-12 | `scripts/ci.sh`（11 步）与 `.github/workflows/ci.yml`（3 job）内容重复但独立维护 | 两者都跑 migration/pytest/vitest/build/e2e | 双份维护，易漂移 |
| P3-13 | `docs/` 中代码注释大量引用 `0-D`/`0-E` 编号，但原文档**不在仓库** | `models.py` 全篇 | 新维护者无法追溯设计依据 |
| P3-14 | `.opencode/` 含 `node_modules` 在仓库内 | 未被 gitignore 覆盖完全 | 仓库体积 |
| P3-15 | 教学评测离线模式输出预置「observed」判定 | `backend/evals/run_teaching_eval.py:33-40` | 无真实教学质量门禁 |
| P3-16 | `model_info` 中 provider 字符串不统一（`quiz-bank`/`quiz-skill`/`rule`/`openai_compatible`） | 实测 quiz_sessions / messages | 统计口径混乱 |
