# 隐私与数据脱敏流程说明

> 状态：Phase 12 文档收口（仅流程说明，不包含可执行删除脚本；真实删除属产品运营审批流程）。

## 1. 目的

本文件说明平台在「审计链保留」与「用户数据脱敏」之间的边界：业务数据以软删为主，审计链通过 `RESTRICT` 外键防止被连带物理删除；`idempotency_keys` 是唯一允许物理删除的基础设施表。

## 2. 审计链 RESTRICT 总览

数据库设计以 `docs/architecture/database-design.md`（0-E）为权威。现有模型的关键外键均使用 `ondelete="RESTRICT"`，确保删除父行时若存在子行则数据库拒绝删除，从而保留完整审计链：

- 学生域：`student_profiles` 被 conversations、learning_sessions、quiz_sessions、memories、insights、episodes 等 RESTRICT 引用。
- 对话域：`conversations` 被 messages、summaries、quiz_sessions 等 RESTRICT 引用。
- 测验域：`quiz_sessions` / `quiz_questions` 被 answers、interactions 等 RESTRICT 引用。
- 内容域：`books` / `chapters` / `content_blocks` / `knowledge_points` 之间以及上传/资源表均为 RESTRICT 链。
- 管理域：`admins` 被 books.created_by、knowledge_resources.uploaded_by 等 RESTRICT 引用。

含义：任何「删除父记录」的操作都会因审计子记录存在而被数据库拒绝；正常运营路径必须使用软删状态，而不是物理 `DELETE`。

## 3. 软删语义对照

| 数据 | 软删/停用字段 | 语义 |
| --- | --- | --- |
| users | `status`（ACTIVE 等） | 账号停用后不再允许登录/继续产生业务数据 |
| teacher_roles | `enabled=false` | 角色下架，学生端不再展示，历史会话归属保留 |
| conversations | `status=DELETED`（含 ARCHIVED） | 对话对用户不可见，消息/摘要/测验记录仍保留审计 |
| student_memories | `status=REMOVED` / `SUPERSEDED` | 记忆从画像中消失，原记录保留证据链 |
| profile_insights | `status=SUPERSEDED` + `valid_until` | 旧画像结论失效但仍可追溯 |
| books / knowledge_resources | `status=ARCHIVED` / `FAILED` 等 | 下架或失败状态，不删除源文件与审计记录 |

## 4. 脱敏流程（5 步）

1. **账号停用**：将用户/管理员账号置为停用状态（`users.status`、`admins.enabled=false`），阻止继续登录与新数据写入。
2. **数据软删**：对业务数据执行软删（conversations → `DELETED`、memories → `REMOVED`、insights → `SUPERSEDED` 等），不执行物理删除。
3. **审计保留**：保留 messages、learning_events、memory_evidence、quiz answers/interactions、episodes 等审计链记录；RESTRICT 外键保证它们不会被误删。
4. **物理清除审批**：若确有物理清除需求，需由运营/合规审批后，按依赖顺序（先子表后父表）在维护窗口内执行，并记录审批单号、执行人与时间。
5. **日志与缓存清理**：清除 Redis 缓存、本地/对象存储中的临时文件与日志中的个人标识（或按保留策略过期）。

## 5. idempotency_keys 唯一物理删除例外

`idempotency_keys`（0-E §3.28）是幂等基础设施表，不承载业务审计价值：

- 每条记录有 24 小时 `expires_at`；
- 过期记录允许物理删除（清理脚本/维护任务）；
- 删除仅限该表，不影响任何业务审计链；
- 删除时不需要走第 4 步业务数据审批流程。

## 6. 本阶段边界

本文件只定义流程与语义，不实现真实删除脚本。比赛演示环境不执行任何物理删除；如需真实脱敏工具，应在后续生产化阶段单独设计与验收。
