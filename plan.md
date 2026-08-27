# 霜铃 K12 AI 数字教师 V3 · 完成后台实施计划

> 本文档是 Hermes 的调度、执行和验收基线。Hermes 只负责规划、调度与验收；具体代码修改由 OpenCode 通过 Herdr 执行。
>
> 目标是把当前“功能原型较完整、生产闭环不完整”的项目收敛为可验证、可重复构建、可演示的完整学习闭环。

## 总体原则

- 严禁通过删除测试、降低标准、硬编码、临时 Mock 或绕过真实业务逻辑来使验收通过。
- 保留当前未提交修改；不得覆盖、回退或丢弃已有有效工作。
- 以实际代码、Git diff、迁移结果、测试、构建和运行结果为验收依据，不只依赖 OpenCode 报告。
- 每个阶段只能修改计划中声明的模块；发现计划外问题时可并入当前阶段或后续阶段。
- OpenCode 暂不执行 git commit；提交由 Hermes 在最终验收后决定。
- 所有阶段完成后执行一次独立最终验收。

## 核心闭环

登录 → 书库/阅读 → 页面感知 AI → 当前章节 Quiz → 学习事件 → 记忆/画像 → 推荐 → AI 后续利用历史继续教学。

## Phase 1：基础设施、内容初始化和 Worker 闭环

### 目标

让项目在全新环境中可迁移、可初始化、可启动，真正运行异步 Worker，并消除内容初始化与依赖中的主要断点。

### 主要问题

- `httpx` 是生产代码直接依赖，却只声明在 dev group。
- Worker 未进入 docker-compose、一键启动、CI 和 GitHub Actions。
- `memory_consolidation` handler 存在但没有任何业务方入队；记忆处理仍在 HTTP 请求内同步执行。
- 知识资源上传会进入 `knowledge_ingest`，但没有 Worker 消费，资源可能长期停留在 `UPLOADED`。
- 内容初始化路径不一致：旧 seed 只产生 12 本旧书和 11 本占位书，未导入 25 本新语料和 56 篇知识文档。
- CI/E2E 在全新 Postgres 上只执行 `seed.py`，不初始化内容。
- 模型仍声明 `VECTOR(64)` 和旧 HNSW 语义，已提交迁移已改为无维度 vector 并移除 HNSW。
- PDF 解析依赖可选 `pypdf`，但该依赖未正式声明。

### 涉及模块

- `backend/pyproject.toml`、`backend/uv.lock`
- `docker-compose.yml`
- `scripts/start.sh`、`scripts/stop.sh`、`scripts/ci.sh`、`scripts/ci-e2e.sh`
- `.github/workflows/ci.yml`
- `backend/app/jobs/`、`backend/app/worker.py`
- `backend/app/modules/learning/service.py`、`backend/app/modules/quiz/service.py`
- `backend/app/scripts/seed.py`、`seed_content.py`、`import_library.py`、`validate_library.py`
- `backend/app/infrastructure/database/models.py`、`backend/alembic/versions/`
- `backend/app/modules/knowledge/ingestion.py`

### 实施要求

1. 将 `httpx` 移入正式 `dependencies`，并更新 uv 锁文件。
2. 将 Worker 加入 `docker-compose.yml`、`scripts/start.sh`、`scripts/stop.sh`、`scripts/ci.sh`、`scripts/ci-e2e.sh` 和 GitHub Actions；Worker 启动后能持续消费 Postgres 队列。
3. 学习事件和 Quiz 答题不再同步执行完整 MemoryPipeline；改为在数据库事务后入队 `memory_consolidation`，并保证失败可重试。
4. 保留 Worker 的三个 handler：`knowledge_ingest`、`conversation_summary`、`memory_consolidation`，并补齐缺失的调度与幂等保护。
5. 统一内容初始化流程：先执行 `validate_library --all`，通过后执行 `import_library --all`。
6. 调整旧 seed 和内容 seed 的职责：`seed.py` 只负责演示账号与演示记忆；旧内容占位数据和旧书数据不得再作为正式初始化路径，或必须明确迁移/清理策略。
7. 修正模型与迁移漂移：模型 `embedding` 字段与迁移的 pgvector 定义一致，并同步删除过时 HNSW 注释/代码语义。
8. 正式声明 PDF 解析依赖，或移除未实现/不可靠的 PDF 能力并同步前后端。
9. 保持所有既有未提交改动，不得回退教师风格、头像、Profile/Settings 重构或其他有效工作。

### 验收标准

