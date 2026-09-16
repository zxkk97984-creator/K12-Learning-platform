# D — Test System Audit

Repo: `/home/zxk/Projects/K12-Learning-platform`
HEAD at audit time: `970ffda` — *fix(seed): give E2E demo memory a linked evidence*
Audit date: 2026-09-16 · Auditor: delegated subagent (read-only; no source/test files modified)

**Method note.** All test runs below are real. Two throwaway PostgreSQL databases
(`shuangling_audit_dtest`, `shuangling_ci_repro`) were created to reproduce CI's fresh-DB
conditions and were **dropped afterwards**. The developer's live `shuangling` database was
read but never mutated by me. Scratch artifacts live under `.audit/` only.

---

## 0. Headline findings

1. **CI's `backend` job is deterministically red.** Reproducing the workflow's exact sequence
   on a fresh database (`alembic upgrade head` → `validate_library --all` → `import_library --all`
   → `pytest -q`) yields **`1 failed, 383 passed`**. The failing test is
   `tests/test_content_ai_visibility.py::TestChapterSourceVisibility::test_published_chapter_loads_source`.
2. **The backend suite has zero test isolation and runs against the developer's live database.**
   `backend/tests/conftest.py` is 11 lines and contains **no fixtures at all**. It never sets
   `DATABASE_URL`, so `pydantic-settings` reads `backend/.env` → the real dev DB `shuangling`
   (149 users, 76 conversations at audit time). No schema create/drop, no transaction rollback,
   no truncation.
3. **`scripts/test-db.sh` is not a test-DB setup helper.** It is a backup/restore utility for a
   manually-created isolated acceptance DB (`shuangling_audit`). Nothing in it is invoked by
   `pytest`, by `.github/workflows/ci.yml`, or by `scripts/ci.sh`. The task brief's assumption
   that it is "the documented path" for test-DB setup does not hold.
4. **The suite is state-dependent and non-hermetic**: the same commit gave `1 failed / 383 passed`
   on a clean DB and `384 passed` on the *second* run against that same DB — the difference is
   purely leftover fixture rows.
5. **The environment stubs out the exact things that would break**: every AI/embedding/voice/TTS
   provider is forced to `mock` and Redis is disabled (`conftest.py:5-10`). No test in the suite
   exercises a real provider adapter, real Redis, or real S3.

---

## 1. Inventory

### 1.1 Backend — 40 test files, 384 tests

Collection output (verbatim tail):

```
384 tests collected in 0.71s
```

| # | File | Tests | Module / feature targeted |
|---|------|-------|---------------------------|
| 1 | `tests/test_quiz_api.py` | 31 | `modules/quiz` — session create, question snapshot, answer/grading |
| 2 | `tests/test_conversation_api.py` | 22 | `modules/conversation` — CRUD, messages, summary |
| 3 | `tests/test_learning_api.py` | 21 | `modules/learning` — events, book progress |
| 4 | `tests/test_admin_api.py` | 21 | `modules/admin` — books/chapters/teacher-role CRUD |
| 5 | `tests/test_knowledge_api.py` | 20 | `modules/knowledge` — ingestion, retrieval, search |
| 6 | `tests/test_identity_extended.py` | 20 | `modules/identity` — profile, preferences |
| 7 | `tests/test_phase5a_security.py` | 17 | `infrastructure/rate_limit`, idempotency, SSE replay |
| 8 | `tests/test_content_api.py` | 17 | `modules/content` — books/chapters/pagination |
| 9 | `tests/test_teacher_roles.py` | 14 | teacher-role styles |
| 10 | `tests/test_library_figures.py` | 13 | `scripts/validate_library` — figure assets, parsing |
| 11 | `tests/test_content_visibility.py` | 13 | visibility rules (DRAFT/ARCHIVED/PUBLISHED) |
| 12 | `tests/test_conversation_sse.py` | 12 | SSE streaming, heartbeat, provider-failure frames |
| 13 | `tests/test_memory_api.py` | 11 | `modules/memory` — API |
| 14 | `tests/test_insights_episodes_api.py` | 10 | insights / episodes |
| 15 | `tests/test_agent_md.py` | 9 | `modules/memory/agent_md` |
| 16 | `tests/test_phase3_stats_recommendation.py` | 8 | learning stats + `modules/recommendation` |
| 17 | `tests/test_phase2_screen_context.py` | 8 | `conversation/teacher_context`, screen context |
| 18 | `tests/test_content_ai_visibility.py` | 8 | `quiz/chapter_source`, AI visibility |
| 19 | `tests/test_worker_queue.py` | 7 | `jobs/queue` state machine, retry/backoff |
| 20 | `tests/test_quiz_review_context.py` | 7 | quiz review context |
| 21 | `tests/test_phase4_platform.py` | 7 | `infrastructure/storage`, TTS-unavailable path |
| 22 | `tests/test_memory_pipeline.py` | 7 | `modules/memory/pipeline` |
| 23 | `tests/test_context_window.py` | 7 | `conversation/context_window` |
| 24 | `tests/test_ai_provider.py` | 7 | `ai/factory`, `ai/mock`, `ai/openai_compatible` |
| 25 | `tests/test_recommendation_rules.py` | 6 | recommendation scoring rules |
| 26 | `tests/test_next_learning_action.py` | 6 | next-action derivation |
| 27 | `tests/test_chapter_completion.py` | 6 | chapter-completion facts |
| 28 | `tests/test_voice_ws.py` | 5 | `modules/voice/ws` |
| 29 | `tests/test_redis_lock.py` | 5 | `infrastructure/cache/redis` (fake-backed) |
| 30 | `tests/test_recommendation_api.py` | 5 | recommendation API |
| 31 | `tests/test_identity_api.py` | 5 | login + `scripts/seed` |
| 32 | `tests/test_embedding.py` | 5 | `ai/embedding` |
| 33 | `tests/test_async_memory_consolidation.py` | 5 | `jobs/handlers/memory` |
| 34 | `tests/test_reviewed_assessments.py` | 4 | `quiz/quiz_bank.select_reviewed_questions` |
| 35 | `tests/test_quiz_skill.py` | 4 | `quiz/skill`, `skills/registry` |
| 36 | `tests/test_smoke.py` | 3 | `main.py` — health, envelope, 404 |
| 37 | `tests/test_content_cache.py` | 3 | content/admin cache invalidation |
| 38 | `tests/test_memory_exclusion.py` | 2 | memory exclusion → teacher context |
| 39 | `tests/test_aliyun_voice.py` | 2 | `ai/voice.AliyunASRProvider` |
| 40 | `tests/test_import_library_collision.py` | 1 | `scripts/import_library` idempotency |

