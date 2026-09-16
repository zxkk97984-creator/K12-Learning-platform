# T26 · 试用发布就绪与文档归一

> 日期：2026-09-07。任务 T26（依赖：T21–T25）。本文件为本轮发布就绪复核；对照 `tasks/plan.md` 完成标准逐条签署。当前阶段唯一验收基线见 `docs/plans/current-phase.md`（HEAD/命令/环境/结果/限制）。

## 逐条复核（对照 plan §7 完成标准）

| 完成标准 | 状态 | 证据 / 说明 |
|---|---|---|
| 学生权限边界完整 | ✅ | T02/T03 学生仅见 PUBLISHED；RAG/出题同步遵守可见性。验收 `content-visibility.md` / `content-ai-visibility.md` |
| 无跨账号 UI 残留 | ✅ | T06 账号切换隔离 + E2E `account-switch.spec` 学生↔管理员真实切换，无残留（全视口通过） |
| 全库分页/搜索正常 | ✅ | T04/T05 分页筛选契约 + 书库 UI；`pagination-backend.md` / `library-pagination-ui.md` |
| 加载错误不误导 | ✅ | T07 统一错误/重试/空态 + E2E 网络失败恢复；`error-retry-query-foundation.md` |
| 三学段样板课程图文真实 | ✅ | T12/T22 真实教学图解 + 三学段样板书，离线校验 PASS；人工审校签署待外部 |
| 学习→练习→讲解→复习→继续闭环正确 | ✅ | T13–T16 闭环；`golden-path.spec` 完整通过（学习→提问→出题→答题→历史→画像） |
| 完成记录与口径一致 | ✅ | T13 章节完成 + 完成记录口径（含 seed 演示记忆 evidence）；`chapter-completion-loop.md` |
| 手机/键盘核心操作可用 | ✅ | T17/T18 + mobile-390/820/1280 全项目回归通过；`global-nav-typography.md` / `companion-panel-quizcard.md` |
| 长对话有边界且费用指标诚实 | ✅ | T20 窗口化 + provider `last_usage` 捕获；`context-window-cost.md` |
| 后台任务可追踪 | ✅ | T21 管理后台处理状态（3s 轮询/错误重试）+ Worker 任务到终态；`admin-resource-loop.md` |
| 技术与教学验收分别有证据 | ✅ | 技术回归 `t25-regression.md`（384 BE / 258 FE / 33 E2E）；教学 offline 37 例 `teaching-eval.md`；真实模型评测待外部 |
| 当前文档与 HEAD 一致 | ✅ | 本文件 + `current-phase.md` 更新至 head `a7b8c9d0e1f2` |

## P0/P1 剩余项（无 P0 未解决）

- **P0**：无未解决项。
- **P1（已解决）**：本轮修复的 ChatComposer 重复提交、CompanionDock 遮挡主按钮、E2E 隔离库 fixture 污染（`prepareContinueLearning` 跳过空内容章节）。均已验证。
- **P1（待外部/边界）**：
  - 真实付费模型教学评测（T23）——负责人：试点负责人；影响：教学质量的真实模型结论未出，**不阻断**离线工具验证，阻断的是"真实模型质量结论"这项。
  - 人工教学审校签署（T22 样板书/题源 DRAFT）——负责人：教学负责人；影响：题源 DRAFT 未审校，**不阻断**功能，阻断"审校签署"。
  - 真实用户招募/试用（5–8 位测试者）——负责人：试点负责人；影响：本轮只备材料，未发邀请。

## 迁移兼容性与回退

- 迁移 head：`a7b8c9d0e1f2`。本轮新增迁移：
  - `a5b6c7d8e9f1`：quiz_sessions 来源 FK + `QUIZ_REVIEW_COMPLETED` 事件（回退：down 移除 FK/事件类型）。
  - `a6b7c8d9e0f1`：conversation_summaries.message_covered_count（可空列，down 删除）。
  - `a7b8c9d0e1f2`：reviewed_questions 表（check 含 PENDING/APPROVED/REJECTED/DRAFT，down 删表）。
  - 前向可升级；down 迁移已提供（`alembic downgrade`）。均为新增列/表，无破坏性改已有数据。
- **行为回退本批应用**：停后端改回固定版本（`git checkout <prev>` / 切分支）即可；前端 `pnpm build` 产物无持久副作用。
- **测试数据恢复**：`scripts/test-db.sh backup|restore`（仅隔离验收库，默认 `shuangling_audit`；拒绝恢复真实开发库 `shuangling`）。已实测备份 2.2M + 恢复 25 书。

## 本批未开放功能（如实声明，不写"全面生产就绪"）

- **真实 S3 对象存储**：仅本地/SigV4 联调，未接真实对象存储；生产如启用需实配并验证，本批**未开放真实 S3**。
- **真实语音 ASR/TTS**：Provider 化，默认 `VOICE_PROVIDER=mock/none`（明确不可用）；真实端点未验证，本批**未开放真实语音**。
- **真实付费模型**：未消费真实额度；全部用 mock provider。真实教学评测待授权与预算。
- 上述未开放项相关功能在 UI 上明示不可用/降级，不冒充可用。

## 结论

满足试用发布就绪的**代码/工具/离线验证**部分；涉及真实外部模型、人工审校、真实用户招募与真实 S3/语音的项，**如实列为待外部验收**，不自动上线。发布由负责人根据具体验收包决定。
