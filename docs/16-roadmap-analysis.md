# 16 · 方向纠正分析与 Roadmap

> 前提：本文件在**完成全部代码考古之后**撰写。每一条判断都能回溯到 `docs/11`–`docs/13` 的证据。
> **本阶段不执行任何修改。** 下列全部是建议，需要你确认后才动手。

---

## 第一部分：方向分析

### ✅ Keep —— 值得继续保留（有真实资产，回退它们才是浪费）

| 资产 | 为什么保留 | 证据 |
| --- | --- | --- |
| **数据模型与迁移纪律** | 三方对账几乎零漂移（368 列/58 FK/68 CHECK/34 索引全一致），23 迁移单链单 head，从零 upgrade 安全。这是**全项目质量最高的一环** | `docs/06` §0 |
| **模块化单体 + Router/Service 分层** | Router 不写 SQL 的纪律被真实执行；比微服务更适合当前团队规模 | `content/service.py:79` |
| **「无 `relationship()`」约定** | 规避了 async 惰性加载的真实事故（`worker.py:45-52` 记录了根因）。**这是用血换来的约定** | 全仓 0 处 `relationship(` |
| **四条幂等链路** | 会话消息、答题、时长结算、内容导入 —— 各有唯一约束兜底，设计正确 | `docs/13` Backend |
| **内容可见性守卫在 Service 层** | 使 Redis 缓存命中路径也无法绕过。这是**架构级的正确决策**，不是补丁 | `content/service.py:94-103` |
| **PG 表驱动任务队列** | `FOR UPDATE SKIP LOCKED` + 指数退避 + 孤儿回收，实测 636 次 success。不需要引入 Celery | `jobs/queue.py` |
| **前端服务注册表模式** | `shared/services.ts` 单一切换点，6 个服务全部切真实后端，零 mock 可达 | `docs/01` §3.2 |
| **前端真实 SSE / WS 传输层** | 幂等键、AbortSignal、epoch 隔离、CRLF/多字节 UTF-8 处理都正确且**有测试** | `docs/04` §3.2 |
| **真实 E2E 测试** | `helpers.ts` 走真实 API 登录/归档/造进度，**零 mock** | `docs/10` §7 |
| **安全基线** | bcrypt、prod 拒绝占位 secret、禁用账号即时失效、路径穿越防护、日志不记敏感信息、限流双模式强制 | `docs/13` Security |
| **「AI 失败不阻塞主流程」的降级** | RAG/TeacherContext/evidence 三处全部 try/except —— 正确的可用性权衡 | `conversation/service.py:624,652,687` |
| **当前产品边界（不做教师端/家长端/支付/排行榜）** | 与语料实际范围（AI 与计算通识）自洽。**不要扩张** | `tasks/plan.md:8` |
| **`.env.example` + `audit-check.sh` 的安全意识** | 项目**已经写好**了正确的隔离守卫，只是没接上 | `scripts/audit-check.sh:30-49` |

### 🔧 Fix —— 方向正确，但实现有问题

| 项 | 问题 | 修复方向 |
| --- | --- | --- |
| **AI Provider 适配器** | `stream:False` + 事后切片伪造 delta；30s 固定超时；零重试 | 改 `stream:True` + 真实 SSE 解析；超时拆为连接/读取两个可配置值；加一次幂等重试。**改动被隔离在这一个文件内** |
| **会话摘要** | 规则式截断 + `message_covered_count` 语义误用 → 删历史 | 先把 `message_covered_count` 改为**真实吸收边界**（最小改动即止血），再考虑 LLM 摘要 |
| **RAG 排序** | 字面子串匹配可压过余弦距离 | 去掉 `request.query in row["content"]` 主导排序；用相似度阈值 + 关键词做**加分项**而非替代 |
| **记忆注入** | 按时间取最近 5 条 | 改为按相关性（需先修情节向量，见下） |
| **归档语义** | 用 `status='FAILED'` + 错误串 | 新增 `ARCHIVED` 状态（一次迁移 + 一个枚举改动） |
| **管理端编辑能力** | 3 个 PATCH 端点有实现有测试但无 UI | 补 UI，成本低（后端已完成） |
| **错误态** | 6 处失败渲染成「安心的空态」 | 按首页的 per-section error flag 模式统一；**把已写好但零引用的 `ResourceState.tsx` 用起来** |
| **`import_assessments`** | 读错字段层级 + 章节解析失败 + 未接入链路 | 3 处小修，成本很低，但能**救活整个 T22b 成果** |
| **CI** | backend job 必红；失败产物永不产生 | 修测试顺序 bug（1 行 fixture 依赖）+ 修 EXIT trap 与 reporter 配置 |

