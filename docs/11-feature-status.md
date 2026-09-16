# 11 · 功能完成度审计

> 状态口径：**COMPLETE** / **PARTIAL** / **MOCK** / **STUB** / **DISCONNECTED** / **BROKEN** / **NOT_IMPLEMENTED** / **UNKNOWN**
>
> ⚠️ **「代码文件存在」≠「功能已实现」**。本表按「前端 / 后端 / 数据库 / 真实联通 / 测试 / 依赖 Mock / 缺口 / 证据」逐项判定。
> 判定依据是实际调用关系与运行实测，不是文件名。

---

## A. 学生端

| 功能 | 前端 | 后端 | DB | 联通 | 测试 | 依赖 Mock | 状态 | 主要缺口 / 证据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 登录 / 登出 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | 实测 200 + token |
| 会话恢复（刷新） | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | ADMIN 刷新时服务端复核 `/me/admin` |
| 账号禁用即时失效 | — | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | `deps.py:41-45` 每请求查 status |
| 账号切换隔离 | ✅ | — | — | ✅ | ✅ | 否 | **PARTIAL** | 桌宠 / toast / ScreenContext 3 处状态残留 |
| 个人资料编辑 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | |
| 头像上传 / 展示 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | 路径穿越防护已测 |
| 学习偏好设置 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | |
| **设置页加载失败** | ⚠️ | ✅ | — | ⚠️ | ❌ | 否 | **BROKEN** | 空 catch → 软锁（`SettingsPage.tsx:96-115`） |
| 教师风格选择 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | 2 个风格（`teacher_roles`） |
| 书库分页 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | 后端搜索 + 游标 |
| 书库搜索 / 筛选 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | 后端全库 ILIKE，非本地过滤 |
| 书本详情 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | |
| 章节阅读（内容块） | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | |
| 教学图片渲染 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | `/library-assets/{slug}/{file}`（T10–T12） |
| **阅读器错误态** | ⚠️ | ✅ | — | ⚠️ | ❌ | 否 | **PARTIAL** | 请求失败伪造空章 → 「本章暂无内容」，无重试 |
| 内容可见性边界 | — | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | Service 层守卫，缓存也绕不过（T02/T03） |
| 页面感知对话（ScreenContext） | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | 3 条通道真实发送 |
| AI 对话（SSE） | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **PARTIAL** | 传输真，**token 流是伪造的** |
| 对话幂等重放 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | `Idempotency-Key` |
| 对话串行锁 | — | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | Redis + asyncio 降级 |
| **长对话上下文** | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **BROKEN** | 摘要删历史 + 谎报覆盖（P0-3） |
| RAG 检索 | — | ✅ | ✅ | ✅ | ✅ | 否 | **PARTIAL** | 真 pgvector，但 58% 知识因维度不可达 |
| **情节记忆被 AI 使用** | ✅(只读) | ⚠️ | ✅ | ❌ | ✅ | 否 | **DISCONNECTED** | `embedding` 硬编码 None（239/0） |
| 长期记忆列表 / 操作 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | CONFIRM/DISPUTE/FORGET/EDIT |
| 遗忘 / 否认不复活 | — | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | T24，按内容对全部状态去重 |
| 学习画像（5 档定性） | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | 无百分比，符合产品约束 |
| `.agent.md` | ⚠️ | ✅ | ✅ | ❌ | ✅ | 否 | **PARTIAL** | 前端自造产物；后端端点无消费者且标题硬编码 |
| 学习会话 / 时长结算 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | 结算天然幂等 |
| 学习事件 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | append-only |
| 章节完成 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | 但线上仅 2 行数据 |
| 继续学习 / 下一步行动 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | `/me/learning-next` |
| 随堂测验（出题） | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | **PARTIAL** | 89% 来自 8 题硬编码题库 |
| **审校题源** | — | ✅ | ✅ | ❌ | ✅ | 否 | **DISCONNECTED** | 未接入 bootstrap + 导入器 bug（P1-3） |
| 测验判分 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | 服务端权威 |
| 答案隐藏（未答不下发） | — | ✅ | — | ✅ | ✅ | 否 | **COMPLETE** | |
| AI 反馈 | ✅ | ⚠️ | ✅ | ✅ | ✅ | 否 | **MOCK** | 两句字面量字符串（`quiz/service.py:594-598`） |
| 提示（hint） | ✅ | ⚠️ | ✅ | ✅ | ✅ | 否 | **PARTIAL** | 非题库题 3 级返回同一句话 |
| 错题讲解 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | T14 上下文契约 |
| 再练一道 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | T16 `source_quiz_session_id` |
| 规则推荐 | ✅ | ✅ | ✅ | ✅ | ✅ | 否 | **COMPLETE** | 带 reason + evidence_ids |
| 语音输入（ASR） | ✅ | ✅ | — | ✅ | 部分 | ❌ | **PARTIAL** | 阿里云实时 ASR 真接入；`audio-capture.ts` 无测试 |
| 语音合成（TTS） | ✅ | ✅ | — | ⚠️ | ✅ | 否 | **DISCONNECTED** | `TTS_PROVIDER` 未配置 → `TTS_UNAVAILABLE`（**有意降级**） |
| 桌宠（Companion） | ✅ | — | — | — | 部分 | 否 | **PARTIAL** | 纯前端；「主动建议」是硬编码定时器 |
| **死 UI：语音聊天按钮** | ⚠️ | — | — | — | ❌ | — | **DEAD** | `QuickActions.tsx:38-44` 无 `onClick` |
| 错误 / 重试 / 空态 | ⚠️ | — | — | — | 部分 | 否 | **PARTIAL** | 多个页面失败渲染为「安心的空态」 |

