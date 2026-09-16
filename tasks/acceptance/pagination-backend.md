# T04 · 分页与筛选后端契约

> 日期：2026-09-06。任务 T04（M，依赖：T02）。

## 已解决的用户问题与行为变化

书库"全部"只有第一页、搜索找不到后续课程的问题，后端契约已完整支持：

- **search 全库过滤后分页**：`GET /books?search=...` 在后端对 title/description/author 做 `ILIKE` 全库过滤（绑定参数），不先拉全量再本地搜；search 参数 `max_length=100` 且 trim。
- **年级区间相交**：`grade_min` 表示为 `book.grade_max >= grade_min`（覆盖到该年级以上的书），`grade_max` 为 `book.grade_min <= grade_max`；跨学段书可被相交范围命中。
- **缓存键含全部筛选**：`search/grade_min/grade_max/tag/status/limit/cursor` 全部进入 cache key 指纹，不同查询不会缓存串用。
- **总数不与页长混同**：新增 `with_total=true` 时返回全库匹配 `total`；未请求时 `meta.total=None`（`BookPageMeta` 新增可选字段）；`total` 由独立 `COUNT` 统计，绝不以当前页长度冒充。
- **章数只计已发布章节**：书列表的 `chapter_count` 与书的 `chapter_count` 只统计 PUBLISHED 章节（与 T02 一致性）。

## 修改文件

| 文件 | 改动 |
|---|---|
| `backend/app/modules/content/schemas.py` | `BookPageMeta` 新增 `total: int | None = None` |
| `backend/app/modules/content/service.py` | `list_books` 增加 `search`/`with_total`；grade 改区间相交；`_books_cache_key` 纳入 search；`counts` 只计 PUBLISHED 章；`with_total` 用独立 count |
| `backend/app/modules/content/router.py` | `/books` 增加 `search`（≤100）、`with_total` 参数并传入 service |
| `backend/tests/test_content_api.py` | `test_grade_filter_intersection`；新增 `TestBookPagination` 类（25 本独立夹具：20+5 分页无重复、独有词命中、区间相交、缓存不串用、total 不为页长） |

## 回归测试

```bash
DATABASE_URL=postgresql+asyncpg://shuangling:shuangling@localhost:5432/shuangling_audit uv run pytest -q
```

结果：**339 passed**, 4 warnings（均为既有弃用警告，与本次改动无关）。

## 数据 / 兼容

- 专用隔离库 `shuangling_audit`；新增 25 本 `PGN` 前缀夹具书（独立 UUID，隔离测试命名空间），未触碰用户开发库。
- 旧 `getBooks` 前端调用暂时仍只能取一页（T05 改前端为 `getBooksPage` + 加载更多）。
- 兼容既有 `list_books` 调用（新增参数均为可选关键字）。

## 尚未验证 / 遗留

- 前端 UI 分页/搜索/加载更多等属 T05（前端契约新增 `getBooksPage`/信封解析）。
- `meta.total` 可选；前端按需请求。

## tasks/todo.md 状态

实现完成 / 验收完成（全量后端 339 passed）。
