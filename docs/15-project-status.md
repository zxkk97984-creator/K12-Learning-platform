# 15 · 项目现状报告

> 生成于 2026-09-16，基于当前工作区代码、线上数据库与运行实例的实测。
> 所有结论都可回溯到 `docs/00`–`docs/14` 或 `.audit/` 中的证据。

---

## 1. 当前处于什么阶段？

# **Prototype+ / MVP−**（介于原型与最小可用产品之间，**不是 Beta**）

不是 Production Ready，也**不只是** Prototype —— 因为它有真实的鉴权、幂等、并发控制、
数据模型、异步任务队列和一条能走通的学习闭环。

但也**不是 Beta** —— 因为：

| Beta 的必要条件 | 现状 |
| --- | --- |
| 干净的、可重现的构建 | ❌ CI 的 backend job 在全新库上**必然失败** |
| 与生产同构的部署 | ❌ 无部署编排，无反向代理，无监控 |
| 数据可信 | ❌ 学生书库中 43/69 本是测试夹具 |
| 核心能力名副其实 | ❌ 「AI 数字教师」无真流式、无工具调用、长对话失忆、出题 89% 硬编码 |
| 质量门禁有效 | ❌ 无覆盖率、无 lint、错误路径零覆盖 |

**一句话**：这是一个**功能面铺得很开、工程纪律在局部很扎实、但核心 AI 能力与工程闭环都还没收口**的
后期原型。

### 阶段判定的直接证据

| 证据 | 含义 |
| --- | --- |
| 98 次提交，最后提交 `970ffda`（2026-08-28）；**但工作区有 96 改 + 46 新增未提交**（T01–T26 整轮） | 开发在 2026-09-16 仍在活跃，只差提交 |
| 线上库出现**当日创建**的 43 本测试书 + 后台任务 | 昨天/今天还在跑测试与 E2E |
| 4 个迁移未提交而库已 stamped 到它们的 head | 一次 `git clean` 就会让仓库无法操作数据库 |
| `docs/plans/current-phase.md` 声称 384/258/33 全绿；实测 1 红（干净库） | 自评与实测不符 |
| `infra/` 空、无 api compose 服务、无反代 | 生产化从未开始 |

---

## 2. 分维度评估

> 说明：**不给伪造的精确百分比**。区间依据是「审计过的功能项中状态为 COMPLETE 的比例」，
> 依据见 `docs/11-feature-status.md` 的逐项判定。

### 2.1 产品功能完整度 —— **约 60–70%**

- **完整**：登录/鉴权、书库发现、阅读、图片渲染、对话（含 SSE 传输）、测验判分、
  错题讲解、章节完成、继续学习、记忆与画像、规则推荐、管理后台主体。
- **半成品**：AI 对话质量、出题、异步能力默认启动。
- **未实现**：教师端、班级、家长端、支付、排行榜、多租户 —— 这些**代码中完全不存在**，
  且 `tasks/plan.md:8` 明确排除在本轮范围外。**这是有意的产品边界，不是缺失。**

### 2.2 前端完整度 —— **约 75%**

- 10 个学生/管理页面全部接真实后端，**零 mock 可达**（已用构建产物证明）。
- `tsc --noEmit` 0 错误（`strict` + `noUnusedLocals`，169 文件），`vite build` 成功，
  Vitest 258/258 通过。
- 路由级 code-split、移动端适配（390/820/1280 四套 Playwright project）、
  账号切换 epoch 隔离、Safe Markdown、真实语音全双工。
- **扣分**：ReaderPage 无错误态、失败渲染成空态（6 处）、SettingsPage 软锁、
  React Query 装了不用、约 1700 行死 mock + 若干死抽象、假建议徽标。

### 2.3 后端完整度 —— **约 70%**

- 33,245 行 Python；11 个领域模块；71 个业务 HTTP 端点 + 1 WS。
- 分层纪律好（Router 不写 SQL）、统一信封与错误码、四层幂等、会话串行锁、
  账号禁用即时失效、严格后台鉴权、可见性守卫在 Service 层。
