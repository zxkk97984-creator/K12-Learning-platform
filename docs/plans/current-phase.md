# 当前阶段状态

> 本文件由 Hermes（总控）维护，是会话恢复的权威进度来源。恢复时先读 `霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md`（Execution Baseline）再读本文件。

## 当前阶段
**Phase 3 — 书库、书籍、章节与阅读器**

## 已完成的 Checkpoint（tag）
- `phase-0-checkpoint`：仓库初始化 + 全套契约（Domain 27 实体 / API 66 端点 / DB 27 表 / 8 图 / 52 需求追溯）
- `phase-1-checkpoint`：React 生产 UI 全 Mock 闭环（Vitest 22 + Playwright 黄金路径）
- `phase-2-checkpoint`：学生身份与个人设置（真实后端 JWT + PG18 + async SQLAlchemy）

## Phase 3 进度
- ✅ 3-A Content Domain（commit `90c3162`）：books/chapters/content_blocks/knowledge_points 4 表 + 5 端点，pytest 24→32
- ✅ 3-B Learning Domain（commit `da5a614`）：learning_sessions/learning_events/book_progress 3 表 + 6 端点，pytest 32→42
- 🔄 3-C 内容种子数据（seed_content.py，**验收进行中**，未 commit）：
  - 已验证：12 本书入库（title/grade/topic/minutes 与前端 mock 一致）；b1 第 3 章「训练数据」6 个 content_blocks + 5 知识点；seed 幂等
  - **待裁定的数据差异（已记录，3-D 处理）**：
    1. b1 章数：seed 建 5 章（原型 reader 目录权威），前端 mockBooks.chapter_count=7 → 3-D 替换时书卡章数显示不一致，需统一（以原型 5 章为准，或后续补 2 章）
    2. keywords 存储位置：0-E Book 表无 keywords 列，seed 把 keywords 放入 tags[1]（tags[0]=topic）→ 3-D 前端需从 tags 取关键词，且 entities/book/types.ts 的 Book.keywords 字段需适配
    3. 其余 11 本书仅 1 个占位章节（「全书导览」），点击进 reader 会空内容 → 3-E 需做「暂无正文」处理

## Phase 3 剩余
- 3-D 前端 ApiContentService 替换 MockContentService（注意上面 3 条数据适配）
- 3-E 阅读器接真实内容 + 学习事件埋点
- 3-F 测试 + Phase 3 Gate
- Phase 3 验收（总控 §12.7）：重新登录后「继续学习」恢复到上一次章节

## 关键基线引用（Phase 3）
- 总控 §12；domain-model.md §5.2/§5.3；api-contract.md §7/§8；database-design.md §3.5~§3.11；page-map/ui-behavior（阅读器）

## 当前 blocker
无（用户正在给 Codex 换模型，恢复后先 `herdr agent list` 重新确认 pane/session）

## Follow-up backlog（跨 Phase）
### Phase 2/3 遗留
- 全局 401 自动登出未接；JWT 默认密钥 dev 占位；seed 密码 demo123 仅本地
- 宿主 8000 被 DAI 项目占用，后端联调用 8002 + VITE_API_PROXY_TARGET
- BookDetailPage 仍是骨架（原型无此页）
- learning_events 并发 ACTIVE 竞态 → IntegrityError 落 500 而非 409（Phase 4+ 统一映射）
### Phase 4 前
- current_teacher_role_id FK 延迟 Phase 11 补；teacher_role_id 会话内不可变；SSE 续传 Redis 流缓冲
### Phase 8 前
- jsonb N:M 是否提升物理关联表
### Phase 12 前
- 隐私脱敏流程细节

## 已裁定决策（长期有效）
- PG18 + pgvector；uv 后端（Python 3.12）；DB 按需启动
- 级联删除 RESTRICT；Quiz 幂等重放；ProfileInsight 五档；JWT Bearer；bcrypt 直调（非 passlib）；PyJWT HS256
- learning_sessions 单一 ACTIVE 部分唯一索引；稳定记忆 ≥2 证据；测试环境 NullPool
- **自治模式**：默认继续不询问；普通技术决策自裁决；FAIL 自动修复；只在 6 类人工介入点暂停

## 执行端
- Codex：herdr pane `w1:p6`（**换模型中，恢复后重新 agent list 确认新 session id**）
- git commit/tag 由 Hermes 执行（Codex 沙箱 .git 只读）
