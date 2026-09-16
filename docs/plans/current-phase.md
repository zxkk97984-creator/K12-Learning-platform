# 当前阶段状态（本轮优化 T01–T26 收口）

> 本文件以 2026-09-07 工作区实际代码与本轮验收实测为准。历史阶段见 git 历史与 `docs/plans/` 其他文件（保留日期）。

## 本轮范围
本轮按 `tasks/plan.md` 执行 T01–T26 优化与回归收口，覆盖：学生内容可见性、分页/搜索/筛选、账号切换隔离、错误/重试/空态、教学图片契约与渲染、章节完成/练习/错题讲解/复习/继续学习闭环、首页/阅读器/成长页/对话面板/移动端、长对话上下文与用量口径、管理后台处理状态、样板课程与题源审校、回归矩阵/性能、试用数据与 AI 记忆控制、发布就绪与文档归一。

## 迁移（Alembic head）
- 当前 head：**`a7b8c9d0e1f2`**（本轮新增 `a5b6c7d8e9f1` quiz 来源 FK + 复习事件、`a6b7c8d9e0f1` 摘要 covered_count、`a7b8c9d0e1f2` 审校题表）。
- 隔离库 `shuangling_audit` 上 `alembic upgrade head` 通过；`alembic check` 无新增升级。

## 测试基线（本轮实测，隔离库 `shuangling_audit`）
- 后端 pytest：**384 passed / 0 failed**
- 前端 Vitest：**258 passed / 0 failed**（49 files）
- 前端 tsc --noEmit / pnpm build：通过（主 bundle 272 kB，独立 admin 18 kB，无 >500 kB 警告）
- E2E Playwright（真实后端 + Redis + Worker + content-init + seed）：**33 passed / 0 failed**（chromium 11 + mobile-390 6 + tablet-820 6 + desktop-1280 6 + 桌面附加）
- Worker：进程存活 + 至少一个任务到终态（入队 `memory_consolidation` → 轮询至 `success/failed`）

## 内容初始化
- validate_library --all：PASS（books=25, violations=0）
- import_library --all：books=25 knowledge=56 幂等导入

## 本阶段新增/修复（要点）
- 章节完成与继续学习闭环；错题讲解上下文；复习/下一步行动（§6.1；`/me/learning-next`）
- 对话面板（真实 AI 教师名）、底部导航/字号/焦点/移动端；长对话窗口化 + provider 用量捕获（`last_usage`）
- 管理后台处理状态（3s 轮询/错误重试）；Admin 独立成包（route lazy）
- Safe Markdown（列表/代码块/安全链接，原始 HTML 转义）
- 试数据与记忆控制：`pipeline` 按内容对全部状态去重，不复活被否认/遗忘记忆；`docs/requirements/pilot-data-policy.md`
- 审校题源幂等导入 + ReviewedQuestion 选择（`generation_kind="reviewed"` 优先选 APPROVED 审校题）
- 教学评测工具：`backend/evals/teaching_cases.jsonl`（37 例）+ `run_teaching_eval.py`
- 回归矩阵/性能：Playwright 手机视口项目 + 失败 trace/log 上传；ChatComposer 重复提交守卫；CompanionDock 遮挡主按钮修复；`prepareContinueLearning` 跳过空内容章节（修复 E2E 隔离库 fixture 污染）

## 尚未确认项（不写“无 blocker”）
- GitHub Actions 云端流水线未在本机实际触发（本机对标 `scripts/ci.sh`/`ci-e2e.sh`）；上传 artifact 逻辑按 workflow 代码交付。
- S3 兼容对象存储仅本地/SigV4 联调，未接真实对象存储服务。
- 真实 LLM/ASR/TTS 外部端点质量未验证（CI/E2E 用 mock provider）；真实付费模型教学评测待授权与预算。
- 人工审校签署（T22 样板书/题源）与真实用户招募（试用 5–8 位测试者）待外部授权，本轮只备材料。
- 多副本部署下 /metrics 进程内口径聚合方案待定。
