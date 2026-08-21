# 霜铃 V3 — 实施后整改执行计划（Post-Audit Plan）

> 依据：`docs/plans/current-phase.md`（Phase 12 已完成）+ 2026-08-21《项目实施情况》审计报告
> 执行模式：Hermes 编排 → herdr 驱动 Codex（同一窗口 w5:p2，同一 Codex 会话）→ Hermes 独立验收 → PASS 才进入下一阶段
> 状态：**P0-1~P1-3 PASS（a9e5934/891917c/56c2ab1/9dcbbdd/fcbea2e）→ P2-1 进行中**（2026-08-21）

---

## 0. 背景

审计确认项目已完成 Phase 0–12 全部阶段（PROJECT IMPLEMENTATION COMPLETE），227 pytest / 123 Vitest / build 全绿。
但存在若干影响验收质量的功能缺口与架构残余问题。本计划按审计报告「建议的后续动作」优先级（P0→P1→P2）分阶段整改。

## 1. 阶段划分与依赖

| 阶段 | 优先级 | 内容 | 依赖 |
| --- | --- | --- | --- |
| P0-1 | P0 | BookDetailPage 补齐（书库→书本详情→开始学习闭环） | 无 |
| P0-2 | P1 | 真实 Embedding Provider + 知识检索相似度阈值 | P0-1 |
| P1-1 | P1 | Worker 进程拆分（PDF 解析/知识索引/摘要/记忆合并异步化） | P0-2 |
| P1-2 | P1 | Redis 接入（锁/缓存；替换进程内 dict 锁） | P1-1 |
| P1-3 | P1 | ConversationSummary 生成（长对话压缩进 TeacherContext） | P1-1（依赖 Worker 或后台任务） |
| P2-1 | P2 | Recommendation 实体 + 推荐 API/Skill（首页/书库真实推荐） | P1-3 |
| P2-2 | P2 | 架构文档裁定与契约同步（pydantic-ai 取舍 + api-contract 端点表对齐 65 个实际端点） | 全部 |

## 2. 执行协议（每阶段固定）

1. Hermes 将本阶段拆为单个有限任务，写入 `.hermes-tasks/task-XX.md`（Context/Goal/Scope/Required Behavior/Data·API/Tests/Acceptance/Out of Scope/Report）；
2. `herdr agent prompt w5:p2 "$(cat .hermes-tasks/task-XX.md)"` 派发；
3. `herdr agent wait w5:p2` 后台等待（零 token）；
4. Codex 返回后，Hermes **独立验收**（读 diff/代码、跑 pytest/vitest/build、必要时起服务跑 E2E）：
   - PASS → Hermes 执行 `git commit`（Codex 不 commit）+ 更新 `docs/plans/current-phase.md` → 进入下一阶段；
   - FAIL → 生成 Fix Task（Root Cause → Expected → Actual → Allowed Files → Required Fix → Regression Test → Acceptance）再次派发，直到 PASS；
5. 每阶段结束后向用户汇报本阶段完成情况。

## 3. 验收口径

- 代码：仅允许本阶段 Scope 内文件被修改（git diff 人工核对）；
- 测试：相关 pytest / Vitest 新增且全绿；回归全量绿；
- 运行：涉及 API 的阶段用 8002 端口起后端实测关键链路（8000 被 DAI 占用）；
- 不提交 Codex 未经验收的修改；不引入新依赖未经裁决。

## 4. 暂停点（HUMAN 介入）

- P2-2 的 pydantic-ai 取舍为架构决策（两方案皆合理）→ 默认建议：**维持自研 Teacher Agent Runtime（路线图 §2.3 口径），更新架构文档 §12 标注实际采用口径**；若用户有其他意向则按用户裁定执行；
- 任何阶段出现破坏性操作 / Secret / 需求冲突 → 暂停询问。

## 5. 阶段明细

### P0-1 BookDetailPage 补齐
- Goal：把 `/books/:bookId` 从骨架占位改为真实书本详情页。
- 内容：封面/简介/适用年级/进度/「你将学会什么」/章节目录（真实 API chapters）/知识点/预计时长/开始学习→Reader 跳转（首章或继续章）。
- 依据：产品需求 §44、api-contract §7.2 BookDetailDTO、BookDetailPage.tsx 现状（9 行占位）。
- 验收：前端 build 通过；路由可访问真实书数据；页面出现章节目录并可从「开始学习」跳转 `/learn/:bookId/:chapterId`；新增页面组件测试。

