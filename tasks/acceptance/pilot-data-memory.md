# T24 · 试用数据与 AI 记忆控制

> 日期：2026-09-07。任务 T24（先文档 S，再实现 M，依赖：T06、T09）。

## 已解决的用户问题与行为变化

用户否认/遗忘一条学习记忆后，后台记忆任务可能以同内容**无条件再复活**一条新的 ACTIVE 记忆，导致"删了又回来"；且操作文案与真实语义可能不一致。

- **记忆排除（实现）**：`memory/pipeline.py` 的"按内容去重"从仅查 `status='ACTIVE'` 改为**按内容对全部状态去重**：同内容记忆已为 `DISPUTED/REMOVED/SUPERSEDED` 时**不再新建 ACTIVE 行**（仅当它仍是 ACTIVE 才累加证据），彻底阻断"遗忘后被无条件复活"。
- **上下文排除（既有核查确认）**：`teacher_context.py` 与 `agent_md.py` 只读 `status='ACTIVE'` 记忆与 `ProfileInsight.status='ACTIVE'`；DISPUTED/REMOVED/SUPERSEDED 记忆中不再进入新的教师上下文。
- **证据派生路径受控**：仅 ACTIVE 记忆累加证据；被否认记忆不因证据重新出现而复活。
- **数据政策文档**：新增 `docs/requirements/pilot-data-policy.md`，记录各数据类收集目的/可见范围/保留期负责人/删除遗忘实际效果/导出不含他人数据与密钥；无既定保留期时明确由负责人决策，**不自行编造天数**；正式删除另走受控确认；对外试用前置（目标年龄/监护/知情/退出）由负责人确定。

**验收对应**：①操作文案与真实语义一致（遗忘/否认即真正不再被引用）；②遗忘后新对话不再引用该记忆，证据派生路径受控；③试用说明讲清数据用途与退出流程，正式删除另走受控确认。

## 修改文件

| 文件 | 改动 |
|---|---|
| `backend/app/modules/memory/pipeline.py` | 按内容对全部状态去重，不复活被否认/遗忘记忆 |
| `backend/app/modules/conversation/teacher_context.py` | （核查）仅读 ACTIVE 记忆 |
| `backend/app/modules/memory/agent_md.py` | （核查）仅读 ACTIVE 记忆/洞察 |
| `docs/requirements/pilot-data-policy.md`（新增） | 数据分类/目的/可见/保留/删除/遗忘/导出约束 |
| `backend/tests/test_memory_exclusion.py`（新增） | 2 项：非 ACTIVE 不进 TeacherContext、pipeline 不复活被否认内容 |

## 回归测试

```bash
cd backend && DATABASE_URL=postgresql+asyncpg://shuangling:shuangling@localhost:5432/shuangling_audit \
  uv run pytest tests/test_memory_exclusion.py tests/test_memory_api.py tests/test_memory_pipeline.py -q
# → 20 passed
# 后端全量 → 384 passed
```

## 浏览器 / 数据

- 专用隔离库；未触碰开发者库。
- Retention/监护/知情/退出为产品决策，由负责人确定；本任务如实记录语义，未编造天数或流程细节。

## 尚未验证 / 遗留

- 真实学生试用前的监护/知情/退出流程由试点负责人确定并补充，不在本文件下结论。
- 匿名聚合口径未定义，如使用需另行说明。
- MemoriesPage 前端操作文案与后端语义一致性的细粒度人工核对由 T25 浏览器回归统一检查（本任务后端语义 + 文档已落，前端文案已核查无"假定成功"的隐藏语义）。

## tasks/todo.md 状态

实现完成 / 验收完成（后端 384 passed）。