- **扣分**：AI 层空心化、管理端只能创建不能编辑、归档语义错误、N+1、
  `role_level` 无实效、部分 token 计量失真。

### 2.4 数据层完整度 —— **约 85%（最好的一环）**

- **三方对账（ORM ↔ 迁移 ↔ 线上库）几乎零漂移**：368 列 / 58 FK / 68 CHECK / 34 索引全部一致；
  23 个迁移单链单 head；从零 `alembic upgrade head` 安全。唯一的差异是一个良性的
  「唯一索引 vs 唯一约束」表示差异。
- 32 张表设计克制：无 `relationship()`、无 mastery/score/percent 数字列、
  幂等靠唯一约束、append-only 表、软删除保审计。
- **扣分**：零向量索引 + 无维度列阻止加索引；2 个延时 FK 永远没补；
  25/58 FK 列无索引；`archive_noncorpus.py` 会误伤合法内容；
  1 个迁移被回溯修改；**最大的问题不在 schema，而在库里的数据是脏的**。

### 2.5 AI 能力完整度 —— **约 35–40%（最大短板）**

- **真实存在**：Provider 适配（真实调用 DeepSeek，33 条真实回复落库）、真实 embedding
  （467 个 1024 维向量）、真实 pgvector SQL、真实 RAG 接线、真实 Worker 队列
  （636 次任务 success）、真实 ASR（阿里云实时）。
- **名不符实**：
  - 无 token 级流式（`stream:False` + 事后切片伪造）
  - 无 Agent、无 Tool Calling（关键词分支冒充）
  - **长对话摘要删历史并谎报覆盖** ← 影响最大
  - 情节记忆向量从不写入 → AI 看不到情节
  - 出题 89% 来自 8 题硬编码题库；反馈/提示硬编码
  - 审校题库三重不通
  - 记忆抽取是规则式 + LLM 润色
  - 无 LLM 可观测性、无重试、30s 硬超时
- **这是「AI 数字教师」这个产品定位的核心风险**：工程外壳真实，AI 内核偏薄。

### 2.6 测试完整度 —— **约 45%**

- 数量充足：后端 384 + 前端 258 + E2E 33 + 教学评测 37 例。
- 质量不均衡：前端单测与 E2E 质量高（含对抗性断言、真端到端零 mock）；
  后端集成测试可用但**环境隔离为零**。
- **致命**：CI backend job 在干净库上必然失败；错误路径零覆盖；无覆盖率工具；
  11 个测试保护死代码；`conftest.py` 只有 11 行且直连开发库。

### 2.7 部署完整度 —— **约 10%**

- 有：本地一键启动/停止脚本、docker-compose（依赖服务）、Dockerfile、GitHub Actions。
- 无：api 的 compose 服务、反向代理、TLS、静态托管、k8s、密钥管理、
  备份演练、监控告警、日志聚合、优雅关闭、灰度回滚。
- `infra/` 是空目录。

### 2.8 安全性 —— **约 65%**

**好**：bcrypt、prod 拒绝占位 JWT secret、账号禁用即时失效、
严格后台鉴权（无 legacy 放行）、路径穿越防护（已测）、
日志明确不记敏感信息、限流双模式强制拒绝、可见性守卫不可被缓存绕过、
真实第三方 Key 未泄漏进 git（已用 `git check-ignore` 验证）。

**差**：硬编码 `admin123`（重复两处）、token 存 localStorage（无 httpOnly 方案）、
2 处 401 处理不一致、`role_level` 无分级授权、无 secrets manager。

### 2.9 可维护性 —— **约 55%**

**好**：注释质量高且大量解释「为什么」（例如 `worker.py:45-52` 记录了一个真实
`MissingGreenlet` 事故的根因）、契约优先、分层清晰、文档量巨大（12,056 行 docs）。

**差**：注释引用**不在仓库里**的 `0-D`/`0-E` 编号；`current-phase.md` 的测试数字不可复现；
5 处前端注释与实现矛盾；约 1700 行死 mock 会持续误导新人；
`models.py` 单文件 1465 行；`conversation/service.py` 1319 行。

