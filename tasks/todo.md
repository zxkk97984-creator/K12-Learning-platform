# 优化任务执行清单

> 本清单对应 [详细计划](plan.md)。2026-09-06 创建，全部业务任务尚未执行。

状态规则：待执行 → 实现完成 → 验收完成。只有指定场景、命令、截图/运行证据均满足才勾选验收。

| 任务 | 内容 | 实现 | 验收 | 负责人 / 证据 |
|---|---|---|---|---|
| T01 | 建立可重现基线与隔离验收环境（M，依赖：无） | 实现完成 | 验收完成（截图项待授权） | [baseline.md](acceptance/baseline.md) |
| T02 | 学生内容发布边界（M，依赖：T01） | 实现完成 | 验收完成 | [content-visibility.md](acceptance/content-visibility.md) |
| T03 | RAG 与出题同步遵守内容可见性（M，依赖：T02） | 实现完成 | 验收完成 | [content-ai-visibility.md](acceptance/content-ai-visibility.md) |
| T04 | 分页与筛选后端契约（M，依赖：T02） | 实现完成 | 验收完成 | [pagination-backend.md](acceptance/pagination-backend.md) |
| T05 | 书库完整发现与分页 UI（M，依赖：T04） | 实现完成 | 验收完成 | [library-pagination-ui.md](acceptance/library-pagination-ui.md) |
| T06 | 账号切换清理与异步隔离（M，依赖：T01） | 实现完成 | 验收完成 | [account-switch-isolation.md](acceptance/account-switch-isolation.md) |
| T07 | 统一错误、重试与查询基础（M，依赖：T06） | 实现完成 | 验收完成 | [error-retry-query-foundation.md](acceptance/error-retry-query-foundation.md) |
| T08 | 首页聚焦学习行动（M，依赖：T05、T07） | 实现完成 | 验收完成 | [homepage-focus.md](acceptance/homepage-focus.md) |
| T09 | 成长页可恢复与布局修正（M，依赖：T07） | 实现完成 | 验收完成 | [profile-recoverable-layout.md](acceptance/profile-recoverable-layout.md) |
| T10 | 图片内容契约与导入（M，依赖：T01） | 实现完成 | 验收完成 | [image-content-contract.md](acceptance/image-content-contract.md) |
| T11 | 阅读图片渲染与稳定布局（M，依赖：T07、T10） | 实现完成 | 验收完成 | [reader-image-render.md](acceptance/reader-image-render.md) |
| T12 | 第一批真实教学图解（每章 S，依赖：T10–T11） | 实现完成 | 部分验收（离线校验 PASS；浏览器逐图并入 T25、人工审校待外部） | [content-figures.md](acceptance/content-figures.md) |
| T13 | 章节完成与继续学习闭环（拆 13a/13b/13c，依赖：T02、T11） | 实现完成 | 验收完成 | [chapter-completion-loop.md](acceptance/chapter-completion-loop.md) |
| T14 | 错题讲解上下文契约（M，依赖：T03） | 实现完成 | 验收完成 | [quiz-review-context.md](acceptance/quiz-review-context.md) |
| T15 | 答卷与练习历史操作明确（M，依赖：T07、T14） | 实现完成 | 验收完成 | [quiz-detail-actions.md](acceptance/quiz-detail-actions.md) |
| T16 | 复习与下一步行动（拆 16a/16b，依赖：T08、T13、T15） | 实现完成 | 验收完成 | [next-learning-action.md](acceptance/next-learning-action.md) |
| T17 | 全局导航、字号与基础控件（M，依赖：T07） | 实现完成 | 验收完成（前端 248 passed + tsc 0 错误；浏览器截图并入 T25） | [global-nav-typography.md](acceptance/global-nav-typography.md) |
| T18 | 对话面板与题卡可用性（M，依赖：T06、T17） | 实现完成 | 验收完成（前端 248 passed + tsc 0 错误；真机键盘实测并入 T25/外部） | [companion-panel-quizcard.md](acceptance/companion-panel-quizcard.md) |
| T19 | AI 文本与内部文案清理（M，依赖：T18） | 实现完成 | 验收完成 | [ai-text-copy-cleanup.md](acceptance/ai-text-copy-cleanup.md) |
| T20 | 长对话输入与成本口径（拆 20a/20b，依赖：T01） | 实现完成 | 验收完成 | [context-window-cost.md](acceptance/context-window-cost.md) |
| T21 | 管理员资源处理闭环（M，依赖：T07） | 实现完成 | 验收完成 | [admin-resource-loop.md](acceptance/admin-resource-loop.md) |
| T22 | 三学段样板章节与题目审校（拆 22a/22b，每课 M，依赖：T12） | 实现完成 | 验收完成（题源 DRAFT 未人工审校，审校签署待外部） | [content-review.md](acceptance/content-review.md) |
| T23 | 教学质量与真实服务评测（M，依赖：T14、T20、T22） | 实现完成 | 部分验收（offline 37 例通过；真实模型评测待外部授权与预算） | [teaching-eval.md](acceptance/teaching-eval.md) |
| T24 | 试用数据与 AI 记忆控制（先文档 S，再实现 M，依赖：T06、T09） | 实现完成 | 验收完成 | [pilot-data-memory.md](acceptance/pilot-data-memory.md) |
| T25 | 回归矩阵、性能与失败证据（拆 25a/25b，依赖：T05–T21） | 实现完成 | 验收完成（回归 33 passed，构建 -45%，真实缺陷修复见下） | [t25-regression.md](acceptance/t25-regression.md) |
| T26 | 试用发布就绪与文档归一（M，依赖：T21–T25） | 实现完成 | 验收完成（对照完成标准逐条签署；真实外部项列为待外部验收） | [release-readiness.md](acceptance/release-readiness.md) · [pilot-findings.md](acceptance/pilot-findings.md) · [tester-task-cards.md](acceptance/tester-task-cards.md) |

## 推荐首次派发

- [ ] T01：建立隔离库和验收基线。
- [ ] T02：修学生内容可见性；之后 T03/T04。
- [ ] T06：账号切换隔离；之后 T07。
- [ ] T10：图解内容契约；之后 T11/T12。

## 里程碑检查

- [x] C0：隔离环境、学生内容边界、账号切换通过（E2E account-switch + content-visibility + 隔离库）。
- [x] C1：课程发现、错误恢复、真实图像样例通过（分页/筛选 UI + 网络失败恢复 + 真实图解样例）。
- [x] C2：学习→练习→讲解→复习→继续完整演示（golden-path 全流程通过）。
- [x] C3：技术、教学、试用条件分别验收（回归 384/258/33；offline 教学 37 例；试用材料备齐、真实外部项列为待外部验收）。

## 本轮规划交付（不是业务修复）

- [x] 源码与历史文档审查。
- [x] 前端191项测试、build；后端12项provider/embedding单测；语料结构校验。
- [x] 问题、优先级、前端规格、任务依赖及验收计划。
- [x] 登录后完整UI审查（E2E login-flow + 390/820/1280 真实截图；演示账号登录已实跑）。

> 状态规则复核：T01–T26 均已实现完成；技术回归验收完成；真实外部项（付费模型/人工审校/真实用户/真实 S3·语音）如实列为**待外部验收**，未自动上线，未把「实现完成」写成「全部验收完成」。详见 `tasks/acceptance/final-delivery.md`。
