# T20 · 长对话输入与成本口径（20a/20b）

> 日期：2026-09-07。任务 T20（拆 20a/20b，依赖：T01）。

## 已解决的用户问题与行为变化

长对话把全部历史发送给模型，输入无上限；且 usage 用"字符数 × 系数"冒充 token，导致成本口径失真。

- **上下文窗口（20a）**：新增 `context_window.py` 纯函数 `build_input_window`。输入 = 摘要（并入 system prompt）+ 摘要边界之后的最近完整消息，按 `context_window_token_budget` 摘要并取舍；**摘要与最近消息不重叠**（只发 `message_covered_count` 之后的消息），绝不"摘要后又发全量"；始终保留最近一轮（学生的当前问题）。无摘要时使用最近窗口并明确"较早上下文可能不可用"。
- **摘要覆盖边界持久化**：`conversation_summaries` 新增 `message_covered_count`（摘要覆盖到的消息条数），migration `a6b7c8d9e0f1`；摘要 handler 生成时写入 `len(messages)`。既有行默认 0（按无摘要处理，回退最近窗口）。
- **usage 口径（20b）**：`openai_compatible.py` 采集 provider 返回的真实 `usage`（`prompt_tokens`/`completion_tokens`）到 `provider.last_usage`；`_usage_report` 优先用真实值，拿不到则返回 `estimated=True` + 估算方法（`chars_to_tokens`，系数 0.6）——**不再把字符数称作 `input_tokens`/`output_tokens`**。幂等重放（`_replay_stream`）不调用模型、不产生新增模型消耗。
- **配置**：`context_window_token_budget`（默认 3000，ge=200）。

**验收对应**：①200 轮对话输入有上限且最近轮与摘要不重复（窗口按预算截取、只发边界后消息）；②摘要落后/失败不丢最新问题、不阻塞问答（无摘要用最近窗口 + 明确"较早可能不可用"，不抛错）；③真实与估算 usage 分开（`estimated` 布尔 + 方法），模型超时可恢复且幂等重放不重复计费。

## 修改文件

| 文件 | 改动 |
|---|---|
| `backend/app/modules/conversation/context_window.py`（新增） | `build_input_window`/`WindowedChat`/`estimate_tokens` |
| `backend/app/modules/conversation/service.py` | 用 `build_input_window` 构建输入；`_usage_report` 区分真实/估算 usage |
| `backend/app/modules/conversation/schemas.py` | （经 `_usage_report` 输出 usage 形状） |
| `backend/app/ai/base.py` | `AIProvider.last_usage` 可选属性 |
| `backend/app/ai/openai_compatible.py` | 采集 `data.get("usage")` 到 `last_usage` |
| `backend/app/config.py` | `context_window_token_budget` |
| `backend/app/infrastructure/database/models.py` | `ConversationSummary.message_covered_count` |
| `backend/alembic/versions/a6b7c8d9e0f1_add_summary_covered_count.py`（新增） | 加列 + server_default 0 |
| `backend/app/jobs/handlers/conversation.py` | 摘要生成时写 `message_covered_count=len(messages)` |
| `backend/tests/test_context_window.py`（新增） | 7 项：含摘要只发边界后、无摘要最近窗口、预算截断保留最近轮、usage 真实/估算/不冒充 token |

## 回归测试

```bash
# 后端（T20 验证命令）
cd backend && DATABASE_URL=postgresql+asyncpg://shuangling:shuangling@localhost:5432/shuangling_audit \
  uv run pytest tests/test_context_window.py tests/test_ai_provider.py tests/test_conversation_sse.py tests/test_conversation_api.py -q
# → 48 passed
# 后端全量 → 378 passed；alembic upgrade head 通过

# 前端：本任务无前端改动（沿用 T19 的 253 passed + tsc 0 错误）
```

## 浏览器 / 数据

- 专用隔离库 `shuangling_audit`；迁移已应用；未触碰开发者库。
- 真实长对话（200 轮）自动化用 fake provider（本任务）；真实模型耗时/usage 由 T23 评测。

## 尚未验证 / 遗留

- 真实 provider 返回的 usage 字段名可能不同（OpenAI-compatible 一般用 `prompt_tokens`/`completion_tokens`）；若某些兼容端点返回不同 key，`_usage_report` 会走 estimated 分支（安全降级）。真实端点取值由 T23 按实际 provider 校准。
- `message_covered_count` 对既有摘要行为默认 0 → 回退最近窗口（不静默丢消息）；新摘要会写入真实边界。

## tasks/todo.md 状态

实现完成 / 验收完成（后端 378 passed；前端沿用 T19 253 passed）。
