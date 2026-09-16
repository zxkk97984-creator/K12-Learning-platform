# 07 · API 审计

> 事实源：运行中实例的 `GET /openapi.json`（实测）+ `backend/app/modules/*/router.py` + `frontend/src/shared/api/*.ts`。
> 「前端调用」由 `.audit/B-frontend.md` 的全量路径字面量普查得出。

---

## 0. 总量

| 指标 | 数值 |
| --- | --- |
| OpenAPI 记录的 operation | **73**（含 `GET /health`、`GET /api/v1/ping` 两个探针） |
| 业务 HTTP 端点 | **71** |
| WebSocket | **1**（`/api/v1/voice/ws`，OpenAPI 不记录） |
| 业务路由总数 | **72** |
| 需要 Bearer Token | 69 |
| 公开端点 | 4（`/health`、`/api/v1/ping`、`POST /auth/login`、`GET /files/avatars/{filename}`、`GET /library-assets/{book_slug}/{filename}`） |

> ⚠️ **与文档不符**：`docs/contracts/api-contract.md:390` 声称
> 「实现核对（2026-08-27）… 合计 **68** 个 HTTP；另含 1 个 WebSocket = 69 条路由」。
> 实际为 **71 HTTP + 1 WS**。差值 3 来自 T10/T13/T16 新增端点（见 §3）。

---

## 1. 端点清单（按业务模块）

图例：**FE** = 前端是否调用；**Test** = 是否有后端测试覆盖；**状态**。

### 1.1 Identity（10）

| 方法 路径 | Auth | FE | Test | 备注 |
| --- | --- | --- | --- | --- |
| `POST /auth/login` | public | ✅ | ✅ | 返回 `{access_token, token_type, expires_at, user}` |
| `POST /auth/logout` | token | ✅ | ✅ | 204 |
| `GET /me` | token | ✅ | ✅ | |
| `PATCH /me` | token | ✅ | ✅ | 昵称/年级/`current_teacher_role_id` |
| `GET /me/preferences` | token | ✅ | ✅ | 不存在时自动建默认 |
| `PATCH /me/preferences` | token | ✅ | ✅ | |
| `GET /me/admin` | token | ✅ | ✅ | ADMIN 专用；前端登录/刷新时**服务端复核** |
| `POST /me/avatar` | token | ✅ | ✅ | multipart；2 MB 上限 |
| `GET /files/avatars/{filename}` | public | ✅(img) | ✅ | 路径穿越防护已测 |
| `GET /teacher-roles` | token | ✅ | ✅ | `?enabled=true` |

### 1.2 Content（5）

| 方法 路径 | Auth | FE | Test | 备注 |
| --- | --- | --- | --- | --- |
| `GET /books` | student | ✅ | ✅ | 游标分页 + 年级相交 + tag + 搜索；**强制 PUBLISHED**（`service.py:94-103`）；Redis 缓存按全参数指纹分键 |
| `GET /books/{book_id}` | student | ✅ | ✅ | 非 PUBLISHED → 404 |
| `GET /books/{book_id}/chapters` | student | ✅ | ✅ | 仅 PUBLISHED；注入 `is_completed` |
| `GET /chapters/{chapter_id}` | student | ✅ | ✅ | **同时校验父书 PUBLISHED**（`service.py:287-292`） |
| `GET /knowledge-points/{id}` | student | ⚠️ **否** | ✅ | 前端定义了 `contentService.getKnowledgePoint` 但**无生产调用方** |

### 1.3 Learning（7）

| 方法 路径 | Auth | FE | Test | 备注 |
| --- | --- | --- | --- | --- |
| `POST /learning-sessions` | student | ✅ | ✅ | 唯一 ACTIVE 会话（部分唯一索引） |
| `PATCH /learning-sessions/{id}` | student | ✅ | ✅ | 结束会话 → 写 `reading_settlements`（幂等） |
| `POST /learning-events` | student | ✅ | ✅ | append-only |
| `GET /me/progress` | student | ✅ | ✅ | |
| `GET /me/progress/{book_id}` | student | ✅ | ✅ | |
| `PUT /me/progress/{book_id}` | student | ✅ | ✅ | |
| **`PUT /me/chapters/{chapter_id}/completion`** | student | ✅ | ✅ | **新增（T13，未提交）**；幂等 |
| `GET /me/learning-events` | student | ⚠️ **否** | ✅ | 前端未调用 |

