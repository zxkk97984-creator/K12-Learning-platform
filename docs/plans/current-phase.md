# 当前阶段状态

> 本文件由 Hermes（总控）维护，是会话恢复的权威进度来源。恢复时先读 `霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md`（Execution Baseline）再读本文件。

## 当前阶段
**Phase 1 已完成 → 待启动 Phase 2（学生身份与个人设置）**

## Phase 0 已完成 ✅（commit `87b7782`，tag `phase-0-checkpoint`）
- 仓库初始化 / Prototype Audit / Domain Model(27实体) / API Contract(66端点) / Database Design(27表) / Diagrams(8图) / Traceability(52需求) 全部 PASS

## Phase 1 已完成 ✅（commit 见下方，tag `phase-1-checkpoint`）
- 1-A 工程脚手架（React19+TS+Vite+Tailwind4）
- 1-B 设计系统 token（oklch 主题，学段适配）
- 1-C 路由 + 9 页面骨架 + topnav
- 1-D Mock Service Layer（6 接口 + 6 Mock 实现）
- 1-E Companion 桌虫（拖拽/SafeZone/持久化/7状态）
- 1-F Conversation Panel（流式/27 intent/quick actions）
- 1-G ScreenContext + Reader（选中→问霜铃链路）
- 1-H Quiz Card（选/提交/提示/修正）
- 1-I History/Profile/Settings + Home/Library（全 Mock 闭环）
- 1-J 测试（Vitest 5文件22断言 + Playwright 黄金路径 E2E 全绿）
- **Phase 1 验收标准达成**：断网无后端可完整演示核心体验（黄金路径 E2E 验证）

## Phase 2 目标（总控 §11）
引入第一个真实后端 Domain：User / StudentProfile / StudentPreference。
- 建立 FastAPI 工程
- PostgreSQL + Migration（users / student_profiles / student_preferences 三表）
- API：POST /auth/login、POST /auth/logout、GET /me、PATCH /me、GET/PATCH /me/preferences
- 前端只替换 MockStudentService，其他业务仍 Mock

## Phase 2 待拆解（Hermes 规划）
- 2-A 后端 FastAPI 工程骨架
- 2-B DB Migration（三表 + Alembic）
- 2-C Auth（login/logout + JWT）
- 2-D Student/Preference API（GET/PATCH /me、preferences）
- 2-E 前端 ApiStudentService 替换 MockStudentService
- 2-F 登录页 + 认证流 + 设置持久化
- 2-G 测试（后端 pytest + 前端）
- Phase 2 Gate

## 关键基线引用（Phase 2 必读）
- 总控 §11（Phase 2 完整定义）+ §2（Domain/API/DB 清单）
- `docs/architecture/domain-model.md`（0-C：User/StudentProfile/StudentPreference 三实体）
- `docs/contracts/api-contract.md`（0-D：auth/students 模块端点）
- `docs/architecture/database-design.md`（0-E：users/student_profiles/student_preferences 表设计）
- `docs/architecture/project-architecture.md`（后端架构）

## 当前 blocker
无

## Follow-up backlog（跨 Phase 长期）
### Phase 2 前（启动时先处理）
- 后端技术栈落地：FastAPI + SQLAlchemy2 + Alembic + Pydantic，Docker Compose 起 postgres（pgvector/pg16 与架构文档 PG18 版本对齐决策）
- docker-compose 默认口令 shuangling123 → 接真实环境前替换
- 总控文件旧路径引用（§65/203/551）修订（Hermes 决定是否动总控文件）
### Phase 1 遗留（不阻塞）
- BookDetailPage 仍是骨架（原型无此页，Phase 3 接真实 Book API 时填充）
- Playwright 未跑 --with-deps（CI 环境需补）
- spritesheet 资产缺失（Companion 用占位，Phase 11/资产接入替换）
- QuizCard submitAnswer 幂等键未传（Phase 6 接真实 API 时必须传，0-D §10.5）
- 书卡「继续」统一跳 ch3 是 mock 约定，接真实 BookProgress 后改 progress.chapter_id
### Phase 4 前
- teacher_role_id 会话内不可变确认；SSE 续传 Redis 流缓冲
### Phase 8 前
- jsonb N:M 是否提升物理关联表
### Phase 12 前
- 隐私脱敏流程细节

## 已裁定决策（长期有效）
- 级联删除 RESTRICT；Quiz 幂等重放；ProfileInsight 五档；JWT Bearer；GET /teacher-roles 归 Identity；learning_sessions 单一 ACTIVE 部分唯一索引；稳定记忆 ≥2 证据。

## 执行端
- Codex：herdr pane `w1:p6`，模型 deepseek-v4-flash max
- git commit/tag 由 Hermes 执行（Codex 沙箱 .git 只读）