### 2.10 可观测性 —— **约 20%**

- 有：结构化访问日志（不记敏感信息）、`X-Request-ID` 全链路、进程内 Prometheus 文本指标。
- 无：LLM 指标、队列指标、DB 指标、外部监控、日志聚合、告警、
  多副本指标聚合、深度健康检查（`/health` 不查 DB/Redis/Worker）。

---

## 3. Documentation Drift Report

> 前置说明：本次调查**先只读代码**，在完成代码、数据库、配置、测试、Git 调查**之后**才读旧文档。
> 下列判定均以**代码为事实源**。

### 3.1 文档正确（代码与文档一致）

| 文档 | 内容 | 验证 |
| --- | --- | --- |
| `docs/architecture/project-architecture.md` | 分层、模块划分、无 `relationship()`、SQLAlchemy async 原则 | ✅ 与代码一致 |
| `docs/architecture/project-architecture.md:529,2294` | 「当前不引入 pydantic-ai，仅作为可选演进方向」 | ✅ 全仓无该依赖，无 import |
| `docs/architecture/project-architecture.md:1162` | 「Redis Cache 与 Distributed Lock 已实现；Worker Job Queue 由 PostgreSQL `background_jobs` 承载」 | ✅ 准确 |
| `README.md:75-79` | AI Provider 开关（mock / openai_compatible） | ✅ 与 `factory.py` 一致 |
| `README.md:68-69` | 演示账号 `xiaoming/demo123`、`admin/admin123` | ✅ 与 `seed.py` 一致 |
| `docs/requirements/pilot-data-policy.md` | 试用数据与记忆控制 | ✅ 与 T24 实现一致 |
| `docker-compose.yml` 的注释 | worker 带 profile、默认以宿主机进程运行 | ✅ 准确 |
| `docs/plans/current-phase.md:33-38`（尚未确认项） | 自述「GitHub Actions 未在本机触发 / S3 仅本地联调 / 真实 LLM 未评测 / 多副本 metrics 待定」 | ✅ **诚实且准确**，值得肯定 |

### 3.2 文档过时（曾经正确，代码已变）

| 文档 | 声称 | 实际 |
| --- | --- | --- |
| `README.md:17` | 「所有开发任务请先阅读执行总控文件 `霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md`」 | 该文件是 2026-08-19 的 Phase 0–12 基线；当前实际入口是 `tasks/plan.md`（未提交） |
| `docs/README.md` | 文档入口同上 | 同上 |
| `docs/plans/post-audit-plan.md` | 其头部已自注「本文件为 2026-08-21 历史记录」 | ✅ 已自我标注，处理得当 |
| `plan.md`（根） | 头部写「状态：计划待执行，业务修复尚未实施」 | 该行是 *tasks/plan.md* 的头部；根 `plan.md` 是 2026-08 的旧计划 |
| `tasks/plan.md` 头部 | 「状态：**计划待执行，业务修复尚未实施**」 | ❌ **过时**：`tasks/todo.md` 显示 T01–T26 全部「实现完成」，且代码与 git 工作区都印证已实施 |
| `main.py:33` | 注释「2-B 接入数据库连接池；当前无任何外部依赖」 | ❌ 实际依赖 DB / Redis / Worker |
| `frontend/src/features/screen-context/types.ts:1` | 「纯前端 Context，**不落服务器**」 | ❌ 经 3 条通道发送到后端 |
| `frontend/src/features/quiz/lib.ts:10` | 「只读 **Mock** 查询」 | ❌ 用真实 `contentService` |
| `frontend/src/shared/api/api-student-service.ts:16` | 「其余 Service 仍 **Mock**」 | ❌ 6 个服务全部 `Api*` |
| `frontend/src/features/conversation/types.ts:13` | quiz payload「本任务仅**占位**」 | ❌ 真的在 `MessageList.tsx:93` 渲染 |
| `frontend/src/features/companion/hooks/useCompanionDock.ts:66` | 「6s 后提示、**7s** 恢复」 | ❌ 代码是 13 s |
| 根 `.env.example` | 使用 `LLM_PROVIDER`/`LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL` | ❌ 代码用 `AI_*`；该文件**无任何读取方** |

