# 当前阶段状态

> 本文件由 Hermes（总控）维护，是会话恢复的权威进度来源。恢复时先读 `霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md`（Execution Baseline）再读本文件。

## 当前阶段
**Phase 3 — 书库、书籍、章节与阅读器**（Phase 2 已完成，自动进入）

## 已完成 Checkpoint
- **phase-0-checkpoint**（`87b7782`）：仓库初始化 + 全套契约（Domain 27 实体 / API 66 端点 / DB 27 表 / 8 图 / 52 需求追溯）
- **phase-1-checkpoint**（`497d7c2`）：React 生产 UI 全 Mock 闭环（Vitest 22 + Playwright 黄金路径）
- **phase-2-checkpoint**（`4a3f936`）：学生身份与个人设置（真实后端）
  - 后端 FastAPI + uv + PG18(pgvector) + async SQLAlchemy + Alembic 三表 migration
  - Identity/Student API 6 端点 + JWT Bearer + bcrypt + seed(小明)
  - 前端 ApiStudentService 替换 MockStudentService（其余 5 Service 仍 Mock）
  - 登录页 + AuthProvider + 路由守卫 + 设置持久化
  - 测试：后端 pytest 24 / 前端 Vitest 31 / E2E 3 全绿

## Phase 3 目标（总控 §12）
把最重要的学习内容系统落地：Book / Chapter / ContentBlock / KnowledgePoint / BookProgress / LearningSession / LearningEvent。

## Phase 3 待拆解（Hermes 规划，按总控 §12）
- 3-A 后端 Content Domain（Book/Chapter/ContentBlock/KnowledgePoint 表 migration + API：GET /books、GET /books/{id}、GET /books/{id}/chapters、GET /chapters/{id}）
- 3-B 学习进度 Domain（BookProgress/LearningSession/LearningEvent 表 migration + API：POST /learning-sessions、PATCH /learning-sessions/{id}、POST /learning-events、GET /me/progress）
- 3-C 内容种子数据（把前端 Mock 的 12 本书/章节/内容块迁到后端 seed）
- 3-D 前端 ApiContentService 替换 MockContentService（书库/阅读器走真实 API）
- 3-E 阅读器接真实内容 + 学习事件埋点（TEXT_SELECTED 等）
- 3-F 测试 + Phase 3 Gate
- 验收（总控 §12.7）：重新登录后「继续学习」恢复到上一次章节

## 关键基线引用（Phase 3 必读）
- 总控 §12（Phase 3 完整定义）
- `docs/architecture/domain-model.md`（0-C：Book/Chapter/ContentBlock/KnowledgePoint/BookProgress/LearningSession/LearningEvent 七实体）
- `docs/contracts/api-contract.md`（0-D §7 Content、§8 Learning 端点）
- `docs/architecture/database-design.md`（0-E §3.5~§3.11 七张表）
- `docs/contracts/page-map.md` + `ui-behavior.md`（阅读器/书库交互）

## 当前 blocker
无

## Follow-up backlog
### Phase 2 遗留
- 全局 401 自动登出未接（token 过期页面报错不跳登录，Phase 3/4 统一）
- JWT 默认密钥 dev 占位（生产替换）；seed 密码 demo123 仅本地
- 后端端口约定：宿主 8000 被 DAI 项目占用，Phase 2 联调用 8002 + VITE_API_PROXY_TARGET
- BookDetailPage 仍是骨架（原型无此页，Phase 3 接真实 Book API 时填充）
### Phase 4 前
- teacher_role_id 会话内不可变确认；SSE 续传 Redis 流缓冲
- current_teacher_role_id FK 延迟 Phase 11 补
### Phase 8 前
- jsonb N:M 是否提升物理关联表
### Phase 12 前
- 隐私脱敏流程细节

## 已裁定决策（长期有效）
- PG18 + pgvector 统一；uv 管理后端（Python 3.12）；DB 按需启动
- 级联删除 RESTRICT；Quiz 幂等重放；ProfileInsight 五档；JWT Bearer；GET /teacher-roles 归 Identity；learning_sessions 单一 ACTIVE 部分唯一索引；稳定记忆 ≥2 证据
- bcrypt 直调（非 passlib）；PyJWT HS256；测试环境 NullPool

## 执行端
- Codex：herdr pane `w1:p6`，模型 deepseek-v4-flash max
- git commit/tag 由 Hermes 执行（Codex 沙箱 .git 只读）
- **自治模式**：默认继续，不询问 Phase/Task 切换；普通技术决策自裁决；FAIL 自动修复循环；只在 6 类人工介入点暂停