### ✂️ Simplify —— 设计过重，可以降低复杂度

| 项 | 为什么可以简化 |
| --- | --- |
| **死 mock 层（约 1700 行）** | 6 个 mock service + 5 个 data 文件零引用，已被 tree-shaking 剔除。**直接删除**；`QUICK_ACTIONS` 移到 feature 目录消除分层违规 |
| **死抽象 `ResourceState`（62 行 + 4 测试）** | 要么用起来（推荐），要么删掉。现在是「写了正确的组件却没人用」 |
| **`query-keys.ts`（19 行）** | 在真正采用 React Query 之前是纯噪音 |
| **重复的 Skill 概念** | `app/skills/registry.py` 只有 1 个注册项且被绕过。要么让对话链路真正走注册表，要么删掉 `app/skills/`，只保留 `modules/quiz/skill.py` |
| **`app/worker.py`** | 重复入口 shim，无调用方 → 删除 |
| **`scripts/ci.sh` 与 `ci.yml` 双份维护** | 让 CI 调用 `scripts/ci.sh`（或反之），消除漂移面 |
| **`pushStreaming`（伪造打字机）** | 真实流式接上后它自然无用；否则现在就删 |
| **后端 4 个 handler/4 个 Skill 的抽象层数** | 当前只有 3 类任务、1 个 skill。抽象是对的，但不要再加层 |

### 🧩 Complete —— 架构已经在了，但链路没走完

| 链路 | 现状 | 完成它需要 |
| --- | --- | --- |
| **情节记忆 → AI** | 表在、写入在、API 在、**向量列恒空** | `pipeline.py:376` 接上 embedding + `teacher_context` 按相似度检索 |
| **审校题源** | 表/迁移/导入器/数据/选择器/集成/测试**全在**，三重不通 | 改导入器 2 处 + 接入 4 个启动脚本 |
| **真实流式** | 前端 SSE 传输层完整正确 | 只改 `openai_compatible.py` 一个文件 |
| **Worker 启动保证** | 队列实现完整且已验证 | 去掉 compose profile 门控 + 加队列健康探针 |
| **`role_level` 分级授权** | 字段与 DTO 都在 | `require_admin` 加一个角色判定 |
| **`.agent.md`** | 后端渲染真实（125 KB 实测） | 前端改调后端端点（并修掉硬编码的 `xiaoming` 标题） |
| **延迟 FK** | 索引已在 | 回填孤儿 + 补 2 个 FK 约束（`learning_events.conversation_id`/`quiz_session_id`） |
| **向量索引** | pgvector 0.8.6 已装 | 锁维度迁移 + 建 HNSW；注意必须同时移除 `vector_dims(...)=:dim` 谓词 |
| **React Query** | provider/retry policy/query-keys 都在 | 要么真正采用（改造 10 个页面的数据获取），要么**移除依赖**承认不用 |
| **图片/审校数据的资源管线** | `assets/` 与 `assessments/` 数据都在 | 接入 `validate_library` 校验 |

### 🤔 Reconsider —— 值得重新讨论的方向（只提理由与替代方案，不擅自改）

#### R1. 「AI 数字教师」的**能力叙事**与实现差距过大

**现状**：产品名与 README 都指向「AI 数字教师」，但实现是
「一个能检索知识库 + 注入学生上下文 + 流式输出的单轮 chat」。
没有 Agent、没有工具调用、没有真流式、长对话会失忆、出题 89% 硬编码。

**两个方向，需要你裁定：**

