# 13 · 技术债地图

> 分三类：**已确认技术债**（有代码证据，确定是债务）、**潜在风险**（结构上成立，尚未造成损害）、
> **尚未确认**（UNKNOWN，需进一步验证）。
>
> **刻意排除**：个人偏好、风格争议、以及「换一个框架会更好」这类没有项目内证据的主张。

---

## Architecture

### 已确认
| 债务 | 证据 | 成本 |
| --- | --- | --- |
| **AI Provider 契约过窄** | `app/ai/base.py:6-26` 只有 `stream_chat/model_info/last_usage`，无 tools / JSON mode / 取消 / 参数面 | 每加一种模型能力都要改所有调用方 |
| **「Skill」有两套并存概念，且真用的那套绕过了抽象** | `app/skills/registry.py:5-7` 只注册 `{"quiz": QuizSkill()}`；`conversation/service.py:282-283` 硬编码 `QuizService()` | 抽象层是装饰性的，无法按注册表扩展 |
| **API 层与 Worker 层共享业务逻辑但入口分离** | `main.py:31-34` lifespan 为空，Worker 完全独立进程 | 无法保证启动一致性；部署容易漏 |
| **`docker-compose.yml` 是依赖编排而非部署编排** | 有 `worker`（profile 门控）无 `api` | 从 compose 得不到可运行系统 |
| **业务代码依赖 CLI 脚本** | `app/modules/content/assets.py:16` `from app.scripts.validate_library import LIB_ROOT` | 脚本无法独立演进；import 时带入脚本模块级代码 |

### 潜在风险
| 风险 | 说明 |
| --- | --- |
| **无 `relationship()` 的约定只靠注释维持** | 全仓 0 处 `relationship(`，是一条好约定，但没有 lint/测试守护，新人极易引入 |
| **`infrastructure/database/models.py` 单文件 1465 行 / 32 表** | 任何 schema 变更都在一个巨型文件里冲突 |
| **`conversation/service.py` 1319 行单函数族** | `send_message` 覆盖 431→1056 行，职责过载 |

---

## Backend

### 已确认
| 债务 | 证据 |
| --- | --- |
| **关键词意图判定劫持正常提问** | `conversation/service.py:55,612` —— 「题目」触发测验 |
| **AI 反馈与提示硬编码** | `quiz/service.py:594-598`（两句字面量）、`skill.py:451-457`（三级同一句） |
| **`.agent.md` 标题硬编码 `xiaoming`** | `memory/agent_md.py:132,170` |
| **归档用 `status='FAILED'` + 错误串表达** | 382 条 `error='archived: test data'`；`KnowledgeResource.status` 无 ARCHIVED |
| **HTML 类型声明支持但无解析** | `models.py:1288` 枚举含 HTML；`ingestion.py` 无分支 |
| **token 计量语义不一致** | `quiz/service.py:845-850,914-919` 用字符数；`conversation/service.py:163-186` 用真实 usage |
| **TeacherContext N+1** | `teacher_context.py:315-335` 按 quiz session 逐条查询 |
| **`admins.role_level` 无实效** | 字段存在，无任何授权逻辑读取 |
| **记忆注入按时间非相关性** | `teacher_context.py:246-285` `LIMIT 5` |
| **`app/worker.py` 重复入口** | shim，无调用方 |

### 潜在风险
- `learning_events.conversation_id` / `quiz_session_id` **只有索引没有 FK** —— 可能产生孤儿行。
- 58 个 FK 列中 **25 个无前导索引** —— 当前规模无碍，数据量上来会痛。
- `books → chapters → content_blocks` 两级 CASCADE —— 草稿书删除会静默带走整棵内容树。
- `quiz_sessions ↔ quiz_questions` **循环 FK** —— autogenerate 对该两表 FK 漂移失明，
  且 `create_all()` / 朴素 DROP 排序不可用。

---

## Frontend

### 已确认
| 债务 | 证据 |
| --- | --- |
| **React Query 装了配了完全没用** | `useQuery`/`useMutation`/`invalidateQueries` 全仓 **0 次**；`query-keys.ts` 0 引用；每页手写 `useState`+`useEffect` |
| **mock 服务层约 1700 行死代码** | 6 个 service 零引用（其中 2 个只被自己的测试引用） |
| **死抽象 `ResourceState`（62 行）** | 0 引用，却有 4 个测试 |
| **死方法 `pushStreaming`（伪造打字机）** | `conversation-store.ts:639-667`，0 调用方 |
| **失败被渲染为「安心的空态」** | 6 处（`docs/04` §3.5） |
| **401 处理不一致** | `api-student-service.ts:58-77`、`learning-service.ts:102-130` 用原生 fetch，不派发全局事件 |
| **假主动建议徽标** | `useCompanionDock.ts:66-78`（6s/13s 定时器） |
| **注释与实现不符 5 处** | `docs/04` §10 |
| **死 UI（语音聊天按钮无 onClick）** | `QuickActions.tsx:38-44` |
| **无测试的页面** | `MemoriesPage`、`LoginPage`、`ReaderPage` 本体、`AdminDashboard`、`AdminLayout` |