### 3.3 文档超前（描述了代码尚未实现的功能）

| 文档 | 声称 | 实际 |
| --- | --- | --- |
| `docs/contracts/api-contract.md:390` | 「实现核对（2026-08-27）… 合计 **68** 个 HTTP + 1 WS = 69 条路由」 | ❌ 实际 **71 HTTP + 1 WS**（T10/T13/T16 新增 3 个端点未回写） |
| `docs/plans/current-phase.md:34` | 「S3 兼容对象存储仅本地/SigV4 联调，未接真实对象存储」 | ✅ 诚实标注 —— 归入此类的**正面**例子 |
| `docs/architecture/diagrams.md:50,251` | 图中写「ModelGateway（**PydanticAI** Adapter）」 | ❌ 实际是自研 httpx 适配器；同文档 `:529` 已裁定不引入，**图与文自相矛盾** |
| `tasks/plan.md` 头部 | 「此文件中的新增接口、组件和测试均为**拟议交付**，不能描述为已存在」 | ❌ 已全部实现；该声明现在是**反向**过时 |
| `docs/plans/current-phase.md:14` | 「后端 pytest：**384 passed / 0 failed**」 | ❌ 干净库上 **1 failed / 383 passed**；该数字只在污染库第二次运行时成立 |

### 3.4 文档错误（与当前实现明显冲突）

| 文档 | 冲突点 |
| --- | --- |
| `docs/plans/current-phase.md:15` | 「主 bundle 272 kB，独立 admin 18 kB，无 >500 kB 警告」——构建确实通过，但前端**没有使用 React Query**，文档未记录这一结构性事实 |
| `docs/plans/current-phase.md:29` | 「审校题源幂等导入 + ReviewedQuestion 选择（`generation_kind="reviewed"` 优先选 APPROVED 审校题）」——描述为已完成能力，实际**三重不通**（未接入 + 导入器 bug + 数据格式不匹配），且线上 0 次使用 |
| `README.md:3` | 「对话 + RAG + SSE 幂等重放」「长对话窗口化」——SSE **传输**真实且幂等健全，但**没有 token 级流式**（`stream:False`），长对话窗口化**会删除历史**。措辞让读者以为流式与上下文管理都是完整的 |
| `README.md:3` | 「随堂测验（多题型/并发序号安全）」——真实，但未提 89% 来自 8 题硬编码题库 |
| `README.md:3` | 「教学图片契约与渲染」「语音 ASR/TTS Provider 化」——图片 ✅；ASR ✅；**TTS 在当前部署返回 `TTS_UNAVAILABLE`**（未提） |
| `docs/plans/current-phase.md:16` | 「E2E **33 passed / 0 failed**」——本次未执行（会写开发库），**UNKNOWN** |

### 3.5 代码未文档化（代码已有能力，文档完全没有）

| 能力 | 证据 | 为何重要 |
| --- | --- | --- |
| `PUT /me/chapters/{chapter_id}/completion` | `learning/router.py:78` | 章节完成闭环的核心端点，契约文档无 |
| `GET /me/learning-next` | `recommendation/router.py:22` | 首页「下一步行动」的核心端点，契约文档无 |
| `GET /library-assets/{book_slug}/{filename}` | `content/assets.py:30` | T10–T12 教学图片契约的出口，契约文档无 |
| `context_window.py` 的 token 预算机制与其**已知缺陷** | `conversation/context_window.py` | 架构文档未描述 |
| Worker 的指数退避与孤儿回收 | `jobs/queue.py`、`config.py:38-43` | 架构文档未描述 |
| `chapter_completions` 与「书完成」的判定语义 | `models.py:517-523` | 领域模型文档未更新 |
| `reviewed_questions` 表与出题来源优先级 | `models.py:1136`、`quiz/skill.py:123-199` | 契约/领域文档未更新 |
| 限流的双模式（Redis / 进程内）与「都强制拒绝」语义 | `infrastructure/rate_limit.py` | 未文档化 |
| 「无 token 级流式」这一实现真相 | `ai/openai_compatible.py:68` | **任何文档都没提**，而它直接影响产品体验与容量规划 |
| 「会话摘要是规则式且谎报覆盖」 | `jobs/handlers/conversation.py:86` | **任何文档都没提** |