---

## B. 管理端

| 功能 | 前端 | 后端 | DB | 联通 | 测试 | 状态 | 缺口 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 平台统计 | ✅ | ✅ | ✅ | ✅ | ✅ | **COMPLETE** | 无空态 |
| 书籍 CRUD | ✅ | ✅ | ✅ | ✅ | ✅ | **PARTIAL** | 无单书详情 UI（`GET /admin/books/{id}` 未用） |
| 章节 CRUD | ✅ | ✅ | ✅ | ✅ | ✅ | **PARTIAL** | 无加载态 |
| 内容块创建 | ✅ | ✅ | ✅ | ✅ | ✅ | **COMPLETE** | |
| **内容块编辑** | ❌ | ✅ | ✅ | ❌ | ✅ | **DISCONNECTED** | `PATCH /admin/content-blocks/{id}` 无 UI |
| 知识点创建 | ✅ | ✅ | ✅ | ✅ | ✅ | **COMPLETE** | |
| **知识点编辑** | ❌ | ✅ | ✅ | ❌ | ✅ | **DISCONNECTED** | `PATCH /admin/knowledge-points/{id}` 无 UI |
| 知识资源上传 | ✅ | ✅ | ✅ | ✅ | ✅ | **COMPLETE** | 202 + 异步 |
| 资源处理状态轮询 | ✅ | ✅ | ✅ | ✅ | ✅ | **COMPLETE** | 3s 轮询 + 失败重试 + 超 2 分钟提示 |
| **资源元数据修正** | ❌ | ✅ | ✅ | ❌ | ✅ | **DISCONNECTED** | `PATCH /admin/knowledge/resources/{id}` 无 UI |
| 资源重新处理 | ✅ | ✅ | ✅ | ✅ | ✅ | **COMPLETE** | |
| **归档语义** | ⚠️ | ⚠️ | ⚠️ | — | ✅ | **BROKEN** | 用 `status='FAILED'` + 错误串表示归档（382 条） |
| 教师风格 CRUD | ✅ | ✅ | ✅ | ✅ | ✅ | **COMPLETE** | |
| Admin 独立打包 | ✅ | — | — | — | — | **COMPLETE** | 路由级 lazy，18 kB |

---