### 潜在风险
- `conversation-store.ts` 692 行单 store，同时管流式、历史、epoch、幂等 —— 职责集中。
- Token 存 `localStorage`（可被 XSS 读取）；缓解是 Markdown 已做 XSS 防护，但缺 httpOnly Cookie 方案。

---

## Database

### 已确认
| 债务 | 证据 |
| --- | --- |
| **`chapter_completions` 唯一索引 vs 唯一约束表示不一致** | 永久 autogenerate churn（`docs/06` §1） |
| **零向量索引** | HNSW 在 `c7d8e9f0a1b2` 被删且从未重建；`EXPLAIN` 确认 Seq Scan |
| **无维度 vector 列阻碍加索引** | 结构性：需先锁维度 |
| **`import_assessments` 的 `revision` 无条件自增** | `:125`，跑 N 次 revision=N |
| **迁移被回溯修改** | `b1c2d3e4f5a6` 被 commit `bce24e9` 改过（已应用的迁移不可变原则被破坏） |
| **`archive_noncorpus.py` 保留规则过窄 + UPDATE 无 status 谓词** | `:58,70-73` |
| **`reindex_embeddings` / `rebuild_memory` 会改变主键** | 跨重建持有 id 的引用会失效 |
| **`idempotency_keys` 无清理策略** | 实测 8442 行 |
| **`seed.py:104` 漏 f 前缀** | 打印字面量 `{SEED_PASSWORD}` |

### 潜在风险
- `import_library` 与 `ingest_knowledge` 对同一文档用**不同 URL 方案** → 可能产生重复资源与重复 chunk。
- `reviewed_questions.chapter_id ON DELETE SET NULL` → 删章节会让审校题变成**永久不可选中的孤儿**。

---

## AI

### 已确认（这是债务最集中的区域）
| 债务 | 证据 |
| --- | --- |
| **没有 token 级流式** | `openai_compatible.py:68` `stream:False`；`:103-104` 事后 16 字符切片 |
| **30 秒固定超时，不可配置** | `:39,76` |
| **零重试** | `grep retry/tenacity/backoff app/ai/` = 0 |
| **无 Agent / 无 Tool Calling** | `tool_calls`/`function_call`/`"tools"` = 0 命中；`tool.start/result` 是关键词分支 |
| **会话摘要是规则式伪摘要且谎报覆盖** | `jobs/handlers/conversation.py:12,16-36,77,86` |
| **`student_episodes.embedding` 从不写入** | `pipeline.py:376` 硬编码 `None` |
| **记忆抽取全靠硬编码阈值与模板** | `pipeline.py:37-173` |
| **RAG 排序用字面子串压过余弦距离** | `knowledge/service.py:173-187` |
| **58% 已嵌入知识不可达** | 636×64 维 vs 467×1024 维 |
| **提示与反馈硬编码** | 见 Backend |
| **无 LLM 可观测性** | `/metrics` 无任何 LLM/队列指标 |
| **教学评测门禁是协议级** | `evals/run_teaching_eval.py:33-40` 输出预置 `"observed"` |

---

## Testing

### 已确认
| 债务 | 证据 |
| --- | --- |
| **conftest.py 零 fixture、不设 DATABASE_URL** | 11 行；测试直连开发库 |
| **无 schema reset / 无事务隔离 / 无 truncate** | 靠手写 `_ensure*()` 造数器 |
| **CI backend job 确定性失败** | 顺序 bug（`docs/10` §1） |
| **`scripts/ci.sh` 与 GitHub CI 跑在不同数据上** | `ci.sh:70-98` 回退到 `.env` |
| **错误路径零覆盖** | 全套测试中唯一出现过的假状态码是 **200** |
| **「测试剧场」7 处** | `docs/10` §6 |
| **无任何覆盖率工具** | 无 pytest-cov / vitest coverage |
| **测死代码的测试 11 个** | mock 服务 7 + ResourceState 4 |
| **`audit-check.sh` 的隔离守卫无人调用** | 项目已写好正确工具却未接上 |

---

## DevOps