Sum = 384 ✓. `conftest.py` is the 41st `.py` file in `tests/`; it contains 0 tests.

### 1.2 Frontend unit tests — 49 files, 258 tests

Raw output:

```
 RUN  v4.1.10 /home/zxk/Projects/K12-Learning-platform/frontend

 Test Files  49 passed (49)
      Tests  258 passed (258)
   Duration  5.09s
```

| Tests | File |
|------:|------|
| 14 | `src/features/conversation/store/conversation-store.test.ts` |
| 13 | `src/features/conversation/components/ChatComposer.test.ts` |
| 12 | `src/features/learning/events.test.ts` |
| 11 | `src/shared/api/learning-service.test.ts` |
| 9 | `src/shared/api/api-memory-service.test.ts` |
| 8 | `src/pages/profile/ProfilePage.test.ts` |
| 8 | `src/pages/library/LibraryPage.test.tsx` |
| 8 | `src/pages/home/HomePage.recommendation.test.tsx` |
| 7 | `src/shared/api/http.test.ts` |
| 7 | `src/pages/reader/ChapterCompletionCard.test.tsx` |
| 7 | `src/pages/book/BookDetailPage.test.tsx` |
| 7 | `src/features/conversation/components/MarkdownMessage.test.tsx` |
| 7 | `src/features/companion/lib/geometry.test.ts` |
| 6 | `src/shared/api/unauthorized.test.ts` |
| 6 | `src/shared/api/sse.test.ts` |
| 6 | `src/shared/api/api-quiz-service.test.ts` |
| 6 | `src/shared/api/api-content-service.test.ts` |
| 6 | `src/pages/reader/ContentBlockView.test.tsx` |
| 5 | `src/shared/ui/AppLayout.test.tsx` |
| 5 | `src/shared/api/voice-client.test.ts` |
| 5 | `src/shared/api/api-student-service.test.ts` |
| 5 | `src/shared/api/api-conversation-service.test.ts` |
| 5 | `src/pages/home/home-time.test.ts` |
| 5 | `src/pages/home/components/ContinueLearningCard.test.tsx` |
| 5 | `src/pages/admin/AdminKnowledge.test.tsx` |
| 5 | `src/mocks/services/content-service.test.ts` |
| 5 | `src/features/conversation/store/conversation-history.test.ts` |
| 5 | `src/features/auth/AuthProvider.admin.test.tsx` |
| 4 | `src/shared/ui/ResourceState.test.tsx` |
| 4 | `src/pages/admin/AdminPages.test.ts` |
| 4 | `src/mocks/services/quiz-service.test.ts` |
| 4 | `src/features/auth/account-switch.test.tsx` |
| 4 | `src/features/auth/AuthProvider.test.tsx` |
| 3 | `src/shared/api/api-recommendation.test.ts` |
| 3 | `src/pages/quizzes/QuizDetailPage.test.tsx` |
| 3 | `src/pages/profile/profile-labels.test.ts` |
| 3 | `src/pages/home/components/NextActionCard.test.tsx` |
| 3 | `src/features/quiz/components/QuizCard.test.tsx` |
| 3 | `src/features/conversation/data/intents.test.ts` |
| 3 | `src/features/companion/store/companion-store.test.ts` |
| 3 | `src/features/companion/lib/sprite.test.ts` |
| 3 | `src/entities/student/types.test.ts` |
| 2 | `src/shared/api/admin-service.test.ts` |
| 2 | `src/pages/settings/SettingsPage.test.ts` |
| 2 | `src/pages/quizzes/QuizzesPage.test.tsx` |
| 2 | `src/features/screen-context/ScreenContextRouteSync.test.tsx` |
| 2 | `src/features/companion/components/CompanionSprite.test.tsx` |
| 2 | `src/features/companion/components/CompanionDock.test.tsx` |
| 1 | `src/features/conversation/components/MessageList.test.tsx` |

All 49 files found by `find` are collected by `vitest.config.ts:14`
(`include: ['src/**/*.test.ts', 'src/**/*.test.tsx']`) — no orphans.

Note: `vitest.config.ts:12` sets the global `environment: 'node'`. All 30 files that render
React opt in per-file with a `// @vitest-environment jsdom` docblock (verified: 0 `.test.tsx`
files are missing it). This is self-enforcing, not a defect.

### 1.3 Playwright e2e — 11 spec files, 33 tests across 4 projects

`npx playwright test --list` → `Total: 33 tests in 11 files`

| Spec | Content |
|------|---------|
| `e2e/golden-path.spec.ts` | Full journey: continue-learning → read → chat → multi-question quiz → history/profile |
| `e2e/login-flow.spec.ts` | Login/logout loop |
| `e2e/memory-flow.spec.ts` | Memory confirm/forget persists across reload |
| `e2e/account-switch.spec.ts` | Student↔admin switching, no cross-account residue (390/820/1280) |
| `e2e/mobile-learning.spec.ts` | Home→library→reader; network-failure UI; 401 handling; idempotent double-send (390/820/1280) |
| `e2e/profile-insights.spec.ts` | Insights loading, evidence + episode detail |
| `e2e/teacher-role.spec.ts` | Teacher-style switch persists |
| `e2e/voice-preference.spec.ts` | Voice preference persists |
| `e2e/grade-persistence.spec.ts` | Grade change persists |
| `e2e/admin.spec.ts` | Admin flows |
| `e2e/companion-sprite.spec.ts` | Companion sprite behaviour |

