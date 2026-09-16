# 性能与回归证据（T25b）

> 日期：2026-09-07。任务 T25b（按测量拆分路由 lazy，独立 admin bundle）。

## 构建结果对照（同环境，`flutter` 无；frontend `pnpm build`）

| 项 | 拆分前（基线） | 拆分后 | 变化 |
|---|---|---|---|
| 主入口 js | `index-*.js` 517.26 kB（gzip 151.17 kB） | `index-*.js` **272.40 kB**（gzip 85.50 kB） | **-45%** |
| 总产物 | 单 JS 517 kB + CSS 35.6 kB | 主 272 kB + 逐页 chunks（每页 4–25 kB）+ services 116 kB + CSS 35.6 kB | 按需加载 |
| admin 包 | 并入主 bundle | 独立 `admin-*.js` **18.15 kB**（gzip 4.91 kB） | 独立成包，不拖累学生主 bundle |
| >500 kB 警告 | 有（517 kB） | 无 | 消除 |

说明：`services-*.js`（116 kB）为共享服务/依赖 chunk（React Query、Zustand、API 客户端等），按需保留；页面组件按路由懒加载（Home 16.7 / Reader 20.3 / Library 12.2 / Admin 18.2 等）。`AppLayout` 与登录页保持即时预加载，不影响登录恢复与预加载体验。

## 首屏与接口数

- 首屏由懒加载 + Suspense：仅首页所需 chunk 在首次进入时加载；首屏**不做全量预加载**，避免拉入全部页面与 admin。
- 接口数：不因拆分改变（同一数据请求）；首页并发独立请求（T08）保持——统计/继续学习/推荐/记忆/测验各一，任一失败独立降级。
- **不以 gzip 大小冒充 LCP**：本文件记录构建产物大小/拆分对照；真实首屏 LCP 需在浏览器记录（见 T25a E2E/浏览器实测，另行记录）。

## 验证命令

```bash
cd frontend
pnpm build        # 无 >500 kB 警告；主 bundle 272 kB
pnpm exec tsc --noEmit   # 0 错误
```

## 说明

- 本任务记录构建前后大小/拆分对照，属有意回归控制；未为了追求单一包阈值而破坏预加载/登录恢复（`AppLayout`/登录保持即时，其余按路由懒加载）。
- 真实浏览器首屏/长列表 LCP 由 T25a 的 Playwright 手机视口项目与真实浏览器记录补充（本文件不含伪 LCP 数据）。