### 已确认
| 债务 | 证据 |
| --- | --- |
| **无生产部署编排** | compose 无 api 服务；`infra/` 空 |
| **无反向代理 / TLS** | 不存在 |
| **Worker 默认不启动** | profile 门控 + lifespan 空 |
| **CI 失败诊断产物永不产生** | 日志被 EXIT trap 删除；Playwright HTML reporter 未配置 |
| **CI 三个 job 并行无 `needs:`，重复 install** | `ci.yml` |
| **`scripts/ci.sh`（11 步）与 `ci.yml`（3 job）双份维护** | 内容重叠、独立演进 |
| **根 `.env.example` 过期且无人读取** | `LLM_*` vs `AI_*` |
| **Node 版本本机 24 / CI 22 未声明** | |

### 潜在风险
- `start.sh` 的容器守卫永不匹配（死逻辑，当前无害）。
- `stop.sh` 不停 redis/minio。

---

## Security

### 已确认（基线良好，问题集中在少数点）
**做得好的（明确记录，避免被误当债务）**：bcrypt 直调、`ENVIRONMENT=prod` 拒绝占位 JWT secret、
账号禁用即时失效、严格后台鉴权（无 admins 行即 403）、路径穿越防护（已测）、
日志明确不记 Authorization/密码/正文、限流双模式强制拒绝、内容可见性守卫在 Service 层使缓存也绕不过。

| 债务 | 证据 |
| --- | --- |
| **硬编码演示凭据 `admin123`** | `seed.py:57`，重复于 `ingest_knowledge.py:36` |
| **Token 存 localStorage** | 无 httpOnly Cookie 方案 |
| **401 处理不一致** | 2 处原生 fetch 不派发全局事件 |
| **`admins.role_level` 无分级授权** | 两个等级权限相同 |
| **明文 `.env`** | 已被 gitignore，但无 secrets manager |

### 潜在风险
- 工作区 `backend/.env` 含**真实第三方 API Key**（DeepSeek / 阿里云百炼）。
  已被 `.gitignore` 正确覆盖（实测 `git check-ignore` 命中），**未泄漏到 git**；
  但轮换与集中管理缺失。

---

## Observability

### 已确认
| 债务 | 证据 |
| --- | --- |
| **无 LLM 指标** | 调用数 / token / 延迟 / 失败率 / RAG 命中率 全无 |
| **无队列指标** | 深度 / 最老 queued 任务年龄 |
| **无 DB / 连接池指标** | |
| **`/metrics` 是进程内文本** | 多副本无法聚合（文档自述待定） |
| **`/health` 不检查 DB / Redis / Worker** | `main.py:152-155` 注释明示「不依赖数据库」 |
| **无外部监控 / 日志聚合 / 告警** | |

---

## Developer Experience

### 已确认
| 债务 | 证据 |
| --- | --- |
| **代码注释大量引用 `0-D` / `0-E` 编号，但原文档不在仓库** | `models.py` 全篇（如 `:43` `users（0-E §3.1）`） |
| **`docs/` 端点总数写 68，实际 71** | `api-contract.md:390` |
| **3 个新端点未进契约文档** | `docs/07` §3.1 |
| **5 处前端注释与实现不符** | `docs/04` §10 |
| **`plan.md`（根）已过期但仍被 README 当作入口** | `README.md:17` 指向「总控文件」，而 `tasks/plan.md` 才是当前 |
| **`backend/空`、`.playwright-mcp/`、`.opencode/node_modules` 残留** | 噪音 |
| **无后端 lint / 类型检查** | 无 ruff / mypy（本地有 `.ruff_cache` 但未声明依赖） |
| **测试数量虚高** | 11 个测试保护死代码 |

---

## 尚未确认（UNKNOWN）

以下项**没有足够证据**判定，需进一步验证后才能列入债务：

| 项 | 为什么是 UNKNOWN |
| --- | --- |
| E2E 33 项在隔离环境是否真的全绿 | 本次审计**未执行** E2E（会写入开发库）。文档声称 33 passed，但环境不同 |
| S3 适配器对接真实对象存储的可用性 | 只有本地联调；`STORAGE_BACKEND=local`，从未真实启用 |
| 阿里云 ASR 的真实识别质量与稳定性 | 代码路径真实，但无自动化验证、无质量数据 |
| 真实 LLM 的教学质量 | `docs/plans/current-phase.md:36` 自述待授权与预算；本次未做真实评测 |
| `reindex_embeddings` 在 1136 行规模下的耗时与成本 | 未执行 |
| 多副本部署下的行为（限流、锁、指标） | 从未多副本运行过 |
| `import_library` vs `ingest_knowledge` 是否**确实**产生了重复资源 | 结构上成立（两种 URL 方案），但未逐条比对线上数据 |
| `quiz_sessions` 中 4 条 `model_info` 为空的原因 | 未追溯 |
| `conversation_summaries` 只有 1 行是否正常 | 会话 103 个、消息 495 条，仅 1 条超过 20 条阈值——合理，但未逐一核对 |
