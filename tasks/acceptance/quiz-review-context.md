# T14 · 错题讲解上下文契约（§4.3）

> 日期：2026-09-07。任务 T14（M，依赖：T03）。

## 已解决的用户问题与行为变化

答卷"再问老师"目标不明确（F06）：原来每题按钮都调用同一个 `askAgain`，意图是"再出一道类似的题"，没有显式 quiz/question/answer 上下文。现在"讲解这道题"传入明确的测验/题目 ID，后端从**自己的快照**查题干、作答、解析，绝不凭客户端传来的正确答案、学生 ID 或权限结论。

- **屏幕上下文扩展（前端）**：`ScreenContext` 新增 `quizSessionId`、`questionId`；adapter 序列化为后端约定的 `quiz_session_id`/`question_id`。
- **后端契约（schemas.py）**：新增 `QuizReviewContext`，从自由格式 screen_context 中容错解析 ID（camel/snake 兼容；畸形 ID 按缺失处理，不炸对话）。
- **后端权威解析（teacher_context.py）**：新增 `_build_review_section`，从 DB 查 `QuizSession`/`QuizQuestion`/`QuizAnswer` 快照，组装【正在讲解的题目】节：
  - 有测验无题 → 明确「还不知道要讲哪一道题（请选择一道题后再问）」；
  - 测验不存在 → 明确「无法定位要讲解的题目」；测验不属于当前学生 → 明确「这不是你的测验，无法讲解」；
  - 题目不属于该测验 → 明确「所选题目不属于这次测验，无法讲解」；
  - 命中 → 输出题干、选项、学生最终作答（含第几次、正确/错误）、服务端正确答案、解析。
- **离开答卷后不沿用旧题**：screen_context 无 quiz 字段时【正在讲解的题目】节不出现（§4.2 上下文替换语义已保证）。

## 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/src/features/screen-context/types.ts` | `ScreenContext` 新增 `quizSessionId`/`questionId` |
| `frontend/src/shared/api/api-conversation-service.ts` | `apiScreenContext` 序列化 `quiz_session_id`/`question_id` |
| `backend/app/modules/conversation/schemas.py` | 新增 `QuizReviewContext` + `from_screen_context`（camel/snake 兼容、畸形容错） |
| `backend/app/modules/conversation/teacher_context.py` | 新增 `_build_review_section` 及 `_letter`/`_render_options`/`_answer_text`/`_submitted_answer_text` 助手，注入【正在讲解的题目】节 |
| `backend/tests/test_quiz_review_context.py`（新增） | 7 项：两题各自事实、非本人测验拒绝、题不属测验拒绝、有测验无题明确、无 quiz 上下文不沿用、双命名解析、畸形 ID 容错 |
| `frontend/src/shared/api/api-conversation-service.test.ts` | 新增 quiz 字段序列化断言 |

## 回归测试

```bash
# 后端（T14 验证命令）
cd backend && DATABASE_URL=postgresql+asyncpg://shuangling:shuangling@localhost:5432/shuangling_audit \
  uv run pytest tests/test_quiz_review_context.py tests/test_phase2_screen_context.py -q
# → 15 passed

# 后端全量
DATABASE_URL=postgresql+asyncpg://shuangling:shuangling@localhost:5432/shuangling_audit uv run pytest tests/ -q
# → 365 passed

# 前端
cd frontend && pnpm exec vitest run src/shared/api/api-conversation-service.test.ts
# → 5 passed；tsc --noEmit 0 错误
```

## 浏览器 / 数据

- 专用隔离库 `shuangling_audit`；未触碰开发者库 `shuangling`。
- 真实浏览器验证（答卷页点击两题各看到对应讲解）并入 T25 关键路径回归统一补录；本任务以接口/单测层验证前端序列化与后端解析。

## 尚未验证 / 遗留

- 真实 LLM provider 下"只引用上下文真实内容"的 prompt 构造，以 mock provider 在测试体现（AI_PROVIDER=mock）；真实 provider 由 T23 评测。
- 前端"讲解这道题"按钮（T15）会真正发出这两个新字段；本任务锁定契约与后端解析，页面级接线在 T15。

## tasks/todo.md 状态

实现完成 / 验收完成（后端 365 passed，前端 5 passed + tsc 0 错误）。