- **方案 A（推荐，成本低）**：**收敛叙事，做实单轮质量**。
  承认这是「带学生上下文与知识库检索的 AI 答疑」，把力气花在
  ① 真流式 ② 摘要止血 ③ 出题来源 ④ 记忆注入相关性 上。
  产品文案与 README 同步调整。**不需要新架构。**
- **方案 B（成本高）**：**真的引入 Agent Runtime**（工具调用 + 多步规划）。
  这会触及 `AIProvider` 契约、对话 service、Skill 注册表、前端 tool 事件渲染 ——
  是一次**架构级改造**，且当前没有证据表明用户需要多步 Agent。
  > 我**不建议**在没有用户反馈之前做这件事。

#### R2. 「出题」到底应该是 LLM 生成还是审校题源？

**现状**：优先级是「审校题 > LLM > 章节模板 > 通用题库」，但实际 89% 落到通用题库。

**需要讨论的点**：
- 对 K12 场景，**LLM 自由出题的正确性风险**高于审校题源。
- 当前 3 本样板书的审校题只有 13 道，**不足以支撑 25 本书**。
- **建议**：明确「章节测验以审校题源 + 章节确定性模板为主，LLM 仅作补充」，
  并把「扩审校题库」列为内容侧任务，而不是继续加强 LLM 出题。
- **但**：如果长期目标是自动扩题，则 LLM 出题链路需要真正的质量门禁
  （当前 `run_teaching_eval.py` 的离线模式只校验协议，**无法作为门禁**）。

#### R3. 无维度 `vector` 列 vs 固定维度 + HNSW 索引

**现状**：为了让 mock（64 维）与真实（1024 维）共存，列被设为无维度，代价是**永远不能建索引**，
且造成 636 个 chunk 不可达。

**替代方案**：锁定 `vector(1024)` + HNSW；mock 维度改为可配置但**不与生产混用**；
用一次迁移 + 一次 `reindex_embeddings` 收敛。
**权衡**：牺牲「同一库多 provider 共存」的灵活性，换来可索引与数据一致性。
在 1136 行的规模下顺序扫描**今天不是问题**，所以这是一个**可以先讨论、后执行**的决策。

#### R4. 是否继续保留 `src/mocks/` 目录

**现状**：零可达，但目录很大且有一个生产文件从它 import 静态配置。

**建议**：**删除 mock service 与 mock data**，把 `QUICK_ACTIONS` 迁入 `features/conversation/`。
保留一个 `src/test/fixtures/` 目录供测试使用。
理由：它现在是纯粹的认知负担 —— 本次审计中，它是**最容易被误判为「前端还在用 mock」**的陷阱。

#### R5. 测试策略：共享可变的开发库 vs 每 run 独立库

**现状**：`conftest.py` 直连开发库；`audit-check.sh` 已写好守卫但无人调用。

**建议**（这也是**技术上最需要你拍板**的一项，因为它决定后续所有开发的手感）：
- **短期**：`conftest.py` 加 fail-fast 守卫 + `ci.sh` 调用 `audit-check.sh`。**成本极低，收益极大。**
- **中期**：测试自建 schema（或 per-run 临时库）。
- **不要**退回「靠纪律」：本次审计已经证明靠纪律失败了。

#### R6. 是否现在就做生产化

**现状**：部署完整度约 10%。

**建议**：**先不做完整生产化，但要做「可部署的最小骨架」**：
一个 `api` compose 服务 + 一个 Caddy/nginx 反代 + 静态产物托管 + 深度 `/health`。
理由是当前目标是「小规模受控试用」，而试用**必须**有一个稳定的、别人能访问的环境 ——
但不需要 k8s、不需要灰度、不需要 APM。

---

## 第二部分：Roadmap

> 每项任务都能从 `docs/11`–`docs/13` 的审计结论中找到原因。**不引入与项目无关的功能。**

---

## Phase A —— 恢复可运行基线

**目标**：让「仓库状态 = 数据库状态 = CI 状态」，消除数据与版本控制风险。
**这一阶段不修任何产品缺陷，只做止血与固化。**

