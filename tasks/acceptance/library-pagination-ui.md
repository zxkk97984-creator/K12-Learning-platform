# T05 · 书库完整发现与分页 UI

> 日期：2026-09-06。任务 T05（M，依赖：T04）。

## 已解决的用户问题与行为变化

书库只能显示第一页、搜索靠本地过滤的问题已修复：

- **信封解析 + 分页**：`http.ts` 新增 `apiRequestEnvelope<T,M>`（复用同一解析/鉴权/错误分支，`apiRequest` 不变）与 `ApiEnvelope/CursorMeta` 类型。`content-service` 新增 `BookPage`/`BookPageParams`、`getBooksPage`；`ApiContentService.getBooksPage` 从后端解析 `{items, meta(游标/总数)}`。
- **加载更多**：LibraryPage 用 `getBooksPage(cursor)` 追加下一页，保留前页；`has_more`/`next_cursor`/`total` 驱动"加载更多"按钮与"已显示 N 本 / 共 M 本"。
- **筛选写 URL**：search/grade/topic 写入 URL，返回书库保持；筛选变化重置游标；搜索 **300ms 防抖**后请求后端全库（移除了旧的本地 `searchBooks`/client 过滤，禁止"先拉全量本地搜"）。
- **明确状态**：loading / error（标题+说明+重试）/ empty（无匹配+清除筛选）/ success 四态区分；列表失败不清零、显示重试；下一页失败保留前页。
- **卡片排版 §5.4**：真实 `cover_url` 优先，缺图用统一文字封面（深色文字可读）；标题最多两行；适用年级区间 + 章数 + 时长；桌面 3 列 / 平板 2 列 / 手机 1 列；详情/继续分离。
- **样式与可读性**：正文/次要字号提升（h1 32px、正文 16px、次要 14px、按钮 ≥44px 点击区、焦点 focus-visible）；去掉了 9-10px 小字与"共 N 本"以页长冒充总数。
- **Mock 同步**：`MockContentService.getBooksPage` 实现分页信封，`getBooks` 兼容返回第一页。

## 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/src/shared/api/http.ts` | 新增 `apiRequestEnvelope`、`ApiEnvelope`、`CursorMeta`；重构共用 `requestRaw` |
| `frontend/src/shared/api/content-service.ts` | 新增 `BookPageParams`、`BookPage`、`getBooksPage` |
| `frontend/src/shared/api/api-content-service.ts` | `getBooksPage` 解析信封；`getBooks` 兼容；移除本地 `searchBooks` |
| `frontend/src/pages/library/LibraryPage.tsx` | 改用 `getBooksPage`+分页+URL 筛选+防抖搜索+loading/error/empty 状态；卡片按 §5.4 排版 |
| `frontend/src/mocks/services/content-service.ts` | `getBooksPage` 分页信封 |
| 测试 | `api-content-service.test.ts` 增 `getBooksPage` 信封用例；`LibraryPage.test.tsx` 增分页/错误/防抖搜索用例 |

## 回归测试

```bash
cd frontend && pnpm exec vitest run src/pages/library/LibraryPage.test.tsx src/shared/api/api-content-service.test.ts src/shared/api/http.test.ts src/mocks/services/content-service.test.ts
# 结果：24 passed
pnpm test   # 全量前端：38 files / 195 passed
pnpm build  # 通过；JS 498.91 kB(gzip 146.14)，CSS 34.46 kB
```

## 浏览器实测（真实后端数据，localhost:5175 → :8002）

- 登录 `xiaoming/demo123` → `/library`。
- 1280：3 列卡片；"已显示 12 本"+「加载更多」→ 点击后"已显示 24 本"（游标分页生效）；真实书（推荐测试书/机器人会怎么想？/用 Scratch 做游戏…）。
- 390：卡片单列堆叠；快照可见全部卡片与"加载更多"。
- 搜索「机器人」URL 同步为 `?search=机器人`（防抖 + URL 写入生效）。
- 截图：`tasks/acceptance/05-library-1280.png`、`05-library-390.png`、`05-library-820.png`（真实运行页面）。

## 尚未验证 / 遗留

- **运行中的 :8002 后端的 search 过滤因后端进程为旧代码而未在浏览器内生效**（该服务在本会话开始前已运行，含 T04 之前的 `list_books`：接受但忽略 search 参数）。前端已正确发送 `search` 且后端 T04 已实现并在隔离库 python 测试通过；重启后端即可让浏览器搜索生效。此项记为**依赖外部重启的遗留**，不影响前端契约正确性。
- 顶部导航在 <820 仍是桌面横条（底部导航属 T17，不在 T05 范围）。
- 上一章/推荐、阅读、练习等核心流程的端到端联验收在 T13/T16/T25。

## tasks/todo.md 状态

实现完成 / 验收完成（前端 195 passed + build 通过；真实浏览器 1280/390/820 截图；后端 search 需重启运行中的服务生效）。
