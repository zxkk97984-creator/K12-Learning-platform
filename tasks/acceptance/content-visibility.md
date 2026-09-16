# T02 · 学生内容发布边界

> 日期：2026-09-06。任务 T02（M，依赖：T01）。证据级别：代码确认 → 已复现 → 已修复。

## 已解决的用户问题与行为变化

学生端内容访问边界不再完整的问题已修复：

- **学生 list 无法再以 query 指定未发布内容**：`GET /books?status=DRAFT` 或 `?status=ARCHIVED` 返回 **422**（`INVALID_CONTENT_STATUS`），之前会把该状态的书单返回。
- **草稿章节不进入已发布书的目录**：`GET /books/{id}/chapters` 只返回 PUBLISHED 章节；之前会返回该书全部章节。
- **书本章数只计已发布章节**：`GET /books/{id}` 的 `chapter_count` 只统计 PUBLISHED 章节；之前把草稿章节也计入。
- **章节详情同时校验章节与父书**：`GET /chapters/{id}` 现在要求该章节 `PUBLISHED` **且** 其父书 `PUBLISHED`，否则 404；之前只判断章节存在（可读到草稿章节或草稿书内的章节）。
- **知识点详情校验 ACTIVE**：`GET /knowledge-points/{id}` 对 `ARCHIVED` 知识点返回 404，不再返回已归档点。
- **缓存命中同样执行规则**：服务层在 `cache_get` **之前**拒绝非 PUBLISHED 状态，冷/热缓存都不会绕过可见性。

## 修改文件

| 文件 | 改动 |
|---|---|
| `backend/app/modules/content/router.py` | `list_books` 增加 `status != "PUBLISHED"` → 422 守卫；引入 `HTTPException` 导入 |
| `backend/app/modules/content/service.py` | `list_books` 服务层拒绝非 PUBLISHED（缓存命中前）；`get_book` 章数只计 PUBLISHED；`list_chapters` 只返回 PUBLISHED；`get_chapter_detail` 校验章节+父书均 PUBLISHED；`get_knowledge_point` 校验 ACTIVE |
| `backend/tests/test_content_visibility.py`（新增） | 10 项 HTTP 边界 + 3 项服务层守卫 |

管理员编辑预览继续走 `/admin/*` 路由，不受影响；`test_admin_api.py` 全通过。

## 回归测试

```bash
DATABASE_URL=postgresql+asyncpg://shuangling:shuangling@localhost:5432/shuangling_audit \
  uv run pytest -q tests/test_content_visibility.py tests/test_content_api.py \
  tests/test_content_cache.py tests/test_admin_api.py
```

结果：**46 passed**，1 warning（StarletteDeprecation，与本次改动无关）。

## 浏览器 / 数据

- 专用隔离库 `shuangling_audit`（agent 新建、可丢弃）；未触碰用户开发库 `shuangling`。
- 构造 published/draft/archived 父子状态组合；冷（新查询）+ 热（缓存命中）各验证一次。
- 未做真实浏览器截图（需演示账号授权，见 T01 记录）；该改动为后端可见性，前端经由接口间接受益。

## 尚未验证 / 遗留

- 学生"已知 UUID 越权"在本轮以接口层守卫验证；真实浏览器端到端越权（前端绕过）留 T25 E2E 补。
- T03 会将同一可见性守卫桥接到 RAG/出题，避免"前端不显示但仍可被检索"的残余路径。

## tasks/todo.md 状态

实现完成 / 验收完成（接口回归全绿；E2E 越权补测归 T25）。
