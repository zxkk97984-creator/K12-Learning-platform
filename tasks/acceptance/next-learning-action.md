# T16 · 复习与下一步行动（§6.1）

> 日期：2026-09-07。任务 T16（拆 16a/16b，依赖：T08、T13、T15）。

## 已解决的用户问题与行为变化

首页推荐/继续学习入口多、下一步目标不明确（F08）。现在有一个**统一的"下一步行动"**，按 §6.1 确定性优先级只挑一条，避免首页同时冒出"继续阅读 / 复习弱项 / 读下一本 / 兴趣匹配"多个建议互相争抢。

- **统一行动契约（16a）**：新增 `GET /me/learning-next`，返回 `{type, label, book_id, chapter_id, quiz_session_id, reason, evidence_ids}`。首页与推荐共用这一套规则，不并存两套。优先级：进行中的练习→继续 → 最近完成测验含错题且未复习→回顾错题 → 最近章节已完成且还有下一章→下一章 → 存在阅读位置→继续阅读 → 否则按年级匹配已发布课程→开始第一章；目标已归档时跳过并计算下一条；空数据仍有合法下一步。
- **相似练习来源（16a 数据子任务）**：`quiz_sessions` 新增可空外键 `source_quiz_session_id` / `source_question_id` + 索引 + DTO 透出，旧行保持 NULL；"再练一道"创建的新测验保留来源；创建时校验来源测验/题均归当前学生、题目属于来源测验（否则 422）。
- **复习完成（16a 数据子任务）**：`learning_events` 扩展事件类型 `QUIZ_REVIEW_COMPLETED`（迁移重建 `ck_learning_events_type` + Pydantic Literal）；该事件记录 `quiz_session_id` 与幂等键 `payload.request_id`（同一 request_id 只计一次），并校验测验所有权（非本人测验 → 403）。"未复习" = 该测验无 `QUIZ_REVIEW_COMPLETED` 事件。
- **前端接入（16b）**：`getLearningNext()` adapter；首页新增 `NextActionCard`（单个行动目标 + "去做/去回顾" + REVIEW_QUIZ 可"暂时跳过"）；导航：CONTINUE_QUIZ/REVIEW_QUIZ→答卷、NEXT_CHAPTER/CONTINUE_READING/START_BOOK→reader、无 chapter 时→书目。

**验收对应**：①未完成练习优先恢复且不新建重复测验（priority 1 直接复用 ACTIVE quiz）；②错题回顾进入原答卷（导航到 `/quizzes/{quiz}`）、相似练习建新记录并保留来源（source FK）；③目标归档/空数据有合法下一步，用户可"暂时跳过复习"。

## 修改文件

| 文件 | 改动 |
|---|---|
| `backend/app/infrastructure/database/models.py` | QuizSession 两可空来源 FK；`ck_learning_events_type` 加 `QUIZ_REVIEW_COMPLETED` |
| `backend/alembic/versions/a5b6c7d8e9f1_add_quiz_source_and_review_event.py`（新增） | 建两来源列+FK+索引；重建 ck 约束；已验证 upgrade/check 与降级再升级往返 |
| `backend/app/modules/learning/schemas.py` | `LearningEventType` 加 `QUIZ_REVIEW_COMPLETED` |
| `backend/app/modules/learning/service.py` | `create_event` 对 QUIZ_REVIEW_COMPLETED 幂等 + 所有权校验 |
| `backend/app/modules/quiz/schemas.py` | CreateQuizSessionRequest/DTO 加来源字段 |
| `backend/app/modules/quiz/service.py` | `create_session` 校验并保留来源 |
| `backend/app/modules/recommendation/schemas.py` | 新增 `LearningNextType` + `LearningNextActionDTO` |
| `backend/app/modules/recommendation/service.py` | 新增 `learning_next`（§6.1 优先级） |
| `backend/app/modules/recommendation/router.py` | `GET /me/learning-next` |
| `backend/tests/test_next_learning_action.py`（新增） | 6 项：空数据兜底、阅读优先、完成章→下一章、未复习错题→回顾、复习完成幂等、他人测验拒绝 |
| `frontend/src/shared/api/recommendation-service.ts` | `LearningNextType`/`LearningNextAction` + `getLearningNext()` |
| `frontend/src/shared/api/api-recommendation.ts` | 实现 `getLearningNext` |
| `frontend/src/mocks/services/recommendation-service.ts` | 替身实现 `getLearningNext` |
| `frontend/src/pages/home/use-home-data.ts` | 并发加载 `learningNext`，失败独立降级 |
| `frontend/src/pages/home/components/NextActionCard.tsx` + `HomePage.tsx` | 下一步行动卡 + 导航；接入首页 |
| `frontend/src/pages/home/components/NextActionCard.test.tsx`（新增） | 3 项：渲染+onOpen、loading、REVIEW_QUIZ 跳过 |
| `frontend/src/shared/api/api-recommendation.test.ts` | `getLearningNext` 路径断言 |

## 回归测试

```bash
# 后端（T16 验证命令）
cd backend && DATABASE_URL=postgresql+asyncpg://shuangling:shuangling@localhost:5432/shuangling_audit \
  uv run pytest tests/test_next_learning_action.py tests/test_recommendation_rules.py tests/test_recommendation_api.py -q
# → 17 passed
# 后端全量 → 371 passed；alembic upgrade head + check 通过（迁移已应用、往返验证）

# 前端
cd frontend && pnpm exec tsc --noEmit && pnpm exec vitest run
# → 243 passed，tsc 0 错误
```

## 浏览器 / 数据

- 专用隔离库 `shuangling_audit`；迁移已应用并验证往返；未触碰开发者库 `shuangling`。
- "阅读→练习→错题→讲解→下一章→次日恢复"完整 E2E 与浏览器截图并入 T25 关键路径回归。

## 尚未验证 / 遗留

- 相似练习的 REST 级（conversation→quiz生成→source FK 落库）集成链路依赖 quiz skill（mock LLM）；本任务以守卫逻辑单测 + 迁移验证覆盖，完整生成链路由现有 quiz API 测试与 T25 E2E 覆盖。
- 真实 LLM 下"下一步"推荐不引外部知识待 T23 评测。

## tasks/todo.md 状态

实现完成 / 验收完成（后端 371 passed，前端 243 passed + tsc 0 错误）。
