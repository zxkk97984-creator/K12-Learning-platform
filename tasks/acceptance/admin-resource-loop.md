# T21 · 管理员资源处理闭环

> 日期：2026-09-07。任务 T21（M，依赖：T07）。

## 已解决的用户问题与行为变化

管理员上传/重处理资源后无法看到处理进度，需手刷；失败原因不清晰；统计接口出错时显示"正在加载"直到无限等待；按钮连点会重复提交。

- **自动轮询（验收①）**：存在非终态资源（UPLOADED/PARSING/CHUNKING/INDEXING）时每 3 秒自动刷新列表，**UPLOADED→READY 无需手刷**；页面隐藏（visibilitychange）暂停轮询、卸载取消、READY/FAILED 停止。非终态时显示"正在自动刷新处理状态"提示。
- **超时提示（不假定失败）**：非终态资源超过 2 分钟仍在处理，显示"仍在处理中，可稍后手动刷新或重处理"，不假定失败。
- **可读失败 + request ID（验收②）**：FAILED 显示"失败原因：…（资源 ID：xxxx）"；"重新处理"按钮可重试且不循环提交（防连点 + 待命态"已加入队列…"）。
- **上传/重处理文案与防连点**：上传成功"已上传，正在处理"；重处理成功"已加入处理队列"；上传/重处理按钮 pending 态禁用（disabled）防连点；失败显示 ApiError 可读信息。
- **统计接口容错（验收③）**：`AdminDashboard` 统计 500/失败时显示"统计加载失败 + 重新加载"，而非无限"正在加载"；表单输入（来源名/URL/作者/License/版权）不因刷新丢失（本地 state 保留）。
- **资源列表拉取全状态**：`getKnowledgeResources` 拉取 READY/FAILED 及全部处理中状态并去重，使处理中的资源出现在列表以便轮询。

**验收对应**：①UPLOADED→READY 无需手刷；②FAILED 显示原因可重试且不循环；③统计接口 500 出错而非无限加载，表单输入不丢。

## 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/src/pages/admin/AdminKnowledge.tsx` | 3s 轮询/visibility 暂停/卸载取消/终态停止；超 2 分钟"仍在处理"提示；失败可读原因+ID；上传/重处理 pending 防连点；可读文案 |
| `frontend/src/pages/admin/AdminDashboard.tsx` | 统计失败显示错误+重试（不再无限加载） |
| `frontend/src/shared/api/admin-service.ts` | `getKnowledgeResources` 拉取全部状态并去重 |
| `frontend/src/pages/admin/AdminKnowledge.test.tsx`（新增） | 5 项：上传文案+防连点、轮询 UPLOADED→READY、FAILED 显示原因可重试、重处理队列提示、超 2 分钟提示 |

## 回归测试

```bash
cd frontend
pnpm exec tsc --noEmit          # 0 错误
pnpm exec vitest run            # 258 passed
```

（本任务纯前端；后端沿用 T20 的 378 passed。）

## 浏览器 / 数据

- 纯前端改动，未触碰数据库。
- 隔离 Worker 上传测试文档一次并查任务终态属后端隔离验证，交由既有 admin/knowledge 后端测试与 T25 回归联动；本任务以 jsdom 验证前端轮询与 UX 行为。

## 尚未验证 / 遗留

- 真实浏览器轮询与 visibility 暂停的实际表现由 T25 浏览器回归覆盖。
- admin 页面表单输入"不因刷新丢失"依赖本地组件 state（未落 localStorage）；刷新页面本身会重置，符合"上传流程中不丢输入"的语义。

## tasks/todo.md 状态

实现完成 / 验收完成（前端 258 passed + tsc 0 错误）。
