# 04 · 前端

> React 19 SPA。主要证据来自 `.audit/B-frontend.md`（572 行完整审计）+ 实测 `tsc --noEmit` / `vitest` / `vite build`。

---

## 0. 结论摘要

- **前端不是 mock 原型。** 6 个服务全部绑定真实后端（`src/shared/services.ts:21-26`），
  生产 bundle 中**不含任何 mock 数据**（已用构建产物逐一比对标记字符串验证）。
- **构建与类型检查全绿**：`tsc --noEmit` 0 错误（`strict` + `noUnusedLocals`，169 个文件在编译程序中），
  `vite build` 成功，Vitest **49 文件 / 258 测试全通过**。
- 主要问题是**堆积的脚手架未清理**（死 mock 服务、死 React Query、死 `ResourceState`、死 `pushStreaming`）
  和**少量未完成边界**（Reader 无错误态、假的主动建议徽标、前端自造的 `.agent.md`、401 处理不一致）。

---

## 1. 路由（`src/app/router/index.tsx`，124 行）

- `createBrowserRouter`，`RequireAuth` 包 `AppLayout`，`AdminGuard` 包 `/admin`。
- 除 `LoginPage` 与 `AppLayout` 外，**全部页面路由级懒加载**（`lazy()` + `Suspense`），Admin 独立成包。
- 有 `path: '*'` 兜底 404 页。
- `/` 重定向到 `/home`。

| 路由 | 页面 | 懒加载 | 守卫 |
| --- | --- | --- | --- |
| `/login` | LoginPage | ❌（即时） | — |
| `/home` | HomePage | ✅ | RequireAuth |
| `/library` | LibraryPage | ✅ | RequireAuth |
| `/books/:bookId` | BookDetailPage | ✅ | RequireAuth |
| `/learn/:bookId/:chapterId` | ReaderPage | ✅ | RequireAuth |
| `/quizzes` | QuizzesPage | ✅ | RequireAuth |
| `/quizzes/:quizId` | QuizDetailPage | ✅ | RequireAuth |
| `/profile` | ProfilePage | ✅ | RequireAuth |
| `/profile/memories` | MemoriesPage | ✅ | RequireAuth |
| `/settings` | SettingsPage | ✅ | RequireAuth |
| `/admin`（+5 子路由） | AdminLayout/Dashboard/Books/Knowledge/Styles/Chapters | ✅ | RequireAuth + AdminGuard |
| `*` | NotFoundPage | ❌ | — |

---

## 2. 页面清单（真实数据 / 状态覆盖 / 测试）

| 页面 | 主要 API | 数据 | 加载/错误/空态 | 测试 |
| --- | --- | --- | --- | --- |
| **HomePage** | `studentService.getMe`、`contentService.getProgress/getBook/getChapter`、`memoryService.getEpisodes/getMemories`、`quizService.getQuizSessions`、`recommendationService.*` | 昵称、5 项统计、继续学习卡、情节、记忆、测验、≤3 推荐、下一步行动 | ✅ **逐区块独立降级**（`use-home-data.ts:52-69` 六个 error flag） | 8+6+3+6 |
| **LibraryPage** | `recommendationService.*`、`contentService.getBooksPage/getProgress` | 推荐（带理由）、分页书库、继续学习 | ✅ 错误+重试、游标「加载更多」 | 9 |
| **BookDetailPage** | `contentService.getBook/getChapters/getBookProgress/getChapter` | 标题、简介、年级、时长、章节列表（含完成态） | ✅ 三态齐全 | 7 |
| **ReaderPage** | `contentService.getChapters/getChapter/getBook/getBookProgress`、`learningService.*` | 正文块、目录、知识点、完成卡、页面感知侧栏 | ⚠️ **无错误态**（见 §5） | 仅子组件（6+7），**无 ReaderPage 测试** |
| **QuizzesPage** | `quizService.getQuizSessions` | 测验历史（含来源书/章） | ✅ 三态 + 重试 | 2 |
| **QuizDetailPage** | `quizService.getQuizSession/getQuestions/getAnswers/getInteractions` | 只读答卷、对错、解析、「讲解这道题」/「再练一道」 | ✅ 加载 + 空 | 3（断言**零写入**） |
| **ProfilePage** | `studentService.getPreferences/updateMe/updatePreferences`、`memoryService.getInsights/getMemories/getEpisodes/getInsightDetail/getEpisodeDetail` | 5 档定性画像（**无百分比**）、情节、记忆、`.agent.md` 卡、学习目标、JSON 导出 | ✅ 逐区块；prefs 失败不清空整页 | 9+2 |
| **MemoriesPage** | `memoryService.getMemories/updateMemory/getEvidence` | 记忆列表 + CONFIRM/DISPUTE/FORGET/EDIT | ✅ 三态 | ❌ **无测试** |
| **SettingsPage** | `studentService.getPreferences/getTeacherRoles/updateMe/updatePreferences/uploadAvatar`、`learningService.createEvent` | 资料、年级、头像（emoji 预设或上传）、教师风格、语音偏好、桌宠选择 | ✅ 加载 + 错误 + toast | 2 |
| **LoginPage** | `useAuth().login` | 账号密码表单、错误 alert、演示凭据提示（仅 `VITE_SHOW_DEMO_CREDENTIALS=true`） | ✅ 提交态 + `role="alert"` | ❌ **无测试** |
| **AdminDashboard** | `adminService.getStats` | 平台统计 | ⚠️ 有错误、**无空态** | ✅ |
| **AdminBooks** | `adminService.getBooks/createBook/patchBook` | 书列表 + 新建 + 状态切换 | ⚠️ **无加载态** | ✅ |
| **AdminKnowledge** | `adminService.getKnowledgeResources/uploadKnowledgeResource/reprocessResource` | 资源表 + 上传 + **轮询** | ✅ 加载/错误/重试 + 超 2 分钟提示 | 5 |
| **AdminStyles** | `adminService.getTeacherRoles/createTeacherRole/patchTeacherRole` | 教师风格卡 | ✅ | ✅ |
| **AdminChapters** | `contentService.*`、`adminService.createChapter/patchChapter/createContentBlock/createKnowledgePoint` | 章节/内容块/知识点编辑 | ✅ | ✅ |

