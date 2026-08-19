# 当前阶段状态

> 本文件由 Hermes（总控）维护，是会话恢复的权威进度来源。恢复时先读 `霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md`（Execution Baseline）再读本文件。

## 当前阶段
**Phase 5 — 练习与测验（Assessment）**（5-A~5-C 已 PASS，5-D 待执行）

## 当前 blocker ⚠️（外部资源，需用户决策）
**Codex（gpt-5.6-luna）OpenAI 配额已耗尽**（2026-08-19 触发 usage limit，提示 2026-08-20 13:45 恢复）。
- 5-D 任务书已写好（`.hermes-tasks/task-5D.md`），Codex 无法执行
- 选项：a) 充值/换账号配额 b) 换回 deepseek 模型（不受 OpenAI 配额，需用户自己换 + /clear 清历史）c) 等 8-20 恢复
- 模型切换用户自行操作（此前模式：用户切换 + Hermes 用 `herdr pane send-text w1:p6 "/clear"` 清历史解决 400 兼容问题）

## 已完成 Checkpoint
- `phase-0-checkpoint`（`87b7782`）：仓库初始化 + 全套契约
- `phase-1-checkpoint`（`497d7c2`）：React 生产 UI 全 Mock 闭环
- `phase-2-checkpoint`（`4a3f936`）：学生身份与个人设置（真实后端）
- `phase-3-checkpoint`（`553be52`）：书库、书籍、章节与阅读器
- `phase-4-checkpoint`（`df7bf63`）：对话与记忆
  - 后端：Conversation 3 表 + 6 端点；AI Provider 抽象（Mock）+ SSE 流式 7 事件；Memory 3 表 + 状态机 API
  - 前端：ApiConversationService + SSE 解析器替换 Mock；ApiMemoryService + 状态机 UI
  - 测试：后端 pytest 93 / 前端 Vitest 66 / E2E 4 全绿

## Phase 5 目标（总控 §15）
练习与测验（Assessment）——Quiz Session / Quiz Question / Quiz Answer / Interaction 全套测验生命周期。

## Phase 5 待拆解（Hermes 规划，按总控 §15）
- 5-A 后端 Quiz Domain（quiz_sessions/quiz_questions/quiz_answers/quiz_interactions 4 表 + API：POST /quiz-sessions、GET /quiz-sessions/{id}、POST /quiz-sessions/{id}/answers、GET /quiz-sessions、GET /quiz-sessions/{id}/answers、GET /quiz-sessions/{id}/interactions）
- 5-B Quiz Skill（生成题目/判定/提示——基于现有 MockQuizService 的题目数据 + 规则判定；AI 生成题目 Phase 9 接真实 LLM）
- 5-C 前端 ApiQuizService 替换 MockQuizService（测验卡/历史/详情走真实 API）
- 5-D Quiz 交互全链路（对话内出题 tool.start/tool.result + quiz 卡 + 答题 + 提示 + 历史）
- 5-E 测试 + Phase 5 Gate

## 关键基线引用（Phase 5）
- 总控 §15（Phase 5 完整定义）、§15.7（答案提交幂等）
- `docs/contracts/api-contract.md`（0-D §10 Assessment：POST /quiz-sessions、POST answers、GET answers/interactions、POST hints）
- `docs/architecture/database-design.md`（0-E §3.15 quiz_sessions、§3.16 quiz_questions、§3.17 quiz_answers、§3.18 quiz_interactions）
- `docs/architecture/domain-model.md`（0-C：QuizSession/QuizQuestion/QuizAnswer/QuizInteraction）

## 当前 blocker
无

## Follow-up backlog
### Phase 2/3/4 遗留
- 全局 401 自动登出未接；JWT 默认密钥 dev 占位；seed 密码 demo123 仅本地
- 宿主 8000 被 DAI 项目占用，后端联调用 8002 + VITE_API_PROXY_TARGET
- BookDetailPage 仍是骨架；learning_events 并发 ACTIVE 竞态 500→409 映射待做
- legacy b1/ch3 别名解析额外请求（ch3 得 422 不影响）；tags[1] 顺序耦合 keywords
- 其余 11 本书仅 1 个占位章节；幂等键统一基建（Idempotency-Key，Phase 5/6 落地）
- SSE 断流学生消息已落库不回滚；sequence max+1 高并发竞争
- 前端「添加记忆」入口移除（0-D 无 POST /me/memories，Phase 9 Skill 创建）
### Phase 8 前
- jsonb N:M 是否提升物理关联表
### Phase 9 前
- 记忆候选 Pipeline / Memory Skill；真实 LLM Provider
### Phase 10 前
- books.created_by FK→admins 延迟补；Admin API
### Phase 11 前
- current_teacher_role_id FK 延迟补；conversations.teacher_role_id FK 延迟补；TeacherRole 系统
### Phase 12 前
- 隐私脱敏流程细节

## 已裁定决策（长期有效）
- PG18 + pgvector；uv 后端（Python 3.12）；DB 按需启动
- 级联删除 RESTRICT；Quiz 幂等重放；ProfileInsight 五档；JWT Bearer；bcrypt 直调；PyJWT HS256
- learning_sessions 单一 ACTIVE 部分唯一索引；稳定记忆 ≥2 证据；测试环境 NullPool
- teacher_role_id 可空放宽（Phase 11 恢复非空+补 FK）；「添加记忆」无 POST（Skill 创建）
- **自治模式**：默认继续不询问；普通技术决策自裁决；FAIL 自动修复；只在 6 类人工介入点暂停

## 执行端
- Codex：herdr pane `w1:p6`，模型 **gpt-5.6-luna max**（用户 2026-08-19 切换）
- git commit/tag 由 Hermes 执行（Codex 沙箱 .git 只读）
- **注意**：Codex 显示 OpenAI weekly limit 剩余 <5%（2026-08-19），如耗尽需用户决策补配额或换模型