Multiplier: `golden-path`, `login-flow`, `memory-flow`, `profile-insights`, `teacher-role`,
`voice-preference`, `grade-persistence`, `admin`, `companion-sprite` run once (chromium);
`mobile-learning` (4 tests) and `account-switch` (2 tests) run in **all 4** projects.

---

## 2. Test infrastructure

### 2.1 `backend/tests/conftest.py` — complete file (11 lines)

```python
 1  import os
 2
 3  # 必须在导入 app.* 之前设置，使 engine 在测试环境使用 NullPool（TestClient 独立事件循环）
 4  os.environ["ENVIRONMENT"] = "test"
 5  os.environ.setdefault("TTS_PROVIDER", "mock")
 6  os.environ["AI_PROVIDER"] = "mock"
 7  os.environ["AI_MODEL"] = "mock-model"
 8  os.environ["EMBEDDING_PROVIDER"] = "mock"
 9  os.environ["VOICE_PROVIDER"] = "mock"
10  os.environ["REDIS_ENABLED"] = "false"
11  os.environ["JWT_SECRET"] = "test-only-32bytes-jwt-secret-0123456789"
```

There are **no fixtures in `conftest.py`** — no `db`, no `client`, no `session`. Every test
module defines its own module-scoped `client` fixture that calls its own `_ensure*()` seeder
(40 modules × ~2 fixtures each).

### 2.2 Does it need a live PostgreSQL? Yes — the developer's own database

- **Env var / `.env.test` / SQLite?** None of these. There is **no `.env.test`** in
  `backend/` (only `.env` and `.env.example`).
- `conftest.py` sets `ENVIRONMENT`, `AI_*`, `EMBEDDING_*`, `VOICE_*`, `TTS_*`, `REDIS_ENABLED`,
  `JWT_SECRET` — but **never `DATABASE_URL`**.
- `app/config.py` uses `SettingsConfigDict(env_file=".env")`. Environment variables win over
  `.env`, but since `DATABASE_URL` is not set by `conftest.py`, it is read from
  **`backend/.env`**:

  ```
  DATABASE_URL=postgresql+asyncpg://shuangling:shuangling@localhost:5432/shuangling
  ```

  That is the live development database. Verified at audit time: **149 users, 76 conversations**.
- Cross-check: `grep -rn "DATABASE_URL\|shuangling_audit\|TEST_DB" backend/tests/` returns
  **nothing**. No test is aware of an isolated DB.
- `app/infrastructure/database/engine.py:7-9` switches to `NullPool` when
  `settings.environment == "test"` — the only test-awareness in the DB layer.

**The project already knows this is dangerous.** `scripts/audit-check.sh:30-49` hard-refuses to
run unless `DATABASE_URL` is explicitly set *and* differs from the dev DB name:

```bash
DEV_DB_NAME="shuangling"   # 已知用户开发库名；audit 不得指向它
...
red "DATABASE_URL 未设置。审计/测试必须显式提供隔离测试库 DSN；拒绝默认指向用户开发库。"
exit 1
...
red "DATABASE_URL 指向用户开发库（$dev_db_name），已拒绝运行。必须使用隔离测试库。"
```

That guard protects `audit-check.sh` only. `pytest` has no equivalent, so a bare
`uv run pytest` silently targets the live DB.

### 2.3 Schema lifecycle: none

There is **no per-test schema creation, no transaction rollback, and no truncation**.

- No `create_all` / `drop_all` / `TRUNCATE` anywhere in `tests/`.
- Tests assume the schema already exists (`alembic upgrade head` must have been run by a human
  or by CI).
- Isolation is attempted ad-hoc, per module, via hand-written `_ensure*()` seeders that use
  **create-if-absent** semantics, e.g. `tests/test_async_memory_consolidation.py:55`:

  ```python
  if await session.get(Book, QUIZ_BOOK_ID) is None:
      session.add(Book(book_id=QUIZ_BOOK_ID, ..., status="PUBLISHED", ...))
  ```

  If the row exists in a wrong state, it is never repaired → the test fails permanently.
- Some modules hand-patch isolation and say so in comments. `tests/test_learning_api.py:207-208`:

  ```python
  # 同时覆盖本模块使用的两本书：共享开发库中可能存在其他
  # 测试模块遗留的进度行（Phase 3 结算语义变更后更需隔离）。
  ```

  …with an `autouse` fixture `_pristine_progress` (line 216) that deletes `BookProgress` rows
  before every test case. This is the authors documenting the shared-DB hazard and patching
  around it locally rather than fixing it globally.

**`scripts/test-db.sh` is not the intended test-DB setup.** Its own header (lines 2-8) describes
it as *backup/restore of a disposable acceptance DB* (`shuangling_audit`), with a guard refusing
destructive restore into the real dev DB unless `TEST_DB_ALLOW_PROD_RESTORE=1`. It exposes only
`backup` and `restore` subcommands. Nothing calls it: not `pytest`, not `ci.yml`, not `ci.sh`.

### 2.4 Are AI providers mocked? Yes — all of them, globally

`conftest.py:5-9` forces `TTS_PROVIDER=mock`, `AI_PROVIDER=mock`, `EMBEDDING_PROVIDER=mock`,
`VOICE_PROVIDER=mock` for the entire suite. CI sets the same in
`.github/workflows/ci.yml:37-40` and `:178-181`.

| Dependency | Status in tests | Evidence |
|---|---|---|
| LLM (`ai/openai_compatible.py`) | **Mocked.** `monkeypatch.setattr("app.ai.openai_compatible.httpx.AsyncClient", FakeClient)` | `tests/test_ai_provider.py:159`, `:206` |
| Embeddings (`ai/embedding.py`) | **Mocked.** `MockEmbeddingProvider` + `monkeypatch.setattr("app.ai.embedding.httpx.Client", FakeClient)` | `tests/test_embedding.py:8`, `:64` |
| Voice/ASR (`ai/voice.py`) | **Mocked.** `FakeWebSocket` injected via the provider's `connect=` seam | `tests/test_aliyun_voice.py:8`, `:75` |
| Redis (`infrastructure/cache/redis.py`) | **Disabled + faked.** `REDIS_ENABLED=false`; module supplies its own `FakeRedis` | `conftest.py:10`; `tests/test_redis_lock.py:1`, `:12` |
| Storage — local | **Real.** `LocalObjectStorage` against `tmp_path` | `tests/test_phase4_platform.py:34-53` |
| Storage — S3 | **Not exercised.** Only `sign_request` determinism + missing-config error | `tests/test_phase4_platform.py:56-95` |
| Database | **Real Postgres, real dev DB, no isolation** | `backend/.env`; `conftest.py` (absent) |

