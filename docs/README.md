# 文档索引（docs）

> ⚠️ **2026-09-16 更新**：本目录新增了一套**以当前代码为唯一事实源**重建的维护文档（`00`–`16` + `AGENT_CONTEXT.md`）。
> 下方「历史基线文档」中的部分内容**已与代码不一致**，其漂移已在 `15-project-status.md` §3 逐条登记。
> **新加入者请从 `AGENT_CONTEXT.md` 开始读。**

---

## 一、维护文档（当前事实源，2026-09-16 生成）

| 文件 | 内容 |
| --- | --- |
| **[AGENT_CONTEXT.md](./AGENT_CONTEXT.md)** | **★ 新 Agent / 新人的第一份文件**：项目是什么、技术栈、核心目录、数据流、架构约定、完成度、最大缺口、启动与测试方式、不能改的设计、已知遗留 |
| [00-project-overview.md](./00-project-overview.md) | 项目定位、用户角色、技术栈（声明 vs 实际）、核心价值链、产品边界、术语表 |
| [01-repository-map.md](./01-repository-map.md) | 真实目录地图：每个目录的职责、核心/辅助/已废弃、模块依赖关系、Git 状态 |
| [02-architecture.md](./02-architecture.md) | 实际架构（分层、横切关注点、数据流、8 条易被误判的事实） |
| [03-business-flows.md](./03-business-flows.md) | 11 条业务流程的逐跳追踪与真实性判定 |
| [04-frontend.md](./04-frontend.md) | 路由、页面清单、API 层、mock 真实状态、状态管理、死代码、测试缺口 |
| [05-backend.md](./05-backend.md) | 应用入口、配置、11 个领域模块、AI 层、基础设施、后台任务、运维脚本 |
| [06-database.md](./06-database.md) | 32 表、迁移链、三方漂移对账、向量列、级联风险、seed、14 条风险登记 |
| [07-api.md](./07-api.md) | 71 HTTP + 1 WS 端点清单（含 Auth / 前端调用 / 测试覆盖）、9 个未被前端使用的端点、不一致项 |
| [08-ai-system.md](./08-ai-system.md) | AI/Agent/RAG/Memory 全链路追踪与真实性判定（**最重要的短板分析**） |
| [09-runtime-and-deployment.md](./09-runtime-and-deployment.md) | 实际运行状态、三条启动路径、bootstrap 顺序、环境变量、11 条配置漂移、部署能力缺口 |
| [10-testing.md](./10-testing.md) | 实测数字、CI 恒红的根因、测试基础设施缺失、覆盖率缺口、「测试剧场」清单 |
| [11-feature-status.md](./11-feature-status.md) | 逐功能完成度审计（前端/后端/DB/联通/测试/Mock/缺口/证据） |
| [12-known-issues.md](./12-known-issues.md) | **问题分级 P0–P3**：现象 → 代码证据 → 影响 → 根因 → 推荐修复方向 |
| [13-technical-debt.md](./13-technical-debt.md) | 技术债地图（10 个分类 × 已确认/潜在风险/尚未确认） |
| [14-development-guide.md](./14-development-guide.md) | 开发指南：环境、启动、**测试前必读**、代码约定、常见任务、排障、提交清单 |
| [15-project-status.md](./15-project-status.md) | **项目现状报告**：阶段判定与证据、10 维度评估、Documentation Drift Report、时间线恢复 |
| [16-roadmap-analysis.md](./16-roadmap-analysis.md) | **方向纠正分析**（Keep/Fix/Simplify/Complete/Reconsider）+ **Phase A–D Roadmap** |
| [17-codelab.md](./17-codelab.md) | **CodeLab（在线编程教学工具）**：能力范围、完整调用链、从 dai 复用了什么、AI 评分口径、安全边界、配置、如何新增任务、明确推迟的能力 |

### 原始审计报告（`.audit/`，非 docs 目录）

本次全量考古的底层证据（共约 3600 行）：

| 文件 | 行数 | 内容 |
| --- | --- | --- |
| `../.audit/A-ai-subsystem.md` | 738 | AI/Provider/RAG/Memory/Quiz/Jobs 完整代码考古 + 组件状态表 |
| `../.audit/B-frontend.md` | 606 | 前端逐文件审计、页面表、死代码清单、未使用端点 |
| `../.audit/C-database.md` | 1353 | 32 表列级清单、23 迁移目录、三方漂移对账、风险登记 |
| `../.audit/D-testing.md` | 870 | 测试实跑结果、CI 根因分析、覆盖率缺口、测试剧场 |

---

## 二、历史基线文档（保留，但**勿直接当事实**）

| 子目录 | 用途 | 状态 |
| --- | --- | --- |
| `requirements/` | 产品需求基线 | 需求意图仍有效；实现口径以 `11-feature-status.md` 为准 |
| `architecture/` | 架构设计基线 | **整体仍与代码高度一致**（已含"落地状态"标注）；`diagrams.md` 仍写 PydanticAI，与 `project-architecture.md:529` 裁定矛盾 |
| `contracts/` | API / 页面 / UI 契约 | ⚠️ `api-contract.md:390` 的端点总数写 68，**实际 71**；缺 3 个新端点 |
| `plans/` | 开发实施计划 | ⚠️ `current-phase.md` 的测试数字（384/258/33）**实测不可复现**（干净库 1 红） |
| `acceptance/` | 验收记录 | 目录基本为空 |

### 具体入口

- 执行总控文件（仓库根）：`霜铃_V3_Hermes-Codex_多Agent协同开发总路线.md` —— Phase 0–12 定义，历史基线
- 当前轮次入口：`../tasks/plan.md` + `../tasks/todo.md` + `../tasks/acceptance/`（⚠️ **均未提交到 git**）
- 产品需求总纲：`requirements/产品需求总纲.md`
- 项目架构设计：`architecture/project-architecture.md`
- 详细开发实施路线图：`plans/development-roadmap.md`
- UI/交互原型：`../prototypes/shuangling-v3-prototype.html`（非生产代码）

---

## 三、阅读顺序建议

**新 Agent / 新人**：`AGENT_CONTEXT.md` → `15-project-status.md` → `12-known-issues.md` → `16-roadmap-analysis.md` → 按需深入具体领域文档。

**要改某一块代码**：先读 `14-development-guide.md` 的约定与排障，
再读 `02-architecture.md` 与对应的 `04`/`05`/`06`/`08`，最后查 `.audit/` 中该领域的完整报告。

**要做技术决策**：`15-project-status.md`（现状）→ `13-technical-debt.md`（债务）→ `16-roadmap-analysis.md`（Reconsider 三问）。
