# B — Frontend Archaeology Audit (霜铃 K12 AI Digital Teacher)

**Target:** `/home/zxk/Projects/K12-Learning-platform/frontend`
**Stack:** React 19.2.8 · TypeScript 7.0.2 · Vite 8.2.1 · react-router-dom 7.18.2 · zustand 5 · @tanstack/react-query 5 · vitest 4 · Playwright 1.62
**Mode:** read-only. No source file was modified. `tsc --noEmit`, `npm run build`, and `vitest run` were executed (build writes only `dist/`, which is git-ignored — `frontend/.gitignore:2`).
**Scale:** 174 source files, 21,535 LOC (ts/tsx), 49 unit test files, 11 Playwright specs.

**Labels used:** `REAL` (talks to backend) · `PARTIAL` (real but gated/limited) · `MOCK` (fabricated data) · `STUB` (placeholder behavior) · `DEAD_CODE` (no reachable caller) · `DISCONNECTED` (implemented but no UI path) · `UNKNOWN`.

---

## 0. Headline verdict (read this first)

1. **There is no mock layer in the running app.** `src/shared/services.ts:21-26` registers **only** `Api*Service` classes. There is no MSW, no mock env-var, no dynamic import, no toggle. Verified: zero `msw`/`VITE_USE_MOCK`/`setupWorker` hits repo-wide.
2. **The production bundle contains zero mock data.** All mock markers (`stu-xiaoming`, `mock-model`, `mock-access-token`, `demo123`, `AI 不是魔法`, `q-live`, `conv-1`, `msg-1`) are **ABSENT** from `dist/assets/*.js`. Only the static `QUICK_ACTIONS` UI labels survive tree-shaking.
3. **Five of six mock service classes have zero importers anywhere** (not even tests) — pure `DEAD_CODE`.
4. **The only production import of `src/mocks/`** is `QuickActions.tsx:3` importing static button labels — real data, not fabricated facts.
5. **React Query is dead infrastructure.** `useQuery`/`useMutation`/`invalidateQueries` appear **zero** times in the entire source tree. `query-keys.ts` has **zero importers**.
6. **`ResourceState` (the Loading/Empty/Error component) has zero importers** — every page hand-rolls its own states.
7. `tsc --noEmit` → **exit 0, zero errors**. `npm run build` → **exit 0**. `vitest run` → **49 files / 258 tests, all pass**.
8. **The most important non-mock defect is `SettingsPage`** (§4.4 #1): a failed preferences load is swallowed, the form then shows an empty nickname plus hardcoded defaults with no error, and saving is impossible (backend rejects the empty nickname) behind a generic "保存失败，请重试". A soft-lock, not data loss — verified against the backend.

---

## 1. Routing — `src/app/router/index.tsx` (124 lines)

`createBrowserRouter` (`:89`). Root `/` redirects to `/home` (`:90`). Login is the only non-layout route (`:122`).

### Layout & guards
| Guard | Lines | Behavior |
|---|---|---|
| `RequireAuth` | `:55-75` | Reads `{currentUser, authUser, loading}` from `useAuth()`. While `loading` renders "正在恢复登录态…" (`:58-64`). If neither `currentUser` nor `authUser` → `<Navigate to="/login" replace state={{from: pathname+search}}>` (`:66-73`) |
| `AdminGuard` | `:77-87` | `if (!authUser \|\| authUser.user_type !== 'ADMIN')` → renders a 403 block (`:81-84`). **Client-side only**; the real check is the backend `require_admin` (see §5.6). |
| `withSuspense` | `:27` | `fallback={null}` — **no loading skeleton on route transitions** |
| `NotFoundPage` | `:29-53` | Catch-all `{ path: '*' }` at `:123` renders it **outside** `RequireAuth`, so 404 is public. Uses `useLocation()` to echo the bad path. Links to `/home` and `/library`. |

### Route table
| Path | Component | Lazy | Auth | Admin | Chunk (build output) |
|---|---|---|---|---|---|
| `/` | `<Navigate to="/home">` | — | — | — | — |
| `/home` | `HomePage` | ✅ `:11` | ✅ | — | `HomePage-*.js` 16.66 kB |
| `/library` | `LibraryPage` | ✅ `:12` | ✅ | — | `LibraryPage-*.js` 12.22 kB |
| `/books/:bookId` | `BookDetailPage` | ✅ `:13` | ✅ | — | `BookDetailPage-*.js` 10.66 kB |
| `/learn/:bookId/:chapterId` | `ReaderPage` | ✅ `:14` | ✅ | — | `ReaderPage-*.js` 20.31 kB |
| `/quizzes` | `QuizzesPage` | ✅ `:15` | ✅ | — | `QuizzesPage-*.js` 4.25 kB |
| `/quizzes/:quizId` | `QuizDetailPage` | ✅ `:16` | ✅ | — | `QuizDetailPage-*.js` 5.73 kB |
| `/profile` | `ProfilePage` | ✅ `:17` | ✅ | — | `ProfilePage-*.js` 25.34 kB |
| `/profile/memories` | `MemoriesPage` | ✅ `:18` | ✅ | — | `MemoriesPage-*.js` 7.04 kB |
| `/settings` | `SettingsPage` | ✅ `:19` | ✅ | — | `SettingsPage-*.js` 11.64 kB |
| `/admin` (index) | `AdminDashboard` | ✅ `:21` | ✅ | ✅ | `admin-*.js` 18.15 kB (shared) |
| `/admin/books` | `AdminBooks` | ✅ `:22` | ✅ | ✅ | ↑ |
| `/admin/knowledge` | `AdminKnowledge` | ✅ `:23` | ✅ | ✅ | ↑ |
| `/admin/styles` | `AdminStyles` | ✅ `:24` | ✅ | ✅ | ↑ |
| `/admin/chapters` | `AdminChapters` | ✅ `:25` | ✅ | ✅ | ↑ |
| `/login` | `LoginPage` | ❌ eager `:7` | — | — | in `index-*.js` |
| `*` | `NotFoundPage` | ❌ `:123` | — | — | in `index-*.js` |

**Verdict: REAL.** All 10 pages are lazy route-split; `AppLayout` and `LoginPage` stay eager for login restore (`:9-10` comment). Catch-all/404 exists (`:123`). Admin is both route-guarded (`:107-119`) **and** verified server-side via `adminService.getAdminMe()` (`AuthProvider.tsx:53-60`).

**Gaps:**
- `Suspense fallback={null}` (`:27`) → blank flash on slow chunk load, no skeleton.
- `/admin` relies on `authUser.user_type` decoded from the JWT (`AuthProvider.tsx:28-41`); on refresh, ADMIN is optimistically set (`:77`) then verified — a brief window where the 403 UI is not yet shown.

---

## 2. API layer — `src/shared/api/`

### 2.1 `http.ts` (123 lines) — fetch wrapper
| Concern | Implementation |
|---|---|
| Base URL | `API_BASE = '/api/v1'` (`:4`) — **relative**; dev proxied by Vite to `localhost:8000` (`vite.config.ts` server.proxy, `ws: true`) |
| Auth header | `getToken()` from localStorage → `Authorization: Bearer <token>` (`:76-77`) |
| 401 handling | `emitUnauthorized()` (`:91-93`) dispatches `shuangling:unauthorized` window event (`:6-15`); `AuthProvider.tsx:149-158` listens and clears all user state |
| Envelope parsing | `apiRequest` unwraps `{ data }` (`:49`); `apiRequestEnvelope` returns `{data, meta}` (`:53-58`) for cursor pagination (`CursorMeta` `:65-69`) |
| Error envelope | Non-2xx → `ApiError(status, code, message, details, requestId, retryAfterMs)` (`:99-110`); reads `error.code`/`error.message`/`error.details` |
| 204 | Returns `undefined` (`:94-96`) |
| Headers surfaced | `x-request-id` (`:87`), `retry-after` parsed as seconds **or** HTTP date (`:116-123`) |
| AbortSignal | Passed through (`:41`, `:84`) for route/account-switch cancellation |
| **Retry** | **None in `http.ts`.** Retry lives only in the React Query client (which never runs) — see §2.7 |

**Raw-`fetch` bypasses (do NOT get the above for free):**
- `api-student-service.ts:58-77` `uploadAvatar` — builds its own `fetch` + `FormData`. **On 401 it does NOT call `emitUnauthorized()`** (unlike every other path) → an expired session during avatar upload throws but leaves the user in a half-logged-in state. *Finding: PARTIAL / inconsistency.*
- `learning-service.ts:102-130` `apiRequestWithToken` — a **second** hand-rolled request path used by `endSession` so it can reuse the token captured at `createSession` time (`:133`, `:141`). It re-implements envelope unwrap + `ApiError` but does **not** emit the 401 event.
- `api-quiz-service.ts:179-202` `requestWithHeaders` — third hand-rolled path (`submitAnswer`), does attach `Bearer` + `Idempotency-Key` (`:251-259`) but no 401 event.
- `admin-service.ts:34-62` `requestWithKey` and `:113-146` `uploadKnowledgeResource` — hand-rolled, but these **do** call `emitUnauthorized()` (`:53-57`, `:134-141`) — explicitly fixed in "Phase 5-A 整改 5" (`:54`).
- `voice-client.ts` / `sse.ts` — `sse.ts:107-109` **does** emit on 401 (and `unauthorized.test.ts` asserts it: *"SSE 收到 401 同样派发统一未授权事件"*).

### 2.2 `sse.ts` (147 lines) — streaming transport
`fetchSSE(url, options)` (`:86-147`) is a **POST-compatible** SSE reader (not `EventSource`, because it must send an auth header + JSON body).
- `parseSSEFrame` (`:32-59`): handles `id`/`event`/`data` fields, strips one leading space (`:43`), joins multiple `data:` lines (`:51`), JSON-parses with plain-text fallback (`:53-57`), returns `null` for comment-only heartbeats (`:50`, `:39`).
- Frame boundaries: `frameEnd` (`:20-29`) supports both `\n\n` and `\r\n\r\n`.
- Incremental `TextDecoder({stream:true})` (`:117`, `:128`) — **correctly handles multi-byte UTF-8 split across chunks**; asserted in `sse.test.ts` (*"在 UTF-8 中文字符被拆到不同 chunk 时仍能解析完整事件"*).
- Sets `accept: text/event-stream` and `content-type: application/json` when a body exists (`:92-95`), injects `authorization` only if absent (`:96-97`).
- 401 → `emitUnauthorized()` (`:107-109`); non-2xx → structured `ApiError` via `responseError` (`:61-71`).
- `finally { reader.releaseLock() }` (`:140-142`); errors re-thrown after `onError` (`:143-146`) so callback failures never mask the transport error (`:73-80`).

**Verdict: REAL, high quality.**

### 2.3 `voice-client.ts` (139 lines) — WebSocket client
- URL: `ws(s)://${host}/api/v1/voice/ws?conversation_id=..&token=..` (`:36-40`) — token in query string, uses `window.location.host` so the Vite proxy handles it.
- Inbound frames (`:57-85`): `state` / `partial` / `final` / `reply` / `audio` / `error`; malformed frames swallowed to keep the socket alive (`:82-84`).
- Outbound (`:124-138`): `connect`, `sendAudioChunk` (`{type:'audio_chunk',data}`), `sendAudioEnd`, `cancel`, `ping`, `sendScreenContext` (`{type:'context',screen_context}`), `close`.
- 30 s heartbeat (`:96`), single reconnect attempt on close (`:117-120`), `initialScreenContext` sent on open (`:105-107`).
- Test seam `createSocket` (`:22`) for unit tests.

**Verdict: REAL and wired — see §5.9.** It is **not** disconnected.

### 2.4 `auth.ts` (13 lines)
localStorage key `shuangling-access-token` (`:1`). `getToken`/`setToken`/`clearToken`. `setToken` is called by `ApiStudentService.login` (`api-student-service.ts:24`).

### 2.5 `query-keys.ts` (19 lines) — **DEAD_CODE**
Defines `queryKeys` (`:3-14`) and `userScopedKey` (`:17-19`) with a documented convention that user-scoped keys must embed `user_id` (`:1`) to prevent cross-account cache bleed.
**Zero importers.** `grep -rn "queryKeys\|userScopedKey" src` returns only the definition file itself. The convention is documented but never applied, because no query exists.

### 2.6 Per-module endpoint table (exact method + path)

All paths are prefixed with `/api/v1` by `API_BASE`.

| Module | Method + Path | Client fn |
|---|---|---|
| `api-student-service.ts` | `POST /auth/login` | `:19` |
| | `POST /auth/logout` | `:29` |
| | `GET /me` | `:36` |
| | `PATCH /me` | `:40` |
| | `GET /me/preferences` | `:44` |
| | `PATCH /me/preferences` | `:48` |
| | `GET /teacher-roles?enabled=true` | `:55` |
| | `POST /me/avatar` (raw fetch, FormData) | `:62` |
| `api-content-service.ts` | `GET /books` (+cursor/limit/stage/topic/search) | `:162-163` |
| | `GET /books/{bookId}` | `:177` |
| | `GET /books/{bookId}/chapters` | `:181` |
| | `GET /chapters/{chapterId}` | `:188` |
| | `GET /knowledge-points/{id}` — **never called in prod** | `:200` |
| | `GET /me/progress` | `:206` |
| | `GET /me/progress/{bookId}` | `:211` |
| `api-conversation-service.ts` | `GET /conversations` (+cursor/limit/status/channel) | `:200-207` |
| | `GET /conversations/{id}` | `:214` |
| | `POST /conversations` (+`Idempotency-Key`) | `:220-224` |
| | `PATCH /conversations/{id}` | `:233` |
| | `GET /conversations/{id}/messages` | `:241-247` |
| | `POST /conversations/{id}/messages` — **SSE stream** | `:330-333` |
| | `GET /conversations/{id}/summary` | `:337` |
| `api-memory-service.ts` | `GET /me/memories` | `:200` |
| | `PATCH /me/memories/{id}` | `:211` |
| | `GET /me/evidence/{id}` | `:224` |
| | `GET /me/insights` | `:231` |
| | `GET /me/insights/{id}` (via `requestWithMeta`, reads `meta.evidence`) | `:242-243` |
| | `GET /me/episodes` | `:253` |
| | `GET /me/episodes/{id}` | `:261` |
| `api-quiz-service.ts` | `POST /quiz-sessions` — **never called in prod** | `:215` |
| | `GET /quiz-sessions` | `:223-224` |
| | `GET /quiz-sessions/{id}` | `:232` |
| | `GET /quiz-sessions/{id}/questions` | `:239-240` |
| | `POST /quiz-sessions/{id}/questions/{qid}/answers` (raw+`Idempotency-Key`) | `:253-254` |
| | `POST /quiz-sessions/{id}/questions/{qid}/hints` | `:265-266` |
| | `GET /quiz-sessions/{id}/answers` | `:277` |
| | `GET /quiz-sessions/{id}/interactions` | `:284` |
| `api-recommendation.ts` | `GET /me/recommendations` | `:11` |
| | `POST /me/recommendations/{id}/dismiss` | `:16` |
| | `GET /me/learning-next` | `:22` |
| `learning-service.ts` | `POST /learning-sessions` | `:137` |
| | `PATCH /learning-sessions/{id}` (`{status:'ENDED'}`) | `:149`/`:155` |
| | `POST /learning-events` | `:168` |
| | `PUT /me/progress/{bookId}` | `:178` |
| | `PUT /me/chapters/{chapterId}/completion` | `:185` |
| `admin-service.ts` | `GET /admin/stats` | `:66` |
| | `GET /admin/books?limit=100` | `:71` |
| | `POST /admin/books` (reprocess-key) | `:77` |
| | `PATCH /admin/books/{id}` | `:85` |
| | `GET /knowledge/resources?status=…&limit=100` ×**6 statuses** | `:90-97` |
| | `POST /admin/knowledge/resources` (FormData) | `:122` |
| | `POST /admin/knowledge/resources/{id}/reprocess` | `:150` |
| | `POST /admin/books/{id}/chapters` | `:157` |
| | `PATCH /admin/chapters/{id}` | `:160` |
| | `POST /admin/chapters/{id}/content-blocks` | `:163` |
| | `POST /admin/knowledge-points` | `:166` |
| | `GET /me/admin` | `:169` |
| | `GET /admin/teacher-roles` | `:173` |
| | `POST /admin/teacher-roles` | `:178` |
| | `PATCH /admin/teacher-roles/{id}` | `:181` |

**Note — N+1 fan-out:** `adminService.getKnowledgeResources()` (`:88-111`) issues **6 parallel requests** (one per status) and de-dupes client-side by `resource_id` (`:100-109`). Backend supports a status filter but not "all"; this multiplies load under the T21 polling loop.

### 2.7 Retry — configured but never exercised
`app/providers/query.ts` defines a careful policy: `shouldRetry` (`:13-22`) — no retry on 401/403, retry on 408/425/429/5xx and network errors, max 1 retry (`:14`); `retryDelay` (`:24-29`) honors `retryAfterMs` for 429, else exponential capped at 8 s. `queryClient` defaults `staleTime: 60_000`, `refetchOnWindowFocus: false` (`:31-42`).
**However: no query or mutation is ever created (§6.2), so this code never executes.** `shouldRetry`/`retryDelay` have **no tests**.

---

## 3. Mocks — `src/mocks/` (CRITICAL SECTION)

### 3.1 How are mocks activated?
**They are not.** Exhaustive search results:

| Mechanism searched | Result |
|---|---|
| `msw` / `setupWorker` / `setupServer` | **0 hits** repo-wide (`package.json` has no `msw` dependency) |
| `VITE_USE_MOCK` / `USE_MOCK` / `MOCK_MODE` env var | **0 hits** |
| Dynamic `import()` of a mock module | **0 hits** |
| `.env` / `.env.local` | **no `.env` file exists** — only `.env.example` (which contains just `VITE_SHOW_DEMO_CREDENTIALS`) |
| Conditional service registration | **none** — `src/shared/services.ts:21-26` unconditionally instantiates `Api*Service` |

The original activation mechanism was **manual source editing**, documented in `src/shared/services.ts:16-20`:
> *"统一 Service 注册表（总控 §10.5 / §27）。替换边界：Phase 2 起逐个把实例替换为 ApiXxxService（接口不变，只改这里）。2-D：StudentService 已切真实后端；3-D：ContentService 已切真实后端；4-D：ConversationService 已切真实后端；4-E：MemoryService 已切真实后端；5-C：QuizService 已切真实后端。"*

All five swaps are complete. `recommendationService` is the sixth and is also `ApiRecommendationService` (`:26`). **The mock activation switch no longer exists — mocks are orphaned.**

### 3.2 Every import of `src/mocks/` — full repo census
```
src/features/conversation/components/QuickActions.tsx:3:  import { QUICK_ACTIONS } from '@/mocks/data/conversation'
src/pages/library/LibraryPage.test.tsx:7:                 import { mockBooks } from '@/mocks/data/books'
```
**That is the complete list.** One production import (static UI labels), one test import.

### 3.3 Mock service reachability — every class
| Mock class | File | Importers | Reachable from app? |
|---|---|---|---|
| `MockStudentService` | `services/student-service.ts:15` | **NONE** (not even a test) | ❌ `DEAD_CODE` |
| `MockContentService` | `services/content-service.ts:31` | `content-service.test.ts:3,5` only | ❌ `DEAD_CODE` (self-test only) |
| `MockConversationService` | `services/conversation-service.ts:58` | **NONE** | ❌ `DEAD_CODE` |
| `MockQuizService` | `services/quiz-service.ts:51` | `quiz-service.test.ts:3,5` only | ❌ `DEAD_CODE` (self-test only) |
| `MockMemoryService` | `services/memory-service.ts:15` | **NONE** | ❌ `DEAD_CODE` |
| `MockRecommendationService` | `services/recommendation-service.ts:8` | **NONE** | ❌ `DEAD_CODE` |

`MockRecommendationService:6` even self-documents: *"测试/离线替身；生产注册表使用 ApiRecommendationService"* — yet it has no test either.

**Consequence:** `content-service.test.ts` (5 tests) and `quiz-service.test.ts` (2 tests) are **tests of dead code**. They pass, and they inflate the suite, but they protect nothing in the shipped app.

### 3.4 Mock data reachability
| File | Consumed by | Verdict |
|---|---|---|
| `data/books.ts` | `MockContentService`, `LibraryPage.test.tsx:7` | `DEAD_CODE` in prod; 1 test fixture |
| `data/conversation.ts` → `QUICK_ACTIONS` (`:88-118`) | **`QuickActions.tsx:3` (production)** | **REAL usage — static UI labels only** |
| `data/conversation.ts` → `mockMessages`/`mockConversation` (`:4-86`) | `MockConversationService` only | `DEAD_CODE`; tree-shaken from bundle |
| `data/memory.ts` | `MockMemoryService` only | `DEAD_CODE` |
| `data/quizzes.ts` | `MockQuizService` only | `DEAD_CODE` |
| `data/student.ts` | `MockStudentService` only | `DEAD_CODE` |
| `delay.ts` (150-300 ms fake latency) | all mock services | `DEAD_CODE` |

### 3.5 Bundle proof (no mock data ships)
Built `dist/` and grepped every chunk:

| Marker | Present in `dist/assets/*.js`? |
|---|---|
| `stu-xiaoming` | ABSENT |
| `mock-model` | ABSENT |
| `mock-access-token` | ABSENT |
| `demo123` | ABSENT |
| `AI 不是魔法` (mock book title) | ABSENT |
| `q-live` | ABSENT |
| `conv-1`, `msg-1` | ABSENT |
| `我看到你现在在` (mock message text) | ABSENT |
| `今天学什么` (**real** `QUICK_ACTIONS` label) | **PRESENT** (`index-DWBdU-65.js`) |

Rollup correctly tree-shook the sibling `mockMessages`/`mockConversation` exports while retaining the genuinely-used `QUICK_ACTIONS`. **VERDICT: no mock data in production.**

---

## 4. Pages — `src/pages/`

All pages consume the real service registry (`src/shared/services.ts`) or real API modules. **No page renders `src/mocks/` data.** No page contains hardcoded fake backend data; the only module-level literals are legitimate option lists: `SettingsPage.tsx:17,23,47` (`AGE_OPTIONS`, `AVATAR_PRESETS` emoji, `SPEED_OPTIONS`), `LibraryPage.tsx:13` (`TOPICS` filter chips), `AdminLayout.tsx:3` (`LINKS` nav).

### 4.1 Page-by-page table

| Page | Route | API service & methods | Data rendered | Real/Mock | Loading/Error/Empty | Tests |
|---|---|---|---|---|---|---|
| **HomePage** | `/home` | `studentService.getMe`; `contentService.getProgress/getBook/getChapter`; `memoryService.getEpisodes/getMemories`; `quizService.getQuizSessions`; `recommendationService.getRecommendations/getLearningNext/dismissRecommendation` (all via `use-home-data.ts:76,95,108,109,131,139,147,161,181,197`) | nickname, 5 stats, continue-learning card, episodes, memories, quizzes, ≤3 recommendations (`status==='ACTIVE'`, `.slice(0,3)` `:162`), next-action | **REAL** | ✅ per-section flags `statsError`/`progressError`/`episodesError`/`memoriesError`/`quizzesError`/`recommendationsError` (`:52-69`); continue card 4 states (`ContinueLearningCard.tsx:28-34,36-52,54-111,114-131`), rec loading/error+retry/empty (`HomePage.tsx:256-268`). ⚠️ **`statsError` (`:209`) and `memoriesError` (`:218`) are NEVER consumed** — a failed `getMe` silently deletes the stats bar (`HomePage.tsx:144`), and a failed `getMemories` renders the cheerful empty copy "我还没有记住关于你的稳定线索" (`:213-216`). `NextActionCard` not rendered at all on failure (`:123`) | `HomePage.recommendation.test.tsx` (8, mocks all 5 services `:21-38`), `components/ContinueLearningCard.test.tsx` (6), `components/NextActionCard.test.tsx` (3), `home-time.test.ts` (6) |
| **LibraryPage** | `/library` | `recommendationService.getRecommendations/dismissRecommendation` (`:108,124`); `contentService.getBooksPage({search,stage,topic,cursor,limit:12})` (`:139-145`); `contentService.getProgress` (`:181`, re-runs on `books` change `:187`); `useScreenContext` (`:59`) | recommendations with reasons + `evidence_ids`, paginated book grid, continue-learning entry | **REAL** | ✅ list loading `:408-411`, error+retry `:412-423`, empty+清除筛选 `:424-435`; featured loading/error/empty `:310-327`. ⚠️ **progress-load error swallowed** (`:183-185` → `{}`) so every book silently shows "未开始". Hardcoded `TOPICS` taxonomy `:13` is sent as the filter value (`:142`) — if it drifts from the backend taxonomy the chips silently return nothing | `LibraryPage.test.tsx` (9) — asserts debounced **backend** search ("非本地过滤"), cursor paging, error+retry; uses `mockBooks` as fixture `:7,28` |
| **BookDetailPage** | `/books/:bookId` | `contentService.getBook/getChapters/getBookProgress` via `Promise.allSettled` (`:52-56`), `getChapter` for knowledge points (`:83`) | title, description, author, grade, minutes, chapter list w/ completion, "你将学会什么" | **REAL** | ✅ page loading (aria-busy + `role="status"`) `:96-108`, book error `:110-129`, chapters skeleton/error/empty (`BookDetailSections.tsx:120-135`), progress unavailable/empty `:72-73,97`. ⚠️ **knowledge-points error silently hidden** — `:85-87` sets `null` and `BookDetailSections.tsx:175` returns `null` | `BookDetailPage.test.tsx` (7, mocks `contentService`) |
| **ReaderPage** | `/learn/:bookId/:chapterId` | `contentService.getChapters/getChapter/getBook/getBookProgress` (`:168,174,181,210`); `learningService.upsertProgress` (`:145,223`) `/createSession` (`:259`) `/endSession` (`:274,287`) `/createEvent` (`:92`) `/markChapterCompleted` (`:576`); `runIntent` (`:447,464`) | chapter body blocks, TOC, knowledge points, completion card, screen-context sidebar | **REAL** | ⚠️ **PARTIAL — no error state.** All content fetches are `catch {}`-swallowed (`:169,175,182`). Worse: if `getChapter` throws but the chapter is in the list, `:176-178` **fabricates** `{...chapter, content_blocks: [], knowledge_points: []}` and `:189` shows "本章暂无内容" — a backend failure masquerades as an empty chapter. If it is not in the list, `detail` stays null → **"章节不存在。"** (`:596`), indistinguishable from a real 404. **No retry anywhere.** ✅ loading `:551-552`, empty notice `:565-569`, route-param 400 page `:474-490` | `ContentBlockView.test.tsx` (5, render-only), `ChapterCompletionCard.test.tsx` (7, stubbed `onSubmit`). **No `ReaderPage.test.tsx`** — service wiring, session lifecycle and event emission untested |
| **QuizzesPage** | `/quizzes` | `quizService.getQuizSessions(paramsForFilter(filter))` (`:42`); `quizSource` helper (`:58`) → `contentService.getBook/getChapter/getChapters` | quiz history list with source book/chapter; per-source failure degrades to `—` (`:55-63,141`) | **REAL** | ✅ loading `:114-115`, error+retry `:102-113`, empty `:116-122` | `QuizzesPage.test.tsx` (2). Dead local: `const filtered = sessions` (`:73`) is vestigial — filtering is server-side |
| **QuizDetailPage** | `/quizzes/:quizId` | `quizService.getQuizSession/getQuestions/getAnswers/getInteractions` (`:46,57,58,59`); `quizSource` (`:70,78`); `runIntent` (`:108,112`) | read-only answer sheet, correct/chosen options, explanations, "讲解这道题"/"再练一道" | **REAL** | ✅ loading `:89-91`. ⚠️ **no error state** — a rejected `getQuizSession` sets `session=null` (`:47-52`) → renders "答卷不存在。" (`:98`), failure indistinguishable from 404, no retry. ⚠️ **no empty state** for 0 questions (`:229-231` renders "共 0 题"). ⚠️ `const { quizId = 'q1' } = useParams()` (`:32`) — a **mock-looking default ID** used for the real API call when the route param is missing | `QuizDetailPage.test.tsx` (3) — asserts read-only (**0 writes**) |
| **ProfilePage** | `/profile` | `studentService.getPreferences/updateMe/updatePreferences` (`:83,153,166`); `memoryService.getInsights/getInsights({SUPERSEDED})/getMemories/getEpisodes/getInsightDetail/getEpisodeDetail` (`:84-87,132,137`) | 5-level qualitative insights (**no percentages**), episodes, memories, `.agent.md` card, learning-goal editor, JSON export | **REAL** (see ⚠️ §4.2) | ✅ not-logged-in `:223-229`, skeleton `:35-43,231`, prefs error+retry `:235-248`. ⚠️ **only the prefs rejection sets `loadError` (`:107`)** — insights/memories/episodes failures are swallowed (`:90-105`) and render as **empty states** (`InsightListCard.tsx:42-45`, `HistoryCard.tsx:14-15`, `EpisodeListCard.tsx:46-47`, `ProfileSidebar.tsx:35-38`) | `ProfilePage.test.ts` (9), `profile-labels.test.ts` (2) |
| **MemoriesPage** | `/profile/memories` | `memoryService.getMemories/updateMemory/getEvidence` (`:64,83,109`) | memory list w/ CONFIRM/DISPUTE/FORGET/EDIT | **REAL** | ✅ loading + error + empty | ❌ **NO TEST** |
| **SettingsPage** | `/settings` | `studentService.getPreferences/getTeacherRoles` (`:96-99`), `updateMe` (`:134`, `:156`), `updatePreferences` (`:135`), `uploadAvatar` (`:174`); `learningService.createEvent(ROLE_SWITCHED)` (`:157-163`) | profile edit, grade/age, avatar (emoji preset or upload), teacher role cards, voice prefs, companion pet picker | **REAL** — ⚠️ **but see the highest-risk finding in §4.4** | ✅ loading gate "正在加载设置…" `:189-197`; teacher-roles empty "暂无可用教师" `:432-433`. ⚠️ **NO error state** — load failure is swallowed at `:113-115` (`// 保留默认表单`) | `SettingsPage.test.ts` (2) — role switch + pet picker only; **`save()`, avatar upload and the load-failure path are untested** |
| **LoginPage** | `/login` | `useAuth().login` → `studentService.login` → `POST /auth/login` | username/password form, error alert, demo-cred hint | **REAL** | ✅ submitting state + `role="alert"` error (`:70-72`) | ❌ **NO TEST** |
| **AdminLayout** | `/admin` | nav shell | 5 admin links | REAL (shell) | n/a | `AdminPages.test.ts` |
| **AdminDashboard** | `/admin` | `adminService.getStats` (`:16`) → `GET /admin/stats` | 8 counters (books/chapters/KP/resources/students) `:31-42` | **REAL** | ✅ loading `:62-63`, error+重新加载 `:44-58`; no empty needed | ❌ **NONE — untested** |
| **AdminBooks** | `/admin/books` | `adminService.getBooks` (`:16`) / `createBook` (`:23`) / `patchBook` (`:39`) | book list + create form + 发布/下架 toggle | **REAL** | ⚠️ **no loading, no error, no empty** — `.catch(() => setBooks([]))` (`:16`) means a failed load renders an empty list with no message; mutation failures toast only (`:33,43`) | `AdminPages.test.ts:97-103` |
| **AdminKnowledge** | `/admin/knowledge` | `adminService.getKnowledgeResources` (`:38`, 6× status fan-out) / `uploadKnowledgeResource` (`:102`, multipart) / `reprocessResource` (`:123`) | resource table + upload form + 3 s polling | **REAL** | ✅ error banner+retry `:137-148`, stale >2 min hint `:132-133,250-254`, visibility-paused polling `:67-70`. ⚠️ **no loading, no empty** | `AdminKnowledge.test.tsx` (5, incl. fake-timer polling) + `AdminPages.test.ts:105-112` |
| **AdminStyles** | `/admin/styles` | `adminService.getTeacherRoles` (`:16`) / `createTeacherRole` (`:32`) / `patchTeacherRole` (`:41`) | teacher role/style cards | **REAL** | `error` `:77-81` doubles as validation message `:27-30`; ⚠️ **no loading, no empty**; ⚠️ `toggle()` `:40-43` has **no try/catch → unhandled rejection, no user feedback** | `AdminPages.test.ts:154-168` |
| **AdminChapters** | `/admin/chapters` | **reads via the STUDENT `contentService`** — `getBooks/getChapters/getChapter` (`:24,37,50,66,77,94`); writes via `adminService.createChapter` (`:61`) / `patchChapter` (`:76`) / `createContentBlock` (`:87`) / `createKnowledgePoint` (`:104`) | chapter/content-block/KP editor | **REAL** | ⚠️ **no loading, no error, no empty** — every catch degrades to `[]`/`null` (`:27-29,40-42,51-53`); only a transient `message` line `:119-123`. Functional gaps: new KP is **not linked to the selected chapter** (`:104-107`); every added block is hardcoded `block_type:'PARAGRAPH'` + `section_key:'新段落'` (`:87-92`); `block_order` computed client-side (`:90`); reads use the **published-only** student book list, not an admin list | `AdminPages.test.ts:170-211` |

### 4.2 ⚠️ `ProfilePage` — real data, client-synthesized artifact
`ArchiveDocCard` (`src/pages/profile/components/ArchiveDocCard.tsx`) renders a document titled `{nickname}.agent.md` (`:63`). It **looks like** the backend's agent profile file, but the content is generated **in the browser** by `buildMarkdown(profile, prefs, insights)` (`:47`, defined in `profile-labels.ts`), and the frontmatter is assembled from client state (`:49-57`). The backend exposes `GET /api/v1/me/agent.md` (present in `backend/app/modules/identity/router.py`) which the frontend **never calls** (§9). The underlying *inputs* are real API data, so this is `PARTIAL`, not `MOCK` — but the artifact is not the server's artifact. Export (`ProfilePage.tsx:180-190`) is a genuine client-side `Blob` download built from real service data (`profile-labels.test.ts`: *"导出内容来自传入的真实服务数据并包含全部维度"*).

### 4.3 ⚠️ `ResourceState` — dead shared abstraction
`src/shared/ui/ResourceState.tsx` (62 lines) is a purpose-built Loading/Empty/Error component (T07) with `role="alert"`/`role="status"`, `data-testid`, optional `requestId` display (`:47-49`) and a keyboard-accessible retry button (`:50-58`).
**It has ZERO importers.** `grep -rn "ResourceState" src` (excluding its own two files) returns nothing. It has its own passing test (`ResourceState.test.tsx`, 4 tests) — a test for unreachable code. Every page instead hand-rolls ad-hoc markup. **`DEAD_CODE`.**

### 4.4 ⚠️ Silent fallbacks that masquerade as real state (highest-value page findings)

No page renders a literal entity array as if it came from the backend. The real risk is different: **failed requests that degrade into states which look like legitimate data**, so the user cannot tell "empty" from "broken". Ranked by risk:

| # | Location | What happens on failure | Risk |
|---|---|---|---|
| **1** | **`SettingsPage.tsx`: prefs-load failure silently produces a wrong-looking form that can never be saved.** `getPreferences()`/`getTeacherRoles()` are awaited in a `Promise.all` (`:96-99`) whose **entire** success block — including the `currentUser`-derived field initialization — sits *after* the await (`:100-112`). The `catch` is empty (`:113-115`, `// 保留默认表单`) and `loaded` is set regardless (`:121`). So on failure the form renders with **`nickname: ''`**, plus hardcoded defaults for `grade=8`, `language='zh-CN'`, `style='EXAMPLE_BASED'`, `difficulty='MEDIUM'`, `sessionLength='SHORT'`, `volumePercent=80`, `speed=1` (`:75-84`), **and no error is shown**. Pressing **保存设置** (`:512`) then builds `profilePatch` from that state (`:127-133`) and calls `updateMe` (`:134`) → `PATCH /me` with `nickname: ''`. The backend schema is `nickname: str \| None = Field(default=None, min_length=1, max_length=32)` (`backend/app/modules/identity/schemas.py:55`), so **422 Unprocessable Entity** → the `catch` at `:149-151` fires → generic toast **"保存失败，请重试"** — with no indication that the nickname field is the cause. Because the throw happens before `:135`, `updatePreferences` is **never reached**, so no preference corruption occurs. | **Medium-High — a soft-lock, *not* data loss.** The user cannot save settings at all, sees a misleading generic error, and the form displays default values that look authoritative. *(An earlier reading of this code suggested silent overwrite of real preferences; the backend `min_length=1` constraint prevents that — verified and corrected. Still worth fixing: surface the load error and initialize the `currentUser`-derived fields **before/independently of** the `await`.)* |
| **2** | `ReaderPage.tsx:176-189` | A failed `getChapter` **fabricates** `{...chapter, content_blocks: [], knowledge_points: []}` and displays "本章暂无内容"; if the chapter isn't in the list → "章节不存在。". No retry. | **HIGH — a backend outage is indistinguishable from an empty/missing chapter.** |
| **3** | `HomePage.tsx:213-216` | `memoriesError` exists (`use-home-data.ts:218`) but is **never consumed** → a failed `getMemories()` renders the cheerful empty copy "我还没有记住关于你的稳定线索". Likewise `statsError` (`:209`) is never consumed → a failed `getMe()` silently deletes the stats bar (`HomePage.tsx:144`). | **MEDIUM-HIGH — fabricated reassurance.** |
| **4** | `ProfilePage.tsx:82-107` | Only the **prefs** rejection sets `loadError` (`:107`). Insights/memories/episodes failures are swallowed (`:90-105`) and render as empty states ("暂无画像判断", "还没有沉淀出值得记住的学习情节。", "还没有沉淀出稳定的记忆"). | **MEDIUM-HIGH.** |
| **5** | `LibraryPage.tsx:183-185` | Progress-load failure swallowed to `{}` → **every book silently shows "未开始"**. | **MEDIUM.** |
| **6** | `QuizDetailPage.tsx:47-52,98` | Rejected `getQuizSession` → `session=null` → **"答卷不存在。"** with no retry; plus `const { quizId = 'q1' } = useParams()` (`:32`) sends a mock-looking ID to the real API if the param is missing. | **MEDIUM.** |
| **7** | `AdminBooks.tsx:16`, `AdminChapters.tsx:27-53`, `AdminStyles.tsx:40-43` | Load failures → empty list with no message; `AdminStyles.toggle()` has **no try/catch** → unhandled promise rejection with no user feedback. | **MEDIUM (admin-only surface).** |
| **8** | `BookDetailPage.tsx:85-87` + `BookDetailSections.tsx:175` | Knowledge-points failure → `null` → section returns `null`; a failure looks identical to "this chapter has no knowledge points". | **LOW.** |

### 4.5 Dead / unreachable UI controls found in pages
- **`NextActionCard.tsx:30-38`** renders a "暂时跳过" button only when an `onSkip` prop is passed, but `HomePage.tsx:125-129` **never passes it** → the skip-review action for `REVIEW_QUIZ` is unreachable in the app. (`NextActionCard.test.tsx` does exercise `onSkip`, so the test covers behavior production cannot reach.)
- **`QuizzesPage.tsx:73`** — `const filtered = sessions` is vestigial; filtering is server-side.
- **`QuickActions.tsx:38-44`** — 语音聊天 button with no handler (§5.3).
- A mechanical scan of all pages found **no other** handler-less `<button>`/`<input>`/`<select>`/`<textarea>`: every other control has `onClick`/`onChange`/`ref`/`onSubmit`.

### 4.6 Persistence caveats (UI toasts success, but no API call)
- **Companion pet selection** — `SettingsPage.tsx:472-478` → `setSelectedPet` → `companion-store.ts:84-87` writes **only** `localStorage['shuangling-companion-pet']`, then toasts "已切换为…". No API.
- **学段 / age switch** — `SettingsPage.tsx:49-52` writes **only** `localStorage['shuangling-age']` + `document.documentElement.dataset.age` (re-read on mount at `AppLayout.tsx:24-30`). No API.

Both are deliberate (the settings copy at `:470` separates 形象 from 教学风格), but they are device-local: they do **not** follow the user across browsers/devices, unlike the genuinely-persisted `current_teacher_role_id` (`:156`) and the voice preferences (`:135`).

---

## 5. Features — `src/features/`

### 5.1 Reachability spine
`app/providers/index.tsx:9-16` → `QueryClientProvider > AuthProvider > ScreenContextProvider`.
`shared/ui/AppLayout.tsx:39` `<ScreenContextRouteSync/>`, `:120` `<Outlet/>`, `:123` `<Companion/>`, `:124` `<ToastHost/>`.
`Companion.tsx:11-12` → `CompanionDock` + `CompanionPanel` → `CompanionPanel.tsx:96` `<ConversationPanelContent/>` → `ConversationPanelContent.tsx:148-150` `<MessageList/> <QuickActions/> <ChatComposer/>`.
⇒ **The whole conversation feature, including the voice microphone, is reachable whenever the dock panel is opened.**

### 5.2 `conversation/store/conversation-store.ts` (692 lines) — the zustand store
**State shape** (`:187-225`): `messages: ChatMessage[]`, `conversationId`, `loaded`, `loadedEpoch`, `lastScreenContext`, `lastIdempotencyKey`, `history: ConversationHistoryEntry[]`, `historyLoaded`.
**Actions:** `load`, `ensureConversationId`, `refresh`, `send`, `abortCurrent`, `runIntent`, `retry`, `loadHistory`, `switchConversation`, `startNewConversation`, `setConversationStatus`, `appendAiText`, `pushStreaming`, `reset`.

**How streaming messages are appended — genuinely real SSE, no fakery:**
- `send()` (`:329-536`) appends the user message **plus a `kind:'typing'` placeholder** in one atomic `set` (`:348-354`) → optimistic update, and sets the pet to `thinking` (`:355`).
- A fresh `AbortController` per send (`:357-359`); the previous one is aborted (`:358`).
- SSE callbacks (`:431-528`) map 1:1 onto backend event types: `onStart` → `message.start` (`:433`), `onDelta` → `text.delta` accumulates `assistantContent` (`:438-442`), `onTextDone` → `text.done` sets authoritative text (`:443-447`), `onToolStart`/`onToolResult` → `tool.start`/`tool.result` (`:448-514`), `onDone` → `message.done` (`:515-523`), `onError` (`:524-527`).
- `upsertAssistant` (`:396-422`) inserts the assistant bubble on first token, **removing the typing placeholder** (`:403`), and patches in place thereafter (`:417-419`).
- Quiz tool results are rendered as real `QuizCard`s using the backend-issued `quiz_session_id` (`:480-499`); **comment `:542-543` explicitly notes the switch away from mock creation**: *"5-D：真实链路——「给我出题」只发文本，后端 SSE 返回 tool.start/tool.result，store 用 tool.result 的 quiz_session_id 渲染真实 QuizCard（不再走 Mock 创建）"*.
- Error path: `showError` (`:375-395`) strips the placeholder and inserts `kind:'error'` with `errorText()` (`:176-179`); guarded by `errorShown` (`:362`, `:377`) so only one error surfaces.
- Idempotency: `crypto.randomUUID()` per send (`:337`), **reused on retry** (`:554-560`) to prevent duplicate student messages.

**Account-switch isolation (T06)** — a real correctness feature:
- Module-level `sessionEpoch` (`:130`) with `currentEpoch`/`bumpEpoch` (`:132-139`). Every async continuation re-checks (`:263,273,281,322`) and a `stale()` closure guards all post-await `set` calls (`:364`, `:450`, `:479`, `:516`), so user A's in-flight response cannot backfill after user B logs in.
- `loadPromise` de-dupes concurrent `load()` (`:124`, `:240`, `:295-297`) and is invalidated by `reset()` (`:676`).
- Per-user localStorage key `shuangling-active-conversation:{userId}` derived from the JWT `sub` (`:29-43`), with a legacy global key cleaned but never migrated (`:26-27`, `:59`).

**`pushStreaming` (`:639-667`) is `DEAD_CODE`.** It is a fake 22 ms/char typewriter using `window.setInterval` (`:650`, `:666`). Its own doc comment says *"内部：逐字流式输出（22ms/字），组件不直接调用"* (`:221-222`). **Verified: zero callers repo-wide** (not even a test). It is the only fabricated-data-rendering code left in the store, and it is unreachable. `streamTimer` (`:123`) exists solely to serve it and is likewise never set — `abortCurrent` (`:622-627`) and `reset` (`:674`) clear a variable that is always `undefined`.

**`appendAiText` (`:629-636`) is REAL** — called by `QuizCard.tsx:90,224`.

**`retry` (`:550-562`) is REAL and reachable** — `MessageList.tsx:133,147` wires `onRetry={() => void retry()}` to the error bubble's 重试 button.

### 5.3 `conversation/components/`
| File | Verdict | Notes |
|---|---|---|
| `ChatComposer.tsx` (285) | **REAL** | Text submit w/ `sendingRef` double-submit guard (`:59`, `:180`, `:183-206`); Enter-to-send / Shift+Enter newline (`:209-214`); voice mic; TTS playback; emits `QUESTION_ASKED` (`:192-200`); voice lifecycle events (`:136-138`, `:167-169`) |
| `ConversationPanelContent.tsx` (153) | **REAL** | Conversation history `<select>` (`:86-104`), new/archive/delete (`:113-142`), archive/delete → `PATCH /conversations/{id}`; `window.confirm` before delete (`:59`); displays live screen-context label (`:70-84`) |
| `MessageList.tsx` (156) | **REAL** | Renders `tool`/`typing`/`error`/`refuse`/`quiz`/`text` kinds; blinking cursor on `streaming` (`:117-119`); error bubble has 重试 + 稍后再问 (`:49-64`); auto-scroll (`:136-139`) |
| `MarkdownMessage.tsx` | **REAL, security-hardened** | Hand-rolled subset; **no `dangerouslySetInnerHTML` anywhere**; links restricted to http/https (`:7-9`) so `javascript:` is inert; raw HTML escaped. Tests assert both. |
| `QuickActions.tsx` (47) | **PARTIAL** | Imports `QUICK_ACTIONS` from `@/mocks/data/conversation:3` (static labels — acceptable). **`DEAD_CODE` inside a live component: the 语音聊天 button (`:38-44`) has a `title` and no `onClick` — it does nothing.** |
| `data/intents.ts` | **REAL** | Pure intent→prompt text; `INTENT_AI_STATE` (`:44-61`). `intents.test.ts` asserts **no intent contains hardcoded book/chapter/count/date facts** — an explicit anti-fabrication guard. |
| `types.ts:13` | stale comment | Says the quiz payload is "本任务仅占位" (placeholder) — it is really rendered at `MessageList.tsx:93`. |

### 5.4 `screen-context/` — what is it, and is it sent?
**Definition** (`types.ts:3-18`): `{ route, pageType, bookId?, chapterId?, chapterTitle?, contentBlockId?, visibleSection?, selectedText?, knowledgePoints?, actions?, quizSessionId?, questionId? }`. `derivePageType` (`:21-29`) maps pathname → `chapter_reader|book_detail|library|quiz_history|profile|settings|home`.

**Produced by:** `ScreenContextProvider.tsx:24` (initial `{route:'/home',pageType:'home'}`), patch-merge `:26-28`, full reset `:32-38`. Cleared on navigation by `ScreenContextRouteSync.tsx:18-20` (mounted `AppLayout.tsx:39`) using a functional update so a page that declares its own context first is not wiped (`:30-37`). Richest producer is `ReaderPage` (book/chapter/title/`visibleSection`/`contentBlockId`/`knowledgePoints`/`actions`, updated via `IntersectionObserver`); also `selectedText` on text selection.

**Is it sent to the backend? YES — three distinct channels:**
1. **Chat (primary):** `ChatComposer.tsx:201` `send(text, screenContext)` → `conversation-store.ts:336` stores it, `:428-430` builds `{content, screen_context}` → `:529` `conversationService.sendMessage` → `api-conversation-service.ts:288` `body.screen_context = apiScreenContext(...)`. `apiScreenContext` (`:143-164`) whitelists and snake_cases all 12 fields. Sent on **`POST /api/v1/conversations/{id}/messages`** (SSE, `:330-333`) with an `Idempotency-Key` (`:296`).
2. **Voice:** `ChatComposer.tsx:106` `initialScreenContext` on connect, and `:71-75` re-pushes on every route change while connected → `voice-client.ts:105-107` / `:130-131` emit WS `{type:'context', screen_context:{...}}` to `/api/v1/voice/ws`. This is a genuinely thoughtful fix for stale-chapter context during a live voice session.
3. **Intents:** `QuickActions.tsx:32`, `HomePage.tsx:30`, `LibraryPage.tsx:200`, `ProfilePage.tsx:125`, `ReaderPage.tsx:447,464` pass it into `runIntent` → same `send` path.

**Stale comment:** `types.ts:1` claims *"纯前端 Context，不落服务器"* (pure frontend, not persisted to server). "Not persisted" is true; "not sent" is **false**. **Verdict: REAL.**

### 5.5 `companion/` — the pet/sprite system
- **Reachable:** `AppLayout.tsx:123` (`Companion`), `HomePage.tsx:95` (`CompanionSprite`), `SettingsPage.tsx:472-475` (`CompanionPetPicker`).
- **Cosmetic-only: YES.** Zero API calls in the entire module. `companion-store.ts` holds `open, position, aiState, dragging, suggest, selectedPetId` (`:55-69`) and persists two localStorage keys: `shuangling-companion-pet` (`:12`) and `shuangling-companion-position` (`geometry.ts:12`, persisted `store.ts:39-42`). No network, cannot affect learning state.
- **Sprite art is REAL raster assets, not emoji/CSS/SVG.** `sprite.ts:9` `SPRITESHEET_URL='/spritesheet-extended.webp'` plus 5 per-pet atlases (`:23,30,37,44,51`). Verified on disk: `public/spritesheet-extended.webp` (2.78 MB) and `public/pets/{anya,doraemon,kun-like,lulu-capybara,shinchan}/spritesheet.webp` (1.5–2.1 MB each) — **12 MB total**. Rendered as CSS `background-position` on `<span role="img">` (`CompanionSprite.tsx:30-47`), 8×11 grid, 192×208 px cells, 220 ms/frame (`sprite.ts:4-8`). `CompanionDock.test.tsx:25` asserts the old `🌙` emoji placeholder is gone.
- **⚠️ `STUB`: `useCompanionDock.ts:66-78` fakes proactivity.** A hardcoded `setTimeout` shows the "有一个新建议" chip at 6 s (`:72`) and hides it at 13 s (`:73`). It is **not** driven by any real suggestion. (The comment at `:66` says "7s 恢复" but the code uses 13000 ms — comment/code mismatch.) This is the only fake behavior that is user-visible in production.
- **⚠️ Dual teacher identity.** `useTeacherName()` (`store.ts:45-48`) returns the **pet's** `displayName`, and it feeds the header (`AppLayout.tsx:43`), the composer placeholder (`ChatComposer.tsx:257`), and message metadata (`MessageList`). Meanwhile the **backend** teacher persona is `current_teacher_role_id`, switched in Settings via `studentService.updateMe(...)` + a `ROLE_SWITCHED` learning event (`SettingsPage.tsx:154-169`). The two are **intentionally decoupled** — `SettingsPage.tsx:470` says *"选择你的 AI 教师形象，教学风格保持不变"* (choose the avatar; teaching style is unchanged) — but the displayed name comes from the local pet, so it can drift from the server's active role after an account switch (also see §5.6: the pet is not reset on logout).

### 5.6 `auth/`
- Token: localStorage `shuangling-access-token` (`shared/api/auth.ts:1-13`), written inside `ApiStudentService.login` (`:24`).
- `login` (`AuthProvider.tsx:122-138`): `studentService.login` → if `user_type === 'ADMIN'`, **must** pass `adminService.getAdminMe()` or the whole state is cleared and `ApiError(403,'ADMIN_PROFILE_REQUIRED')` is thrown (`:127-133`); students get `refreshMe()` (`:135`).
- Refresh restore (`:63-107`): decodes the JWT (`:28-41`), and for ADMIN **re-verifies against `/me/admin` even on restore** rather than trusting the token (`:74-85`) — explicitly fixed in "Phase 5-A 整改" (`:51-52`, `:72-73`). Optimistic `setAuthUser` (`:77`) avoids a login redirect flash, with `clearAuthState()` on failure (`:80`).
- Global 401 (`:149-158`): listens for `shuangling:unauthorized` and clears token + authUser + currentUser.
- `reset-user-state.ts:12-18` clears **exactly**: `clearToken()`; `useConversationStore.reset()` (`conversation-store.ts:669-691` — aborts in-flight SSE, bumps epoch, clears the per-user + legacy active-conversation keys, resets pet `aiState` to `idle`, nulls all 8 state fields); `queryClient.clear()`.
- **Gaps:** it does **not** reset the companion store (`selectedPetId` + dock position survive an account switch), the toast store, or the `ScreenContextProvider` React state (the provider sits **inside** `AuthProvider` at `providers/index.tsx:12-13` and is never unmounted on logout, so a previous user's `screenContext` can persist until the next route change).

### 5.7 `feedback/`
`store.ts:16-25` — zustand toast store, `showToast` auto-removes after **2200 ms** (`:22`). `ToastHost.tsx` renders `role="status"` toasts, mounted at `AppLayout.tsx:124`. **31 production `showToast(...)` call sites.** No API. **REAL. No tests.**

### 5.8 `learning/events.ts`
Pure builder functions: `shouldEmitSectionRead` (`:21-29`), `sectionEventKey` (`:32-34`), `buildQuestionAskedEvent` (`:51-69`, returns `null` when there is no real `conversationId` — refuses to emit untraceable events, `:54`), `createVoiceEndedGuard` (`:82-99`, guarantees `VOICE_SESSION_ENDED` fires exactly once), `buildVoiceSessionEvent` (`:102-112`), plus a module-level current-session registry (`:119-127`).
Consumed by `ReaderPage` and `ChatComposer`; POSTed to `POST /learning-events` (`learning-service.ts:167-175`). **REAL** — and `events.test.ts` (9 tests) covers dedupe, cross-chapter reset, refuse-without-conversation, and the once-only guard.

### 5.9 `voice/` — is voice reachable? **YES**
`src/features/voice/` contains only `.gitkeep` + `audio-capture.ts`, which is misleading — the feature is implemented across `voice/audio-capture.ts` + `shared/api/voice-client.ts` + `conversation/components/ChatComposer.tsx`.

- `audio-capture.ts`: `navigator.mediaDevices.getUserMedia({audio:{echoCancellation,noiseSuppression,autoGainControl}})` (`:14-20`), `AudioContext({sampleRate:48000})` (`:33`), **AudioWorklet (not MediaRecorder)** loading `/audio-worklet-processor.js` (`:36-37`), frames via `workletNode.port.onmessage` (`:44-46`), `stop()` disconnects + stops tracks (`:50-62`). Typed errors: `NO_MIC_PERMISSION`, `CAPTURE_FAILED`, `WORKLET_UNSUPPORTED`.
- `public/audio-worklet-processor.js` (1,602 bytes) really exists: 48 kHz→16 kHz linear-interpolation downsample, Int16 PCM, fixed 100 ms (1600-sample) frames.
- **UI that instantiates it: `ChatComposer.tsx`** — `startVoice()` (`:99-157`), `stopVoice()` (`:159-171`), `toggleVoice` (`:173-176`), and the 🎤 button at `:262-273` (`aria-label` toggles 语音输入/停止录音). It is gated on `voicePrefs.input_enabled` (`:261`), which is fetched from `studentService.getPreferences()` (`:63-65`) but **defaults to `true` locally** (`:40-45`), so the mic is visible by default.
- Full-duplex: PCM → base64 → `sendAudioChunk` (`:128-130`); server `onAudio` base64 WAV → `new Audio(...)` with `volume`/`speed` from prefs (`:110-116`); `onState` drives both the status overlay (`:216-244`) and the pet animation (`:91-97`); `onReply` refreshes history (`:109`).

**Evidence both ways:** the **only** dead voice affordance is the duplicate 语音聊天 button in `QuickActions.tsx:38-44`. The implementation itself is live. **Verdict: REAL / REACHABLE** (the earlier hypothesis that voice is disconnected is **wrong**).

**Test gap: `audio-capture.ts` has NO test.** `voice-client.test.ts` (6 tests) covers the WS client including 30 s heartbeat and screen-context frames.

---

## 6. State management

### 6.1 zustand — exactly three stores
| Store | File | Scope | Backend? |
|---|---|---|---|
| `useConversationStore` | `features/conversation/store/conversation-store.ts:227` | messages, streaming, conversation id/history, epoch isolation, idempotency | **REAL** (SSE + REST) |
| `useCompanionStore` | `features/companion/store/companion-store.ts:71` | panel open, dock position, pet id, AI animation state | **local-only** (localStorage) |
| `useToastStore` | `features/feedback/store.ts:16` | transient toasts | local-only |

### 6.2 React Query — **installed, configured, and dead**
- `QueryClientProvider` wraps the app (`app/providers/index.tsx:11`), `queryClient` is configured with a real retry policy and `staleTime: 60_000` (`app/providers/query.ts:31-42`).
- **`useQuery`: 0 occurrences. `useMutation`: 0 occurrences. `invalidateQueries`: 0. `setQueryData`: 0.**
- The only two `@tanstack/react-query` imports are the provider (`providers/index.tsx:1`) and the `QueryClient` constructor (`providers/query.ts:1`). The only `queryClient` use is `queryClient.clear()` on logout (`reset-user-state.ts:17`).
- `query-keys.ts` has **zero importers**.
- **Therefore:** there is no query cache, no cache invalidation pattern, and no automatic refetch. Every page does manual `useState` + `useEffect` fetching and manual re-fetch after mutations (e.g. `use-home-data.ts:194-204`, `MemoriesPage.tsx:64,83`, `LibraryPage.tsx:139,181`).
- `queryClient.clear()` is still *correct* (harmless), and it is the mechanism that would prevent cross-account cache bleed — the `query-keys.ts:1` intent — except nothing is ever cached.

**Verdict: `DEAD_CODE` infrastructure.** This is the single largest structural gap: the team built the caching conventions (T07 query keys, retry policy) but never adopted the library.

---

## 7. Tests

### 7.1 Unit — `vitest` (`vitest.config.ts`)
`environment: 'node'` by default; the 30 DOM tests opt in via `// @vitest-environment jsdom` docblock (all 33 `.test.tsx` are covered; verified none is missing the docblock). `env: { NODE_ENV: 'test' }` is forced (`vitest.config.ts`) because a production `NODE_ENV` breaks `React.act`.

**Result: `npx vitest run` → 49 files, 258 tests, ALL PASS, exit 0 (4.90 s).**

| Area | Files | Coverage summary |
|---|---|---|
| `shared/api/` | `http.test.ts` (8), `sse.test.ts` (6), `unauthorized.test.ts` (9), `voice-client.test.ts` (6), `learning-service.test.ts` (11), `admin-service.test.ts` (2), `api-content-service.test.ts`, `api-conversation-service.test.ts`, `api-memory-service.test.ts`, `api-quiz-service.test.ts`, `api-student-service.test.ts`, `api-recommendation.test.ts` (3) | Strong. Envelope unwrap, `ApiError` fields, `requestId`/`retryAfterMs`, AbortSignal forwarding, CRLF frames, multi-byte UTF-8 split across chunks, heartbeat-comment skipping, **401 on both `apiRequest` and SSE**, admin raw-fetch 401, `Idempotency-Key` generation |
| `features/conversation/store/` | `conversation-store.test.ts` (12), `conversation-history.test.ts` (5) | SSE start/delta/done aggregation, error bubbles, quiz tool flow, missing-bubble cleanup, history merge/sort, archive/delete auto-switch |
| `features/auth/` | `AuthProvider.test.tsx` (4), `AuthProvider.admin.test.tsx` (7), `account-switch.test.tsx` (4) | Refresh restore, 401 clearing, ADMIN server verification (both login and restore), **account-switch epoch isolation and per-user keys** |
| `features/companion/` | dock (2), sprite (2), store (3), sprite math (3), geometry (9) | Real atlas URLs, drag rows, clamp/placePanel incl. mobile drawer |
| `features/conversation/components/` | `ChatComposer.test.ts` (13), `MarkdownMessage.test.tsx` (7), `MessageList.test.tsx` (1), `intents.test.ts` (3) | **Voice: mic render/hide, no-permission fallback, PCM base64 + audio_end, TTS volume/speed, live screen-context push, QUESTION_ASKED linkage, ENDED-exactly-once.** Markdown XSS (`javascript:` rejected, raw HTML escaped) |
| `features/quiz/`, `memory/`, `learning/`, `screen-context/`, `feedback/` | `QuizCard.test.tsx` (3), `events.test.ts` (9), `ScreenContextRouteSync.test.tsx` (2) | Quiz multi-type + resume + Idempotency/Bearer headers. **`memory/` and `feedback/` have NO tests** |
| `pages/` | home (8+6+3+6), library (9), book (7), quizzes (2+3), reader (6+7), profile (9+2), settings (2), admin (5+5) | Substantive: per-section degradation, backend (not local) search, read-only quiz detail, qualitative-only insights |
| `mocks/services/` | `content-service.test.ts` (5), `quiz-service.test.ts` (2) | ⚠️ **Tests of `DEAD_CODE`** |
| `shared/ui/` | `AppLayout.test.tsx` (5), `ResourceState.test.tsx` (4) | ⚠️ `ResourceState.test.tsx` tests `DEAD_CODE` |

**Test gaps (no test file at all):** `MemoriesPage.tsx`, `LoginPage.tsx`, `ReaderPage.tsx` (only its children), `features/memory/`, `features/feedback/`, `features/voice/audio-capture.ts`, `features/quiz/lib.ts`, `QuickActions.tsx`, `ConversationPanelContent.tsx`, `CompanionPanel/PetPicker/useCompanionDock/useSpriteFrame`, `app/providers/query.ts` (`shouldRetry`/`retryDelay`).

### 7.2 E2E — Playwright (`playwright.config.ts`, 11 specs)
`e2e/`: `account-switch`, `admin`, `companion-sprite`, `golden-path`, `grade-persistence`, `login-flow`, `memory-flow`, `mobile-learning`, `profile-insights`, `teacher-role`, `voice-preference` + `helpers.ts`.

**These are true end-to-end tests against a real backend and a real database — zero mocking.** `helpers.ts:19-25` logs in through `POST /api/v1/auth/login` with the seed account (`xiaoming`/`demo123`), `:31-49` archives conversations via real `PATCH /conversations/{id}`, `:52+` picks a real published book and seeds progress with `PUT /me/progress/{bookId}`, and drives the UI at `http://localhost:5175` via `vite --port 5175` (`webServer`).

Config notes: `fullyParallel: false`, `workers: 1` — deliberately serial because specs share one seed account and would race on the same rows (`playwright.config.ts` comment). Four projects: `chromium` (desktop, all specs) + `mobile-390` / `tablet-820` / `desktop-1280` restricted to the viewport-portable specs.

`e2e/*.spec.ts` was **not executed** during this audit (it requires a running backend on :8000 and a seeded DB); results are `UNKNOWN`. The `frontend/test-results/` directory exists from a prior run.

---

## 8. Build / typecheck

Environment: `node_modules` **exists** (pnpm layout, `.pnpm` store).

### 8.1 `npx tsc --noEmit` — **PASSES**
Raw command and result:
```
$ cd /home/zxk/Projects/K12-Learning-platform/frontend && npx tsc --noEmit 2>&1 | head -50
(no output)
=== TSC EXIT: 0 ===
```
TypeScript **7.0.2**, and it is genuinely checking: `tsconfig.json` has `"include": ["src"]`, `strict: true`, `noUnusedLocals: true`, `noUnusedParameters: true`, `noFallthroughCasesInSwitch: true`, `verbatimModuleSyntax`, `isolatedModules`. `--listFiles` confirms **169 `src/` files** are in the program (not a vacuous pass). **Zero errors under strict + unused-locals.**

### 8.2 `npm run build` — **PASSES**
`build` = `tsc --noEmit && vite build`.
```
✓ 164 modules transformed.
dist/index.html                    0.49 kB │ gzip:  0.33 kB
dist/assets/index-*.css           35.78 kB │ gzip:  7.79 kB
dist/assets/lib-*.js               0.41 kB │ gzip:  0.28 kB
dist/assets/QuizzesPage-*.js       4.25 kB │ gzip:  1.82 kB
dist/assets/QuizDetailPage-*.js    5.73 kB │ gzip:  2.12 kB
dist/assets/MemoriesPage-*.js      7.04 kB │ gzip:  2.68 kB
dist/assets/BookDetailPage-*.js   10.66 kB │ gzip:  3.38 kB
dist/assets/SettingsPage-*.js     11.64 kB │ gzip:  3.95 kB
dist/assets/LibraryPage-*.js      12.22 kB │ gzip:  3.82 kB
dist/assets/HomePage-*.js         16.66 kB │ gzip:  5.14 kB
dist/assets/admin-*.js            18.15 kB │ gzip:  4.91 kB
dist/assets/ReaderPage-*.js       20.31 kB │ gzip:  6.28 kB
dist/assets/ProfilePage-*.js      25.34 kB │ gzip:  7.52 kB
dist/assets/services-*.js        116.39 kB │ gzip: 37.85 kB
dist/assets/index-*.js           272.64 kB │ gzip: 85.57 kB
✓ built in 265ms
=== BUILD EXIT: 0 ===
```
Code-splitting works exactly as the router intends: one chunk per lazy page, one shared `services`/vendor chunk, plus the eager `index` entry. Router-only eager imports (`LoginPage`, `AppLayout`) land in `index-*.js` as designed (`router/index.tsx:9-10`).

**Build hygiene:** `VITE_SHOW_DEMO_CREDENTIALS` is **not** set (no `.env` file exists), so the demo-credential hint (`LoginPage.tsx:82-86`) is correctly **excluded** from the production bundle — verified: `演示账号` is ABSENT from `dist/`. `dist/` is git-ignored (`frontend/.gitignore:2`).

**Bundle observation:** `services-*.js` is 116 kB / 37.85 kB gzip — the single largest chunk after the entry — because the service registry statically instantiates **all six** `Api*Service` classes and pulls in the whole `shared/api` graph on first paint, including `voice-client` and `sse`. Combined with `index-*.js` (272 kB), initial JS is ~389 kB raw (~123 kB gzip) before any page chunk. Lazy-loading `voice-client`/`sse` (only needed once the panel opens) would be an easy win.

---

## 9. Backend endpoints the frontend NEVER calls

Cross-referenced the FastAPI route table (`backend/app/modules/*/router.py`, all mounted under `/api/v1` in `backend/app/main.py:97-106`) against every path literal in `frontend/src`. Verified as absent from production code:

| Method + Path | Backend module | Note |
|---|---|---|
| **`POST /knowledge/search`** | `knowledge/router.py` | **RAG retrieval search — the most significant gap.** The frontend has no way to query the knowledge base directly; all retrieval happens server-side inside the chat SSE flow. |
| **`GET /knowledge/resources/{resource_id}`** | `knowledge/router.py` | Single-resource detail never fetched; admin only lists (`admin-service.ts:94`) |
| **`GET /knowledge/resources/{resource_id}/chunks`** | `knowledge/router.py` | Chunk inspector never surfaced in the admin UI |
| **`PATCH /admin/content-blocks/{block_id}`** | `admin/router.py` | Content blocks can be **created** (`admin-service.ts:163`) but never **edited** |
| **`PATCH /admin/knowledge-points/{knowledge_point_id}`** | `admin/router.py` | Knowledge points can be created (`:166`) but never edited |
| **`PATCH /admin/knowledge/resources/{resource_id}`** | `admin/router.py` | Resource metadata (license/copyright/source) cannot be corrected after upload |
| **`GET /admin/books/{book_id}`** | `admin/router.py` | Admin book list is fetched (`:71`); single-book detail is never fetched |
| **`GET /me/agent.md`** | `identity/router.py` | **See §4.2** — the UI shows a `.agent.md` that the browser synthesizes via `buildMarkdown()` instead |
| `GET /files/avatars/{filename}` | `content/assets.py` | Static avatar serving; consumed as an `<img src>` from `avatar_url`, so not "uncalled" in a meaningful sense |

### 9.1 Frontend service methods defined but never called (dead API surface)
| Method | Endpoint | Evidence |
|---|---|---|
| `contentService.getKnowledgePoint` | `GET /knowledge-points/{id}` (`api-content-service.ts:197-201`) | Only referenced as a `vi.fn()` stub in `BookDetailPage.test.tsx:14` |
| `memoryService.getInsight` | delegates to `getInsightDetail` (`api-memory-service.ts:236-239`) | 0 production callers (`getInsightDetail` is used instead at `ProfilePage.tsx:132`) |
| `quizService.createQuizSession` | `POST /quiz-sessions` (`api-quiz-service.ts:205-220`) | **0 production callers.** `conversation-store.test.ts:251` actively asserts it is *not* called: *"「给我出题」只发送文本，不再触发 Mock 的 createQuizSession"*. Quiz creation is entirely backend-driven via the SSE `tool.start`/`tool.result` flow. |
| `quizService.getHints` | alias of `requestHint` (`api-quiz-service.ts:272-274`) | Self-documented alias; `requestHint` is what `QuizCard.tsx:222` uses |

---

## 10. Dead-code inventory (no reachable caller)

| Artifact | Location | Why dead |
|---|---|---|
| **5 mock services** | `MockStudentService`, `MockConversationService`, `MockMemoryService`, `MockRecommendationService` (+2 self-tested) | `src/shared/services.ts` registers only `Api*Service` |
| **`query-keys.ts`** (19 lines) | `shared/api/query-keys.ts` | 0 importers |
| **React Query runtime** | `useQuery`/`useMutation`/`invalidateQueries` | 0 occurrences repo-wide |
| **`ResourceState`** (62 lines) + its test | `shared/ui/ResourceState.tsx` | 0 importers |
| **`pushStreaming`** + `streamTimer` | `conversation-store.ts:639-667`, `:123` | 0 callers; fake 22 ms/char typewriter |
| **`quizService.createQuizSession`** | `api-quiz-service.ts:205` | 0 prod callers |
| **`contentService.getKnowledgePoint`** | `api-content-service.ts:197` | 0 prod callers |
| **`memoryService.getInsight`** | `api-memory-service.ts:236` | 0 prod callers |
| **`quizService.getHints`** | `api-quiz-service.ts:272` | alias, unused |
| **`appendAiText`** | — | **NOT dead** (used by `QuizCard.tsx:224`) |
| **`retry`** | — | **NOT dead** (used by `MessageList.tsx:147`) |
| **`QuickActions` 语音聊天 button** | `QuickActions.tsx:38-44` | Rendered but has **no `onClick`** |
| **`NextActionCard` 暂时跳过 branch** | `NextActionCard.tsx:30-38` | `onSkip` is never passed by `HomePage.tsx:125-129` → unreachable (its test does exercise it) |
| **`QuizzesPage` local filter** | `QuizzesPage.tsx:73` | `const filtered = sessions` is vestigial; filtering is server-side |
| **`shouldRetry`/`retryDelay`** | `app/providers/query.ts:13,24` | Only referenced as never-executed config |
| **`statsError` / `memoriesError`** | `use-home-data.ts:209,218` | Computed but never consumed by `HomePage` → dead error flags (§4.4 #3) |
| `mocks/delay.ts` | fake 150-300 ms latency | Only used by dead mock services |

**Not dead but suspicious:** `src/features/companion/hooks/useCompanionDock.ts:66-78` — the fake "proactive suggestion" timer (`STUB`).

---

## 11. Stale / misleading comments (documentation drift)

| Location | Comment claims | Reality |
|---|---|---|
| `features/screen-context/types.ts:1` | "纯前端 Context，**不落服务器**" | It **is** sent to the backend on 3 channels (§5.4) |
| `features/quiz/lib.ts:10` | "只读 **Mock** 查询" | Uses the real `contentService` (`:19,26,29`) |
| `api-student-service.ts:16` | "其余 Service 仍 **Mock**，总控 §27" | All services are `Api*` (§0) |
| `features/conversation/types.ts:13` | quiz payload "本任务仅**占位**" | Really rendered at `MessageList.tsx:93` |
| `useCompanionDock.ts:66` | "6s 后提示、**7s** 恢复" | Code hides at **13** s (`:73`) |

---

## 12. FINAL VERDICT — "Are mocks still reachable in production?"

## ❌ NO. Zero mock data is reachable from the running application.

The evidence is convergent and independent:

1. **Registration:** `src/shared/services.ts:21-26` instantiates only `ApiStudentService`, `ApiContentService`, `ApiConversationService`, `ApiQuizService`, `ApiMemoryService`, `ApiRecommendationService`. No conditional, no env branch.
2. **No activation mechanism exists:** no MSW dependency, no mock env var, no dynamic import, no `.env` file, no toggle. The original switch was *manual editing* of that one file (`:16-20`), and all six swaps are recorded as complete.
3. **Import census:** the entire repo has exactly **two** imports of `src/mocks/` — one production import of static UI labels (`QuickActions.tsx:3`), one test fixture (`LibraryPage.test.tsx:7`). **No page, store, or feature imports a mock service or mock data.**
4. **Reachability:** 4 of 6 mock service classes have **zero importers anywhere**; the other 2 are imported only by their own tests. `MockRecommendationService:6` self-documents as a non-production替身.
5. **Bundle proof:** every mock data marker (`stu-xiaoming`, `mock-model`, `mock-access-token`, `demo123`, `AI 不是魔法`, `q-live`, `conv-1`, `msg-1`, mock message prose) is **ABSENT** from `dist/assets/*.js`, while the genuinely-used `QUICK_ACTIONS` label IS present. Rollup tree-shakes correctly; nothing mock ships.

### The honest caveats — what *is* fake or hollow

Mocks are gone, but the audit found ten real integrity issues worth flagging:

| # | Finding | Severity |
|---|---|---|
| 1 | **`SettingsPage` silently shows a wrong, unsavable form when prefs fail to load.** The load `catch` is empty (`SettingsPage.tsx:113-115`) and every `currentUser`-derived field is initialized *after* the `await` (`:100-112`), so `nickname` renders empty while other fields show hardcoded defaults — with no error. Saving then sends `nickname: ''`, which the backend rejects (`min_length=1`, `backend/.../identity/schemas.py:55`) → generic "保存失败，请重试" and settings can never be saved. **Soft-lock, not data loss** (verified against the backend; `updatePreferences` is never reached). | Medium-High |
| 2 | **`ReaderPage` conflates failure with empty/not-found.** All content fetches are `catch {}`-swallowed (`:169,175,182`); a failed `getChapter` fabricates an empty chapter and shows "本章暂无内容" (`:176-189`) or "章节不存在。" (`:596`), with no retry. | High |
| 3 | **Failed requests render as reassuring empty states** in `HomePage` (unconsumed `statsError`/`memoriesError`, `:209,218`), `ProfilePage` (only prefs surfaced, `:107`), `LibraryPage` (progress → "未开始", `:183-185`), `QuizDetailPage` ("答卷不存在。", `:98`). | Medium-High |
| 4 | **`useCompanionDock.ts:72-73` fake proactive suggestion** — a 6 s/13 s hardcoded timer drives a "有一个新建议" badge. The only user-visible fabricated behavior in production. | Medium |
| 5 | **`.agent.md` is client-synthesized** (`ArchiveDocCard.tsx:47`) while the backend's `GET /me/agent.md` sits unused. Looks like a server artifact; is not one. Inputs are real, artifact is not. | Medium |
| 6 | **React Query is dead weight** — a configured retry/caching policy that never executes; `query-keys.ts` unused. Every page hand-rolls `useState`+`useEffect` fetching with no cache and no cross-page invalidation. | Medium (structural) |
| 7 | **Inconsistent 401 handling** — `api-student-service.ts:58-77` (`uploadAvatar`) and `learning-service.ts:102-130` do not dispatch `shuangling:unauthorized`, so an expired session during those calls leaves inconsistent auth state. Other paths were fixed in "Phase 5-A". | Medium (security/UX) |
| 8 | **Companion pet + 学段 are device-local only** — toasts claim success but only `localStorage` is written (`companion-store.ts:84-87`, `SettingsPage.tsx:49-52`). | Low |
| 9 | **`QuickActions.tsx:38-44`** renders a 语音聊天 button with no handler — dead UI in a live component. `NextActionCard`'s 暂时跳过 is likewise unreachable (`HomePage.tsx:125-129`). | Low |
| 10 | **5 stale comments** assert mock/placeholder behavior that no longer exists (§11), and `reset-user-state.ts` does not clear the companion store or `ScreenContextProvider` state on account switch. | Low |

### Overall assessment

This is **not** a mock-driven prototype. It is a genuinely integrated frontend with a real streaming AI pipeline (POST-SSE with idempotency keys and abort/generation-epoch correctness), a real bidirectional voice path (AudioWorklet → WebSocket → base64 TTS playback), real auth with server-verified admin, and honest per-section error degradation. The tests are unusually substantive — including adversarial guards such as `intents.test.ts` asserting *no intent contains hardcoded book/chapter/count/date facts*, and `unauthorized.test.ts` asserting 401 dispatch on both the REST and SSE paths.

The problems are **accumulated scaffolding that was never removed** (dead mock services and their tests, dead React Query + query-keys, dead `ResourceState`, dead `pushStreaming`, dead service methods) plus **a few unfinished edges** (reader error state, the fake suggestion badge, the synthesized `.agent.md`, inconsistent raw-`fetch` 401 handling). `tsc --noEmit` clean under `strict` + `noUnusedLocals`, `npm run build` clean, and 258/258 unit tests green.

**No page that "looks complete but is backed by mock data" was found** — there is no page rendering fabricated entity data. The closest analogue to that failure mode is **`SettingsPage` (§4.4 #1)**: when preferences fail to load it silently renders a form of hardcoded defaults with an empty nickname and no error, and every save attempt fails behind a generic message. Alongside it, the client-synthesized `.agent.md` (§4.2) and the fake companion suggestion badge (§5.5) are `PARTIAL`/`STUB` respectively, not `MOCK`.
