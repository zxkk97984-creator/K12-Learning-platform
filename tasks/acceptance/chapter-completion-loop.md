# T13 · 章节完成与继续学习闭环

> 日期：2026-09-07。任务 T13（拆 13a/13b/13c，依赖：T02、T11）。

## 已解决的用户问题与行为变化

章节末尾原来缺乏"明确收尾"，且"完成"语义被滚动事件污染（F07）：滚动到末块只发 `CHAPTER_FINISHED` 事件，却可能被当成"学完这本书"，导致完成数/进度口径失真。现在改为**唯一的、主动的"完成"事实**，并串联下一章/练习的下一步行动。

- **统一完成语义（13a/13b）**：新增 `chapter_completions` 事实表，唯一约束 `(student_id, chapter_id)`，`source ∈ {EXPLICIT, LEGACY_EVENT}`。幂等 `PUT /me/chapters/{chapter_id}/completion`：重复/并发提交只计一次；滚动到章节末尾**不会**标为完成（F07 口径），历史 `CHAPTER_FINISHED` 事件也**不**回填为主动完成。
- **诚实完成口径**：书籍"已完成" = 本书所有**已发布**章节（草稿不计）均已在此表完成；返回 `book_completed / completed_chapters / published_chapters`。目录与章节详情 DTO 填充真实 `is_completed`。
- **下一步行动（13c）**：Reader 每章末尾新增 `ChapterCompletionCard`，显示"完成本章"按钮；提交后结果卡给出"下一章 →"（本书还有后续已发布章节时）或"再练一题巩固"，另有"给我出题"练习入口。失败保留可重试操作；`alreadyCompleted` 状态直接进入结果态。
- **可见性守卫**：未发布书/章（DRAFT/ARCHIVED）、chapter 与 book 归属不匹配 → 404/422，与 T02/T03 一致。

## 修改文件

| 文件 | 改动 |
|---|---|
| `backend/app/infrastructure/database/models.py` | 新增 `ChapterCompletion` 表（唯一约束、`source` CHECK、`(student_id, book_id)` 索引） |
| `backend/alembic/versions/a4b5c6d7e8f9_add_chapter_completions.py`（新增） | 建表 + 索引 + CHECK；downgrade 回退；已验证 upgrade/check 与降级再升级往返 |
| `backend/app/modules/learning/schemas.py` | 新增 `ChapterCompletionDTO` |
| `backend/app/modules/learning/service.py` | `mark_chapter_completed` 幂等写入 + 进度更新 + 诚实完成计数 |
| `backend/app/modules/learning/router.py` | `PUT /me/chapters/{chapter_id}/completion` |
| `backend/app/modules/content/schemas.py`、`service.py` | `ChapterDTO.is_completed`（目录/详情填充） |
| `backend/app/modules/content/router.py` | `list_chapters` / `get_chapter_detail` 解析学生并填完成态 |
| `backend/tests/test_chapter_completion.py`（新增） | 6 项：幂等、整书完成、目录/详情完成态、未发布拒绝 |
| `backend/tests/test_quiz_api.py` | 修复隔离库跨套件残留导致的 16 项失败（见下） |
| `frontend/src/shared/api/learning-service.ts` | 新增 `markChapterCompleted` + `ChapterCompletionResult` DTO |
| `frontend/src/pages/reader/ChapterCompletionCard.tsx`（新增） | 完成按钮 + 结果卡（下一章/练习）+ 失败重试 |
| `frontend/src/pages/reader/ReaderPage.tsx` | 章末接入 `ChapterCompletionCard` |
| `frontend/src/shared/api/learning-service.test.ts` | `markChapterCompleted` 2 项 |
| `frontend/src/pages/reader/ChapterCompletionCard.test.tsx`（新增） | 7 项：默认不自动完成、pending/结果、整书完成、末章再练、失败重试、alreadyCompleted、下一章导航 |

## 关键修复：隔离库跨套件残留导致 16 项 quiz 测试失败

`test_quiz_api.py` 在 T13 后端改完后出现 **16 failed**（`POST /quiz-sessions` 全部 422）。定位后确认不是 T13 回归，而是**隔离库持久化 + 固定 UUID 夹具彼此冲突**：

- `test_quiz_api.py` 的 `CHAPTER_ID = c5000000-…-000001` 与 `test_chapter_completion.py` 的 `CH1 = c5000000-…-000001` **是同一个 UUID**，却分属不同书（`b5000000` vs `d5000000`）。
- `test_quiz_api` 的 `_ensure_content` 只在该行 `is None` 时创建，**不会在已存在时重新断言 `book_id`**。于是先跑的完成测试把该章绑定到 `d5000000`，随后的 quiz 测试**沿用旧归属** → 后端返回 `chapter does not belong to book`（422）。
- 修复：`_ensure_content` 改为自愈——即使行已存在也重新断言 `book_id / status / chapter_order`，与既有的 `test_chapter_completion` 自愈清理模式一致。

这属于测试隔离库在多次套件运行间累积状态的固有问题（隔离库不重建）。全量套件由 T13 前的 352 → 现 **358 passed**。

## 回归测试

```bash
# 后端（T13 验证命令）
cd backend && DATABASE_URL=postgresql+asyncpg://shuangling:shuangling@localhost:5432/shuangling_audit \
  uv run pytest tests/test_chapter_completion.py tests/test_learning_api.py tests/test_phase3_stats_recommendation.py -q
# → 35 passed

# 后端全量
DATABASE_URL=postgresql+asyncpg://shuangling:shuangling@localhost:5432/shuangling_audit uv run pytest tests/ -q
# → 358 passed

# 前端（新增 + reader/learning 相关）
cd frontend && pnpm exec vitest run src/pages/reader src/features/learning src/shared/api/learning-service.test.ts
# → 36 passed；tsc --noEmit 0 错误
```

## 浏览器 / 数据

- 专用隔离库 `shuangling_audit`；未触碰开发者库 `shuangling`，未清空/重置既有数据。
- 首次端到端演示：用 README demo 账号 `xiaoming` 打开一本书的章末，点击"完成本章"，确认目录/首页完成态一致；截图与真实浏览器验证待 T25 关键路径回归统一补录。

## 尚未验证 / 遗留

- 前端"刷新后目录/首页/书本详情完成态一致"的跨页面一致断言，已在单测层覆盖后端 DTO 与组件行为；真实浏览器跨页刷新一致性由 T25 E2E 回归验证。
- 真实 LLM 评测（T23）确认"完成"是否影响推荐等内容，属 T23 范畴，未在本任务硬编码。

## tasks/todo.md 状态

实现完成 / 验收完成（后端 358 passed，前端相关 36 passed + tsc 0 错误）。
