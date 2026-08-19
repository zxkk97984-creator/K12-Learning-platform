# 当前阶段状态

> 本文件由 Hermes（总控）维护，是会话恢复的权威进度来源。恢复时先读 `霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md`（Execution Baseline）再读本文件。

## 当前阶段
**Phase 8 — Knowledge Base 与 RAG**（Phase 7 已完成，自动进入）

## 已完成 Checkpoint（编号已对齐总控 2026-08-19）
- `phase-0-checkpoint`：仓库初始化 + 全套契约
- `phase-1-checkpoint`：React 生产 UI 全 Mock 闭环
- `phase-2-checkpoint`：学生身份与个人设置
- `phase-3-checkpoint`：书库、书籍、章节与阅读器
- `phase-4-checkpoint`：Conversation 与 Teacher Agent Runtime（SSE 流式 + 记忆 Domain）
- `phase-5-checkpoint`：Screen Context（1-G/3-E 覆盖）+ Quiz Skill 全链路（原编号 Phase 5 合并说明见 git 历史）
- `phase-7-checkpoint`（`2a3c535`）：长期记忆与 AI 学习画像
  - Memory Pipeline 规则版（事件→Evidence→Candidate→Stable Memory/ProfileInsight）
  - student_episodes/profile_insights 2 表 + pgvector 扩展（无 HNSW）
  - 4 端点（insights 列表/详情+evidence、episodes 列表/详情）+ 前端画像页（5 档定性，无数字）
  - .agent.md 渲染视图 + 「为什么这样判断」证据引用回答（§16.7 验收）
  - 意图变体修复（怎么看出/凭什么判断）+ xfail 移除
  - pytest 152 / Vitest 90 / E2E 5 全绿

## Phase 8 目标（总控 §17）
Knowledge Base 与 RAG——knowledge_resources 表 + 解析管线 + 向量检索（HNSW 落地）+ 引用。

## Phase 8 待拆解（Hermes 规划，按总控 §17）
- 8-A 后端 Knowledge Domain（knowledge_resources/knowledge_chunks 表 + pgvector HNSW 索引 + 上传/列表/详情 API + 解析管线骨架）
- 8-B RAG 检索服务（向量检索 + 关键词混合；GET /knowledge/resources 检索端点 + 对话流引用注入）
- 8-C 前端知识库页面/引用展示（若原型有；无则后端先行）
- 8-D 测试 + Gate

## 关键基线引用（Phase 8）
- 总控 §17（Phase 8 完整定义）
- `docs/contracts/api-contract.md`（0-D §12 Knowledge：GET /knowledge/resources 等）
- `docs/architecture/database-design.md`（0-E knowledge_resources 表 + student_episodes.embedding HNSW 落地）
- 现有：student_episodes.embedding 列已建（7-A），HNSW 索引 Phase 8 落地

## 当前 blocker
无

## Follow-up backlog
### 跨 Phase 遗留
- 全局 401 自动登出未接；JWT 默认密钥 dev 占位；seed 密码 demo123 仅本地
- 宿主 8000 被 DAI 项目占用，后端联调用 8002 + VITE_API_PROXY_TARGET
- BookDetailPage 仍是骨架；learning_events 并发 ACTIVE 竞态 500→409 映射待做
- legacy b1/ch3 别名解析额外请求；tags[1] 顺序耦合 keywords
- 其余 11 本书仅 1 个占位章节；幂等键全局基建待做（quiz answers 已用）
- SSE 断流学生消息已落库不回滚；sequence max+1 高并发竞争
### Phase 9 前
- 真实 LLM Provider（AI provider 接真实模型；Memory/Quiz Skill 换 LLM 生成）；语音 WebSocket（§16 定稿实现）；STT/TTS provider 抽象
### Phase 10 前
- books.created_by FK→admins 延迟补；Admin API（书/章/块/知识点 CRUD + 知识资源管理）
### Phase 11 前
- current_teacher_role_id/conversations.teacher_role_id/quiz_sessions.teacher_role_id FK 延迟补；TeacherRole 系统
### Phase 12 前
- 隐私脱敏流程细节；生产化（CI、部署、监控）

## 已裁定决策（长期有效）
- PG18 + pgvector；uv 后端（Python 3.12）；DB 按需启动
- 级联删除 RESTRICT；Quiz 幂等重放；ProfileInsight 5 档定性（无数字）；JWT Bearer；bcrypt 直调；PyJWT HS256
- learning_sessions 单一 ACTIVE 部分唯一索引；稳定记忆 ≥2 证据；测试环境 NullPool
- teacher_role_id 可空放宽（Phase 11 恢复）；「添加记忆」无 POST（Skill 创建）
- vitest include *.test.tsx + env NODE_ENV=test；E2E workers=1（共享 seed 账号串行）
- **自治模式**：默认继续不询问；普通技术决策自裁决；FAIL 自动修复；只在 6 类人工介入点暂停

## 执行端
- Codex：herdr pane `w1:p6`，模型 **deepseek-v4-flash max**（gpt-5.6-luna OpenAI 配额 2026-08-19 耗尽后切回）
- git commit/tag 由 Hermes 执行（Codex 沙箱 .git 只读）
