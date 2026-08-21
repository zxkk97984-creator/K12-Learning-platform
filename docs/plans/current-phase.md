# 当前阶段状态

> 本文件由 Hermes（总控）维护，是会话恢复的权威进度来源。恢复时先读 `霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md`（Execution Baseline）再读本文件。

## 当前阶段
**Phase 12 + Post-Audit 整改完成**（Phase 12 与 P0-1~P2-2 全部完成，2026-08-21；最终回归与文档契约核查通过）

## 已完成 Checkpoint
- `phase-0-checkpoint` ~ `phase-11-checkpoint`（`f8de0b0`）：Phase 0~11 全部 PASS
- 12-A（`3605fe3`）：真实 LLM Provider 落地（config 字段 + OpenAICompatibleProvider + 对话/证据引用/Quiz/记忆 4 处切换 + 兜底；pytest 219）
- 12-B（`5f8aae4`）：一键 CI 门禁（scripts/ci.sh + ci-e2e.sh + GitHub Actions；pytest 219 / Vitest 106 / E2E 8 全绿）
- 12-C（`0c270d8`）：JWT 密钥环境化 + seed 演示警告 + conversations 创建幂等 + privacy.md + README 收口
- 12-D（工作区，待 Hermes 提交）：最终全量回归（pytest 222 / Vitest 106 / build / E2E 8 / ci.sh 54s）+ DoD 六维核查 + 交付统计
- Phase 11（多 AI 教师角色与 Persona 管理）：teacher_roles 表 + **3 延迟 FK 补齐**（students SET NULL / conversations RESTRICT / quiz_sessions RESTRICT）+ 学生端角色列表/切换（404/409）+ Admin 角色 CRUD（name 冲突 409/version 递增/启停）+ 新会话/测验默认角色 + persona 注入 provider 上下文 + 设置页角色切换前端 + §20.2 隔离（记忆/画像不绑定角色）；pytest 215 / Vitest 106 / E2E 8
- Phase 9 语音部分（9-B/9-C/9-D）已 PASS（tag `phase-9-voice-checkpoint`）

## Post-Audit 整改 Checkpoint
- P0-1（`4b39de0`）：BookDetailPage 真实详情与书库→Reader 闭环，PASS
- P0-2：真实 Embedding Provider 与知识检索相似度阈值，PASS
- P1-1：PostgreSQL Job 表驱动 Worker、PDF 解析与会话摘要/记忆任务，PASS
- P1-2：Redis 分布式锁、缓存层与进程内降级，PASS
- P1-3：ConversationSummary 读取 API 与 TeacherContext 注入闭环，PASS
- P2-1（`fc2ff48`）：Recommendation 实体、规则生成 API 与首页真实推荐，PASS
- P2-2：架构/API 契约/需求状态同步，完成

## Phase 12 目标（总控 §21）
将「功能完成」变成「可稳定比赛演示」：
- CI（GitHub Actions 或本地脚本：pytest/vitest/build/e2e 全绿门禁）
- 生产化收尾（JWT 密钥环境化、seed 密码、storage 路径、E2E 稳定、性能优化、文档）
- 最终全量回归（三端测试 + 黄金路径）
- 比赛交付检查（总控 §31 Definition of Done：Product/Engineering/AI/UX/CI-E2E/Competition）
- 隐私脱敏流程细节（12-C 已文档化：`docs/operations/privacy.md`）
- PROJECT IMPLEMENTATION COMPLETE 判定 + 最终交付报告

## Phase 12 待拆解（Hermes 规划）
- 12-A ✅ 真实 LLM Provider（9-A 落地：config 字段 + OpenAICompatibleProvider + 对话/Quiz/记忆/证据引用 4 处切换；P0-2 后真实 embedding 可选接入，mock 仍为默认兜底）
- 12-B ✅ CI 门禁（scripts/ci.sh + ci-e2e.sh + GitHub Actions）
- 12-C ✅ 生产化收尾（JWT 环境化、seed 警告、conversations 创建幂等、隐私脱敏文档、README 收口）
- 12-D ✅ 最终全量回归 + DoD 核查 + PROJECT IMPLEMENTATION COMPLETE 报告

