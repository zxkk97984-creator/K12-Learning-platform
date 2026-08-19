# 当前阶段状态

> 本文件由 Hermes（总控）维护，是会话恢复的权威进度来源。恢复时先读 `霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md`（Execution Baseline）再读本文件。

## 当前阶段
**Phase 7 — 长期记忆与 AI 学习画像**（Memory Domain 已完成，Memory Pipeline + ProfileInsight 待做）

> 编号对齐说明（2026-08-19）：此前推进编号与总控有偏差——已完成的「Phase 4/5」实为总控 Phase 4（Conversation）+ Phase 5（Screen Context，1-G/3-E 已覆盖）+ Phase 6（Quiz Skill，全部完成）。总控 Phase 0~6 实质全部完成。下一任务按总控 Phase 7 编号推进。

## 已完成 Checkpoint
- `phase-0-checkpoint`：仓库初始化 + 全套契约
- `phase-1-checkpoint`：React 生产 UI 全 Mock 闭环
- `phase-2-checkpoint`：学生身份与个人设置
- `phase-3-checkpoint`：书库、书籍、章节与阅读器
- `phase-4-checkpoint`：对话与记忆（SSE 流式 + 记忆状态机）
- `phase-5-checkpoint`（`5dbee00`）：练习与测验
  - 后端：Quiz 4 表 + 8 端点 + QuizSkill（tool.start/tool.result SSE 联动）；pytest 127
  - 前端：ApiQuizService 替换 + 对话内出题全链路（tool 事件 → QuizCard → 答题 → 历史）；Vitest 84
  - 修复：.tsx 测试激活（include + NODE_ENV=test + vi.hoisted + cleanup + ApiError 401 类型）+ memory-flow seed 自恢复
  - E2E 4 全绿

## Phase 6 目标（总控 §16）
语音对话（Voice）——语音输入/输出、VoiceSession、语音偏好落地。

## Phase 7 待拆解（Hermes 规划，按总控 §16）
- 7-A Memory Pipeline（LearningEvent → Evidence → MemoryCandidate → 聚合 → Stable Memory / ProfileInsight；规则版，无真实 LLM）
- 7-B ProfileInsight（profile_insights 表 + 5 档定性：偏弱/一般/较稳定/较强/仍需观察；GET /me/insights、GET /me/insights/{id}、GET /me/episodes）
- 7-C StudentEpisode（情节记忆表 + API）
- 7-D `.agent.md` 渲染（xiaoming.agent.md：Structured Memory → Renderer → Markdown View）
- 7-E 验收：学生问「为什么你觉得我比较喜欢通过例子学习？」AI 引用真实 Evidence 回答（规则版）
- 7-F 前端画像页接入 + 测试 + Gate
- 前置：Phase 2~6 已完成（身份/内容/对话/Quiz/记忆 Domain）

## Phase 8 目标（总控 §17）
Knowledge Base 与 RAG（knowledge_resources 表 + 解析管线 + 检索 + 引用）

## Phase 9 目标（总控 §18）
语音输入 / TTS（WebSocket 契约 §16 定稿实现；voice_preference 落地；STT/TTS provider 抽象）

## 当前 blocker
无

## Follow-up backlog
### Phase 2~5 遗留
- 全局 401 自动登出未接；JWT 默认密钥 dev 占位；seed 密码 demo123 仅本地
- 宿主 8000 被 DAI 项目占用，后端联调用 8002 + VITE_API_PROXY_TARGET
- BookDetailPage 仍是骨架；learning_events 并发 ACTIVE 竞态 500→409 映射待做
- legacy b1/ch3 别名解析额外请求（ch3 得 422 不影响）；tags[1] 顺序耦合 keywords
- 其余 11 本书仅 1 个占位章节；幂等键统一基建（Idempotency-Key，quiz answers 已用，全局化待做）
- SSE 断流学生消息已落库不回滚；sequence max+1 高并发竞争
- 前端「添加记忆」入口移除（0-D 无 POST /me/memories，Phase 9 Skill 创建）
### Phase 8 前
- jsonb N:M 是否提升物理关联表
### Phase 9 前
- 记忆候选 Pipeline / Memory Skill；真实 LLM Provider
### Phase 10 前
- books.created_by FK→admins 延迟补；Admin API
### Phase 11 前
- current_teacher_role_id FK 延迟补；conversations.teacher_role_id FK 延迟补；quiz_sessions.teacher_role_id FK 延迟补；TeacherRole 系统
### Phase 12 前
- 隐私脱敏流程细节

## 已裁定决策（长期有效）
- PG18 + pgvector；uv 后端（Python 3.12）；DB 按需启动
- 级联删除 RESTRICT；Quiz 幂等重放；ProfileInsight 五档；JWT Bearer；bcrypt 直调；PyJWT HS256
- learning_sessions 单一 ACTIVE 部分唯一索引；稳定记忆 ≥2 证据；测试环境 NullPool
- teacher_role_id 可空放宽（Phase 11 恢复非空+补 FK）；「添加记忆」无 POST（Skill 创建）
- vitest include *.test.tsx + env NODE_ENV=test（React.act 依赖 development 构建）
- **自治模式**：默认继续不询问；普通技术决策自裁决；FAIL 自动修复；只在 6 类人工介入点暂停

## 执行端
- Codex：herdr pane `w1:p6`，模型 **deepseek-v4-flash max**（用户 2026-08-19 切回；gpt-5.6-luna OpenAI 配额耗尽）
- git commit/tag 由 Hermes 执行（Codex 沙箱 .git 只读）
