# 当前阶段状态

> 本文件由 Hermes（总控）维护，是会话恢复的权威进度来源。恢复时先读 `霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md`（Execution Baseline）再读本文件。

## 当前阶段
**Phase 6 — 语音对话**（Phase 5 已完成，自动进入）

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

## Phase 6 待拆解（Hermes 规划，按总控 §16）
- 6-A 后端 Voice Domain（voice_sessions 表 + API：POST /voice-sessions、PATCH /voice-sessions/{id}、GET /voice-sessions、SSE 语音事件）
- 6-B 语音服务抽象（STT/TTS provider 接口 + Mock 实现；settings 切换；前端可用 mock 语音）
- 6-C 前端语音输入（录音 → STT 文本 → 对话）/ 语音输出（TTS 播放）
- 6-D 语音偏好落地（voice_preference 设置页生效）+ 测试 + Gate

## 关键基线引用（Phase 6）
- 总控 §16（Phase 6 完整定义：语音对话）
- `docs/contracts/api-contract.md`（0-D §9.4 conversations channel=VOICE、voice 相关端点；§15 SSE）
- `docs/architecture/database-design.md`（0-E voice_sessions 表定义，若有）
- `docs/architecture/domain-model.md`（0-C VoiceSession）

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