### 具体任务

| # | 任务 | 依据 |
| --- | --- | --- |
| A1 | **提交 T01–T26 全部未提交工作**（96 改 + 46 新增），拆成若干个语义清晰的提交（建议：迁移 / 后端 / 前端 / 文档 / 脚本各一组） | `docs/12` P1-0、`docs/15` §4 |
| A2 | **确认 4 个新迁移进入 git**，并在一个全新克隆上验证 `alembic upgrade head` 成功、`alembic current` = `a7b8c9d0e1f2` | R1（head 落后于库会让 Alembic 完全不可用） |
| A3 | **修 `test_content_ai_visibility.py` 的顺序 bug**：让 `TestChapterSourceVisibility` 依赖 `client` fixture | `docs/10` §1（CI 恒红） |
| A4 | **给 `conftest.py` 加 DATABASE_URL fail-fast 守卫**：未设置或等于开发库名 → 拒绝运行；并让 `scripts/ci.sh` 调用 `scripts/audit-check.sh` | `docs/12` P0-2 |
| A5 | **修 `ci-e2e.sh` 的 EXIT trap 与 `playwright.config.ts` reporter**，让 CI 承诺的失败产物真的产生 | `docs/12` P2-19 |
| A6 | **清理开发库中的测试夹具**：把 title 匹配夹具模式的 PUBLISHED 书归档；清理测试账号与 8442 条 idempotency_keys | P0-2 的后果 |
| A7 | **在 CI 中加 `alembic check` 门禁** | `docs/06` §9.10 |
| A8 | 清理噪音：`backend/空`、`.playwright-mcp/`、根 `.env.example`、`app/worker.py` | `docs/12` P3-1/2/3/4 |

### 完成标准
- ✅ 全新克隆 → `docker compose up -d postgres redis` → `uv run alembic upgrade head` → `pytest` **全绿**
- ✅ GitHub Actions 三个 job **全绿**（并在本机至少手动触发过一次验证）
- ✅ 学生书库中**不再出现**任何测试夹具
- ✅ `git status` 干净（除 gitignore 覆盖的运行态文件）
- ✅ 失败时 CI 能真的下载到后端/worker 日志

---

## Phase B —— 打通核心业务闭环

**目标**：把「已经有架构但没接上」的链路接上，把「有缺陷」的核心链路修对。
**这一阶段全部是 Complete + Fix，不引入新能力。**

### 具体任务

| # | 任务 | 依据 |
| --- | --- | --- |
| B1 | **会话摘要止血**：`message_covered_count` 改为真实吸收边界，使未被吸收的消息仍进入窗口；加回归测试（30 轮对话后第 25 轮内容仍可被引用） | P0-3，影响最大的 AI 缺陷 |
| B2 | **真 token 级流式**：`openai_compatible.py` 改 `stream:True` + 真实 SSE 解析；超时拆为连接/读取两个可配置项；加一次幂等重试 | P1-1 |
| B3 | **修 `import_assessments`**（读顶层 `review_status` + 从 `slug`+`chapter` 解析章节 + 让 `skipped_no_chapter` 真正生效），并接入 `start.sh`/`ci.sh`/`ci-e2e.sh`/CI | P1-3（救活整个 T22b） |
| B4 | **Worker 启动保证**：去掉 compose `worker` 的 profile 门控；`/health` 增加队列深度与最老 queued 任务年龄 | P1-2 |
| B5 | **情节记忆接上向量**：`pipeline.py:376` 写入 embedding；`teacher_context` 按相似度检索 top-k episode | P1-4 |
| B6 | **修 ReaderPage 与统一错误态**：把 `ResourceState.tsx` 真正用起来，逐页替换「安心的空态」 | P1-6、`docs/04` §3.5 |
| B7 | **修 SettingsPage 软锁**：字段初始化移到 `await` 之前，`catch` 设错误态 | P1-7 |
| B8 | **整治意图劫持**：`QUIZ_INTENT_KEYWORDS` 改为显式意图或 LLM 判定 | P1-8 |
| B9 | **管理端补齐 3 个编辑 UI**（内容块 / 知识点 / 资源元数据） | P2-2（后端已完成，成本低） |
| B10 | **归档语义**：新增 `ARCHIVED` 状态替代 `status='FAILED'` 的滥用 | P2-5 |
| B11 | **向量数据收敛**：执行 `reindex_embeddings` 消除 636 个 64 维遗留 chunk（或在讨论 R3 后统一锁维度） | P1-5 |
| B12 | **前端死代码清理**：删 mock services + mock data、`query-keys.ts`、`pushStreaming`、死按钮；`QUICK_ACTIONS` 迁入 feature | P2-6、Simplify 建议 |

