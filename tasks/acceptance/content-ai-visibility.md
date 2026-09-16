# T03 · RAG 与出题同步遵守内容可见性

> 日期：2026-09-06。任务 T03（M，依赖：T02）。

## 已解决的用户问题与行为变化

学生端通过"出题/检索"绕过内容可见性的残余路径已封堵：

- **章节出题核实归属与发布状态**：`load_chapter_source` 现在只在章节与其父书**均为 PUBLISHED** 时返回出题素材；否则返回 None（调用方走既有"章节不可用"显式错误或审计过的题库回退，绝不静默用无关内容出题）。
- **篡改 chapter/book 组合被拒绝**：若调用方传入的 `book_id` 与章节实际 `chapter_id` 归属不符，`load_chapter_source` 返回 None；`QuizService.create_session` 也明确校验 `chapter.book_id != book_id` → 422。
- **非 PUBLISHED 书不可出题**：`QuizService.create_session` 对 DRAFT/ARCHIVED 书返回 404，不再允许从未发布书出题。
- **RAG 不从失效资源检索**：`KnowledgeService.search` 与 `_keyword_fallback` 现在 INNER JOIN `knowledge_resources` 并要求 `kr.status='READY'`，因此 FAILED 等非可用资源的 chunk 不再被检索返回（即使 chunk 本身标了 READY）。
- **历史答卷仍可读**：答卷题目与答案存于 `questions_snapshot`（快照），T03 只限制"新访问"内容，不误伤既有答卷（既有测试 `test_phase3` linkage 通过验证）。

## 修改文件

| 文件 | 改动 |
|---|---|
| `backend/app/modules/quiz/chapter_source.py` | `load_chapter_source` 增加章节+父书 PUBLISHED 校验 + book/chapter 归属匹配校验 |
| `backend/app/modules/quiz/service.py` | `create_session` 增加 book 存在 + PUBLISHED、chapter PUBLISHED + 归属校验 |
| `backend/app/modules/knowledge/service.py` | `search` SQL 用 `kc` 别名并 JOIN `knowledge_resources kr` 且 `kr.status='READY'`；`_keyword_fallback` 同样 JOIN 并过滤资源状态 |
| `backend/tests/test_content_ai_visibility.py`（新增） | 8 项：章节源可见性、quiz API 可见性、RAG 失效资源排除 |
| `backend/tests/test_phase2_screen_context.py` | 夹具书升级为 PUBLISHED（满足 T03 守卫；补 `.else` 修复历史 DRAFT 残留） |
| `backend/tests/test_phase3_stats_recommendation.py` | 同上：书本状态强制 PUBLISHED |

## 回归测试

```bash
DATABASE_URL=postgresql+asyncpg://shuangling:shuangling@localhost:5432/shuangling_audit uv run pytest -q
```

结果：**334 passed**, 3 warnings（均为既有 StarletteDeprecation / PytestRemovedIn10，与本次改动无关）。基线为 313 passed，+21 来自新增用例。

## 浏览器 / 数据

- 专用隔离库 `shuangling_audit`；未触碰用户开发库 `shuangling`。
- 未做真实浏览器截图（后端可见性改动，前端经由接口间接受益；待 T01 授权补图）。

## 尚未验证 / 遗留

- 真实外部 LLM 输入中"不包含不可见内容"的断言，当前以 deterministic/mock provider 体现（测试环境 AI_PROVIDER=mock）。真实 provider 的 prompt 构造可复核 `_try_llm_generate`（只接收 `chapter_source` 的已过滤内容）。真实 provider 单独由 T23 评测。
- 若后续资源引入"ARCHIVED"状态，需同步在此过滤（当前资源无 ARCHIVED 枚举，状态为 UPLOADED/PARSING/CHUNKING/INDEXING/READY/FAILED）。

## tasks/todo.md 状态

实现完成 / 验收完成（全量后端 334 passed）。