`tests/test_redis_lock.py:1` states it outright:

```python
"""Redis infrastructure tests use an in-memory fake; no Redis server required."""
```

`tests/test_content_cache.py:1` likewise:

```python
"""Books-list cache tests; database and Redis are both replaced with fakes."""
```

### 2.5 Is the environment representative of production?

**No — it stubs out precisely the integrations most likely to break.**

- `backend/.env` production-ish settings are `AI_PROVIDER=openai_compatible` (DeepSeek),
  `VOICE_PROVIDER=aliyun`, `EMBEDDING_PROVIDER=openai_compatible` (1024-dim), `TTS_PROVIDER`
  real, `REDIS_ENABLED=true`, `STORAGE_BACKEND=local`. **Not one of these real paths is
  executed by any test.** The suite runs `mock`/`mock`/`mock`/`mock`/`REDIS_ENABLED=false`.
- Consequence: the entire HTTP surface of `OpenAICompatibleProvider.stream_chat`
  (`app/ai/openai_compatible.py:75-104`) — real `httpx.AsyncClient` construction, `trust_env=False`,
  proxy resolution via `_http_proxy_url()`, `Authorization` header, timeout, and the
  **HTTP ≥ 400 error branch (lines 88-92)** — is never executed. `grep` confirms
  `_http_proxy_url` has **0 references in `tests/`**, and no test constructs a non-200
  `FakeResponse` (no `status_code = 4xx/5xx` anywhere in `tests/`).
- Same for `S3ObjectStorage.put/get/exists` (`app/infrastructure/storage/s3.py:127,140,152`):
  the only S3 test constructs the object to assert it raises on missing config
  (`tests/test_phase4_platform.py:55-63`). MinIO is up and healthy in `docker compose ps`
  and is never contacted by the suite.
- `metrics_registry.py` and `observability.py` are referenced **only by `app/main.py`** —
  0 references in `tests/`. The `/metrics` endpoint and access-log middleware have no test.

### 2.6 Skipped / xfail / conditional tests

**There are none.** `grep -rn "skip\|xfail" backend/tests/*.py` returns zero `@pytest.mark.skip`,
`@pytest.mark.xfail`, `pytest.skip()`, or `pytest.importorskip()` calls. The only `pytest.mark`
usages are 10 `@pytest.mark.parametrize` decorators. Nothing is silently skipped — which makes
the two hard failures below more significant, not less.