**所有页面都用真实服务。没有任何页面渲染 `src/mocks/` 的数据。**

---

## 3. API 层（`src/shared/api/`）

### 3.1 `http.ts`（123 行）—— fetch 封装

- `API_BASE = '/api/v1'`（相对路径，由 Vite proxy 转发，规避 CORS）。
- 自动附加 `Authorization: Bearer <localStorage token>`。
- 解析统一信封 `{data, meta}`；非 2xx 抛结构化 `ApiError(status, code, message, details, requestId, retryAfterMs)`。
- 401 时 `emitUnauthorized()` 派发全局事件。
- 支持 `AbortSignal`（T07：路由/账号切换后取消迟到请求）。
- `parseRetryAfter()` 同时支持秒数与 HTTP 日期两种格式。

### 3.2 `sse.ts`（147 行）—— 流式传输

正确处理：CRLF、跨 chunk 的多字节 UTF-8 拆分、心跳注释行跳过、401 派发。
**传输层是这套系统里质量最高的部分之一。**

### 3.3 `voice-client.ts`（139 行）—— WebSocket 客户端

30 秒心跳、屏幕上下文帧、连接状态机，测试覆盖 6 例。

### 3.4 各模块端点映射（完整）

| 模块 | 端点覆盖 |
| --- | --- |
| `api-student-service.ts` | `POST /auth/login`、`POST /auth/logout`、`GET /me`、`PATCH /me`、`GET/PATCH /me/preferences`、`GET /teacher-roles?enabled=true`、`POST /me/avatar`（原生 fetch + FormData） |
| `api-content-service.ts` | `GET /books`（游标/limit/年级/主题/搜索）、`GET /books/{id}`、`GET /books/{id}/chapters`、`GET /chapters/{id}`、`GET /knowledge-points/{id}`（**生产未调用**）、`GET /me/progress`、`GET /me/progress/{bookId}` |
| `api-conversation-service.ts` | `GET/POST /conversations`、`GET/PATCH /conversations/{id}`、`GET /conversations/{id}/messages`、**`POST /conversations/{id}/messages`（SSE）**、`GET /conversations/{id}/summary` |
| `api-memory-service.ts` | `GET /me/memories`、`PATCH /me/memories/{id}`、`GET /me/evidence/{id}`、`GET /me/insights`、`GET /me/insights/{id}`、`GET /me/episodes`、`GET /me/episodes/{id}` |
| `api-quiz-service.ts` | `POST /quiz-sessions`（**生产未调用**）、`GET /quiz-sessions`、`GET /quiz-sessions/{id}`、`GET .../questions`、`POST .../questions/{qid}/answers`、`POST .../hints`、`GET .../answers`、`GET .../interactions` |
| `api-recommendation.ts` | `GET /me/recommendations`、`POST /me/recommendations/{id}/dismiss`、`GET /me/learning-next` |
| `learning-service.ts` | `POST /learning-sessions`、`PATCH /learning-sessions/{id}`、`POST /learning-events`、`PUT /me/progress/{bookId}`、`PUT /me/chapters/{chapterId}/completion` |
| `admin-service.ts` | `GET /admin/stats`、`GET /admin/books`、`POST/PATCH /admin/books`、`POST /admin/books/{id}/chapters`、`PATCH /admin/chapters/{id}`、`POST /admin/chapters/{id}/content-blocks`、`POST /admin/knowledge-points`、`POST /admin/knowledge/resources`、`POST .../reprocess`、`GET /knowledge/resources`（6 种 status 各拉一次）、`GET /me/admin`、`GET/POST/PATCH /admin/teacher-roles` |

