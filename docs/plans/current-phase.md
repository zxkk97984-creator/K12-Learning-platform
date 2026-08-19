# 当前阶段状态

> 本文件由 Hermes（总控）维护，是会话恢复的权威进度来源。恢复时先读 `霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md`（Execution Baseline）再读本文件。

## 当前阶段
**Phase 1 — 前端工程化与 UI 原型 React 化（全部 Mock）**

## Phase 0 已完成（全部 PASS + 已 commit + tag）
- Task 0-A 仓库初始化 ✅
- Task 0-B Prototype Audit（page-map 121 行 + ui-behavior 392 行）✅
- Task 0-C Domain Model（27 实体 + D1~D10）✅
- Task 0-D API Contract（10 模块 66 端点 + SSE 7 事件 + WS 骨架）✅
- Task 0-E Database Design（27 表 + idempotency_keys）✅
- Task 0-F Architecture Diagrams（8 图）✅
- Task 0-G Traceability（52 需求六层追溯）✅
- 补录返工（TEXT_SELECTED + 2 错误码 + 3 微调）+ 日志清理 ✅

**Checkpoint**：commit `87b7782`，tag `phase-0-checkpoint`

## Phase 1 目标
把 `prototypes/shuangling-v3-prototype.html`（单文件 SPA 原型）转为正式 React + TypeScript 工程，**全部业务仍 Mock**，断网无后端也能完整演示产品核心体验。

## Phase 1 技术栈（总控 §10.1）
React 19 / TypeScript / Vite / React Router / Tailwind CSS / Radix Primitives / Motion / TanStack Query / Zustand / Vitest / Playwright

## Phase 1 待拆解（Hermes 需按总控 §10 拆成有限可验收 Task）
- 页面路由：/home /library /books/:bookId /learn/:bookId/:chapterId /quizzes /quizzes/:quizId /profile /profile/memories /settings
- 前端模块结构：app/ pages/ features/ entities/ shared/ mocks/
- 核心 Features：companion/ conversation/ screen-context/ quiz/ memory/ voice
- Mock Service Layer：StudentService/ContentService/ConversationService/QuizService/MemoryService/TeacherRoleService 接口 + Mock 实现
- Companion 桌虫：全局悬浮/拖动/Safe Zone/Dock/点击开 Panel/状态/路由切换常驻
- ScreenContextProvider：纯前端 Context
- 测试：Vitest + Playwright 黄金路径（Home→Library→Reader→选中→Companion→对话→Mock Quiz→答题→History→Profile）
- 验收标准（总控 §10.9）：断网、无 Backend 也能完整演示核心体验

## 关键基线引用（Phase 1 必读）
- 原型：`prototypes/shuangling-v3-prototype.html`（UI/交互唯一参考，Codex 不得擅自改成普通后台样式）
- 契约：`docs/contracts/page-map.md` + `ui-behavior.md`（0-B，页面/交互/Mock 数据形状）
- 架构：`docs/architecture/project-architecture.md` §6 前端架构 + §6.3 目录结构
- Mock 替换边界：总控 §27 + ui-behavior §4.2

## 当前 blocker
无

## Follow-up backlog（跨 Phase 长期）
### Phase 2 前
- 总控文件旧路径引用（§65/203/551）修订（Hermes 决定是否动总控文件）。
- pgvector/pg16 vs 架构文档 PG18 对齐；docker-compose 默认口令替换。
- git 身份已设本地 zxk@localhost（未 push，仅本地）。
### Phase 4 前
- teacher_role_id 会话内不可变确认；SSE 续传落地 Redis 流缓冲。
### Phase 8 前
- jsonb N:M 是否提升为物理关联表（依查询模式）。
### Phase 12 前
- 隐私脱敏流程细节定稿。

## 已裁定决策（长期有效，Hermes 记录）
- 级联删除：审计链一律 RESTRICT，隐私删除走独立脱敏。
- Quiz 同 attempt 幂等重放、答错再提交=新 attempt。
- ProfileInsight 五档以总控 §16.4 为准；禁百分比。
- 认证 JWT Bearer；GET /teacher-roles 归 Identity。
- learning_sessions 每学生单一 ACTIVE 用部分唯一索引。
- 稳定记忆最小证据量默认 ≥2 独立证据或 1 用户确认。

## 执行端
- Codex：herdr pane `w1:p6`，模型 deepseek-v4-flash max
- 注意：Codex 沙箱内 `.git` 为只读 tmpfs，git commit/tag 必须由 Hermes 执行。