---

## 4. 与「上一次开发进行到哪」的恢复结论

**时间线（由 git 历史 + 文件时间 + 数据库时间三方交叉得出）**

| 时间 | 事件 |
| --- | --- |
| 2026-08-19 | Phase 0–1：基线、架构契约、React 前端工程化（含 mock 服务层） |
| 2026-08-19 ~ 08-25 | Phase 2–12 陆续完成并提交 → 迁移 head `d4e5f6a7b8c9`（311 pytest） |
| 2026-08-21 | Post-Audit P0-1 ~ P2-2 全部 PASS 并提交 |
| 2026-08-25 ~ 08-28 | Phase 5-A/5-B 收口（安全、可观测、真实 Embedding、Worker 退避、CI 修复）→ **HEAD `970ffda`（08-28）** |
| **2026-09-06** | 交接：撰写 `tasks/plan.md` / `project-review.md` / `todo.md`，启动 **T01–T26 优化轮** |
| 2026-09-06 ~ 09-07 | T01–T26 逐个实现 + 验收（`tasks/acceptance/` 30+ 份证据 + 截图） |
| 2026-09-07 ~ 09-16 | 收尾与零散修复（图片资源、asm 导入、`profile-insights` e2e 等） |
| **2026-09-16 08:26** | 最后一次启动完整系统（API + Worker + 前端 + 三个容器），此后**无提交** |
| **2026-09-16（本次审计）** | 工作区仍有 **96 改 + 46 新增未提交**；库中出现当日创建的 43 本测试书 |

**结论**：项目**不是「搁置很久」**，而是**「一整轮 T01–T26 优化全部做完但从未提交」**。
最后一次真实活动就在审计当天早上（系统在 08:26 被完整启动）。

**未提交的量（`git diff --stat`）**：96 文件、**+3353 / −1142 行**，含：
4 个新迁移、19 个新后端文件（含 `content/assets.py`、`conversation/context_window.py`、
`scripts/import_assessments.py`、`evals/`）、19 个新前端文件（含 `ContentBlockView.tsx`、
`ChapterCompletionCard.tsx`、`use-home-data.ts`、`home/components/`、`ResourceState.tsx`、
`BottomNav.tsx`、`query-keys.ts`）、`scripts/audit-check.sh`、`scripts/test-db.sh`、
`docs/requirements/pilot-data-policy.md`，以及 `tasks/` 全部验收证据。

**因此本次接管的第一优先级不是「重新理解一个陌生项目」，而是「先把这一轮完整工作安全落到版本控制里」。**
详见 `docs/16-roadmap-analysis.md` Phase A。

---

## 5. 当前最大缺口（Top 5）

1. **P0 · 一整轮 T01–T26 工作未提交**，且 4 个迁移未提交而库已 stamped 到它们的 head ——
   一次 `git clean` 就能让仓库无法操作自己的数据库。
2. **P0 · CI backend job 在干净库上必然失败**（测试顺序 bug），质量门禁实际失效。
3. **P0 · 开发库被测试夹具污染**：学生书库 69 本中 43 本是夹具，32 本零章节 ——
   测试直连开发库且无任何强制隔离。
4. **P0 · 长对话摘要删除历史并谎报覆盖范围** —— 核心教学链路的正确性缺陷。
5. **P1 · AI 内核名不符实**：无真流式、无工具调用、情节记忆 AI 看不到、
   出题 89% 硬编码、审校题库三重不通。