### 1.4 Conversation（7）+ Voice（1 WS）

| 方法 路径 | Auth | FE | Test | 备注 |
| --- | --- | --- | --- | --- |
| `GET /conversations` | student | ✅ | ✅ | 游标 |
| `POST /conversations` | student | ✅ | ✅ | 支持 `Idempotency-Key` |
| `GET /conversations/{id}` | student | ✅ | ✅ | |
| `PATCH /conversations/{id}` | student | ✅ | ✅ | ARCHIVED/DELETED |
| **`POST /conversations/{id}/messages`** | student | ✅ | ✅ | **SSE 流式；会话锁 + 幂等重放** |
| `GET /conversations/{id}/messages` | student | ✅ | ✅ | |
| `GET /conversations/{id}/summary` | student | ✅ | ✅ | |
| `WS /api/v1/voice/ws` | token(查询参数) | ✅ | ✅ | 双向音频；无 TTS 时明确返回 `TTS_UNAVAILABLE` |

### 1.5 Quiz（8）

| 方法 路径 | Auth | FE | Test | 备注 |
| --- | --- | --- | --- | --- |
| `POST /quiz-sessions` | student | ⚠️ **否** | ✅ | **前端定义了但无生产调用**；出题实际由对话 SSE 的 `tool.result` 驱动 |
| `GET /quiz-sessions` | student | ✅ | ✅ | |
| `GET /quiz-sessions/{id}` | student | ✅ | ✅ | |
| `GET /quiz-sessions/{id}/questions` | student | ✅ | ✅ | 未作答时**不下发答案** |
| `POST /quiz-sessions/{id}/questions/{qid}/answers` | student | ✅ | ✅ | 幂等；服务端判分 |
| `POST /quiz-sessions/{id}/questions/{qid}/hints` | student | ✅ | ✅ | |
| `GET /quiz-sessions/{id}/answers` | student | ✅ | ✅ | |
| `GET /quiz-sessions/{id}/interactions` | student | ✅ | ✅ | |

### 1.6 Memory（8）

| 方法 路径 | Auth | FE | Test | 备注 |
| --- | --- | --- | --- | --- |
| `GET /me/memories` | student | ✅ | ✅ | |
| `PATCH /me/memories/{id}` | student | ✅ | ✅ | CONFIRM/DISPUTE/FORGET/EDIT |
| `GET /me/evidence/{id}` | student | ✅ | ✅ | |
| `GET /me/insights` | student | ✅ | ✅ | 5 档定性 |
| `GET /me/insights/{id}` | student | ✅ | ✅ | 证据在 `meta.evidence` |
| `GET /me/episodes` | student | ✅ | ✅ | |
| `GET /me/episodes/{id}` | student | ✅ | ✅ | |
| **`GET /me/agent.md`** | student | ⚠️ **否** | ✅ | 后端真实渲染（实测 125 KB）；**前端自己合成了一份**（`docs/04` §4.1） |

### 1.7 Recommendation（3）

| 方法 路径 | Auth | FE | Test | 备注 |
| --- | --- | --- | --- | --- |
| `GET /me/recommendations` | student | ✅ | ✅ | 规则式，带 `reason` + `evidence_ids` |
| `POST /me/recommendations/{id}/dismiss` | student | ✅ | ✅ | |
| **`GET /me/learning-next`** | student | ✅ | ✅ | **新增（T16，未提交）** |

### 1.8 Knowledge（4）

