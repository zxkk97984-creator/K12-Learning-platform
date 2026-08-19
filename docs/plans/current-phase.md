# 当前阶段状态

> 本文件由 Hermes（总控）维护，是会话恢复的权威进度来源。恢复时先读 `霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md`（Execution Baseline）再读本文件。

## 当前阶段
**Phase 12 — 生产化、E2E、比赛交付**（Phase 11 已完成；9-A 真实 LLM Provider 挂起待接）

## 已完成 Checkpoint
- `phase-0-checkpoint` ~ `phase-11-checkpoint`（`f8de0b0`）：Phase 0~11 全部 PASS
- Phase 11（多 AI 教师角色与 Persona 管理）：teacher_roles 表 + **3 延迟 FK 补齐**（students SET NULL / conversations RESTRICT / quiz_sessions RESTRICT）+ 学生端角色列表/切换（404/409）+ Admin 角色 CRUD（name 冲突 409/version 递增/启停）+ 新会话/测验默认角色 + persona 注入 provider 上下文 + 设置页角色切换前端 + §20.2 隔离（记忆/画像不绑定角色）；pytest 215 / Vitest 106 / E2E 8
- Phase 9 语音部分（9-B/9-C/9-D）已 PASS（tag `phase-9-voice-checkpoint`）
- **9-A 真实 LLM Provider 挂起**：密钥已备（DeepSeek 官方 `api.deepseek.com` / `deepseek-chat` / 已验证连通，存于 backend/.env，gitignore 保护）；`.env` 当前 `AI_PROVIDER=mock`；待实现 config.py 字段 + OpenAICompatibleProvider + 4 处 mock→真实切换

## Phase 12 目标（总控 §21）
将「功能完成」变成「可稳定比赛演示」：
- CI（GitHub Actions 或本地脚本：pytest/vitest/build/e2e 全绿门禁）
- 生产化收尾（JWT 密钥环境化、seed 密码、storage 路径、E2E 稳定、性能优化、文档）
- 最终全量回归（三端测试 + 黄金路径）
- 比赛交付检查（总控 §31 Definition of Done：Product/Engineering/AI/UX/CI-E2E/Competition）
- 隐私脱敏流程细节（Phase 12 前 backlog）
- PROJECT IMPLEMENTATION COMPLETE 判定 + 最终交付报告

## Phase 12 待拆解（Hermes 规划）
- 12-A 真实 LLM Provider（9-A 落地：config 字段 + OpenAICompatibleProvider + 对话/Quiz/记忆/证据引用 4 处切换 + search 相似度阈值）
- 12-B CI 门禁（GitHub Actions 或本地 make ci：pytest/vitest/build/e2e）
- 12-C 生产化收尾（JWT 环境化、seed 密码、幂等键全局化、隐私脱敏说明、文档收口）
- 12-D 最终全量回归 + Gate + PROJECT IMPLEMENTATION COMPLETE 报告

## 当前 blocker
无（9-A 密钥已就绪，12-A 直接做）

## Follow-up backlog（Phase 12 收口清单）
### 生产化
- JWT 默认密钥 dev 占位 → 环境化；seed 密码 demo123/admin123 仅本地（启动警告）
- 全局 401 自动登出未接（前端）；SSE 断流不回滚；sequence max+1 竞争
- BookDetailPage 骨架；其余 11 本书 1 个占位章节
- knowledge search 无相似度阈值（12-A 真实 embedding 或阈值）
- Admin 4 偏差（enabled 放行/空文件 422/DRAFT→ARCHIVED 409/source_url 去重）
- 幂等键全局化（student 写端点；idempotency_keys 表已有）
- learning_events 并发 ACTIVE 竞态 500→409
- 宿主 8000 被 DAI 占用 → 联调 8002 + VITE_API_PROXY_TARGET（文档化）
### 隐私
- 隐私脱敏流程细节（审计链 RESTRICT + 软删已就位；正式脱敏脚本/文档）
### 比赛交付
- 总控 §31 DoD 逐项核对 + 最终交付报告

## 已裁定决策（长期有效）
- PG18 + pgvector；uv 后端（Python 3.12）；DB 按需启动
- 级联删除 RESTRICT（审计链）；Quiz 幂等重放；ProfileInsight 5 档定性；JWT Bearer；bcrypt；PyJWT HS256
- teacher_role_id 3 处 FK 已补齐（Phase 11）；「添加记忆」无 POST（Skill 创建）
- mock embedding 64 维（12-A 换真实或阈值）；vitest include *.test.tsx + NODE_ENV=test；E2E workers=1 + 会话归档
- **自治模式**：默认继续不询问；普通技术决策自裁决；FAIL 自动修复；6 类人工介入点（HUMAN_VERIFY 比赛彩排除外）

## 执行端
- Codex：herdr pane `w1:p6`，模型 **deepseek-v4-flash max**
- git commit/tag 由 Hermes 执行（Codex 沙箱 .git 只读）