- 全新 Postgres 上 `alembic upgrade head` 成功，无模型/迁移漂移错误。
- `validate_library --all` 输出 `PASS (books=25, violations=0)`，或实际语料数量与 manifest 完全一致。
- `import_library --all` 导入 25 本书、56 篇知识文档，重复执行无新增重复数据。
- 启动脚本能同时启动 API、Worker 和依赖服务；停止脚本能正确停止 Worker。
- 上传知识资源后，Worker 能将其处理到 `READY` 或可观察的确定性失败状态。
- 学习事件/答题后生成 `memory_consolidation` job，并由 Worker 消费成功。
- 后端生产依赖安装包含 `httpx`、PDF 所需依赖；`uv sync` 通过。
- 后端 pytest、前端 Vitest 和 TypeScript 检查通过。
- Git diff 不包含删除既有测试、绕过业务逻辑或临时 Mock。

## Phase 2：页面感知 AI、当前章节 Quiz 与 TeacherContext

### 目标

让 AI 对话只在正确上下文下运行，并让“当前章节测验”真正与阅读位置关联；同时把学生画像、偏好、记忆和近期学习历史注入教师上下文。

### 主要问题

- Reader 快捷动作、选中提问、重试、Quiz 不传 ScreenContext。
- Reader 离开页面只清理部分上下文，会残留书和章节。
- 语音对话不携带当前页面上下文。
- 对话触发 Quiz 时不传 `book_id/chapter_id`。
- 题库只有 8 道训练数据题，不能支撑任意章节。
- QuizCard 只加载第一题，无法完成多题。
- QuizCard 对题型支持不完整，且正确/错误反馈硬编码为训练数据相关文案。
- TeacherContext 只包含角色、摘要、知识库和页面文本，没有年级、偏好、长期记忆、画像、近期测验/阅读和证据。

### 涉及模块

- `frontend/src/features/screen-context/`
- `frontend/src/features/conversation/store/conversation-store.ts`
- `frontend/src/features/conversation/components/`
- `frontend/src/pages/reader/ReaderPage.tsx`
- `frontend/src/features/quiz/components/QuizCard.tsx`
- `frontend/src/pages/quizzes/QuizDetailPage.tsx`
- `backend/app/modules/conversation/service.py`
- `backend/app/modules/quiz/service.py`、`backend/app/modules/quiz/skill.py`、`backend/app/modules/quiz/quiz_bank.py`
- `backend/app/modules/voice/ws.py`

### 实施要求

1. 所有对话入口统一发送结构化 ScreenContext，包括文本、快捷动作、选中文本、Quiz、重试和语音。
2. ScreenContext 在页面切换时必须正确清除；离开 Reader 后不能继续携带上一本书或章节。
3. 对话触发 Quiz 时必须从当前上下文取得 `book_id/chapter_id`，并防止测验与错误章节关联。
4. 实现当前章节题目来源：优先真实章节内容生成，无法生成时必须有明确的、可审计的题库/回退策略，禁止临时 Mock。
5. QuizCard 支持题目逐题推进、所有题目类型、提交失败重试、提示、完成态和结果汇总。
6. 移除 QuizCard 中与章节无关的硬编码反馈；反馈应基于题目、解析和当前学生答案。
7. 构建完整的 TeacherContext：学生年级、学习偏好、长期记忆、画像、最近学习事件、最近测验、当前阅读内容、当前章节和知识库证据。
8. 记忆与证据必须来自数据库，不能使用前端硬编码或演示文案。

### 验收标准

- Reader、语音、快捷动作、选中提问、重试均能在服务端收到正确的 ScreenContext。
- 页面切换后不会向 AI 发送上一页面的 Book/Chapter 上下文。
- 对话测验创建出的 quiz session 与当前书和章节一致。
- 任意章节可以生成或取得至少一道相关题目；无法生成时有明确错误而非错误题。
- 前端可完成多题测验，并正确处理单选、多选、判断和填空。
- TeacherContext 在真实 LLM 与 Mock 模式下都能被测试验证包含年级、偏好、记忆或画像等字段。
- 后端测试覆盖 ScreenContext 传递、Quiz 上下文、多题完成和 TeacherContext。
- 不引入临时 Mock、硬编码答案或绕过真实生成逻辑。

## Phase 3：学习事件、统计数据、记忆画像与推荐闭环

### 目标

让所有关键学习行为产生真实、可追溯的事件与证据，并让记忆、画像、统计和推荐都由真实学习记录驱动。

### 主要问题

- 前端学习事件接口没有 `session_id`、`conversation_id`、`quiz_session_id` 字段。
- Reader 发送的 `CHAPTER_STARTED`、`BOOK_STARTED`、`TEXT_SELECTED` 未关联 LearningSession。
- `CHAPTER_FINISHED`、`BOOK_FINISHED`、`SECTION_READ`、`KNOWLEDGE_CARD_VIEWED`、`QUESTION_ASKED`、`VOICE_SESSION_STARTED`、`ROLE_SWITCHED` 等事件基本未触发。
- 学生统计字段 `learning_days`、`total_learning_minutes`、`completed_books`、`completed_chapters`、`quiz_count` 没有更新逻辑。
- `BookProgress.total_seconds` 没有实际累加。
- 推荐 API 虽已实现，但书库精选仍使用静态前 3 本书和静态推荐理由。
- AI 后续对话虽能回答证据问题，但常规教学未真正引用长期记忆、画像和最近学习。