### 完成标准
- ✅ 30 轮对话后 AI 仍能正确引用第 25 轮的内容（有自动化测试）
- ✅ 真实 LLM 的回复**逐 token 到达**（可在浏览器 Network 面板观察到持续 delta）
- ✅ 全新环境 seed 后 `reviewed_questions` 有 13 道 APPROVED 审校题，且章节测验的 `generation_kind` 出现 `reviewed`
- ✅ `docker compose up` 之后任务能被消费；`/health` 反映队列状态
- ✅ 任意页面的任何请求失败都给出**可重试的错误态**，不再伪装成空态
- ✅ 学生端与管理端再无「只能创建不能编辑」的缺口
- ✅ 前端 bundle 中不再包含 mock 层；死代码清单归零

---

## Phase C —— 架构修正

**目标**：处理那些「不改会一直疼」的结构性债务。**这一阶段需要你先对 Reconsider 的 R1/R3/R5 拍板。**

### 具体任务

| # | 任务 | 依据 |
| --- | --- | --- |
| C1 | **测试基础设施重建**：自建 schema 或 per-run 临时库；补统一 fixture（client / db / 用户 / 书）；清理三个 `_ensure*()` 造数器为幂等 upsert | P2-18、Reconsider R5 |
| C2 | **补错误路径测试**：Provider 的 HTTP ≥400 分支、`_http_proxy_url()`、超时与重试；真实 Redis / MinIO 集成测试 | `docs/10` §6（唯一假状态码是 200） |
| C3 | **加覆盖率与静态检查**：pytest-cov + vitest coverage + ruff + mypy（至少对 `app/ai`、`app/modules` 生效） | `docs/10` §5 |
| C4 | **向量索引决策落地**（依 R3 裁定）：锁维度迁移 + HNSW；同时移除 `vector_dims(...)=:dim` 谓词 | `docs/06` R4 |
| C5 | **补 2 个延迟 FK**（`learning_events.conversation_id`/`quiz_session_id`），先回填清理孤儿 | `docs/06` R6 |
| C6 | **补 25 个缺失的 FK 索引**（一次纯索引迁移） | `docs/06` R8 |
| C7 | **统一 `chapter_completions` 唯一对象表示**，让 autogenerate 安静 | `docs/06` R11 |
| C8 | **拆解 `models.py`（1465 行）与 `conversation/service.py`（1319 行）**为按领域/职责分文件；**保持无 `relationship()` 约定** | `docs/13` Architecture |
| C9 | **`.agent.md` 单一实现**：前端改调后端端点；修掉 `agent_md.py` 的硬编码 `xiaoming` | P2-7 |
| C10 | **React Query 二选一**（依 R1 讨论）：真采用（改造 10 个页面）或移除依赖；不允许继续「装了不用」 | P2-3 |
| C11 | **`role_level` 分级授权**落地 | P2-14 |
| C12 | **可观测性补齐**：LLM 调用/token/延迟/失败率、RAG 命中率、队列深度、DB 连接池；`/health` 深度检查；进程内 metrics 的多副本方案 | P2-4、`docs/09` §6 |
| C13 | **`archive_noncorpus.py` 的保留规则放宽 + 加 status 谓词**；为三个破坏性脚本写 break-glass 文档 | `docs/06` R3 |
| C14 | **修 `quiz` 的 token 计量**（字符数 → 真实 usage） | P2-4 |
| C15 | **把 `0-D`/`0-E` 编号对应的规格补进 `docs/`**，或把注释改为指向现存文档 | `docs/13` DX |