---

## 3.5 ⚠️ 失败被渲染成「安心的空态」（跨页面系统性问题）

多个页面在请求失败时展示的是**看起来正常的空状态**，学生无法区分「没有数据」与「加载失败」：

| 位置 | 失败后的表现 |
| --- | --- |
| `use-home-data.ts:209,218` | `statsError`/`memoriesError` 未被消费 → `getMemories` 失败时显示「我还没有记住关于你的稳定线索」 |
| `LibraryPage.tsx:183-185` | 进度请求失败 → **每本书都静默显示「未开始」** |
| `QuizDetailPage.tsx:98` | 加载失败 → 「答卷不存在。」 |
| `ProfilePage.tsx:107` | 只暴露 prefs 失败，其余区块失败不提示 |
| `ReaderPage.tsx:176-189` | `getChapter` 失败时**伪造** `{...chapter, content_blocks: []}` → 显示「本章暂无内容」 |
| `SettingsPage.tsx:96-115` | 见 §4.4 |

> 首页（`use-home-data.ts`）反而是**正面样板**：它有 6 个独立的 per-section error flag，一个次要接口失败不会拖垮整页。
> 问题是这些 flag 并未全部被消费。

## 4. ⚠️ 需要特别注意的四处的「看起来是 A，其实是 B」

### 4.1 `ProfilePage` 的 `.agent.md` 是**前端合成**的

- `ArchiveDocCard.tsx:63` 渲染标题 `{nickname}.agent.md`，看起来像后端的 agent 档案文件。
- 实际内容由浏览器端 `buildMarkdown(profile, prefs, insights)`（`ArchiveDocCard.tsx:47`，实现在 `profile-labels.ts`）生成，
  frontmatter 由客户端 state 拼装（`:49-57`）。
- 后端**确实有** `GET /api/v1/me/agent.md`（实测返回 125 KB 真实 Markdown），**前端从不调用它**。
- 定性：**PARTIAL**（输入数据是真的，产物不是服务端的那个产物）。

### 4.2 `useCompanionDock` 的「主动建议」是**假定时器**

`useCompanionDock.ts:66-78`：硬编码 `setTimeout` 在 6 秒时显示「有一个新建议」徽标，13 秒隐藏。
**不由任何真实建议驱动**。这是生产环境中**唯一用户可见的伪造行为**。
（注释写「7s 恢复」，代码是 13000ms —— 注释与代码也不一致。）

### 4.3 `ResourceState` 是**死代码**

`src/shared/ui/ResourceState.tsx`（62 行）是一个做得很好的加载/空/错误组件
（`role="alert"`/`role="status"`、`data-testid`、`requestId` 展示、键盘可达的重试按钮），
**零引用**。它还有自己的 4 个测试（测试死代码）。各页面各自手写了临时标记。

### 4.4 ⚠️ `SettingsPage` 的加载失败会导致**软锁**（Medium-High）

`SettingsPage.tsx:96-99` 用一个 `Promise.all([getPreferences(), getTeacherRoles()])` 初始化表单，
但**整个成功分支（含全部 `currentUser` 派生字段的初始化）都写在 `await` 之后**（`:100-112`），
而 `catch` 是**空的**（`:113-115`）。

**后果**：加载失败时表单静默渲染 `nickname: ''` + 硬编码默认值，**没有任何错误提示**。
用户点击保存 → 提交 `nickname: ''` → 后端拒绝（`identity/schemas.py:55` 有 `min_length=1`）
→ 前端只显示通用的「保存失败，请重试」。

