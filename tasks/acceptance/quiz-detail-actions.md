# T15 · 答卷与练习历史操作明确

> 日期：2026-09-07。任务 T15（M，依赖：T07、T14）。

## 已解决的用户问题与行为变化

答卷里"再问老师"目标不明确（F06）：原来每题一个按钮，意图混成"再出一道类似的题"，无显式 quiz/question/answer 上下文。现在每题拆成两个清晰的行动：

- **"讲解这道题"**：给后端传明确 `quizSessionId` + `questionId`，走 T14 的错题讲解契约，老师讲解的是**这一道**题（题干/作答/解析），不是泛泛"再出一题"。
- **"再练一道类似的"**：走 `quiz-requestion` 意图，仅关联本测验（`quizSessionId`），创建同类新练习（页面零生成调用）。
- **多选文本与解析**：单选/多选/判断的答案与正确答案都映射到**选项文本**；多选 A/C 显示"老师给答案；学生自己分组"两个文本，不再只显一个键；每题展示"解析"。
- **历史筛选可恢复**：`QuizzesPage` 切换筛选立即重置 loading（不再闪现旧列表）；加载失败显示错误态可"重新加载"；来源按 book/chapter 去重（lib 缓存），单个来源失败降级为占位 `—`，**不抹掉整份列表**。
- **只读答卷（0 写）**：`QuizDetailPage` 仅 `get*` 查询（会话/题目/答案/交互），绝不调用 create/submit；答题只出现在 `runIntent` 打开对话组合框，不直接产生测验。

## 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/src/features/conversation/types.ts` | 新增 `explain-question` 意图 |
| `frontend/src/features/conversation/store/conversation-store.ts` | `INTENT_PROMPTS` 新增 `explain-question` 文案 |
| `frontend/src/features/conversation/data/intents.ts` | `texts` / `INTENT_AI_STATE` 新增 `explain-question` |
| `frontend/src/pages/quizzes/QuizDetailPage.tsx` | 答案/正确选项映射到文本、支持多选、展示解析、拆分"讲解这道题/再练一道"、读来源容错、全程只读 |
| `frontend/src/pages/quizzes/QuizzesPage.tsx` | 筛选切换重置 loading、错误可恢复（重新加载）、来源单失败不抹列表 |
| `frontend/src/pages/quizzes/QuizDetailPage.test.tsx`（新增） | 3 项：多选 A/C 双文本、讲解传明确 ID 且只读、再练一道传 quizSessionId |
| `frontend/src/pages/quizzes/QuizzesPage.test.tsx`（新增） | 2 项：来源失败不抹列表、加载失败可重试 |

## 回归测试

```bash
cd frontend
pnpm exec tsc --noEmit            # 0 错误
pnpm exec vitest run              # 239 passed
```

（后端本任务无改动；全量后端已在 T14 验证为 365 passed。）

## 浏览器 / 数据

- 页面级行为以 jsdom + mocked 服务验证；真实浏览器接入（打开答卷点两题各看对应讲解）并入 T25 关键路径回归统一补录截图。
- 未触碰任何数据库（纯前端页面改动 + 意图文案）。

## 尚未验证 / 遗留

- "再练一道"真正创建新测验并记录 `source_quiz_session_id` / `source_question_id` 属于 T16 数据补充子任务（后端模型/迁移），本任务只锁定页面触发与只读口径。
- Tailwind 视觉细节由 T17/T18 视觉规范化统一覆盖。

## tasks/todo.md 状态

实现完成 / 验收完成（前端 239 passed + tsc 0 错误）。