### 完成标准
- ✅ 测试可以在**任意干净库**上一次性全绿，且不依赖执行顺序
- ✅ CI 有覆盖率报告与 lint/类型检查门禁，且覆盖率不再是黑盒
- ✅ `alembic revision --autogenerate` 输出为空（无 churn）
- ✅ Provider 的错误路径、超时、重试都有测试
- ✅ `/metrics` 能回答「今天花了多少 token、RAG 命中率多少、队列积压多少」
- ✅ 任何持久化层对象（`models.py`、`conversation/service.py`）单文件 < 600 行

---

## Phase D —— 产品能力完善

**目标**：在基线稳固之后，补齐产品承诺与实现之间的差距。**顺序可按试用反馈调整。**

### 具体任务

| # | 任务 | 依据 |
| --- | --- | --- |
| D1 | **按 R2 裁定收敛出题策略**：以审校题源 + 章节确定性模板为主；扩审校题库至覆盖三学段样板书 | 出题 89% 硬编码 |
| D2 | **AI 反馈与提示真实化**：`ai_feedback` 接 LLM（保留规则兜底）；三级 hint 分级生成 | P2-1 |
| D3 | **教学评测升级为质量门禁**：把 `run_teaching_eval.py` 的真实模式接入 CI（可只在发布前跑），离线模式改为真断言 | `docs/10` §6 |
| D4 | **记忆注入改相关性排序**（B5 完成后自然可得） | P2-12 |
| D5 | **可部署的最小骨架**：`api` compose 服务 + 反代 + 静态托管 + 深度健康检查 | `docs/09` §6、Reconsider R6 |
| D6 | **TTS 落地**（依 Reconsider 讨论）：配置真实 TTS provider，让语音链路闭环为「说-听」 | TTS 当前 `DISCONNECTED` |
| D7 | **试用准备**：真实用户招募、受控试用数据策略落地、试用反馈收集 | `docs/plans/current-phase.md:37` 自述待外部 |
| D8 | **内容侧**：把 25 本书的图片资源、审校题按样板书标准补齐 | T12/T22 的推广 |

### 完成标准
- ✅ 章节测验的 `generation_kind` 分布中，`reviewed` + `chapter_deterministic` 占多数，`bank` 仅作兜底
- ✅ 每一道题的反馈与三级提示都与题目内容相关（有测试）
- ✅ 教学评测能真实拦截一次质量回归
- ✅ 有一个外部可访问的试用环境，且有基础监控
- ✅ 语音链路可完成「说 → 听」闭环
- ✅ 5–8 位真实学生完成一轮受控试用，产出可分析的反馈

---

## 建议的执行顺序与依赖

```
Phase A（止血，1 个迭代）
   A1 ─┬─► A2
       ├─► A3 ──► A4 ──► A7
       ├─► A5
       └─► A6
              │
              ▼
Phase B（闭环，2–3 个迭代）   ← 可与 R1 讨论并行
   B1 ─► B5 ─► D4
   B2
   B3
   B4
   B6 ─► B7
   B9 ─► B10
   B12
              │
              ▼
Phase C（结构，2–3 个迭代）   ← 需要 R1/R3/R5 先拍板
   C1 ─► C2 ─► C3
   C4（依赖 R3 裁定）
   C5 ─► C6 ─► C7
   C8 ─► C9 ─► C10
   C12 ─► C13
              │
              ▼
Phase D（产品，按试用反馈）
   D1 ─► D2 ─► D3
   D5 ─► D7
   D6
   D8
```

**关键判断**：
- **Phase A 没有任何讨论余地** —— 它是所有后续工作的前提。
- **Phase B 的核心是 B1/B2/B3** —— 这三个决定了「AI 数字教师」是否名副其实。
- **Phase C 需要你先对 R1（能力叙事）、R3（向量索引）、R5（测试隔离）拍板。**
- **Phase D 的顺序应该由真实试用反馈决定**，现在排出精确顺序是伪精确。