### P0-2 真实 Embedding Provider + 检索阈值
- Goal：embedding 从 mock（64 维哈希）升级为真实 provider（OpenAI-compatible embeddings，兼容 DeepSeek/Qwen 中转），并给知识检索加相似度阈值过滤。
- 内容：`app/ai/embedding.py` 增加真实 provider（config：embedding_base_url/api_key/model/dimension）；ingestion/search 用真实向量；`KnowledgeService.search` 增加 min_similarity（无阈值时按 0 处理或返回空）。
- 注意：mock 数据需重索引（seed 脚本或 reprocess 路径）；dimension 变更涉及 `vector(n)` 列 ALTER（需 migration）。
- 验收：`test_embedding.py` 扩展 + knowledge API 测试通过；真实 embedding 请求经 httpx mock 验证；migration 可升可降。

### P1-1 Worker 进程拆分
- Goal：重任务移出 HTTP 请求（架构 §31）。
- 内容：新建 worker 进程入口（`app/worker.py` + `app/jobs/` 目录），首版承担：知识资源解析/索引（PDF 解析接入 pypdf 或类似）、ConversationSummary 生成、Memory Consolidation 兜底；HTTP 侧改为「创建 job → 返回 queued → worker 处理 → 状态更新」；KnowledgeResource 状态机 UPLOADED→PARSING→…→READY 由 worker 驱动；docker-compose 增加 worker 服务；scripts/start.sh 支持一并启动。
- 注意：PDF 解析（需求 §83 明确支持 PDF）在本阶段落地；现有同步 ingestion 保留为 fallback 或迁移。
- 验收：上传 md/txt 后资源异步到 READY（E2E 或 API 轮询）；PDF 上传成功解析；pytest 全绿；start.sh 一键启动包含 worker。

### P1-2 Redis 接入
- Goal：Redis 承担锁/缓存（架构 §33），替换 `_CONVERSATION_LOCKS` 进程内 dict。
- 内容：新增 `app/infrastructure/cache/redis.py`（redis-py async，连接串 config）；对话锁改 Redis 分布式锁（带 TTL 兜底防死锁）；可选：learning-session ACTIVE 并发、quiz 幂等可复用锁；docker-compose redis 已有，.env 补 REDIS_URL；无 Redis 时优雅降级到进程内锁（保证本地 mock 体验）。
- 验收：pytest（含锁竞争用例）全绿；起 redis 容器后锁生效；无 redis 时降级路径可用。

### P1-3 ConversationSummary 生成
- Goal：长对话压缩（需求 §7.2、架构 §23）真正可用。
- 内容：消息数超过阈值（如 20 条）时触发摘要生成（LLM 或规则压缩），写入 conversation_summaries；`ConversationService` 构建 TeacherContext 时携带 summary + recent messages；可复用 P1-1 worker 或请求内懒生成（阈值内）。
- 验收：发满阈值消息后 `GET /conversations/{id}/summary` 返回非空；新对话回答仍含完整上下文；相关测试通过。

### P2-1 Recommendation 实体 + 推荐 API
- Goal：首页/书库推荐从 mock 文案改为真实 Recommendation（domain-model §5.8、api-contract §3.8/§4）。
- 内容：新增 `recommendations` 表 + migration + API（GET /me/recommendations 等）+ 推荐 Skill（基于 LearningEvent/QuizAnswer 的规则推荐，可解释 reason + evidence_ids）+ 前端 HomePage/LibraryPage 接入。
- 验收：推荐接口返回真实理由与证据；前端不再引用 `homeRecommendation` mock；E2E/测试覆盖。

### P2-2 架构文档裁定与契约同步
- Goal：消除文档与实现的偏差。
- 内容：① pydantic-ai 取舍裁决（默认：维持自研 Runtime，架构 §12 加注「实际采用路线图 §2.3 自研轻量 Runtime，PydanticAI 为可选演进」）；② api-contract.md 端点总表与实际 65 个端点对齐；③ 需求总纲/架构文档中已变更口径（如 PDF 解析落地、Worker 落地、Redis 落地）同步；④ current-phase.md 收口。
- 验收：文档 grep 抽查无残留矛盾；端点表与实际路由一一对应。

## 6. 完成判据

所有阶段 PASS 且提交后，向用户输出最终整改报告（每阶段实际修改/测试/验收结果 + 剩余风险）。
