# T06 · 账号切换清理与异步隔离

> 日期：2026-09-06。任务 T06（M，依赖：T01）。

## 已解决的用户问题与行为变化

共享设备切换账号可能看到上个账号对话的问题已修复：

- **统一 resetUserState 入口**：新增 `features/auth/reset-user-state.ts`，登出、401、账号切换统一调用：清 token、清对话 store、清用户 query 缓存（TanStack `queryClient.clear()`），防止 A 用户的 `/me`、`/progress`、`/recommendation` 等在 B 登录后瞬间回填。
- **终止在途流**：`conversation-store.reset()` abort 当前 SSE 流、清 streamTimer；清空 `messages/history/loaded/conversationId/lastScreenContext/lastIdempotencyKey/historyLoaded`。
- **会话世代（epoch）隔离**：递增 `sessionEpoch`；`load()` 不再用全局 `loaded` 短路（改为 `loaded + loadedEpoch`），账号切换后旧 `loaded` 不生效；`send()` 的 upsert/showError/onToolStart/onToolResult/onDone 以及 `refresh()` 在每次 `set` 前校验世代，A 用户慢请求在 B 登录后返回不写入。
- **用户作用域 active-conversation 键**：由全局 `shuangling-active-conversation` 改为 `shuangling-active-conversation:<userId>`（从 JWT `sub` 读取）；旧全局键只清理不迁移给新用户，B 不会读到 A 的活动会话。
- **AuthProvider 接线**：`clearAuthState` 与全局 401 handler 均改调 `resetUserState`（不再只清 token/user）。

## 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/src/features/auth/reset-user-state.ts`（新增） | 统一重置入口（清 token + 对话 store + query 缓存） |
| `frontend/src/features/conversation/store/conversation-store.ts` | 用户作用域 active-conversation 键；epoch 世代；`reset` action；`load/refresh/send` 异步 set 世代校验；`loadedEpoch` 短路 |
| `frontend/src/features/auth/AuthProvider.tsx` | `clearAuthState` 与 401 handler 改调 `resetUserState` |
| `frontend/src/features/auth/account-switch.test.tsx`（新增) | 4 项：reset 清空、慢请求不回填、用户键隔离、迟到 delta 不回填 |

## 回归测试

```bash
cd frontend && pnpm exec vitest run src/features/auth/account-switch.test.tsx src/features/conversation/store/conversation-store.test.ts
# 结果：conversation-store 14 passed（原状）；account-switch 4 passed
pnpm test    # 全量前端：39 files / 199 passed
pnpm build   # 通过；JS 499.87 kB(gzip 146.36)
```

## 浏览器 / 数据

- 真实浏览器中以 `xiaoming` 登录验证了对话面板；尚未用第二个独立账号做端到端切换（需另一账号在本地 seed）。**E2E 双账号切换（account-switch.spec.ts）归 T25 回归矩阵**。

## 尚未验证 / 遗留

- 双账号真实浏览器切换的端到端（含一帧闪现检查）在 T25 用两个独立测试账号补 E2E；本任务以 store/Auth 单测 + 世代隔离覆盖逻辑正确性。
- companion 用户偏好恢复到哪些命名空间（如桌面偏好）未独立验证；T18 对话面板可用性涵盖触屏场景。

## tasks/todo.md 状态

实现完成 / 验收完成（前端 199 passed + build；双账号 E2E 留 T25）。
