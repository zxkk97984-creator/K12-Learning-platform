# T11 · 阅读图片渲染与稳定布局

> 日期：2026-09-07。任务 T11（M，依赖：T07、T10）。

## 已解决的用户问题与行为变化

阅读器"图解没有图"、IMAGE 不渲染、标记文本截断的问题已修复：

- **提取 `ContentBlockView`**：从 ReaderPage（776 行）按职责拆出 `pages/reader/ContentBlockView.tsx`，单测可独立覆盖。
- **FIGURE/IMAGE 真实渲染**：
  - 有 `src` → 渲染 `<img>`（`loading=lazy`、`max-width:100%`、保留纵横比、`alt` 正确）；
  - 加载失败 → "图解暂时无法加载" + 重试按钮（后文完整）；
  - 无 `src`（旧式两段 FIG）→ 明确"暂无图解" + 等价文字（来自 alt），**不伪造图**。
- **标记文本多次出现不截断**：`renderMarkedText` 由 `split()` 改为 `splitAll`，同一术语出现两次时第二次之后的正文不再丢失，且两处术语都高亮。
- **未知内容类型明确反馈并上报**：不再静默 `return null`；渲染"暂不支持的内容类型（…）"并调用 `onUnknownBlockType`。
- **可读性**：阅读正文 18px / 行高 1.85；知识卡/例/呼出字号提升；去掉 9-10px 小字。

## 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/src/pages/reader/ContentBlockView.tsx`（新增） | 块视图 + FigureView（img/暂无图解/失败重试）+ `renderMarkedText` splitAll |
| `frontend/src/pages/reader/ReaderPage.tsx` | 移除本地 block 渲染函数，改为导入 `ContentBlockView`；`ContentBlock` 类型不再直接引用 |
| `frontend/src/pages/reader/ContentBlockView.test.tsx`（新增） | 6 项：标记两次不截断、FIGS rc 渲染/无 src 暂缺、IMG 失败重试、未知类型上报、正文 18px |

## 回归测试

```bash
cd frontend && pnpm exec vitest run src/pages/reader/ContentBlockView.test.tsx
# 6 passed
pnpm test    # 全量：43 files / 224 passed
pnpm build   # 通过
```

## 浏览器实测（localhost:5175 → :8002，xiaoming，真实章节《机器怎么学习？》第一章）

- FIGURE `<figure role="img">` 显示"暂无图解"+ 等价文字（该章 FIG 为旧两段无资源，如实暂缺，不伪造图）；图注"一张图分清三大流派：看的是答案、结构还是奖励"显示。
- 知识卡（监督学习/无监督学习）标题/正文/例子 + "让霜铃讲给我听"；CALLOUT（想一想/动手归类/下一章预告）；正文按 18px。
- 目录（左侧 01-05 节）+ 当前上下文（右侧）。阅读正文布局正常。
- 截屏：`tasks/acceptance/11-reader-1280.png`（真实运行页面）。

## 尚未验证 / 遗留

- 真实教学图解（`assets/*`）尚未添加：T12 补图后，FIG 将带 `src` 渲染 <img>；当前均为"暂无图解"。**这是本任务的预期边界**（T10 只建契约，T12 补资产）。
- 慢图加载不推走阅读按钮、390/820 断点阅读布局留 T17/T25 统一验证（本任务以 1280 验证）。
- 章节完成/末章收尾闭环属 T13（当前 Reader 底部仍是"我想问一个问题"，未接 T13 的完成卡）。

## tasks/todo.md 状态

实现完成 / 验收完成（前端 224 passed + build；真实浏览器 1280 截图；末章完成卡归 T13）。