| 方法 路径 | Auth | FE | Test | 备注 |
| --- | --- | --- | --- | --- |
| `GET /knowledge/resources` | **admin** | ✅ | ✅ | 后台资源表用此端点（6 种 status 各拉一次） |
| `GET /knowledge/resources/{id}` | **admin** | ⚠️ **否** | ✅ | 无单资源详情 UI |
| `GET /knowledge/resources/{id}/chunks` | **admin** | ⚠️ **否** | ✅ | 无 chunk 检查器 UI |
| `POST /knowledge/search` | student | ⚠️ **否** | ✅ | **RAG 检索入口，前端无直接查询能力**（检索只在对话 SSE 内部发生） |

### 1.9 Admin（17）

| 方法 路径 | Auth | FE | Test | 备注 |
| --- | --- | --- | --- | --- |
| `GET /admin/stats` | admin | ✅ | ✅ | |
| `GET /admin/books` | admin | ✅ | ✅ | |
| `POST /admin/books` | admin | ✅ | ✅ | |
| `GET /admin/books/{id}` | admin | ⚠️ **否** | ✅ | 无单书详情 UI |
| `PATCH /admin/books/{id}` | admin | ✅ | ✅ | |
| `POST /admin/books/{id}/chapters` | admin | ✅ | ✅ | |
| `PATCH /admin/chapters/{id}` | admin | ✅ | ✅ | |
| `POST /admin/chapters/{id}/content-blocks` | admin | ✅ | ✅ | 只能**创建**内容块 |
| `PATCH /admin/content-blocks/{id}` | admin | ⚠️ **否** | ✅ | **无编辑 UI** → 内容块创建后不可改 |
| `POST /admin/knowledge-points` | admin | ✅ | ✅ | 只能**创建** |
| `PATCH /admin/knowledge-points/{id}` | admin | ⚠️ **否** | ✅ | **无编辑 UI** |
| `POST /admin/knowledge/resources` | admin | ✅ | ✅ | multipart；202 入队 `knowledge_ingest` |
| `PATCH /admin/knowledge/resources/{id}` | admin | ⚠️ **否** | ✅ | **上传后无法修正 license/copyright/source** |
| `POST /admin/knowledge/resources/{id}/reprocess` | admin | ✅ | ✅ | |
| `GET /admin/teacher-roles` | admin | ✅ | ✅ | |
| `POST /admin/teacher-roles` | admin | ✅ | ✅ | |
| `PATCH /admin/teacher-roles/{id}` | admin | ✅ | ✅ | |

### 1.10 Library assets（1，新增）

| 方法 路径 | Auth | FE | Test | 备注 |
| --- | --- | --- | --- | --- |
| `GET /library-assets/{book_slug}/{filename}` | public | ✅(img) | ✅ | **新增（T10/T11，未提交）** 教学图片服务 |

### 1.11 探针（2）

`GET /health`（不依赖 DB）、`GET /api/v1/ping`、`GET /metrics`（`include_in_schema=False`）。

---

## 2. 后端存在但前端未使用的端点（9）

| 端点 | 影响 |
| --- | --- |
| `POST /knowledge/search` | **最显著**：RAG 检索能力对学生不可直接触达（只在对话内部使用）。属设计选择，非缺陷 |
| `GET /me/agent.md` | **前端自己合成了一份同名产物**（`ArchiveDocCard.tsx:47`），后端能力无消费者 |
| `GET /knowledge/resources/{id}` | 后台无法查看单资源详情 |
| `GET /knowledge/resources/{id}/chunks` | 后台无法检查分块质量 |
| `PATCH /admin/content-blocks/{id}` | **内容块创建后无法编辑** |
| `PATCH /admin/knowledge-points/{id}` | **知识点创建后无法编辑** |
| `PATCH /admin/knowledge/resources/{id}` | **资源元数据（许可/版权/来源）上传后无法修正** |
| `GET /admin/books/{id}` | 无单书详情 |
| `GET /me/learning-events` | 前端用 `GET /me/progress` 与画像接口替代 |

