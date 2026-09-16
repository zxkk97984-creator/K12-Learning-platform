# T07 · 统一错误、重试与查询基础

> 日期：2026-09-06。任务 T07（M，依赖：T06）。

## 已解决的用户问题与行为变化

为"失败被误报为没有"的系统性修复奠定基础：

- **http 支持 signal / request ID / Retry-After**：`ApiRequestOptions` 加 `signal`（fetch 透传，路由/账号切换后可取消）；`ApiError` 新增 `requestId`（读 `X-Request-ID`）与 `retryAfterMs`（解析 `Retry-After` 秒或 HTTP 日期）。
- **统一请求状态视图**：`shared/ui/ResourceState.tsx` 提供 `loading/empty/error` 三种可组合视图；错误带标题/说明/可选 request ID/重试按钮（≥44px、可键盘触发）；空态只在 success 且数据确为空时使用。
- **查询键用户隔离**：`shared/api/query-keys.ts` 提供 `queryKeys` 与 `userScopedKey`，用户数据 key 必须含 user_id，防跨账号缓存串用。
- **查询重试策略**：`app/providers/query.ts` 配置 TanStack：401/403 不重试（权限失败，由 UNAUTHORIZED_EVENT 清状态）；网络错误/5xx 最多自动重试 1 次；429 尊重 Retry-After（`retryDelay`）；mutation 失败不自动重试。

## 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/src/shared/api/http.ts` | `ApiError` 加 `requestId`/`retryAfterMs`；`ApiRequestOptions` 加 `signal`；`requestRaw` 透传 signal、读取响应头 |
| `frontend/src/shared/ui/ResourceState.tsx`（新增） | Loading/Empty/Error 可组合视图 + 重试按钮 |
| `frontend/src/shared/api/query-keys.ts`（新增） | 用户隔离查询键 |
| `frontend/src/app/providers/query.ts` | 重试/退避策略（401/403 不重试，5xx 重试 1 次，429 尊重 Retry-After） |
| `frontend/src/shared/api/http.test.ts` | 增 requestId/retry-after/signal 用例 |
| `frontend/src/shared/ui/ResourceState.test.tsx`（新增） | 4 项：三态渲染 + 重试可触发 + 键盘可聚焦 |

## 回归测试

```bash
cd frontend && pnpm exec vitest run src/shared/api/http.test.ts src/shared/ui/ResourceState.test.tsx
# 11 passed
pnpm test    # 全量：40 files / 205 passed
pnpm build   # 通过
```

## 尚未验证 / 遗留

- `ResourceState`/`queryKeys` 为基础设施，**具体页面接用**在 T08（首页）、T09（成长）、T21（管理）落实。
- 真实浏览器对"已有内容刷新失败保留旧数据"的验证在 T08/T09 页面改造后补截图。
- 401 清用户状态已在 T06 的 `resetUserState` 接线（UNAUTHORIZED_EVENT → resetUserState）。

## tasks/todo.md 状态

实现完成 / 验收完成（前端 205 passed + build）。