(Stale artifacts only: `tests/__pycache__/` contains compiled files for `_test_quiz_debug.py`
and `test_ttsdbg.py`, neither of which exists in the tree. `_test_quiz_debug.py` also would not
match pytest's default `python_files` patterns. No effect on collection.)

---

## 3. Backend test runs (raw output)

### 3.1 `docker compose ps` — services up

```
NAME                  IMAGE                    COMMAND                  SERVICE    CREATED       STATUS                       PORTS
shuangling-minio      minio/minio:latest       "/usr/bin/docker-ent…"   minio      3 weeks ago   Up About an hour (healthy)   0.0.0.0:9000-9001->9000-9001/tcp, [::]:9000-9001->9000-9001/tcp
shuangling-postgres   pgvector/pgvector:pg18   "docker-entrypoint.s…"   postgres   3 weeks ago   Up About an hour (healthy)   0.0.0.0:5432->5432/tcp, [::]:5432->5432/tcp
shuangling-redis      redis:7-alpine           "docker-entrypoint.s…"   redis      3 weeks ago   Up About an hour (healthy)   0.0.0.0:6379->6379/tcp, [::]:6379->6379/tcp
```

Postgres, Redis **and** MinIO are all up. This matters: the suite has real Postgres and real
Redis available and chooses not to use Redis.

### 3.2 Collection only

```
$ uv run pytest -q --no-header -x --co 2>&1 | tail -20
...
tests/test_worker_queue.py::test_worker_loop_survives_bad_job_and_processes_next

=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
384 tests collected in 0.71s
```

Imports resolve; collection is clean.

### 3.3 Full run against the default DB (the developer's `shuangling`)

```
$ uv run pytest -q --no-header 2>&1 | tail -60
...
>           assert quiz.status_code == 201
E           assert 404 == 201
E            +  where 404 = <Response [404 Not Found]>.status_code

tests/test_async_memory_consolidation.py:350: AssertionError
...
        source = self.run_loader(VISUAL_BOOK, VISUAL_CH)
>       assert source is not None
E       assert None is not None

tests/test_content_ai_visibility.py:169: AssertionError
=========================== short test summary info ============================
FAILED tests/test_async_memory_consolidation.py::test_quiz_answer_enqueues_memory_consolidation
FAILED tests/test_content_ai_visibility.py::TestChapterSourceVisibility::test_published_chapter_loads_source
2 failed, 382 passed, 4 warnings in 59.88s
```

(Exit code from the pipeline is 0 because `| tail` masks pytest's status; pytest itself exited 1.)

### 3.4 Reproduction of CI's exact sequence on a **fresh** database

Fresh DB → `alembic upgrade head` → `validate_library --all` → `import_library --all` → `pytest -q`:

```
== alembic ==
OK
== validate_library ==

RESULT: PASS (books=25, violations=0)
== import_library ==
== 导入知识文档 your-data-in-smart-city ==
  resource=19f77e20-e9b5-4eea-934a-2c5d39c3d7ca chunks=8 cjk=837 source=智慧城市与你的数据
import_library --all 完成：books=25 knowledge=56 legacy_archived=0
== pytest ==
=========================== short test summary info ============================
FAILED tests/test_content_ai_visibility.py::TestChapterSourceVisibility::test_published_chapter_loads_source
1 failed, 383 passed, 4 warnings in 62.04s (0:01:02)
```

**CI's `backend` job fails.** The content-init step cannot help: it imports 25 corpus books and
56 knowledge docs, none of which is the fixture book the failing test needs.

### 3.5 Second run on the *same* now-dirty database

```
384 passed, 4 warnings in 53.78s
```

Clean → `1 failed / 383 passed`; dirty → `384 passed`. The single variable is leftover data.

### 3.6 Root-cause analysis of the two failures

Both are **state/order dependence**, not product bugs.

**(a) `test_published_chapter_loads_source` — an ordering bug that always breaks a fresh DB.**

- `tests/test_content_ai_visibility.py:159` defines `TestChapterSourceVisibility` as the **first**
  class in the file.
- Its four methods (`:167`, `:172`, `:176`, `:180`) take **no `client` fixture**. The seeding
  function `_ensure()` is called only from the module-scoped `client` fixture at `:129-133`.
- Therefore the seeding runs only when `TestQuizApiVisibility` (`:185+`) requests `client` —
  i.e. **after** the test that needs the data has already run.
- Confirmed by timestamps: after the clean-DB run, `shuangling_audit_dtest` contained
  `b3000000-0000-0000-0000-000000000001 | PUBLISHED | 2026-09-16 00:59:31` — created *during* the
  run, after the failure.
- Only this file references that UUID (`grep -ln` over `tests/` returns exactly one file), so no
  other module can accidentally pre-seed it.
- Re-running the single test after the DB was dirtied by the first run: `1 passed`.

**(b) `test_quiz_answer_enqueues_memory_consolidation` — permanent failure caused by data
governance applied to a shared DB.**

- `tests/test_async_memory_consolidation.py:52-72` `_ensure_quiz_content()` inserts
  `QUIZ_BOOK_ID = b6000000-0000-0000-0000-0000000000a1` ("异步记忆测验书") only
  `if await session.get(Book, QUIZ_BOOK_ID) is None`, and never resets `status`.
- In the live dev DB that row is **`ARCHIVED`**, so `POST /api/v1/quiz-sessions` correctly
  returns 404.
- It got there because `app/scripts/archive_noncorpus.py:93-100` archives every book that is not
  in the official 25-book corpus:

  ```sql
  update books set status='ARCHIVED', published_at=NULL
  where status != 'ARCHIVED' and book_id not in (...)
    and book_id::text not like '5e3%0000%'
  ```

- The `'5e3%0000%'` clause (`:84`, `:98`) is a deliberate escape hatch — the comment at `:77-78`
  says it exists to protect test fixture books. But the fixture naming convention has drifted:
  every fixture book now uses a `bN000000-…` prefix. **All 17 distinct fixture book UUIDs
  referenced anywhere in `tests/` fail the `5e3%0000%` test, so all 17 are archivable.** Current
  DB state shows the damage:

  | book_id | status | title |
  |---|---|---|
  | `b0000000-…-a003` | ARCHIVED | 可见性·归档书 *(intentional)* |
  | `b1000000-…-0001` | **ARCHIVED** | 学习测试书一 *(unintended)* |
  | `b2000000-…-0001` | **ARCHIVED** | 学习测试书二 *(unintended)* |
  | `b6000000-…-00a1` | **ARCHIVED** | 异步记忆测验书 *(unintended)* |

- On a clean DB the same test **passes** (`_ensure_quiz_content` creates it `PUBLISHED`).

---

## 4. Frontend unit test run (raw output)

```
$ npx vitest run 2>&1 | tail -40
 RUN  v4.1.10 /home/zxk/Projects/K12-Learning-platform/frontend

 Test Files  49 passed (49)
      Tests  258 passed (258)
   Start at  08:56:56
   Duration  5.09s (transform 5.40s, setup 0ms, import 11.17s, tests 14.15s, environment 25.20s)
```

**0 failures, 0 skipped.** Frontend unit tests are green and hermetic (all I/O mocked, no DB,
no network). They are also fast (5s) — a genuine strength of this repo.

Playwright e2e was enumerated (`33 tests in 11 files`) but **not executed** in this audit: it
requires starting a backend + worker + seed on port 8002 and would mutate whichever database
`DATABASE_URL` resolves to. `ci-e2e.sh` resolves that to the dev DB when `DATABASE_URL` is unset,
so running it would have written seed data into the developer's live database. That is itself
finding §6.3.

---

## 5. Coverage gaps

### 5.1 Backend modules with no test file

Routers are exercised indirectly through `TestClient(app)` HTTP calls (`app/main.py:97-107`), so
"0 direct references" for a `router.py` is not automatically a gap. The genuine gaps are the
modules that are **not reachable from any test at all**:

| Module | Coverage | Notes |
|---|---|---|
| `app/infrastructure/metrics_registry.py` | **NONE** | 0 refs in `tests/`; used only by `main.py:15,76,147` |
| `app/infrastructure/observability.py` | **NONE** | 0 refs in `tests/`; `setup_access_logging` untested |
| `GET /metrics` endpoint | **NONE** | `main.py:147` |
| `app/infrastructure/storage/s3.py` | **put/get/exists NONE** | Only `sign_request` + missing-config raise |
| `app/jobs/worker.py` (`main` loop) | partial | `worker_loop_survives_bad_job_and_processes_next` only |
| `app/scripts/archive_noncorpus.py` | **NONE** | No test file |
| `app/scripts/preview_data_governance.py` | **NONE** | No test file |
| `app/scripts/reindex_embeddings.py` | **NONE** | No test file |
| Real Redis integration | **NONE** | Deliberately faked (`test_redis_lock.py:1`) |
| Real LLM/ASR/TTS adapters | **NONE end-to-end** | `conftest.py:5-9` forces mocks |

`app/modules/*/router.py` have 0 *direct* references but are covered via HTTP — e.g.
`test_quiz_api.py` (31 tests) drives `/api/v1/quiz-sessions`. The one exception worth flagging is
`app/modules/voice/ws.py`, which has 5 tests via `test_voice_ws.py` — real coverage, but only
under `VOICE_PROVIDER=mock`.

Also absent: **no coverage measurement at all**. There is no `pytest-cov` in
`backend/pyproject.toml` (dev deps are only `psycopg2-binary` and `pytest`), no
`@vitest/coverage-*` in `frontend/package.json`, and no coverage step in `ci.yml`. So
"coverage gaps" can only be assessed structurally, as above — nobody can currently see a number.

### 5.2 Frontend pages with no test file

| Page | Unit test | Indirect / e2e coverage |
|---|---|---|
| `src/pages/login/LoginPage.tsx` | none | e2e `login-flow.spec.ts` |
| `src/pages/reader/ReaderPage.tsx` | none | e2e `golden-path.spec.ts`, `mobile-learning.spec.ts` |
| `src/pages/profile/MemoriesPage.tsx` | none | **none found** |
| `src/pages/admin/AdminDashboard.tsx` | none | **none found** |
| `src/pages/admin/AdminLayout.tsx` | none | **none found** |
| `src/pages/book/BookDetailSections.tsx` | none | rendered via `BookDetailPage.test.tsx` |
| `src/pages/profile/components/` — `ArchiveDocCard`, `ChangeCard`, `EpisodeListCard`, `HistoryCard`, `InsightListCard`, `ProfileOverviewCard`, `ProfileSidebar`, `SectionCard` | none | **indirect only** — `ProfilePage.tsx:19-25` imports and renders them, and `ProfilePage.test.ts` does *not* mock them, so they get render coverage without assertions |

Highest-value gaps: **`MemoriesPage`** and **`AdminDashboard`/`AdminLayout`** have neither unit
nor e2e coverage.

---

## 6. CI workflow assessment

### 6.1 What actually runs

`.github/workflows/ci.yml` triggers on every `push` and `pull_request` (`:3-5`), with three
**parallel, independent** jobs (no `needs:` between them):

**`backend`** (`:8-124`) — services: `pgvector/pgvector:pg18` (`:12-24`) + `redis:7-alpine`
(`:25-33`), both health-checked. Steps: `uv sync --frozen` → `alembic upgrade head` →
`validate_library --all` → `import_library --all` → `pytest -q` → boot worker, assert alive 5s →
enqueue `memory_consolidation`, poll `background_jobs` up to 30s for a terminal status.

**`frontend`** (`:126-147`) — `pnpm install --frozen-lockfile` → `pnpm test` (vitest) →
`pnpm build` (`tsc --noEmit && vite build`). **No Playwright here.**

**`e2e`** (`:149-227`) — same Postgres+Redis services, plus `uv sync`, `alembic upgrade head`,
`pnpm install`, `playwright install --with-deps chromium`, then `bash scripts/ci-e2e.sh`, which
starts backend `:8002` + worker, runs `validate_library`/`import_library`/`seed`, and runs
Playwright with `workers=1`.

**Migrations:** yes — `alembic upgrade head` runs in both `backend` (`:49-50`) and `e2e`
(`:197-199`).

**E2E:** yes, in the dedicated `e2e` job (`:206-207`).

### 6.2 Is anything declared but not actually executed?

**(a) `backend` job is red on a fresh DB.** As shown in §3.4, the workflow's own sequence
produces `1 failed, 383 passed`. Unless the service container somehow already contains
`b3000000-0000-0000-0000-000000000001`, this job cannot pass. This is the single most important
CI finding.

**(b) The "logs on failure" artifact can never contain anything.** `ci.yml:219-227` uploads:

```yaml
path: |
  /tmp/shuangling-backend.*.log
  /tmp/shuangling-worker.*.log
```

Those files are created by `ci-e2e.sh` via `mktemp "${TMPDIR:-/tmp}/shuangling-backend.XXXXXX.log"`,
but the script's `cleanup()` trap — which runs on `EXIT`, i.e. on failure too — **deletes them**:

```bash
cleanup() {
  local code=$?
  ...
  rm -f "$BACKEND_LOG" "$WORKER_LOG"
  exit "$code"
}
```

Combined with `if-no-files-found: ignore`, this step silently uploads nothing. The
failure-diagnostics capability it advertises does not exist.

**(c) The Playwright HTML report half of the artifact glob is dead.** `ci.yml:217` includes
`frontend/playwright-report/**/*.html`, but `frontend/playwright.config.ts:11` sets
`reporter: [['list']]` — no HTML reporter is configured, so `playwright-report/` is never
created (verified absent on disk). Only the `test-results/**/*.zip` trace and `*.png` screenshot
globs can match, because `trace: 'retain-on-failure'` and `screenshot: 'only-on-failure'` are set
(`playwright.config.ts:16-17`).

**(d) No backend static analysis or type checking.** There is no `ruff`, `mypy`, or any lint step
in `ci.yml`, and neither is a declared dependency (`backend/pyproject.toml` dev deps:
`psycopg2-binary`, `pytest`). A `.ruff_cache/` directory exists in `backend/`, indicating ruff is
run locally by developers — but nothing enforces it. Frontend does get `tsc --noEmit` via
`pnpm build`.

**(e) No coverage gate** anywhere (§5.1).

**(f) Duplicated setup.** The `e2e` job repeats `uv sync --frozen`, `alembic upgrade head`, and
`pnpm install --frozen-lockfile` already done by the `backend`/`frontend` jobs. Not incorrect,
just wasteful; no `needs:`/artifact sharing is used.

### 6.3 Does CI match how a developer runs things locally?

**No — they target different databases, which is the root of the "works for me" divergence.**

| Concern | GitHub CI | Local `scripts/ci.sh` / bare `pytest` |
|---|---|---|
| Database | Fresh service container (ephemeral) | `backend/.env` → live dev DB `shuangling` |
| Migrations | `alembic upgrade head` in-job | `alembic upgrade head` (same) |
| Content init | `validate_library --all` + `import_library --all` | Same |
| Providers | `AI_PROVIDER=mock` etc. via job env | Same via exported env |
| Redis | Real service container, but `REDIS_ENABLED=false` in tests | Same |
| E2E | `scripts/ci-e2e.sh`, fresh DB | `scripts/ci-e2e.sh` → **dev DB** |

`scripts/ci.sh:70-98` (`prepare_backend_env`) only sets `DATABASE_URL` **if it is not already
set**, otherwise falling back to whatever `backend/.env` says — i.e. `shuangling`. So the
"documented local CI" runs the same test suite against the developer's working database, while
GitHub runs it against a pristine one. A test that only passes because of accumulated dev-DB
residue will be green locally and red in CI *and vice versa* — exactly the pair of behaviours
observed in §3.3–§3.5.

Also note `scripts/ci-e2e.sh:19-21,40,80-85`: it prepends `AI_PROVIDER=mock` etc. to a
**newly created** `backend/.env` if one is missing, and then runs `import_library --all` and
`seed` against the resolved DB. Locally that mutates the dev DB.

`scripts/audit-check.sh` — the one script that *does* enforce isolated-DB discipline — is never
invoked by `ci.yml` or by `ci.sh`. Its own conclusion section concedes that the full pytest/E2E
runs "需在隔离库上经 scripts/ci.sh 运行" (must be run against an isolated DB via `ci.sh`), a
precondition `ci.sh` does not itself establish.

---

## 7. "Testing theatre" — tests that pass without exercising production code

These are ordered roughly by severity. None of them is a *bad* unit test in isolation; the
problem is that the suite contains **no other layer** that covers the same ground for real, so
the untested surface is genuinely untested.

### 7.1 The suite never touches a real provider adapter (global, by construction)

`backend/tests/conftest.py:5-9` forces every provider to `mock` for all 384 tests. There is no
integration test, no smoke test against a real endpoint, and no contract test. Combined with
`ci.yml:37-40` and `:178-181` setting the same, **the real `openai_compatible`, Aliyun ASR, and
real TTS code paths have zero end-to-end coverage in CI or locally.**

### 7.2 `tests/test_ai_provider.py:134-175` — asserts against a hand-written fake HTTP client

```python
134  def test_openai_compatible_provider_returns_full_text(monkeypatch,) -> None:
...
159      monkeypatch.setattr("app.ai.openai_compatible.httpx.AsyncClient", FakeClient)
```

`FakeClient.post()` (`:156-157`) returns a canned `FakeResponse` whose `.json()` is a literal
dict (`:143-144`). What is therefore never executed in
`app/ai/openai_compatible.py`:

- line 12 `_http_proxy_url()` — **0 references in `tests/`** despite being non-trivial
  env-var/scheme-filtering logic;
- lines 75-79, real `httpx.AsyncClient(timeout=…, trust_env=False, proxy=…)` construction;
- lines 88-92, the HTTP ≥ 400 → `RuntimeError("AI_PROVIDER_ERROR: …")` branch — no test ever
  returns a 4xx/5xx. Verified exhaustively: the only `status_code` assignments to fake responses
  anywhere in `tests/` are `status_code = 200` (`test_ai_provider.py:138`, `:184`,
  `test_embedding.py:38`, `:96`).
- line 97 `self.last_usage = data.get("usage")` — the usage-capture feature is asserted nowhere
  against the real adapter (`test_context_window.py:100` sets `last_usage` **by hand** on a fake).

Note also that `FakeResponse` (`:137-144`) defines only `status_code`, `raise_for_status`, and
`json` — it has no `.text`, which the real ≥400 branch reads at line 89. The fake could not
survive the error path even if it were exercised.

This test does correctly cover the success-path response parsing and the chunking loop
(lines 98-104), which is real value. It just is not the integration test its name implies.

### 7.3 `tests/test_aliyun_voice.py` — the real DashScope WebSocket is never dialed

```python
  8  class FakeWebSocket:
...
 75          provider = AliyunASRProvider(api_key="test-key", models=["asr-a", "asr-b"], connect=connect)
```

The provider's `connect=` seam is dependency-injected with a fake, so `websockets.connect`,
TLS, the real `run-task`/`finish-task` handshake framing, audio chunking, and reconnect/backoff
are unexercised. The model-fallback-on-quota-exhaustion logic *is* genuinely tested — that is
real value — but the transport is not.

### 7.4 `tests/test_redis_lock.py` — real Redis is running and deliberately bypassed

```python
  1  """Redis infrastructure tests use an in-memory fake; no Redis server required."""
...
 12  class FakeRedis:
```

`FakeRedis` reimplements `set(nx=…)`, `eval`, `get`, `delete`, `scan_iter` in ~40 lines of
Python. `redis:7-alpine` is healthy on `localhost:6379` in `docker compose ps` **and** in CI
(`ci.yml:25-33`), yet `conftest.py:10` sets `REDIS_ENABLED=false`. Therefore the real Lua
`eval` locking script, TTL expiry, key-prefix scanning, and — most importantly — the
**degradation path when Redis is unavailable**, are validated only against a Python mock whose
semantics the author wrote to match their own expectations. A drift between `FakeRedis` and real
Redis would not be caught.

### 7.5 `tests/test_phase4_platform.py` — S3 object storage is config-tested only

```python
 55      def test_s3_config_error_is_explicit(self, monkeypatch):
 66      def test_sigv4_signature_is_deterministic(self, monkeypatch):
 87      def test_factory_uses_configured_backend(self, monkeypatch, tmp_path):
```

`S3ObjectStorage.put` / `.get` / `.exists` (`app/infrastructure/storage/s3.py:127,140,152`) are
never called. Only `sign_request` (SigV4 string construction) and the missing-config `raise` are
covered. `test_factory_uses_configured_backend` asserts the factory returns an
`S3ObjectStorage` **instance** — it does not then use it. MinIO is available and unused; the
production `STORAGE_BACKEND=s3` path has no test.

### 7.6 `tests/test_content_cache.py` — database *and* Redis replaced

```python
  1  """Books-list cache tests; database and Redis are both replaced with fakes."""
...
 21  class FakeSession:
```

Same class of issue: cache-invalidation logic is tested against a `FakeSession` with an
`EmptyResult` stub, plus monkeypatched `app.modules.admin.service` / `app.modules.content.service`
modules. It verifies call sequencing, not cache behaviour.

### 7.7 `frontend/src/pages/admin/AdminPages.test.ts` — asserts on mocks, cannot catch broken wiring

```ts
 33  vi.mock('@/shared/api/admin-service', () => ({
 34    adminService: {
 35      getBooks: mocks.getBooks,
...
```

The **entire** API module is replaced at line 33. The tests then assert against those mocks, e.g.
`AdminPages.test.ts:162`:

```ts
    await waitFor(() =>
      expect(mocks.createTeacherRole).toHaveBeenCalledWith({
        name: '幽默风趣', tone: '耐心鼓励', teaching_style: '温暖清晰',
      }),
    )
```

This proves the component calls *something named* `createTeacherRole`. If the real
`adminService.createTeacherRole` were deleted, renamed, given a different signature, or pointed at
a wrong URL, this file would still pass — the import is mocked away. The assertions cannot fail
for any wiring reason. (The same technique appears in `ProfilePage.test.ts:12`, which mocks
`@/shared/services` wholesale.)

Mitigating factor: `src/shared/api/admin-service.test.ts` exists (2 tests) and
`src/shared/api/http.test.ts` (7 tests) exercise the real fetch layer, and the e2e
`admin.spec.ts` covers the real path. So this is a *layering* observation — the unit test is
fine for what it is, but it must not be counted as coverage of the admin API.

### 7.8 The worker smoke test in CI proves liveness, then separately proves one job

`ci.yml:57-63` asserts the worker process is still alive after 5 seconds. On its own that is
weak (a worker that instantly stops polling but does not exit would pass). To the authors'
credit, `ci.yml:66-120` adds a real end-to-end assertion: enqueue a `memory_consolidation` job
and poll `background_jobs` for `success`/`failed` within 30s. The second step is genuine
integration coverage and is one of the strongest tests in the pipeline. The first step is
largely redundant theatre.

### 7.9 `tests/test_smoke.py:22-31` — an assertion that was defused

```python
def test_validation_error_uses_envelope() -> None:
    response = client.get("/api/v1/ping?unexpected=1")
    # GET 无 query 参数约束，该请求应 200；改用不存在的路径验证 404 信封
    assert response.status_code == 200
    not_found = client.get("/api/v1/not-exist")
    assert not_found.status_code == 404
```

The test name promises coverage of the **validation-error** envelope (422), but it now asserts
200 and checks the **404** envelope instead. The 422 envelope branch of
`app/api/envelope.py` is not covered by this test despite the name.

---

## 8. Summary tables

### Backend

| Metric | Default (dev DB) | Fresh DB (CI-equivalent) | Same DB, 2nd run |
|---|---|---|---|
| Collected | 384 | 384 | 384 |
| Passed | 382 | 383 | **384** |
| Failed | **2** | **1** | 0 |
| Errors | 0 | 0 | 0 |
| Skipped | 0 | 0 | 0 |
| Duration | 59.88s | 62.04s | 53.78s |

Failing tests:
1. `tests/test_content_ai_visibility.py::TestChapterSourceVisibility::test_published_chapter_loads_source`
   — `assert source is not None` (`:169`). **Fails on every fresh database, i.e. in CI.**
2. `tests/test_async_memory_consolidation.py::test_quiz_answer_enqueues_memory_consolidation`
   — `assert quiz.status_code == 201` got 404 (`:350`). Fails only on the dev DB because
   `archive_noncorpus.py` archived the fixture book.

### Frontend

| Metric | Value |
|---|---|
| Test files | 49 passed (49) |
| Tests | 258 passed (258) |
| Failed / errors / skipped | 0 / 0 / 0 |
| Duration | 5.09s |

### Playwright e2e

| Metric | Value |
|---|---|
| Spec files | 11 |
| Tests (all projects) | 33 |
| Executed in this audit | No — would mutate the live dev DB (§4) |

---

## 9. Prioritised recommendations

1. **Make the test DB explicit and isolated.** Introduce `backend/tests/conftest.py` fixtures that
   set `DATABASE_URL` to a dedicated DB (or refuse to run when it equals the dev DB, reusing the
   `audit-check.sh:30-49` guard). This is the one change that removes findings 1, 2, 4 and (b) of §6.2.
2. **Fix the ordering defect in `test_content_ai_visibility.py`.** Move the four
   `TestChapterSourceVisibility` methods behind the `client` fixture (or call `_ensure()` from a
   module-scoped `autouse` fixture) so the first test in the file seeds its own data. CI cannot go
   green without this.
3. **Make seeders self-healing.** `_ensure*()` helpers should upsert the required `status` rather
   than `if … is None: insert` — `test_async_memory_consolidation.py:55` is the concrete offender.
4. **Fix or delete the `5e3%0000%` escape hatch** in `app/scripts/archive_noncorpus.py:84,98`.
   Either extend it to the `bN000000-…` convention used by all 17 current fixtures, or move test
   fixtures out of the production UUID space entirely.
5. **Per-test isolation** (transaction rollback or truncate-between-modules) to make the suite
   order-independent and parallelisable.
6. **Add real integration coverage for the paths that actually break**: one test each against real
   Redis (it is already running in CI) and against the S3/MinIO backend; a contract test for
   `OpenAICompatibleProvider` covering the ≥400 branch and `_http_proxy_url()`.
7. **Repair or remove the dead CI artifacts**: keep the backend/worker logs alive past
   `ci-e2e.sh`'s cleanup trap, and either configure the Playwright HTML reporter or drop it from
   the upload glob (`ci.yml:217`).
8. **Add coverage measurement** (pytest-cov + vitest coverage) so gaps are visible as numbers, and
   add a `ruff` step for the backend — it is already used locally but enforced nowhere.
