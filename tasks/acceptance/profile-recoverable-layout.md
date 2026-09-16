# T09 · 成长页可恢复与布局修正

> 日期：2026-09-06。任务 T09（M，依赖：T07）。

## 已解决的用户问题与行为变化

成长页首个接口失败导致持续骨架、以及网格布局错误的问题已修复：

- **区块独立请求/失败**：`load()` 改用 `Promise.allSettled`，偏好/画像/历史记忆/记忆/情节各自独立；任一接口失败不拖垮整页，其余成功区块仍可用。
- **prefs 失败不再持续骨架**：原先 `loading || !prefs` 恒为骨架；现加载完成后若 prefs 失败，主列顶部显示行内错误 + 重试，右栏与其余区块仍渲染（不再是"加载中"死循环）。
- **网格布局修正 §5.7**：主体列与右栏为**两个直接子元素**；"管理我的记忆"按钮从"第三个直接子元素"并入右栏 ProfileSidebar（第三个按钮），不再掉到下一行主列。
- **二级内容降权**：AI 档案（原始 frontmatter 编辑）保留在"AI 档案"标签页（二级内容），普通学生不强制编辑 YAML/Markdown。

## 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/src/pages/profile/ProfilePage.tsx` | `load` 改 `Promise.allSettled` 独立失败；`loadError` 状态；主列行内 prefs 错误+重试；网格去掉第三个直接子元素；ArchiveDocCard 需 prefs 才渲染 |
| `frontend/src/pages/profile/components/ProfileSidebar.tsx` | 新增 `onManageMemories`，右栏加入"管理我的记忆"按钮；字号提升 |
| `frontend/src/pages/profile/ProfilePage.test.ts` | 增 3 项：prefs 失败→错误+重试非骨架；prefs 失败但其余可用；管理记忆在右栏 |

## 回归测试

```bash
cd frontend && pnpm exec vitest run src/pages/profile/ProfilePage.test.ts src/pages/profile/profile-labels.test.ts
# 2 files / 11 passed
pnpm test    # 全量：42 files / 218 passed
pnpm build   # 通过
```

## 浏览器实测（localhost:5175 → :8002，xiaoming）

- 1280：主列（学习画像：当前表现/最近变化/画像版本记录/学习情节）+ 右栏（证据覆盖/霜铃记得这些 + 问霜铃/查看原始 AI 档案/**管理我的记忆 →**）。
- 网格只有两个直接子元素（主列 + 右栏）；"管理记忆"位于右栏第三按钮。
- 未注入时（getPreferences 正常）整页可用。
- 截屏：`tasks/acceptance/09-profile-1280.png`（真实运行页面）。

## 尚未验证 / 遗留

- 390px 堆叠未截图（右栏在主列下）；已由 `grid-cols-[..._280px] max-md:grid-cols-1` 控制，后续 T17 统一做断点审查。
- 开发库中存在疑似被测试数据污染的记忆（如"该学生已开始学习4111945384824350651768382490617708058804480这一章节"——数值溢出/随机 ID），属用户开发库既有数据，未触碰；仅记录为数据质量观察，不影响本次布局修复。
- 记忆页的质疑/修正/遗忘/导出控制属 T24。

## tasks/todo.md 状态

实现完成 / 验收完成（前端 218 passed + build；真实浏览器 1280 截图）。
