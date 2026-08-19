# 当前阶段状态

> 本文件由 Hermes（总控）维护，是会话恢复的权威进度来源。恢复时先读 `霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md`（Execution Baseline）再读本文件。

## 当前阶段
**Phase 9 — 语音输入 / TTS + 真实 LLM Provider**（Phase 8 已完成，自动进入）

## 已完成 Checkpoint
- `phase-0-checkpoint` ~ `phase-8-checkpoint`（`eb3637d`）：Phase 0~8 全部 PASS
- Phase 8（Knowledge Base 与 RAG）：
  - knowledge_resources/knowledge_chunks 2 表 + 2 处 HNSW 索引（episodes 补）
  - mock embedding（64 维确定性）+ Ingestion CLI（Parser→Chunk→Embedding→入库，幂等）
  - 4 端点（resources 列表/详情/chunks ADMIN_ONLY + search STUDENT，D9 source 溯源）
  - RAG 注入对话流（retrieve + screen_context → TeacherContext → 引用来源回复）
  - pytest 175 / Vitest 90 / E2E 5 全绿
  - 修复：golden-path beforeAll 归档遗留 ACTIVE 会话（消除 .last() 偶发失败）

## Phase 9 目标（总控 §18 + 0-D §16）
语音输入 / TTS：
- WebSocket 契约定稿实现（/api/v1/voice/ws?conversation_id&token，JSON 帧，audio_chunk/audio_end/cancel/ping ↔ state/partial/final/error/pong）
- 状态机（IDLE→LISTENING→THINKING→SPEAKING→IDLE，barge-in）
- STT/TTS provider 抽象 + Mock 实现；voice_preference 落地
- 真实 LLM Provider（本 Phase 或独立任务：AI provider 接真实模型，Memory/Quiz Skill 换 LLM 生成；注意 mock embedding 检索质量 + 相似度阈值）
- final 文本写入 Conversation（type=TEXT）走同一 SSE/Agent 流程（架构 §38）

## Phase 9 待拆解（Hermes 规划）
- 9-A 真实 LLM Provider（settings 配置 + OpenAI 兼容 provider；Memory/Quiz Skill/证据回答换 LLM 生成；search 相似度阈值）——注意 Codex 执行端当前为 deepseek 中转，真实 LLM 接入需用户提供密钥/端点（外部资源，可能触发人工介入）
- 9-B 语音 WebSocket 定稿（ws 连接/帧/状态机/STT mock + TTS mock；voice_sessions 表）
- 9-C 前端语音（录音 → WS → STT → 对话；TTS 播放；voice-overlay 状态动画）
- 9-D 语音偏好落地（voice_preference 设置生效）+ 测试 + Gate

## 当前 blocker
无（9-A 若需真实 LLM 密钥属外部资源，届时暂停相关路径并询问）

## Follow-up backlog
### 跨 Phase 遗留
- 全局 401 自动登出未接；JWT 默认密钥 dev 占位；seed 密码 demo123/admin123 仅本地
- 宿主 8000 被 DAI 项目占用，后端联调用 8002 + VITE_API_PROXY_TARGET
- BookDetailPage 仍是骨架；learning_events 并发 ACTIVE 竞态 500→409 映射待做
- legacy b1/ch3 别名解析额外请求；tags[1] 顺序耦合 keywords
- 其余 11 本书仅 1 个占位章节；幂等键全局基建待做
- SSE 断流学生消息已落库不回滚；sequence max+1 高并发竞争
- **knowledge search 无相似度阈值**（纯文本无命中仍返回 top-N，9-A 真实 embedding 时加）
### Phase 10 前
- books.created_by FK→admins 延迟补；Admin API（书/章/块/知识点 CRUD + 知识资源上传 HTTP 端点 + require_admin 已有）
### Phase 11 前
- current_teacher_role_id/conversations.teacher_role_id/quiz_sessions.teacher_role_id FK 延迟补；TeacherRole 系统（角色列表/切换/Persona）
### Phase 12 前
- 隐私脱敏流程细节；生产化（CI、部署、监控、比赛交付）

## 已裁定决策（长期有效）
- PG18 + pgvector；uv 后端（Python 3.12）；DB 按需启动
- 级联删除 RESTRICT；Quiz 幂等重放；ProfileInsight 5 档定性（无数字）；JWT Bearer；bcrypt 直调；PyJWT HS256
- learning_sessions 单一 ACTIVE 部分唯一索引；稳定记忆 ≥2 证据；测试环境 NullPool
- teacher_role_id 可空放宽（Phase 11 恢复）；「添加记忆」无 POST（Skill 创建）
- mock embedding 64 维（Phase 9 换真实）；vitest include *.test.tsx + NODE_ENV=test；E2E workers=1 串行 + golden-path 归档遗留会话
- **自治模式**：默认继续不询问；普通技术决策自裁决；FAIL 自动修复；只在 6 类人工介入点暂停（真实 LLM 密钥/端点=外部资源类）

## 执行端
- Codex：herdr pane `w1:p6`，模型 **deepseek-v4-flash max**（gpt-5.6-luna OpenAI 配额 2026-08-19 耗尽后切回；中转站可能不支持部分 tool 调用——遇 400 先报 Hermes 再处理）
- git commit/tag 由 Hermes 执行（Codex 沙箱 .git 只读）
