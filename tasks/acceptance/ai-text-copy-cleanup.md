# T19 · AI 文本与内部文案清理

> 日期：2026-09-07。任务 T19（M，依赖：T18）。

## 已解决的用户问题与行为变化

教师消息不支持列表/代码块/链接，且学生界面出现"Quiz Skill / Memory Skill / Phase 9 / 技能版本"等开发细节（§5.6 验收③）。

- **安全 Markdown 子集（MarkdownMessage）**：支持段落、有序/无序列表、围栏代码块、安全链接；**不引入 dangerouslySetInnerHTML**——原始 HTML 一律按纯文本处理（React 自动转义，不执行）；链接仅放行 `http/https`，`javascript:`/`data:` 按纯文本显示。采用手写安全子集而非引入解析库：需求仅段落/列表/代码/链接四类，自足子集不含「执行 HTML」路径，避免为极小需求引入重量依赖与受攻击面。
- **术语映射（§5.6）**：`Quiz Skill 已创建` → `测验已创建`；`Quiz Skill 生成失败` → `测验生成失败`；`Memory Skill 生成` → `记忆由学习记录生成`；`语音聊天（Phase 9 实现）` → `语音聊天`；答卷页移除"技能版本 {skill_version}"。老师名称仍来自 `useTeacherName` 统一配置，未在文案中硬编码唯一"霜铃"。
- **教师消息渲染**：标题/正文/列表/代码块/链接可读；Inline 加粗/斜体/代码保留。

**验收对应**：①常见讲解/列表/代码块可读；②javascript 链接与 raw HTML 不执行（单测覆盖）；③学生界面不存在 Phase/骨架/技能版本/Skill 等开发细节。

## 修改文件

| 文件 | 改动 |
|---|---|
| `features/conversation/components/MarkdownMessage.tsx` | 安全子集：列表/代码块/安全链接；禁止 raw HTML 执行（React 转义） |
| `features/conversation/components/MarkdownMessage.test.tsx` | 新增列表/代码块/安全链接/`javascript:`/raw HTML 5 项 |
| `features/conversation/store/conversation-store.ts` | `Quiz Skill` → `测验`；`conversation-store.test.ts` 同步 |
| `features/conversation/components/QuickActions.tsx` | 移除"（Phase 9 实现）" |
| `pages/quizzes/QuizDetailPage.tsx` | 移除"技能版本"开发细节 |
| `pages/profile/MemoriesPage.tsx` | `Memory Skill` → `记忆由学习记录生成` |
| `mocks/data/conversation.ts` | `Quiz Skill` → `测验` |

## 回归测试

```bash
cd frontend
pnpm exec tsc --noEmit          # 0 错误
pnpm exec vitest run            # 253 passed
```

（本任务纯前端；后端沿用 T16 的 371 passed。）

## 浏览器 / 数据

- 纯文案/markdown 渲染改动，未触碰数据库。
- 教师消息列表/代码块/链接的真实渲染效果与浏览器回归并入 T25。

## 尚未验证 / 遗留

- 真实 LLM 产出中若含更复杂 Markdown（表格/嵌套引用），当前子集按纯文本/段落降级显示（不崩溃），扩展至表格属后续需求，非本次范围。
- "Skill"一词在管理端（admin 样式/章节）与后端日志中未替换（学生界面已清理；管理端/日志不属于学生可见界面，如实保留避免误伤运维信息）。

## tasks/todo.md 状态

实现完成 / 验收完成（前端 253 passed + tsc 0 错误）。