### 涉及模块

- `frontend/src/shared/api/learning-service.ts`
- `frontend/src/pages/reader/ReaderPage.tsx`
- `frontend/src/pages/library/LibraryPage.tsx`
- `frontend/src/shared/api/api-recommendation.ts`
- `backend/app/modules/learning/`
- `backend/app/modules/memory/`
- `backend/app/modules/conversation/service.py`
- `backend/app/modules/recommendation/service.py`
- `backend/app/modules/quiz/service.py`

### 实施要求

1. 前端事件接口补齐 `session_id`、`conversation_id`、`quiz_session_id`、`block_id` 和 `knowledge_point_ids`。
2. Reader 使用真实 LearningSession，并让所有阅读相关事件关联当前 session、书、章节和内容块。
3. 实现章节完成、书籍完成、阅读段落、知识卡查看、提问、语音会话、教师风格切换等关键事件。
4. 学习会话开始/结束时更新统计字段；答题、完成章节、完成书籍时更新计数。
5. 阅读位置更新时累加 `BookProgress.total_seconds`，并保证重复更新不重复计入。
6. MemoryPipeline 改为异步，并在事件事务提交后产生可追溯证据。
7. 推荐 API 必须使用真实进度和测验数据；书库和首页统一消费真实推荐，不使用静态精选。
8. AI 常规对话的 System Prompt 注入长期记忆、画像和最近学习，并允许学生追问依据。
9. 所有事件、统计、记忆和推荐都补充数据库层测试。

### 验收标准

- 一次完整阅读、提问、测验流程会生成可查询的学习事件，且每个事件能追溯到对应 session/conversation/quiz。
- 统计字段在真实学习行为后发生变化，且值可解释、可重算。
- `BookProgress.total_seconds` 只按实际时间增长，重复请求不重复累加。
- 记忆/画像数据来自真实学习记录。
- 书库精选与首页推荐都来自真实推荐 API，并支持忽略推荐。
- AI 对话在测试中能引用至少一个真实记忆、画像或最近学习事件。
- 后端测试覆盖事件关联、统计更新、异步记忆和推荐数据源。
- 所有静态 Mock 推荐、硬编码画像文案和演示记忆均不再作为正式业务数据源。

## Phase 4：产品缺口与存储/语音/管理端

### 目标

补齐用户可感知的管理、历史、画像和语音能力，并完成生产文件和对象存储决策。

### 主要问题

- 对话历史、新建、删除/归档 UI 缺失。
- Profile“AI 档案”编辑/导出只是本地状态和 toast。
- `/profile/memories` 有路由但无导航入口。
- Admin 缺少教师风格、章节、内容块、知识点管理页面。
- Admin 知识库上传未开放 PDF。
- TTS 仍是静音 Mock。
- 知识资源和头像均使用本地存储，未接对象存储。
- 推荐 dismiss 虽实现但前端未使用。
- 页面中仍有较多硬编码演示文案和静态时间/推荐。

### 涉及模块

- `frontend/src/features/conversation/store/`
- `frontend/src/features/conversation/components/`
- `frontend/src/pages/profile/`
- `frontend/src/pages/admin/`
- `frontend/src/pages/library/LibraryPage.tsx`
- `backend/app/modules/conversation/`
- `backend/app/modules/identity/`
- `backend/app/modules/knowledge/ingestion.py`
- `backend/app/modules/admin/service.py`
- `backend/app/ai/voice.py`
- `backend/app/modules/voice/ws.py`

### 实施要求

1. 实现对话历史列表、新建对话、归档/删除对话、切换历史对话和清空当前对话。
2. 对话相关 API 补齐返回 `teacher_role` 和真实 `recent_messages`，前端不得再只依赖内存单会话。
3. 实现 Profile 真实编辑/导出；编辑结果持久化到数据库，导出生成可下载文件。
4. 增加 `/profile/memories` 导航入口，并让记忆管理页可从 Profile 直接进入。
5. Admin 增加教师风格、章节、内容块、知识点管理页面；所有操作调用真实 API。
6. Admin 知识库上传开放 PDF，并显示处理状态、错误和重处理。
7. 引入明确的存储抽象：本地存储和对象存储均可配置；知识资源和头像走同一抽象。
8. 实现或接入真实 TTS；若仍有外部依赖，必须提供可配置 Provider、降级行为和明确错误。
9. 首页/书库/设置页移除硬编码日期、推荐理由、画像文案等演示数据。
10. 推荐 dismiss/refresh 接入前端真实交互。