**定性**：**软锁，不是数据损坏**。经核对后端，`updatePreferences` 根本不会被触达，
所以**不会**静默覆盖真实的用户偏好。（这一点值得强调：如果只读前端代码，很容易误判为数据丢失。）

---

## 5. 已达成的良好实践（不要回退）

| 实践 | 位置 |
| --- | --- |
| **账号切换隔离**：生成纪元（epoch）+ 按用户分键 | `conversation-store.ts`、`account-switch.test.tsx` |
| **SSE 幂等**：`Idempotency-Key` + 重放 | `api-conversation-service.ts:296`、`conversation-store.ts` |
| **ADMIN 身份服务端复核**（刷新时也复核，不信任 token） | `AuthProvider.tsx:74-85` |
| **全局 401 事件** 统一清登录态 | `http.ts:91-93`、`AuthProvider.tsx:149-158` |
| **Safe Markdown**：原始 HTML 转义、`javascript:` 链接拒绝 | `MarkdownMessage.tsx`（7 测试） |
| **语音全双工**：AudioWorklet（非 MediaRecorder）48k→16k 降采样，100ms 定长 PCM 帧 | `audio-capture.ts` + `public/audio-worklet-processor.js` |
| **拒绝发出无法追溯的事件**：无真实 `conversationId` 时 `buildQuestionAskedEvent` 返回 `null` | `learning/events.ts:54` |
| **`VOICE_SESSION_ENDED` 恰好一次**守卫 | `learning/events.ts:82-99` |
| **测试反硬编码**：断言没有任何 intent 包含写死的书/章/数量/日期 | `intents.test.ts` |
| **逐区块错误降级**：一个次要接口失败不拖垮整页 | `use-home-data.ts`、`ProfilePage.tsx` |

---

## 6. 状态管理

### 6.1 zustand —— 恰好 3 个 store

| Store | 作用域 | 后端 |
| --- | --- | --- |
| `useConversationStore`（692 行） | 消息、流式、会话 id/历史、epoch 隔离、幂等 | **真实**（SSE + REST） |
| `useCompanionStore` | 面板开合、Dock 位置、桌宠 id、AI 动画态 | 仅本地（localStorage） |
| `useToastStore` | 瞬时 toast（2200ms 自动消失，31 处调用） | 仅本地 |

### 6.2 ⚠️ React Query **装了、配了、但完全没用**

- `QueryClientProvider` 包裹应用，`queryClient` 配了完整的重试策略（401/403 不重试、408/425/429/5xx 重试 1 次、429 尊重 `retryAfterMs`）与 `staleTime: 60_000`。
- **`useQuery`: 0 次。`useMutation`: 0 次。`invalidateQueries`: 0 次。`setQueryData`: 0 次。**
- 唯一的 `queryClient` 使用是登出时 `queryClient.clear()`（`reset-user-state.ts:17`）。
- `query-keys.ts`（19 行，定义了防跨账号缓存污染的 `userScopedKey` 约定）**零引用**。
- **后果**：没有查询缓存、没有失效策略、没有自动重取。每个页面手写 `useState` + `useEffect` 拉取并在变更后手动重取。

> 这是前端**最大的结构性缺口**：T07 建立的缓存约定（query keys + retry policy）从未被采纳。
> `docs/09-runtime-and-deployment.md` 与 `docs/13-technical-debt.md` 有进一步分析。

---

## 7. 安全相关

| 项 | 现状 | 评价 |
| --- | --- | --- |
| Token 存储 | `localStorage['shuangling-access-token']` | 可被 XSS 读取（无 httpOnly Cookie）。缓解：Markdown 已做 XSS 防护 |
| 密码 | 表单 POST，不落 localStorage | ✅ |
| 演示凭据泄露 | 仅当 `VITE_SHOW_DEMO_CREDENTIALS === 'true'`（`LoginPage.tsx:82`） | ✅ 生产构建默认不显示 |
| 401 处理 | `http.ts` 与 `sse.ts` 均派发；但 **`api-student-service.ts:58-77`（uploadAvatar）与 `learning-service.ts:102-130` 使用原生 fetch，未派发** | ⚠️ **不一致**：会话过期时这两条路径不会清登录态 |
| Admin 前端守卫 | `AdminGuard` 检查 `authUser.user_type`；后端 `require_admin` 独立强制 | ✅ 前端仅体验，后端才是权威 |