## C. 平台 / 基础设施能力

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| 统一响应信封 | **COMPLETE** | |
| 错误码体系 | **COMPLETE** | |
| JWT 鉴权 | **COMPLETE** | HS256 + bcrypt |
| 严格后台鉴权 | **COMPLETE** | `ADMIN_PROFILE_REQUIRED`，已移除 legacy 放行 |
| `admins.role_level` 分级授权 | **NOT_IMPLEMENTED** | 字段存在但无人读取 |
| 限流（全局 + 登录） | **COMPLETE** | Redis / 进程内双模式**都强制拒绝** |
| 幂等 | **COMPLETE** | 对话 / 答题 / 结算 / 导入四层 |
| 缓存（书库列表） | **COMPLETE** | 按全参数指纹分键 |
| 分布式锁 | **COMPLETE** | 带 TTL 与本地降级 |
| 对象存储抽象 | **PARTIAL** | local 可用；S3 手写 SigV4，**仅本地联调，且当前未启用** |
| 后台任务队列 | **COMPLETE** | `FOR UPDATE SKIP LOCKED` + 指数退避 + 孤儿回收 |
| Worker 默认启动保证 | **DISCONNECTED** | lifespan 空 + compose profile 门控 |
| 队列积压可观测 | **NOT_IMPLEMENTED** | |
| 访问日志 | **COMPLETE** | 结构化，不记敏感信息 |
| Prometheus 指标 | **PARTIAL** | 仅 HTTP；无 AI / 队列 / DB 指标；**多副本无法聚合** |
| LLM token 计量 | **PARTIAL** | 对话分支真实；quiz 两个分支把字符数当 token |
| 教学评测门禁 | **PARTIAL** | 离线 37 例只校验协议；真实模式手动、不在 CI |
| CI 流水线 | **BROKEN** | backend job 在全新库上必然失败；失败产物永不产生 |
| Schema 漂移门禁 | **NOT_IMPLEMENTED** | CI 无 `alembic check` |
| 后端 lint / 类型检查 | **NOT_IMPLEMENTED** | 无 ruff / mypy |
| 前端类型检查 | **COMPLETE** | `tsc --noEmit` 0 错误（在 build 中） |
| 覆盖率报告 | **NOT_IMPLEMENTED** | 无任何覆盖率工具 |
| 生产部署编排 | **NOT_IMPLEMENTED** | 无 api 服务 / 无反代 / 无 k8s |
| 监控告警 / 日志聚合 | **NOT_IMPLEMENTED** | |
| 备份演练 | **NOT_IMPLEMENTED** | 有 dump/restore 能力但无调用方 |
| React Query（缓存 / 失效） | **DISCONNECTED** | 装了配了，`useQuery`/`useMutation` 全仓 0 次 |

---

## D. 代码资产状态

| 资产 | 状态 | 证据 |
| --- | --- | --- |
| `src/mocks/`（5 service + 5 data，约 1700 行） | **DEAD_CODE** | 仅 2 处外部引用（1 生产静态标签 + 1 测试夹具） |
| `shared/ui/ResourceState.tsx`（62 行） | **DEAD_CODE** | 0 引用（含自己的 4 个测试） |
| `shared/api/query-keys.ts`（19 行） | **DEAD_CODE** | 0 引用 |
| `conversation-store.pushStreaming` | **DEAD_CODE** | 0 调用方；伪造 22ms/字符 打字机 |
| `app/worker.py` | **DEAD_CODE** | shim，所有脚本用 `app.jobs.worker` |
| `app/skills/registry.py` | **DISCONNECTED** | 只注册 `quiz`，而对话链路硬编码 `QuizService()` 绕过它 |
| `app/scripts/import_assessments.py` | **DISCONNECTED** | 仅测试调用 |
| `post_content_ai_visibility` 等 4 个新迁移 | **未提交** | `git status ??`（P1-0） |
| `infra/` | **EMPTY** | 仅 `.gitkeep` |
| `prototypes/*.html` | **历史参考** | 152 KB UI 原型，非生产代码 |
| `backend/空` | **垃圾** | 4 字节 |
| `.playwright-mcp/`（36 文件） | **调试残留** | 未跟踪 |

---

## E. 汇总计数

| 状态 | 数量 | 代表 |
| --- | --- | --- |
| COMPLETE | ~38 | 鉴权、书库、阅读、图片、判分、记忆/画像、推荐、Worker 队列、限流、幂等 |
| PARTIAL | ~13 | AI 流式、RAG、语音 ASR、出题、管理端编辑、错误态 |
| BROKEN | 3 | 长对话摘要、CI backend job、设置页软锁 |
| DISCONNECTED | 7 | 情节记忆检索、审校题库、TTS、Worker 默认启动、`.agent.md`、React Query、3 个管理端 PATCH |
| MOCK | 2 | quiz AI 反馈、`MockAIProvider`（仅本地默认） |
| NOT_IMPLEMENTED | ~10 | role_level 授权、部署编排、监控告警、覆盖率、队列告警 |
| DEAD_CODE | ~8 项 | mock 层、ResourceState、query-keys、pushStreaming 等 |

---

## F. 一句话结论

**「学生能完整走完一条学习闭环」是真的**（登录 → 书库 → 阅读 → 提问 → 测验 → 讲解 → 复习 → 继续），
且这条链路上的鉴权、幂等、并发、可见性边界都做得扎实。
**但「AI 数字教师」这个产品核心是半成品**：没有真流式、没有工具调用、长对话会失忆、
出题 89% 来自 8 道硬编码题、情节记忆 AI 看不到、审校题源三重不通。
**同时工程侧存在一个 P0 级红色 CI 和一个 P0 级脏数据库。**
