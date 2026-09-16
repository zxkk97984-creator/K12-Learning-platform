# T17 · 全局导航、字号与基础控件（§5.1–5.2）

> 日期：2026-09-07。任务 T17（M，依赖：T07）。

## 已解决的用户问题与行为变化

导航在移动端缺失、桌面导航把"设置"当第一级、字号偏小、键盘焦点不明显、底部提交会被遮挡。现在：

- **全局导航响应式（§5.2）**：桌面/平板（≥820px）顶部保留 首页/学习/练习/成长 四项（"测验"改名"练习"）；设置与退出收敛到账户区；管理员"管理"入口仅管理员可见。<820px 隐藏顶部横向导航，改为底部四项导航（首页/学习/练习/成长），设置/退出从账户区进入；底部导航 56px 高 + `safe-area-inset-bottom`；`<main>` 加 `pb-20 md:pb-10`，底部导航不遮正文/提交。
- **字号与字体（§5.1）**：正文默认字号 15→16px；`--font-body` 补齐中文回退（PingFang SC / Microsoft YaHei / Noto Sans CJK SC / Source Han Sans SC）；display 字体仅用于短标题。
- **焦点清晰（§5.1 验收③）**：全局 `:focus-visible` 2px accent outline + 2px offset；主操作按钮 `min-h-[44px]`。
- **动效尊重**：`prefers-reduced-motion: reduce` 下停用非必要动画/骨架/过渡。
- **404 页面**：文案改为可读的"你访问的地址不存在"+ 返回首页/去书库入口，去除"Phase 1 骨架占位"占位话。

## 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/src/index.css` | 中文回退字体栈；`--fs-body` 15→16px；全局 `:focus-visible`；`prefers-reduced-motion` 规则 |
| `frontend/src/shared/ui/AppLayout.tsx` | 四项导航 + 设置/退出入账户区 + 管理员入口；<820 顶部导航隐藏；`<main>` 底部 padding；接入 `BottomNav` |
| `frontend/src/shared/ui/BottomNav.tsx`（新增） | <820px 底部四项导航（56px + safe-area） |
| `frontend/src/app/router/index.tsx` | 404 文案 + 返回首页/去书库入口 |
| `frontend/src/shared/ui/AppLayout.test.tsx`（新增） | 5 项：导航四项、"测验"改名、设置/退出、底部导航、非管理员无管理入口、内容出口 |

## 回归测试

```bash
cd frontend
pnpm exec tsc --noEmit      # 0 错误
pnpm exec vitest run        # 248 passed
```

（本任务纯前端；后端无改动，沿用 T16 的 371 passed。）

## 浏览器 / 数据

- 纯前端改动，未触碰数据库。
- 逐断点浏览器截图（320/390/820/1280、200% 字号、键盘焦点、底部导航不遮挡）并入 T25 回归矩阵统一补录；本任务以 jsdom + tsc 验证导航结构与样式规则落地。

## 尚未验证 / 遗留

- 200% 字号放大后"不丢操作"的具体逐页面视觉核对、各断点元素矩形是否超出视口，由 T25 浏览器回归统一检查（不以 overflow-x:hidden 冒充修复）。
- 各页面局部 9px 小字逐页替换仍待后续视觉规范化批次（T17 先落地通用字体与导航骨架；具体页面局部字号属于 §5.1 的持续项，后续任务按页覆盖）。

## tasks/todo.md 状态

实现完成 / 验收完成（前端 248 passed + tsc 0 错误；浏览器截图并入 T25）。