---

## 8. 测试覆盖缺口（无测试文件）

`MemoriesPage.tsx`、`LoginPage.tsx`、`ReaderPage.tsx`（仅其子组件有）、
`features/memory/`、`features/feedback/`、`features/voice/audio-capture.ts`、`features/quiz/lib.ts`、
`QuickActions.tsx`、`ConversationPanelContent.tsx`、
`CompanionPanel` / `CompanionPetPicker` / `useCompanionDock` / `useSpriteFrame`、
`app/providers/query.ts`（`shouldRetry`/`retryDelay`）。

**测死代码的测试**（通过但无价值）：`mocks/services/content-service.test.ts`（5）、
`mocks/services/quiz-service.test.ts`（2）、`shared/ui/ResourceState.test.tsx`（4）。

---

## 9. 死代码清单（无任何可达调用方）

| 产物 | 位置 | 原因 |
| --- | --- | --- |
| **5 个 mock service 类** | `src/mocks/services/*.ts` | `src/shared/services.ts` 只注册 `Api*Service` |
| **`query-keys.ts`**（19 行） | `shared/api/query-keys.ts` | 0 引用 |
| **React Query 运行时** | `useQuery`/`useMutation`/`invalidateQueries` | 全仓 0 次 |
| **`ResourceState`**（62 行）+ 其测试 | `shared/ui/ResourceState.tsx` | 0 引用 |
| **`pushStreaming` + `streamTimer`** | `conversation-store.ts:639-667, :123` | 0 调用方；伪造 22ms/字符 打字机 |
| `quizService.createQuizSession` | `api-quiz-service.ts:205` | 0 生产调用方（测试反而断言它**不该**被调用） |
| `contentService.getKnowledgePoint` | `api-content-service.ts:197` | 0 生产调用方 |
| `memoryService.getInsight` | `api-memory-service.ts:236` | 0 生产调用方（用的是 `getInsightDetail`） |
| `quizService.getHints` | `api-quiz-service.ts:272` | 别名，未使用 |
| 「语音聊天」按钮 | `QuickActions.tsx:38-44` | 渲染了但**没有 `onClick`** |
| `shouldRetry`/`retryDelay` | `app/providers/query.ts:13,24` | 仅作为永不执行的配置存在 |
| `mocks/delay.ts` | 伪造 150–300ms 延迟 | 仅被死 mock 服务使用 |

---

## 10. 注释与实现不符（文档漂移，前端侧）

| 位置 | 注释声称 | 实际 |
| --- | --- | --- |
| `features/screen-context/types.ts:1` | 「纯前端 Context，**不落服务器**」 | 实际经 3 条通道发送到后端（见下） |
| `features/quiz/lib.ts:10` | 「只读 **Mock** 查询」 | 使用的是真实 `contentService` |
| `api-student-service.ts:16` | 「其余 Service 仍 **Mock**，总控 §27」 | 6 个服务全部是 `Api*` |
| `features/conversation/types.ts:13` | quiz payload「本任务仅**占位**」 | 真的在 `MessageList.tsx:93` 渲染 |
| `useCompanionDock.ts:66` | 「6s 后提示、**7s** 恢复」 | 代码是 **13s** |

### ScreenContext 的真实去向（澄清上面第一条）

`ScreenContext` 定义在 `features/screen-context/types.ts:3-18`（route / pageType / bookId / chapterId /
chapterTitle / contentBlockId / visibleSection / selectedText / knowledgePoints / actions / quizSessionId / questionId），
**经三条通道真实发送到后端**：

1. **对话（主通道）**：`ChatComposer.tsx:201` → `conversation-store.ts:336,428-430` →
   `POST /conversations/{id}/messages` 的 `screen_context` 字段（`api-conversation-service.ts:288`，白名单 + snake_case 12 个字段）。
2. **语音**：`voice-client.ts:105-107,130-131` 通过 WS 发 `{type:'context', screen_context}`；
   路由变化时在通话中重新推送（避免陈旧章节上下文）。
3. **Intent**：`QuickActions.tsx:32`、`HomePage.tsx:30`、`LibraryPage.tsx:200`、`ProfilePage.tsx:125`、`ReaderPage.tsx:447,464` → 同一 `send` 路径。

→ 注释「不落服务器」中「不持久化」为真，「不发送」为假。
