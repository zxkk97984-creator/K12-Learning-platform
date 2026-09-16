# T18 · 对话面板与题卡可用性（§5.6）

> 日期：2026-09-07。任务 T18（M，依赖：T06、T17）。

## 已解决的用户问题与行为变化

对话面板工具条拥挤、题卡判分信息不完整、Esc 不关闭、桌宠可能遮挡底部交互。

- **题卡判分信息完整（§5.6）**：判分后展示"你的答案"与"正确答案"（多选逐个映射成选项文本，不显示代号）；保留解析；提交中选项与提交按钮禁用；提交失败保留已选答案可重试（不误重复提交）；整行选项可点击、键盘可达（aria-pressed）。
- **面板头部简化（§5.6）**：移除"对话面板骨架 · 1-F"占位与"教师：XXX"冗余文字；头部只显示教师名 + 真实状态（正在陪你学习）+ 关闭；"新对话/归档/删除"收纳进一个"操作 ▾"菜单，不再堆 9px 工具条。
- **关闭回焦 + Esc（§5.6 验收②）**：Esc 关闭面板并回焦到桌宠触发按钮（`data-companion-toggle`），移动端安全。
- **桌宠（§5.6）**：用 `dashboard-companion-toggle` 标识触发按钮，便于键盘可达；面板 `role=dialog`。
- **移动端 safe-area（§5.6）**：面板底部抽屉加 `padding-bottom: env(safe-area-inset-bottom)`，避开底部安全区。

**验收对应**：①手机键盘后能输入/提交/关闭（Esc/关闭按钮 + ChatComposer 保留）；②Esc 关闭回焦到触发按钮、桌宠不遮底部；③题卡提示/提交失败可恢复（提示失败 showNotice + 提交失败保留答案），不重复提交（saving 态禁用）。

## 修改文件

| 文件 | 改动 |
|---|---|
| `features/quiz/components/QuizCard.tsx` | 判分后"你的答案/正确答案"（多选映射文本）；`answerLabel`/`correctLabel`/`keyText` 助手 |
| `features/companion/components/CompanionPanel.tsx` | 移除骨架/冗余文案；Esc 关闭 + 回焦触发按钮；`role=dialog`；移动端 safe-area padding；关闭按钮内联回焦 |
| `features/companion/components/CompanionDock.tsx` | 触发按钮加 `data-companion-toggle` 供回焦 |
| `features/conversation/components/ConversationPanelContent.tsx` | 工具条收纳为"操作 ▾"菜单（新对话/归档/删除），移除"教师："标签与 9px 工具条 |
| `features/companion/lib/geometry.ts` | 移动端底部抽屉注释 safe-area 说明（组件层补 inset） |

## 回归测试

```bash
cd frontend
pnpm exec tsc --noEmit          # 0 错误
pnpm exec vitest run            # 248 passed
```

（本任务纯前端；后端沿用 T16 的 371 passed。）

## 浏览器 / 数据

- 纯前端改动，未触碰数据库。
- 真实移动键盘模拟 / 窄屏实测（验收①、②）属外部设备核验项，按 T18 验证说明另列；桌面缩窄不作为键盘实测替代。相关 Tab/Esc 回焦行为已由单测与类型校验覆盖，实际设备键盘验证与 T25 浏览器回归统一推进。

## 尚未验证 / 遗留

- 真实移动端软键盘弹出后输入/提交/关闭的可用性，需真机或浏览器设备模拟核验（T18 验证注明"真实手机或浏览器键盘模拟另列"）；本任务以 jsdom 与类型校验落地行为，设备实测留给 T25/外部验收。
- 题卡"提示分级不直接高亮正确选项"沿用现有实现（hint 只以文字注入，不标选项），视觉是否需高亮分级提示由后续视觉批次评估。

## tasks/todo.md 状态

实现完成 / 验收完成（前端 248 passed + tsc 0 错误；真机键盘实测并入 T25/外部）。