**后端测试覆盖**：上述 9 个端点**全部有测试**（`test_admin_api.py`、`test_knowledge_api.py`、
`test_agent_md.py` 等），所以这是「已实现且有测试但无 UI」的**未接入**，而非「未实现」。

---

## 3. 前端调用但文档未记录 / 可能不存在的端点

### 3.1 文档缺失（3 个，全部来自未提交的 T 轮）

`docs/contracts/api-contract.md` 的端点总表中**不存在**这 3 个端点：

| 端点 | 引入 |
| --- | --- |
| `PUT /api/v1/me/chapters/{chapter_id}/completion` | T13 章节完成闭环 |
| `GET /api/v1/me/learning-next` | T16 复习/下一步行动 |
| `GET /api/v1/library-assets/{book_slug}/{filename}` | T10/T11 教学图片契约 |

全量比对结果：**73 个实际 operation 中，只有这 3 个未在 `api-contract.md` 中被提及。**
（其余 70 个均可检索到。）

### 3.2 前端调用不存在的 API

**未发现。** 前端所有路径字面量均能在后端路由表中找到对应（含 template literal 参数化路径）。

### 3.3 参数 / Response Schema 不一致

| 项 | 说明 |
| --- | --- |
| 分页字段 | 后端统一 `{data, meta:{next_cursor, has_more, total}}`；前端 `http.ts` 早期版本**丢弃 meta**，已在 T04/T05 修复为 `apiRequestEnvelope` |
| Quiz 题量 | `skill.py:176-183` 审校题来源可能返回少于 `question_count` 的题目，而 `result_summary`（`:295-299`）仍按 `question_count` 声称 → **响应内部自相矛盾** |
| Token 计量字段 | `quiz/service.py:845-850, 914-919` 把**字符数**填入 `input_tokens`/`output_tokens`，与 `conversation/service.py:163-186` 的真实 usage 语义不一致 |
| 401 处理 | `api-student-service.ts:58-77`（uploadAvatar）与 `learning-service.ts:102-130` 用原生 `fetch`，**未派发全局 401 事件** |

---

## 4. 错误处理约定（实际生效）

所有业务错误统一为：

```json
{ "error": { "code": "SNAKE_UPPER_CODE", "message": "human readable", "details": {...} } }
```

由 `app/api/envelope.py` + `main.py:110-141` 的两个 exception handler 强制。
前端 `http.ts:99-110` 解析为结构化 `ApiError`（含 `requestId` 与 `retryAfterMs`）。

常见 code：`UNAUTHENTICATED`、`ACCOUNT_DISABLED`、`FORBIDDEN`、`ADMIN_ONLY`、
`ADMIN_PROFILE_REQUIRED`、`VALIDATION_ERROR`、`RATE_LIMITED`、`BOOK_NOT_FOUND`、
`CHAPTER_NOT_FOUND`、`RESOURCE_NOT_FOUND`、`INVALID_CONTENT_STATUS`、`QUIZ_SKILL_ERROR`、`TTS_UNAVAILABLE`。

---

## 5. 鉴权矩阵小结

| 依赖 | 语义 | 使用者 |
| --- | --- | --- |
| `require_student` | `user_type == 'STUDENT'`，否则 403 | content / learning / conversation / memory / quiz / recommendation / `knowledge/search` / voice |
| `require_admin` | `user_type=='ADMIN'` **且** `admins` 行存在且 `enabled` | 全部 `/admin/*` + 全部 `/knowledge/resources*` |
| `get_current_user` | 仅需有效 token（无角色要求） | identity 的 `/me*`、`/teacher-roles` |
| public | 无鉴权 | `/health`、`/ping`、`/auth/login`、`/files/avatars/*`、`/library-assets/*` |

> ⚠️ **`admins.role_level`（SUPERVISOR / CONTENT_EDITOR）未被任何授权逻辑读取** ——
> 两个等级目前拥有完全相同的权限。见 `docs/13-technical-debt.md`。
