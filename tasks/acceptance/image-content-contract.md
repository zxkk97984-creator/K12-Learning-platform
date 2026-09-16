# T10 · 图片内容契约与导入

> 日期：2026-09-07。任务 T10（M，依赖：T01）。

## 已解决的用户问题与行为变化

图解"没有图"、IMAGE 内容不渲染的链路根因（内容契约缺资源引用）已修复：

- **FIG 内容契约扩展**：`FIG: 描述 :: 图注`（旧式兼容）与新 `FIG: 描述 :: 图注 :: assets/文件.svg`（可选资源引用）。第三个 `::` 段**仅当严格匹配 `assets/<文件名>`** 才视为资源，避免把含 `::` 的普通图注（如 robot-mind-ethics 的"权利…阶梯"）误判。
- **导入产真实字段**：导入器为 FIGURE 块写入 `content = {alt, caption}`（无资源）或 `{alt, caption, src}`（有资源）；`src` 为公开静态 URL `/api/v1/library-assets/<slug>/<file>`；不伪造 src——缺资源的旧图解如实保留 `alt/caption` 由前端明确显示"暂无图解"。
- **安全资源校验（R8）**：`validate_library` 增加 R8 规则：仅允许 `assets/<文件名>` 相对路径、白名单扩展名（svg/png/webp/jpg/jpeg）、必须落在本书目录内、文件必须存在；绝对路径/`..`/反斜杠/非法扩展名/缺文件 → R8 拒绝。R8 与结构校验（R1–R7）区分，报告可分辨"结构通过"与"图像完整性缺口"。
- **静态资源路由**：`GET /api/v1/library-assets/{book_slug}/{filename}` 只读分发书内资产；防路径穿越（resolve 后必须落在 assets/ 下）、非法扩展名/缺文件 404；图片不经鉴权（书内公开内容）。

## 修改文件

| 文件 | 改动 |
|---|---|
| `backend/app/scripts/validate_library.py` | `build_content` FIG 三段解析（仅 assets/* 视为资源）+ 常量提前；`_validate_fig_asset` R8 校验；`validate_chapter` FIG 分支调用 |
| `backend/app/scripts/import_library.py` | `_fig_content` 补 src/alt、去 aria_label/asset；`load_book_files` 对 FIG 调用 |
| `backend/app/modules/content/assets.py`（新增） | 静态资源路由（防穿越/白名单/404） |
| `backend/app/main.py` | 注册 `library_assets_router` |
| `backend/data/library/README.md` | FIG 文档更新（三段式 + content 形状） |
| `backend/tests/test_library_figures.py`（新增） | 11+3 项：build_content 三段/旧式、R8 非法路径/扩展名/缺文件、静态路由穿越/未知书/缺文件、import 无伪 src、import 有资源加 src |

## 回归测试

```bash
DATABASE_URL=postgresql+asyncpg://shuangling:shuangling@localhost:5432/shuangling_audit uv run pytest -q
# 352 passed（基线 339，+13 来自 T10）
```

- `validate_library --all`（经 import `_require_pass` 内联验证）：`ml-how-machines-learn` 导入成功（5 章 / 81 块，7 kp），确认 R8 不误伤正规内容。
- 隔离库 `shuangling_audit` 导入该书后 FIGURE block `content` 为 `{alt,caption}`（无 src，不伪造）。

## 尚未验证 / 遗留

- 真实教学图解资产（T12/T22a）尚未添加到任何书——表样书 `assets/` 目录为空；等 T12 补图后，含 `assets/*` 引用的 FIG 才会有 `src`。
- 前端渲染 IMAGE/FIGURE（含加载失败重试、等价文字）在 T11。
- 静态路由在 `main.py` 生效取决于后端重启；运行中的 :8002 为旧代码（无此路由），前端图片验证在重启后或 T25 E2E。

## tasks/todo.md 状态

实现完成 / 验收完成（后端 352 passed；契约/校验/导入/静态路由齐备）。