### 验收标准

- 对话历史、新建、删除/归档可从 UI 完成，并刷新后保持。
- Profile 编辑和导出是真实持久化行为。
- 用户可从导航进入记忆管理，并能确认、质疑、编辑、忘记记忆。
- Admin 所有新增管理页面均可读、可写并刷新保持。
- Admin 可上传 PDF，并能看到真实处理状态和失败原因。
- 对象存储配置可切换；本地存储仍有明确回退和路径隔离。
- TTS 返回真实音频，或在无外部配置时显示明确不可用状态而非静音。
- 页面中不再以硬编码 Mock 冒充真实推荐、画像或最近学习数据。

## Phase 5：安全、生产化、测试、CI/E2E 与最终验收

### 目标

完成生产安全、可观测性、一致性和交付质量收口，修复过时测试与文档，并完成独立最终验收。

### 主要问题

- 登录和 `get_current_user` 未校验 `User.status`。
- 无登录/API 限流、无全局 401 自动登出、无 X-Request-ID/结构化日志/metrics/trace。
- AdminGuard 仅依赖前端解码 JWT；前端鉴权设计不可靠。
- IdempotencyKey 不检查 `expires_at`。
- SSE 消息和 Quiz hint 未统一定义幂等行为。
- message/quiz sequence 使用 `max+1`，并发场景有重复风险。
- 模型与迁移定义不一致。
- E2E 仍断言旧角色名、旧 UI 文案，且测试覆盖与文档不一致。
- 文档声称“Phase 12 完成、无 blocker”，但实际工作区不干净、多项 backlog 未实现。
- 当前无真实运行环境可证明完整测试、构建、E2E、Worker 和初始化流程。

### 涉及模块

- `backend/app/api/deps.py`、`backend/app/modules/identity/`
- `backend/app/main.py`、`backend/app/infrastructure/`
- `backend/app/modules/admin/service.py`
- `backend/app/modules/conversation/`
- `backend/app/modules/quiz/`
- `backend/app/infrastructure/database/models.py`、`backend/alembic/`
- `frontend/src/shared/api/http.ts`、`frontend/src/features/auth/`
- `frontend/e2e/`
- `.github/workflows/ci.yml`
- `docs/`

### 实施要求

1. 登录和鉴权校验用户状态；禁用用户不可登录、不可继续使用 token。
2. 增加登录与 API 限流，或明确使用反向代理层实现并补充配置，不能只停留在文档。
3. 所有 API 请求产生或透传 request id，并支持结构化日志、基础 metrics。
4. 前端收到 401 后全局登出，避免局部错误后用户仍停留在受保护页面。
5. 移除或修正 AdminGuard 客户端鉴权策略；前端只负责展示，真正的权限判定必须由后端完成。
6. IdempotencyService 检查过期时间，并处理过期 key 的清理或拒绝。
7. SSE 消息和 Quiz hint 统一携带、校验幂等 key；不能只对部分写操作生效。
8. 消息和 quiz 序号改为数据库原子递增或等价安全方案，避免并发重复。
9. 完成模型与迁移对齐；重新生成或校正 embedding 相关迁移。
10. 修正所有 E2E 与单元测试断言，确保与当前 UI/API/DTO 一致。
11. 更新 README、当前阶段文档、API 契约、数据库设计和 traceability，使之与实际代码一致。
12. 在干净环境完成全过程验证：迁移、初始化、后端测试、前端测试、构建、E2E、Worker、对象存储配置、启动/停止。

### 验收标准

- 禁用用户无法登录；已登录禁用用户的下一次 API 调用失败。
- 401 会触发前端登出；API 响应包含可追踪的 request id。
- Idempotency 过期行为有测试覆盖。
- 幂等 key、SSE、Quiz hint 行为与契约一致。
- 消息和 quiz 序号在并发测试中不会重复。
- `alembic upgrade head` 与模型一致。
- 后端 pytest、前端 Vitest、TypeScript 和 build 全部通过。
- 干净环境 E2E 全部通过，且不再依赖旧角色名、旧文案或预先已导入的旧数据。
- Worker 在干净环境能正确消费知识处理、会话摘要和记忆任务。
- Git 工作区状态清晰，生成的中间文件不污染仓库。
- 最终验收报告逐项记录证据：代码、Git diff、迁移、测试、构建、E2E、Worker、初始化和文档一致性。

## 最终验收范围

1. 核心业务链路从登录到推荐、AI 后续引用全部跑通。
2. 所有阶段验收标准可重复执行。
3. 后端、前端、迁移、Worker、内容初始化和 E2E 均有实际命令输出。
4. 删除任何临时 Mock、硬编码、被绕过或被降低的验收条件。
5. 当前未提交的有效工作全部保留并理解。
6. 输出最终验收报告，不应只依据 OpenCode 的完成声明。