## 当前 blocker
无（Phase 12 + Post-Audit 整改完成）

## Follow-up backlog（Phase 12 收口清单）
### 生产化
- 全局 401 自动登出未接（前端）；SSE 断流不回滚；sequence max+1 竞争
- Admin 4 偏差（enabled 放行/空文件 422/DRAFT→ARCHIVED 409/source_url 去重）
- learning_events 并发 ACTIVE 竞态 500→409
- 宿主 8000 被 DAI 占用 → 联调 8002 + VITE_API_PROXY_TARGET（文档化）
- MinIO/对象存储仍为后续生产化接入项；当前知识资源使用本地 storage 适配器
### 比赛交付
- 总控 §31 DoD 逐项核对 + 最终交付报告（12-D 已完成，见下）

## DoD 核查结果（12-D，2026-08-20）

| 维度 | 结论 | 证据 | 残余 gap（不阻塞） |
| --- | --- | --- | --- |
| Product | 满足 | 学生账号/Grade 1–12/书库/BookDetail/Reader/Continue Learning/Companion/连续对话/Screen Context/Voice/Quiz/History/Memory/画像/Knowledge/Admin/多 AI Teacher 均已实现并有 API/E2E 覆盖 | 其余 11 本书仍有占位章节内容 |
| Engineering | 部分满足 | PostgreSQL + pgvector + HNSW、AsyncSession 分层、Alembic migration、Docker Compose、信封/错误码、幂等键、Worker、Redis 缓存/锁、CI/E2E 均落地 | MinIO/对象存储仍为本地 storage 适配器 |
| AI | 满足 | Teacher Agent（persona/RAG/证据引用）、Quiz Skill、Memory Pipeline、Knowledge Retrieval、Provider factory（mock / openai_compatible）、ConversationSummary、Recommendation、Quiz/记忆失败兜底均可用 | 主对话失败按裁定直接报错不静默降级 |
| UX | 部分满足 | 路由覆盖 Home/Library/Reader/Quiz/Profile/Settings/Admin；Companion geometry 测试覆盖 1440×900 不挡内容；原型对齐 | 无自动化 1280×720 与视觉回归用例 |
| CI-E2E | 满足 | `scripts/ci.sh` 一键门禁：migration + 257 pytest + 136 Vitest + build + 8 E2E 全绿 | GitHub Actions 未在远端实测 |
| Competition | 满足 | 一键启动/验证、演示账号与 seed、默认 mock 无外部依赖、真实 LLM 可选（openai_compatible） | 演示数据量偏小（比赛前可按需扩充） |

## 交付统计（12-D）

- commit 数：60
- checkpoint tag：11 个（phase-0 ~ phase-11 + phase-9-voice）
- 后端业务表：27 张（另含 alembic_version，共 28 张实际表）
- API 端点：65 个 HTTP 端点 + 1 个 WebSocket（`/api/v1/voice/ws`），共 66 个业务 API 路由
- 代码量：后端 Python + 前端 TS/TSX 约 32,681 行；仓库总 tracked 行数约 53,314

## 已裁定决策（长期有效）
- PG18 + pgvector；uv 后端（Python 3.12）；DB 按需启动
- 级联删除 RESTRICT（审计链）；Quiz 幂等重放；ProfileInsight 5 档定性；JWT Bearer；bcrypt；PyJWT HS256
- teacher_role_id 3 处 FK 已补齐（Phase 11）；「添加记忆」无 POST（Skill 创建）
- mock embedding 64 维；P0-2 已支持 OpenAI-compatible 真实 embedding 与相似度阈值；vitest include *.test.tsx + NODE_ENV=test；E2E workers=1 + 会话归档
- **自治模式**：默认继续不询问；普通技术决策自裁决；FAIL 自动修复；6 类人工介入点（HUMAN_VERIFY 比赛彩排除外）

## 执行端
- Codex：herdr pane `w1:p6`，模型 **deepseek-v4-flash max**
- git commit/tag 由 Hermes 执行（Codex 沙箱 .git 只读）
