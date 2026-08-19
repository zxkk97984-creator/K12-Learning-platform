# 当前阶段状态

> 本文件由 Hermes（总控）维护，是会话恢复的权威进度来源。恢复时先读 `霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md`（Execution Baseline）再读本文件。

## 当前阶段
**Phase 0 — 项目初始化与基线固化**

## 已完成
- Task 0-A「仓库初始化」：**PASS**
- Task 0-B「Prototype Audit」：**PASS**
- Task 0-C「Domain Model」：**PASS**（27 实体）
- Task 0-D「API Contract」：**PASS**（66 端点）
- Task 0-E「Database Design」：**PASS**（27 表 + idempotency_keys）
- 验收时间：2026-08-19

## 进行中
- Task 0-F「Architecture Diagrams」（进行中）

## 待办（Phase 0 剩余）
- Task 0-G：Traceability
- Phase 0 Gate

## 下一阶段
Phase 1 — 前端工程化与 UI 原型 React 化（全部 Mock）

## 当前 blocker
无

## Gate 前返工清单（0-F/0-G 完成后，一次性让 Codex 修正）
### 0-C domain-model.md 补录
1. LearningEvent.event_type 补 `TEXT_SELECTED`（总控 §12.5，0-D/0-E 已先行支持）。
### 0-D api-contract.md 补录
2. 错误码表补 `LEARNING_SESSION_INVALID_STATUS`、`RECOMMENDATION_INVALID_STATUS`（正文已用通用 409）。
### 0-E database-design.md 微调（Hermes 已裁定）
3. idempotency_keys 作用域扩展为 `actor_id + actor_type`（覆盖 Admin 端点）。
4. conversations 移除冗余列 `conversation_summary`（由 JOIN conversation_summaries 提供）。
5. book_progress.student_id 的 ON DELETE 由 CASCADE 改为 RESTRICT（与其它学生数据一致）。

## 已裁定决策（Hermes 记录）
- 级联删除：审计链（LearningEvent/QuizSession/Messages）一律 RESTRICT，隐私删除走独立脱敏流程，不级联物理删。
- N:M jsonb vs 物理关联表：MVP 用 jsonb，Phase 8 若成瓶颈再提升。
- learning_sessions 每学生单一 ACTIVE 用部分唯一索引（DB 级不变量）。
- 认证 JWT Bearer；Quiz 同 attempt 幂等重放、答错再提交=新 attempt。
- ProfileInsight 五档以总控 §16.4 为准。
- GET /teacher-roles 归 Identity（Phase 11 实现）。
- SSE 续传 Phase 4 落地 Redis 流缓冲（30s）。

## Follow-up backlog（按 Phase 归口，不阻塞）
### Phase 2 前
- 总控旧路径引用（§65/203/551）修订。
- pgvector/pg16 vs 架构文档 PG18 对齐；docker-compose 口令替换。
### Phase 4 前
- teacher_role_id 会话内不可变确认。
### Phase 7 前
- 稳定记忆最小证据量（默认 ≥2 独立证据或 1 用户确认）。
### Phase 11 前
- StudentPreference 版本化、quiz_kind/status 细分。

## 最新 commit
尚未 commit（Phase 0 全部验收后统一提交，消息：`docs: establish V3 architecture and product contracts`）

## 执行端
- Codex：herdr pane `w1:p6`，模型 deepseek-v4-flash max
- 注意：Codex 沙箱内 `.git` 为只读 tmpfs，git commit 必须由 Hermes 执行。
