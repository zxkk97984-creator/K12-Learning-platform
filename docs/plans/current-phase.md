# 当前阶段状态

> 本文件由 Hermes（总控）维护，是会话恢复的权威进度来源。恢复时先读 `霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md`（Execution Baseline）再读本文件。

## 当前阶段
**Phase 4 — 对话与记忆**（Phase 3 已完成，自动进入）

## 已完成 Checkpoint
- `phase-0-checkpoint`（`87b7782`）：仓库初始化 + 全套契约
- `phase-1-checkpoint`（`497d7c2`）：React 生产 UI 全 Mock 闭环
- `phase-2-checkpoint`（`4a3f936`）：学生身份与个人设置（真实后端）
- `phase-3-checkpoint`（`553be52`）：书库、书籍、章节与阅读器
  - 后端：Content Domain 4 表 + 5 端点；Learning Domain 3 表 + 6 端点 + PUT progress upsert；内容种子 12 本书
  - 前端：ApiContentService 替换 Mock；Reader 学习事件埋点 + LearningSession + 继续学习恢复
  - 测试：后端 pytest 57 / 前端 Vitest 45 / E2E 3 全绿

## Phase 4 目标（总控 §13）
对话（Conversation）与记忆（Memory）——AI 教学对话、记忆沉淀、AI 助手接口。

## Phase 4 待拆解（Hermes 规划，按总控 §13）
- 4-A 后端 Conversation Domain（conversations/messages 表 + API：POST /conversations、GET /conversations/{id}/messages、GET /conversations）
- 4-B 后端 AI 服务抽象（LLM provider 接口 + 路由：POST /ai/ask、POST /ai/summarize、POST /ai/quiz）
- 4-C 记忆 Domain（memory_entries/memory_evidence 表 + API：GET /memories、POST /memories、PATCH /memories/{id}、DELETE）
- 4-D 前端 ApiConversationService 替换 Mock（对话面板走真实 API）
- 4-E 前端 AI 助手接入（快速提问/讲解接真实 LLM 或 mock 响应切换）
- 4-F 记忆前端 + 测试 + Phase 4 Gate

## 关键基线引用（Phase 4）
- 总控 §13（Phase 4 完整定义：对话与记忆）
- `docs/contracts/api-contract.md`（0-D §9 Conversation、§10 AI、§11 Memory）
- `docs/architecture/database-design.md`（0-E §3.12 conversations、§3.13 messages、§3.14 memory_entries、§3.15 memory_evidence）
- `docs/architecture/domain-model.md`（0-C：Conversation/Message/MemoryEntry/MemoryEvidence）
- 总控 §16~§22（Phase 5-11 预览）

## 当前 blocker
无

## Follow-up backlog
### Phase 2/3 遗留
- 全局 401 自动登出未接；JWT 默认密钥 dev 占位；seed 密码 demo123 仅本地
- 宿主 8000 被 DAI 项目占用，后端联调用 8002 + VITE_API_PROXY_TARGET
- BookDetailPage 仍是骨架（Phase 3 未填充，原型无此页，后续接 Book API 时填）
- learning_events 并发 ACTIVE 竞态 → IntegrityError 落 500 而非 409（映射待做）
- legacy b1/ch3 别名解析会额外请求书库/章节列表（resolveBookId/resolveChapterId fallback 请求 ch3 得 422，不影响功能）
- tags[1] 顺序变化会导致 keywords 为空（3-C 裁定固有耦合，Phase 8 tags 语义变化时同步）
- 其余 11 本书仅 1 个占位章节（「全书导览」），点击进 reader 内容为空（预期，3-E 已处理「暂无正文」）
### Phase 4 内
- 记忆证据链（stable 记忆 ≥2 证据）；SSE 续传 Redis 流缓冲；teacher_role_id 会话内不可变
### Phase 8 前
- jsonb N:M 是否提升物理关联表
### Phase 10 前
- books.created_by FK→admins 延迟补；current_teacher_role_id FK 延迟补
### Phase 12 前
- 隐私脱敏流程细节

## 已裁定决策（长期有效）
- PG18 + pgvector；uv 后端（Python 3.12）；DB 按需启动
- 级联删除 RESTRICT；Quiz 幂等重放；ProfileInsight 五档；JWT Bearer；bcrypt 直调（非 passlib）；PyJWT HS256
- learning_sessions 单一 ACTIVE 部分唯一索引；稳定记忆 ≥2 证据；测试环境 NullPool
- **自治模式**：默认继续不询问；普通技术决策自裁决；FAIL 自动修复；只在 6 类人工介入点暂停

## 执行端
- Codex：herdr pane `w1:p6`，模型 **gpt-5.6-luna max**（2026-08-19 用户切换；deepseek 旧会话历史 400 已用 /clear 解决）
- git commit/tag 由 Hermes 执行（Codex 沙箱 .git 只读）
- **注意**：Codex 显示 OpenAI weekly limit 剩余 <5%（2026-08-19 提示），如耗尽需用户决策补配额或换模型
