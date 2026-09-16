# Audit C — Database Layer

**Target:** `/home/zxk/Projects/K12-Learning-platform/backend` — FastAPI + SQLAlchemy 2.0 async + Alembic + PostgreSQL 18 (pgvector 0.8.6)
**Mode:** read-only, evidence-based archaeology. **No source file was modified.** Scratch artifacts live in `/tmp/audit/`.
**Date of audit:** live database inspected while `shuangling-postgres` was up and stamped at head.

---

## 0. Method (so every number below is reproducible)

| Evidence source | How it was obtained | Artifact |
|---|---|---|
| ORM metadata | Loaded `Base.metadata` in-process; dumped every table/column/index/constraint to JSON, with `models.py` line numbers recovered by AST walk | `/tmp/audit/models.json` |
| Live schema | `information_schema` + `pg_indexes` + `pg_constraint` via asyncpg (**read-only SELECTs**) | `/tmp/audit/db.json` |
| Migration output | `uv run alembic upgrade head --sql` — Alembic **offline** mode, emits all DDL from base to head **without connecting to any database** | `/tmp/audit/migrations_offline.sql` (946 lines) |
| Revision graph | Re-parsed `revision`/`down_revision` literals from all 23 files with `ast.literal_eval` (quotes/casts handled) | `/tmp/audit/` |
| Autogenerate drift | `alembic.autogenerate.compare_metadata()` against the live DB (**read-only**) | §3 |
| Query plans | `EXPLAIN (VERBOSE, COSTS)` — no `ANALYZE`, so no execution | §7 |

The three-way comparison **models ↔ live DB ↔ migration DDL** is what makes the drift verdicts below conclusive: a column present in models *and* live DB *and* migration output cannot be drift, and a column present in only two of the three is flagged.

Committed (read-only) commands used against the live DB: `alembic current`, `alembic heads`, `alembic history`, `docker compose ps`, `EXPLAIN`, `SELECT`. **No `upgrade`, `downgrade`, `INSERT`, `UPDATE`, `DELETE` or DDL was executed.**

---

## 1. Executive summary

### 1.1 Is the migration chain sane? — **YES. CONFIRMED.**

The revision graph is a **single, strictly linear chain of 23 revisions** with:

* **exactly one root**: `8468855342d3` (`down_revision = None`)
* **exactly one head**: `a7b8c9d0e1f2`
* **zero branch points** (no revision has >1 child), **zero merge revisions**, **zero orphaned revisions**, **zero dangling `down_revision`s**, **zero cycles**
* `branch_labels` and `depends_on` are `None` in all 23 files
* all 23 revisions are reachable by walking from the root; the walk visits 23/23
* `alembic heads` on the live DB returns exactly `a7b8c9d0e1f2 (head)` and `alembic current` returns `a7b8c9d0e1f2 (head)`

The 4 untracked (new, uncommitted) migrations are **positions 20, 21, 22 and 23** of the chain — i.e. they are the newest segment and **the last of them *is* the head**. They are fully reachable, not orphaned. See §4.

### 1.2 What drift exists? — **Almost none. One benign item. CONFIRMED.**

Running Alembic's own `compare_metadata()` (the engine behind `alembic revision --autogenerate`) against the live database produces **exactly 2 diff entries, which are two halves of one single discrepancy**:

```
('remove_index',      Index('uq_chapter_completion_student_chapter', ... unique=True))
('add_constraint',    UniqueConstraint(Column('student_id'), Column('chapter_id')))
```

* `models.py:527-529` declares a `UniqueConstraint("student_id","chapter_id", name="uq_chapter_completion_student_chapter")` → SQLAlchemy would emit `ALTER TABLE ... ADD CONSTRAINT`.
* `a4b5c6d7e8f9_add_chapter_completions.py:40-45` instead calls `op.create_index(..., unique=True)` → a **unique index**, not a unique constraint.

Both enforce the same uniqueness, so **there is no correctness or data-integrity impact**. But the two objects are not the same catalog object, so every future `--autogenerate` will keep proposing a churn pair (drop the index, add the constraint). This is the **only** real model↔DB drift in the entire schema.

Everything else reconciles exactly:

| Dimension | Result |
|---|---|
| Tables: models vs live DB | **32 vs 32, names identical** (DB additionally has `alembic_version`, which is Alembic's own bookkeeping table and correctly has no ORM model) |
| Columns: models vs live DB | **368 vs 368 — zero model-only, zero DB-only** |
| Column types | **zero mismatches** (all 74 `DateTime` columns are `timezone=True` on both sides; `vector` columns are dimension-less on both sides) |
| Nullability | **zero mismatches** |
| Server defaults | **zero mismatches** |
| Foreign keys (target + `ondelete`) | **58 FKs, zero mismatches in either direction** |
| CHECK constraints | **68 named CHECKs in migrations = 68 in the live DB, identical name sets** |
| UNIQUE constraints | **zero drift** (the 4 DB-only `*_key` entries come from column-level `unique=True`, which SQLAlchemy renders inline, not as named constraints) |
| Indexes | **34 model `Index` objects → all 34 present in the DB**; **every index created by a migration is present in the DB**; the extra DB indexes are only primary keys / unique-constraint backings / the one unique index in §1.2 |
| Tables created by migrations from base | **33** (32 app + `alembic_version`); **none dropped**; every table's column set after replaying all `ALTER TABLE ADD/DROP COLUMN` matches the live DB **exactly** |

> **Therefore: `models.py` ≡ live DB ≡ `alembic upgrade head` output.** The schema is in far better shape than "1465-line models file with 23 migrations" usually implies.

### 1.3 What would break on a fresh `alembic upgrade head`? — **Nothing expected. It is safe.**

* `alembic upgrade head --sql` (offline, from base, all 23 revisions) **completes with exit code 0** and renders 946 lines of DDL. No revision in the chain reads a table or column created by a *later* revision — every cross-migration reference points backwards. CONFIRMED.
* The one environment prerequisite is that **the pgvector package must exist in the server image**, because `CREATE EXTENSION IF NOT EXISTS vector` (`f0e1d2c3b4a5_create_episodes_and_insights.py:32`) needs the extension *available*, not merely guarded. It is available here (`pgvector/pgvector:pg18`, extension version 0.8.6). LIKELY env-dependent.
* The data-dependent backfills are **inert, not failing, on an empty DB**: `a1b2c3d4e5f6:120-141` inserts an `admins` row only for a user named `admin` and then NULL-fills `books.created_by` / `knowledge_resources.uploaded_by`; on a fresh DB `users`/`books` are empty, so both statements affect 0 rows. CONFIRMED — a silent no-op, not an error.
* Two real hygiene defects that do **not** break a fresh upgrade but are worth fixing (details in §4 and §5):
  1. **`b1c2d3e4f5a6` is an already-applied migration that was edited in place** by commit `bce24e9` (it originally seeded `'shuangling'`/`'strict-mentor'`; it now seeds `'温暖鼓励'`/`'严谨清晰'`). Fresh DBs and the incumbent DB reach the same end state, but the migration set is no longer byte-reproducible.
  2. **`c7d8e9f0a1b2` drops both HNSW vector indexes and never recreates them**, so *every* database — fresh or existing — is born with **zero vector indexes** and RAG runs on a sequential scan (§7).

### 1.4 Bootstrap order for a fresh database

```
docker compose up -d postgres                 # pgvector/pgvector:pg18
cd backend && uv run alembic upgrade head     # 23 revisions → a7b8c9d0e1f2
uv run python -m app.scripts.seed             # REQUIRED: demo accounts + admin row + teacher styles
uv run python -m app.scripts.validate_library --all    # structural gate (no DB needed)
uv run python -m app.scripts.import_library --all      # books/chapters/blocks/knowledge (idempotent)
uv run python -m app.scripts.import_assessments        # reviewed_questions (idempotent by stable_key)
```

**`migrate` must come before `seed`** (seed writes `teacher_roles`, `admins`, `student_profiles`). This is also exactly what CI does: `.github/workflows/ci.yml:50` → `alembic upgrade head`, then `:53-55` → `validate_library --all` → `import_library --all`. The E2E script layers `seed` on top (`scripts/ci-e2e.sh:166-167`).

**Demo credentials:** `admin` / **`admin123`** (hardcoded, `seed.py:57`, `user_type=ADMIN` + an `admins` row with `role_level=SUPERVISOR`) and `xiaoming` / **`demo123`** (`seed.py:30`, overridable via `SEED_PASSWORD`; `student_profiles.grade=8`, nickname `小明`). `seed.py` is **idempotent** (select-then-create throughout). Details in §6.

---

## 2. Live database check (item 7)

**A database WAS reachable — all checks below are CONFIRMED against the running instance.**

```
$ docker compose ps
shuangling-postgres   pgvector/pgvector:pg18   Up 52 minutes (healthy)   0.0.0.0:5432->5432/tcp
shuangling-minio      minio/minio:latest       Up 52 minutes (healthy)   0.0.0.0:9000-9001->9000-9001/tcp
shuangling-redis      redis:7-alpine           Up 52 minutes (healthy)   0.0.0.0:6379->6379/tcp
```

```
$ cd backend && uv run alembic current
a7b8c9d0e1f2 (head)

$ uv run alembic heads
a7b8c9d0e1f2 (head)

$ SELECT version_num FROM alembic_version;
a7b8c9d0e1f2
```

* **Actual current revision = `a7b8c9d0e1f2`; head = `a7b8c9d0e1f2`. The database is exactly at head — zero pending migrations.** CONFIRMED
* Extensions installed: `plpgsql 1.0`, **`vector 0.8.6`**. CONFIRMED
* Server: PostgreSQL 18 (`pgvector/pgvector:pg18`). CONFIRMED
* Tables in `public`: **33** = 32 application tables + `alembic_version`. CONFIRMED — no leftover/legacy/rogue tables.

### Live row counts (context for the index/perf findings)

| table | rows | | table | rows |
|---|---:|---|---|---:|
| `idempotency_keys` | 8499 | | `quiz_sessions` | 90 |
| `content_blocks` | 2018 | | `student_memories` | 66 |
| `knowledge_chunks` | 1153 | | `quiz_answers` | 63 |
| `profile_insights` | 931 | | `book_progress` | 53 |
| `background_jobs` | 698 | | `memory_candidates` | 50 |
| `messages` | 535 | | `reading_settlements` | 24 |
| `learning_events` | 499 | | `student_preferences` | 11 |
| `knowledge_resources` | 498 | | `reviewed_questions` | 5 |
| `memory_evidence` | 397 | | `teacher_roles` | 4 |
| `knowledge_points` | 367 | | `admins` | 4 |
| `student_episodes` | 248 | | `chapter_completions` | 2 |
| `books` | 136 | | `conversation_summaries` | 4 |
| `chapters` | 169 | | `learning_sessions` | 170 |
| `recommendations` | 199 | | `conversations` | 159 |
| `users` | 190 | | `quiz_questions` | 109 |
| `student_profiles` | 133 | | `quiz_interactions` | 142 |

**Note on data hygiene:** `users` contains **190 rows**, the overwhelming majority of which are test fixtures (`test_student`, `test_quiz_user`, `test_p2_ctx_user`, `recommendation_student_065e49eb73`, …) — see §6.5.

---


## 3. Complete table inventory (32 ORM tables)

Source of truth: `app/infrastructure/database/models.py`. Every column was verified against BOTH the live PostgreSQL database (`information_schema`) and the DDL emitted by the 23 migrations. `L` = line number in `models.py`.

**Totals: 32 tables, 368 columns, 34 model `Index` objects, 68 CHECK constraints, 19 UNIQUE constraints, 58 FOREIGN KEYs.**


### `admins`  (models.py:1402, `__table_args__` at :1406) — class `Admin`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `admin_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 1414 |
| `user_id` | UUID | NO | `—` | `users.user_id` (CASCADE) | 1417 |
| `display_name` | String(128) | NO | `—` | — | 1422 |
| `role_level` | String(24) | NO | `'SUPERVISOR'` | — | 1423 |
| `permissions` | JSONB | YES | `—` | — | 1426 |
| `enabled` | BOOLEAN | NO | `true` | — | 1427 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 1428 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 1431 |

**Indexes:** (only the primary key)

**Unique constraints:** `uq_admins_user`(user_id)

**CHECK constraints:** `ck_admins_role_level`: `role_level IN ('SUPERVISOR','CONTENT_EDITOR')`


### `background_jobs`  (models.py:1328, `__table_args__` at :1332) — class `BackgroundJob`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `job_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 1340 |
| `job_type` | String(64) | NO | `—` | — | 1343 |
| `status` | String(16) | NO | `'queued'` | — | 1344 |
| `attempt` | INTEGER | NO | `0` | — | 1347 |
| `payload` | JSONB | NO | `'{}'::jsonb` | — | 1348 |
| `error` | TEXT | YES | `—` | — | 1351 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 1352 |
| `started_at` | DateTime(tz=True) | YES | `—` | — | 1355 |
| `finished_at` | DateTime(tz=True) | YES | `—` | — | 1356 |
| `next_attempt_at` | DateTime(tz=True) | YES | `—` | — | 1358 |

**Indexes:** `ix_background_jobs_status_created`(status, created_at)

**CHECK constraints:** `ck_background_jobs_status`: `status IN ('queued','running','success','failed')`


### `book_progress`  (models.py:473, `__table_args__` at :477) — class `BookProgress`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `progress_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 489 |
| `student_id` | UUID | NO | `—` | `student_profiles.student_id` (RESTRICT) | 492 |
| `book_id` | UUID | NO | `—` | `books.book_id` (RESTRICT) | 496 |
| `chapter_id` | UUID | YES | `—` | `chapters.chapter_id` (RESTRICT) | 499 |
| `block_id` | UUID | YES | `—` | `content_blocks.block_id` (SET NULL) | 502 |
| `status` | String(16) | NO | `'NOT_STARTED'` | — | 506 |
| `position_percent` | INTEGER | NO | `0` | — | 507 |
| `last_read_at` | DateTime(tz=True) | YES | `—` | — | 508 |
| `started_at` | DateTime(tz=True) | YES | `—` | — | 509 |
| `completed_at` | DateTime(tz=True) | YES | `—` | — | 510 |
| `total_seconds` | INTEGER | NO | `0` | — | 511 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 512 |

**Indexes:** (only the primary key)

**Unique constraints:** `uq_book_progress_student_book`(student_id, book_id)

**CHECK constraints:** `ck_book_progress_total_seconds`: `total_seconds >= 0`; `ck_book_progress_position`: `position_percent BETWEEN 0 AND 100`; `ck_book_progress_status`: `status IN ('NOT_STARTED','READING','COMPLETED')`


### `books`  (models.py:218, `__table_args__` at :222) — class `Book`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `book_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 236 |
| `title` | String(255) | NO | `—` | — | 239 |
| `cover_url` | String(512) | YES | `—` | — | 240 |
| `description` | TEXT | YES | `—` | — | 241 |
| `grade_min` | INTEGER | NO | `—` | — | 242 |
| `grade_max` | INTEGER | NO | `—` | — | 243 |
| `difficulty` | String(16) | NO | `—` | — | 244 |
| `estimated_minutes` | INTEGER | NO | `—` | — | 245 |
| `author` | String(255) | YES | `—` | — | 246 |
| `source_ids` | JSONB | NO | `'[]'::jsonb` | — | 247 |
| `license` | String(128) | YES | `—` | — | 248 |
| `copyright_status` | String(128) | YES | `—` | — | 249 |
| `tags` | JSONB | NO | `'[]'::jsonb` | — | 250 |
| `status` | String(16) | NO | `'DRAFT'` | — | 251 |
| `created_by` | UUID | YES | `—` | `admins.admin_id` (RESTRICT) | 252 |
| `published_at` | DateTime(tz=True) | YES | `—` | — | 256 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 257 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 260 |

**Indexes:** `ix_books_grade_min_max`(grade_min, grade_max)

**CHECK constraints:** `ck_books_grade_range`: `grade_min <= grade_max`; `ck_books_status`: `status IN ('DRAFT','PUBLISHED','ARCHIVED')`; `ck_books_estimated_minutes`: `estimated_minutes > 0`; `ck_books_grade_max`: `grade_max BETWEEN 1 AND 12`; `ck_books_difficulty`: `difficulty IN ('EASY','MEDIUM','HARD')`; `ck_books_grade_min`: `grade_min BETWEEN 1 AND 12`


### `chapter_completions`  (models.py:517, `__table_args__` at :526) — class `ChapterCompletion`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `completion_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 537 |
| `student_id` | UUID | NO | `—` | `student_profiles.student_id` (RESTRICT) | 540 |
| `chapter_id` | UUID | NO | `—` | `chapters.chapter_id` (RESTRICT) | 544 |
| `book_id` | UUID | NO | `—` | `books.book_id` (RESTRICT) | 549 |
| `completed_at` | DateTime(tz=True) | NO | `—` | — | 552 |
| `source` | String(16) | NO | `'EXPLICIT'` | — | 553 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 554 |

**Indexes:** `ix_chapter_completions_student_book`(student_id, book_id)

**Unique constraints:** `uq_chapter_completion_student_chapter`(student_id, chapter_id)

**CHECK constraints:** `ck_chapter_completions_source`: `source IN ('EXPLICIT','LEGACY_EVENT')`


### `chapters`  (models.py:265, `__table_args__` at :269) — class `Chapter`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `chapter_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 277 |
| `book_id` | UUID | NO | `—` | `books.book_id` (CASCADE) | 280 |
| `title` | String(255) | NO | `—` | — | 284 |
| `chapter_order` | INTEGER | NO | `—` | — | 285 |
| `summary` | TEXT | YES | `—` | — | 286 |
| `estimated_minutes` | INTEGER | NO | `—` | — | 287 |
| `status` | String(16) | NO | `'DRAFT'` | — | 288 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 289 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 292 |

**Indexes:** (only the primary key)

**Unique constraints:** `uq_chapters_book_order`(book_id, chapter_order)

**CHECK constraints:** `ck_chapters_status`: `status IN ('DRAFT','PUBLISHED','ARCHIVED')`; `ck_chapters_estimated_minutes`: `estimated_minutes > 0`


### `content_blocks`  (models.py:297, `__table_args__` at :301) — class `ContentBlock`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `block_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 310 |
| `chapter_id` | UUID | NO | `—` | `chapters.chapter_id` (CASCADE) | 313 |
| `block_type` | String(32) | NO | `—` | — | 317 |
| `content` | JSONB | NO | `—` | — | 318 |
| `block_order` | INTEGER | NO | `—` | — | 319 |
| `section_key` | String(128) | YES | `—` | — | 320 |
| `knowledge_point_ids` | JSONB | NO | `'[]'::jsonb` | — | 321 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 324 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 327 |

**Indexes:** (only the primary key)

**Unique constraints:** `uq_content_blocks_chapter_order`(chapter_id, block_order)

**CHECK constraints:** `ck_content_blocks_type`: `block_type IN ('TITLE','PARAGRAPH','IMAGE','FIGURE','KNOWLEDGE_CARD','EXAMPLE','CALLOUT','HIGHLIGHT')`


### `conversation_summaries`  (models.py:729, `__table_args__` at :733) — class `ConversationSummary`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `summary_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 742 |
| `conversation_id` | UUID | NO | `—` | `conversations.conversation_id` (CASCADE) | 745 |
| `summary` | TEXT | NO | `—` | — | 749 |
| `token_count` | INTEGER | NO | `0` | — | 750 |
| `summary_version` | INTEGER | NO | `1` | — | 751 |
| `source_message_ids` | JSONB | NO | `'[]'::jsonb` | — | 752 |
| `message_covered_count` | INTEGER | NO | `0` | — | 757 |
| `model_info` | JSONB | YES | `—` | — | 758 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 759 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 762 |

**Indexes:** (only the primary key)

**Unique constraints:** `uq_conversation_summaries_conversation`(conversation_id)

**CHECK constraints:** `ck_conversation_summaries_token_count`: `token_count >= 0`


### `conversations`  (models.py:639, `__table_args__` at :643) — class `Conversation`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `conversation_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 660 |
| `student_id` | UUID | NO | `—` | `student_profiles.student_id` (RESTRICT) | 663 |
| `teacher_role_id` | UUID | YES | `—` | `teacher_roles.role_id` (RESTRICT) | 668 |
| `title` | String(255) | YES | `—` | — | 672 |
| `status` | String(16) | NO | `'ACTIVE'` | — | 673 |
| `channel` | String(16) | NO | `'TEXT'` | — | 674 |
| `current_page_context` | JSONB | NO | `'{}'::jsonb` | — | 675 |
| `recent_messages` | JSONB | NO | `'[]'::jsonb` | — | 678 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 681 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 684 |
| `last_message_at` | DateTime(tz=True) | YES | `—` | — | 687 |

**Indexes:** `ix_conversations_teacher_role`(teacher_role_id); `ix_conversations_student_updated`(student_id)

**CHECK constraints:** `ck_conversations_channel`: `channel IN ('TEXT','VOICE')`; `ck_conversations_status`: `status IN ('ACTIVE','ARCHIVED','DELETED')`


### `idempotency_keys`  (models.py:1436, `__table_args__` at :1440) — class `IdempotencyKey`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `idempotency_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 1454 |
| `actor_id` | UUID | NO | `—` | — | 1457 |
| `actor_type` | String(16) | NO | `—` | — | 1458 |
| `key` | String(64) | NO | `—` | — | 1459 |
| `request_hash` | String(64) | NO | `—` | — | 1460 |
| `response` | JSONB | NO | `—` | — | 1461 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 1462 |
| `expires_at` | DateTime(tz=True) | NO | `—` | — | 1465 |

**Indexes:** `ix_idempotency_keys_actor_expires`(actor_id, expires_at)

**Unique constraints:** `uq_idempotency_keys_actor_key`(actor_id, actor_type, key)

**CHECK constraints:** `ck_idempotency_keys_actor_type`: `actor_type IN ('STUDENT','ADMIN')`


### `knowledge_chunks`  (models.py:1361, `__table_args__` at :1365) — class `KnowledgeChunk`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `chunk_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 1376 |
| `resource_id` | UUID | NO | `—` | `knowledge_resources.resource_id` (CASCADE) | 1379 |
| `chunk_index` | INTEGER | NO | `—` | — | 1383 |
| `content` | TEXT | NO | `—` | — | 1384 |
| `content_type` | String(64) | YES | `—` | — | 1385 |
| `metadata` | JSONB | NO | `'{}'::jsonb` | — | — |
| `knowledge_point_ids` | JSONB | NO | `'[]'::jsonb` | — | 1389 |
| `embedding` | VECTOR (no dim) | YES | `—` | — | 1392 |
| `token_count` | INTEGER | NO | `0` | — | 1393 |
| `status` | String(16) | NO | `'PENDING'` | — | 1394 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 1397 |

**Indexes:** (only the primary key)

**Unique constraints:** `uq_knowledge_chunks_resource_index`(resource_id, chunk_index)

**CHECK constraints:** `ck_knowledge_chunks_token_count`: `token_count >= 0`; `ck_knowledge_chunks_status`: `status IN ('PENDING','READY','FAILED')`


### `knowledge_points`  (models.py:332, `__table_args__` at :336) — class `KnowledgePoint`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `knowledge_point_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 342 |
| `name` | String(128) | NO | `—` | — | 345 |
| `slug` | String(128) | NO | `—` | — | 346 |
| `description` | TEXT | YES | `—` | — | 347 |
| `topic` | String(64) | YES | `—` | — | 348 |
| `parent_id` | UUID | YES | `—` | `knowledge_points.knowledge_point_id` (SET NULL) | 349 |
| `status` | String(16) | NO | `'ACTIVE'` | — | 353 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 354 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 357 |

**Indexes:** (only the primary key)

**Unique constraints:** (column-level UNIQUE, unnamed)(slug)

**CHECK constraints:** `ck_knowledge_points_status`: `status IN ('ACTIVE','ARCHIVED')`


### `knowledge_resources`  (models.py:1282, `__table_args__` at :1286) — class `KnowledgeResource`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `resource_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 1299 |
| `source_name` | String(255) | NO | `—` | — | 1302 |
| `source_url` | String(512) | NO | `—` | — | 1303 |
| `author` | String(255) | YES | `—` | — | 1304 |
| `license` | String(128) | NO | `—` | — | 1305 |
| `copyright_status` | String(128) | NO | `—` | — | 1306 |
| `storage_key` | String(512) | NO | `—` | — | 1307 |
| `file_type` | String(16) | NO | `—` | — | 1308 |
| `status` | String(16) | NO | `'UPLOADED'` | — | 1309 |
| `uploaded_by` | UUID | YES | `—` | `admins.admin_id` (RESTRICT) | 1312 |
| `error` | TEXT | YES | `—` | — | 1316 |
| `uploaded_at` | DateTime(tz=True) | NO | `now()` | — | 1317 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 1320 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 1323 |

**Indexes:** `ix_knowledge_resources_status_created`(status, created_at); `ix_knowledge_resources_uploaded_by`(uploaded_by)

**CHECK constraints:** `ck_knowledge_resources_file_type`: `file_type IN ('PDF','MARKDOWN','TXT','HTML')`; `ck_knowledge_resources_status`: `status IN ('UPLOADED','PARSING','CHUNKING','INDEXING','READY','FAILED')`


### `learning_events`  (models.py:413, `__table_args__` at :417) — class `LearningEvent`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `event_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 438 |
| `student_id` | UUID | NO | `—` | `student_profiles.student_id` (RESTRICT) | 441 |
| `session_id` | UUID | YES | `—` | `learning_sessions.session_id` (RESTRICT) | 445 |
| `event_type` | String(48) | NO | `—` | — | 449 |
| `occurred_at` | DateTime(tz=True) | NO | `—` | — | 450 |
| `book_id` | UUID | YES | `—` | `books.book_id` (RESTRICT) | 451 |
| `chapter_id` | UUID | YES | `—` | `chapters.chapter_id` (RESTRICT) | 454 |
| `block_id` | UUID | YES | `—` | `content_blocks.block_id` (RESTRICT) | 457 |
| `knowledge_point_ids` | JSONB | NO | `'[]'::jsonb` | — | 460 |
| `conversation_id` | UUID | YES | `—` | — | 464 |
| `quiz_session_id` | UUID | YES | `—` | — | 466 |
| `payload` | JSONB | NO | `—` | — | 467 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 468 |

**Indexes:** `ix_learning_events_conversation`(conversation_id); `ix_learning_events_quiz_session`(quiz_session_id); `ix_learning_events_student_type`(student_id, event_type); `ix_learning_events_student_occurred`(student_id); `ix_learning_events_session`(session_id)

**CHECK constraints:** `ck_learning_events_type`: `event_type IN ('CHAPTER_STARTED','CHAPTER_FINISHED','SECTION_READ','KNOWLEDGE_CARD_VIEWED','HELP_REQUESTED','EXPLAIN_REQUESTED','SUMMARY_REQUESTED','QUIZ_CREATED','QUIZ_ANSWERED','ANSWER_CORRECT','ANSWER_WRONG','HINT_REQUESTED','QUESTION_ASKED','BOOK_STARTED','BOOK_FINISHED','VOICE_SESSION_STARTED','VOICE_SESSION_ENDED','ROLE_SWITCHED','TEXT_SELECTED','QUIZ_REVIEW_COMPLETED')`


### `learning_sessions`  (models.py:362, `__table_args__` at :366) — class `LearningSession`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `session_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 390 |
| `student_id` | UUID | NO | `—` | `student_profiles.student_id` (RESTRICT) | 393 |
| `book_id` | UUID | NO | `—` | `books.book_id` (RESTRICT) | 397 |
| `chapter_id` | UUID | NO | `—` | `chapters.chapter_id` (RESTRICT) | 400 |
| `started_at` | DateTime(tz=True) | NO | `—` | — | 403 |
| `ended_at` | DateTime(tz=True) | YES | `—` | — | 404 |
| `duration_seconds` | INTEGER | NO | `0` | — | 405 |
| `status` | String(16) | NO | `'ACTIVE'` | — | 406 |
| `entry_route` | String(64) | YES | `—` | — | 407 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 408 |

**Indexes:** `uq_learning_sessions_one_active`(student_id) UNIQUE; `ix_learning_sessions_student_started`(student_id)

**CHECK constraints:** `ck_learning_sessions_ended_after_started`: `ended_at IS NULL OR ended_at >= started_at`; `ck_learning_sessions_status`: `status IN ('ACTIVE','ENDED','ABANDONED')`; `ck_learning_sessions_duration`: `duration_seconds >= 0`


### `memory_candidates`  (models.py:823, `__table_args__` at :827) — class `MemoryCandidate`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `candidate_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 846 |
| `student_id` | UUID | NO | `—` | `student_profiles.student_id` (RESTRICT) | 849 |
| `candidate_type` | String(16) | NO | `—` | — | 853 |
| `content` | TEXT | NO | `—` | — | 854 |
| `proposed_memory` | JSONB | NO | `—` | — | 855 |
| `evidence_ids` | JSONB | NO | `'[]'::jsonb` | — | 856 |
| `confidence` | String(8) | NO | `—` | — | 859 |
| `status` | String(16) | NO | `'PENDING'` | — | 860 |
| `rule_version` | String(64) | NO | `—` | — | 861 |
| `model_info` | JSONB | NO | `—` | — | 862 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 863 |
| `resolved_at` | DateTime(tz=True) | YES | `—` | — | 866 |

**Indexes:** `ix_memory_candidates_student_status`(student_id, status); `ix_memory_candidates_status_created`(status, created_at)

**CHECK constraints:** `ck_memory_candidates_type`: `candidate_type IN ('PROFILE','PREFERENCE','LEARNING','EPISODIC')`; `ck_memory_candidates_status`: `status IN ('PENDING','APPROVED','REJECTED','MERGED')`; `ck_memory_candidates_confidence`: `confidence IN ('LOW','MEDIUM','HIGH')`


### `memory_evidence`  (models.py:869, `__table_args__` at :873) — class `MemoryEvidence`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `evidence_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 886 |
| `student_id` | UUID | NO | `—` | `student_profiles.student_id` (RESTRICT) | 889 |
| `source_type` | String(24) | NO | `—` | — | 893 |
| `event_ids` | JSONB | NO | `'[]'::jsonb` | — | 894 |
| `payload` | JSONB | NO | `—` | — | 897 |
| `count` | INTEGER | NO | `1` | — | 898 |
| `first_occurred_at` | DateTime(tz=True) | YES | `—` | — | 899 |
| `last_occurred_at` | DateTime(tz=True) | YES | `—` | — | 900 |
| `derived_at` | DateTime(tz=True) | NO | `—` | — | 901 |
| `rule_version` | String(64) | NO | `—` | — | 902 |

**Indexes:** `ix_memory_evidence_student_derived`(student_id)

**CHECK constraints:** `ck_memory_evidence_source_type`: `source_type IN ('QUIZ','LEARNING_SESSION','CONVERSATION','BOOK_PROGRESS')`; `ck_memory_evidence_count`: `count >= 1`


### `messages`  (models.py:690, `__table_args__` at :694) — class `Message`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `message_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 709 |
| `conversation_id` | UUID | NO | `—` | `conversations.conversation_id` (RESTRICT) | 712 |
| `role` | String(16) | NO | `—` | — | 716 |
| `type` | String(32) | NO | `—` | — | 717 |
| `content` | TEXT | NO | `—` | — | 718 |
| `metadata` | JSONB | NO | `'{}'::jsonb` | — | — |
| `sequence` | INTEGER | NO | `—` | — | 722 |
| `model_info` | JSONB | YES | `—` | — | 723 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 724 |

**Indexes:** (only the primary key)

**Unique constraints:** `uq_messages_conversation_sequence`(conversation_id, sequence)

**CHECK constraints:** `ck_messages_role`: `role IN ('STUDENT','TEACHER','SYSTEM')`; `ck_messages_type`: `type IN ('TEXT','QUIZ','TOOL_STATUS','HINT','RECOMMENDATION','SYSTEM','LEARNING_SUMMARY')`


### `profile_insights`  (models.py:954, `__table_args__` at :958) — class `ProfileInsight`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `insight_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 983 |
| `student_id` | UUID | NO | `—` | `student_profiles.student_id` (RESTRICT) | 986 |
| `insight_type` | String(24) | NO | `—` | — | 990 |
| `dimension` | String(64) | NO | `—` | — | 991 |
| `level` | String(8) | NO | `—` | — | 992 |
| `description` | TEXT | NO | `—` | — | 993 |
| `evidence_ids` | JSONB | NO | `'[]'::jsonb` | — | 994 |
| `status` | String(16) | NO | `'ACTIVE'` | — | 997 |
| `valid_from` | DateTime(tz=True) | NO | `—` | — | 998 |
| `valid_until` | DateTime(tz=True) | YES | `—` | — | 999 |
| `rule_version` | String(64) | NO | `—` | — | 1000 |
| `model_info` | JSONB | YES | `—` | — | 1001 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 1002 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 1005 |

**Indexes:** `ix_profile_insights_student_status_valid`(student_id, status)

**CHECK constraints:** `ck_profile_insights_status`: `status IN ('ACTIVE','SUPERSEDED')`; `ck_profile_insights_level`: `level IN ('偏弱','一般','较稳定','较强','仍需观察')`; `ck_profile_insights_type`: `insight_type IN ('STRENGTH','WEAKNESS','UNDERSTANDING','HABIT','CHANGE','INTEREST')`; `ck_profile_insights_valid_range`: `valid_until IS NULL OR valid_until >= valid_from`


### `quiz_answers`  (models.py:1179, `__table_args__` at :1183) — class `QuizAnswer`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `answer_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 1202 |
| `quiz_session_id` | UUID | NO | `—` | `quiz_sessions.quiz_session_id` (RESTRICT) | 1205 |
| `question_id` | UUID | NO | `—` | `quiz_questions.question_id` (RESTRICT) | 1209 |
| `student_id` | UUID | NO | `—` | `student_profiles.student_id` (RESTRICT) | 1213 |
| `submitted_answer` | JSONB | NO | `—` | — | 1217 |
| `is_correct` | BOOLEAN | NO | `—` | — | 1218 |
| `attempt_no` | INTEGER | NO | `—` | — | 1219 |
| `hint_level_at_submit` | INTEGER | NO | `0` | — | 1220 |
| `is_final` | BOOLEAN | NO | `false` | — | 1223 |
| `submitted_at` | DateTime(tz=True) | NO | `—` | — | 1226 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 1227 |

**Indexes:** `ix_quiz_answers_session_question_created`(quiz_session_id, question_id, created_at)

**Unique constraints:** `uq_quiz_answers_attempt`(quiz_session_id, question_id, attempt_no)

**CHECK constraints:** `ck_quiz_answers_attempt_no`: `attempt_no >= 1`; `ck_quiz_answers_hint_level`: `hint_level_at_submit >= 0`


### `quiz_interactions`  (models.py:1232, `__table_args__` at :1236) — class `QuizInteraction`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `interaction_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 1255 |
| `quiz_session_id` | UUID | NO | `—` | `quiz_sessions.quiz_session_id` (RESTRICT) | 1258 |
| `question_id` | UUID | YES | `—` | `quiz_questions.question_id` (RESTRICT) | 1262 |
| `interaction_type` | String(24) | NO | `—` | — | 1266 |
| `payload` | JSONB | NO | `—` | — | 1267 |
| `message_id` | UUID | YES | `—` | `messages.message_id` (RESTRICT) | 1268 |
| `answer_id` | UUID | YES | `—` | `quiz_answers.answer_id` (RESTRICT) | 1272 |
| `sequence` | INTEGER | NO | `—` | — | 1276 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 1277 |

**Indexes:** `ix_quiz_interactions_session_question_created`(quiz_session_id, question_id, created_at); `ix_quiz_interactions_answer`(answer_id); `ix_quiz_interactions_message`(message_id)

**Unique constraints:** `uq_quiz_interactions_session_sequence`(quiz_session_id, sequence)

**CHECK constraints:** `ck_quiz_interactions_type`: `interaction_type IN ('HINT_REQUEST','HINT_RESPONSE','QUESTION_ASK','TEACHER_REPLY','ANSWER_SUBMIT','ANSWER_RESULT')`


### `quiz_questions`  (models.py:1094, `__table_args__` at :1098) — class `QuizQuestion`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `question_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 1108 |
| `quiz_session_id` | UUID | NO | `—` | `quiz_sessions.quiz_session_id` (RESTRICT) | 1111 |
| `question_order` | INTEGER | NO | `—` | — | 1115 |
| `question_type` | String(24) | NO | `—` | — | 1116 |
| `stem` | TEXT | NO | `—` | — | 1117 |
| `options` | JSONB | NO | `—` | — | 1118 |
| `correct_answer` | JSONB | NO | `—` | — | 1119 |
| `explanation` | TEXT | NO | `—` | — | 1120 |
| `source_context` | JSONB | YES | `—` | — | 1121 |
| `interaction_policy` | JSONB | NO | `'{"allow_hint": true, "max_hint_level": 3}'::jsonb` | — | 1122 |
| `knowledge_point_ids` | JSONB | NO | `'[]'::jsonb` | — | 1128 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 1131 |

**Indexes:** (only the primary key)

**Unique constraints:** `uq_quiz_questions_session_order`(quiz_session_id, question_order)

**CHECK constraints:** `ck_quiz_questions_type`: `question_type IN ('SINGLE_CHOICE','MULTIPLE_CHOICE','TRUE_FALSE','FILL_BLANK')`


### `quiz_sessions`  (models.py:1010, `__table_args__` at :1014) — class `QuizSession`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `quiz_session_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 1040 |
| `student_id` | UUID | NO | `—` | `student_profiles.student_id` (RESTRICT) | 1043 |
| `conversation_id` | UUID | NO | `—` | `conversations.conversation_id` (RESTRICT) | 1047 |
| `teacher_role_id` | UUID | YES | `—` | `teacher_roles.role_id` (RESTRICT) | 1052 |
| `book_id` | UUID | YES | `—` | `books.book_id` (RESTRICT) | 1056 |
| `chapter_id` | UUID | YES | `—` | `chapters.chapter_id` (RESTRICT) | 1059 |
| `source_quiz_session_id` | UUID | YES | `—` | `quiz_sessions.quiz_session_id` (SET NULL) | 1064 |
| `source_question_id` | UUID | YES | `—` | `quiz_questions.question_id` (SET NULL) | 1068 |
| `title` | String(255) | NO | `—` | — | 1072 |
| `quiz_kind` | String(16) | NO | `—` | — | 1073 |
| `status` | String(16) | NO | `'GENERATING'` | — | 1074 |
| `questions_snapshot` | JSONB | NO | `—` | — | 1077 |
| `result_summary` | JSONB | YES | `—` | — | 1078 |
| `duration_seconds` | INTEGER | NO | `0` | — | 1079 |
| `ai_feedback` | TEXT | YES | `—` | — | 1082 |
| `model_info` | JSONB | NO | `—` | — | 1083 |
| `skill_version` | String(64) | NO | `—` | — | 1084 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 1085 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 1088 |
| `completed_at` | DateTime(tz=True) | YES | `—` | — | 1091 |

**Indexes:** `ix_quiz_sessions_book_chapter`(book_id, chapter_id); `ix_quiz_sessions_conversation`(conversation_id); `ix_quiz_sessions_source_quiz`(source_quiz_session_id); `ix_quiz_sessions_student_created`(student_id)

**CHECK constraints:** `ck_quiz_sessions_duration`: `duration_seconds >= 0`; `ck_quiz_sessions_status`: `status IN ('GENERATING','ACTIVE','COMPLETED','ABANDONED')`; `ck_quiz_sessions_completed_after_created`: `completed_at IS NULL OR completed_at >= created_at`; `ck_quiz_sessions_kind`: `quiz_kind IN ('CHAPTER_QUIZ','AI_QUIZ')`


### `reading_settlements`  (models.py:559) — class `ReadingSettlement`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `session_id` **[PK]** | UUID | NO | `—` | `learning_sessions.session_id` (RESTRICT) | 568 |
| `student_id` | UUID | NO | `—` | `student_profiles.student_id` (RESTRICT) | 573 |
| `book_id` | UUID | NO | `—` | `books.book_id` (RESTRICT) | 577 |
| `settled_seconds` | INTEGER | NO | `—` | — | 580 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 581 |

**Indexes:** (only the primary key)


### `recommendations`  (models.py:586, `__table_args__` at :590) — class `Recommendation`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `recommendation_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 603 |
| `student_id` | UUID | NO | `—` | `student_profiles.student_id` (RESTRICT) | 606 |
| `recommendation_type` | String(32) | NO | `—` | — | 610 |
| `title` | String(255) | NO | `—` | — | 611 |
| `description` | TEXT | NO | `—` | — | 612 |
| `reason` | TEXT | NO | `—` | — | 613 |
| `evidence_ids` | JSONB | NO | `'[]'::jsonb` | — | 614 |
| `related_book_id` | UUID | YES | `—` | `books.book_id` (SET NULL) | 617 |
| `source_ids` | JSONB | NO | `'[]'::jsonb` | — | 622 |
| `license` | String(128) | YES | `—` | — | 625 |
| `source_url` | String(512) | YES | `—` | — | 626 |
| `model_info` | JSONB | YES | `—` | — | 627 |
| `skill_version` | String(64) | YES | `—` | — | 628 |
| `expires_at` | DateTime(tz=True) | YES | `—` | — | 629 |
| `status` | String(16) | NO | `'ACTIVE'` | — | 630 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 631 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 634 |

**Indexes:** `ix_recommendations_student_status_created`(student_id, status)

**CHECK constraints:** `ck_recommendations_status`: `status IN ('ACTIVE','DISMISSED','EXPIRED')`


### `reviewed_questions`  (models.py:1136, `__table_args__` at :1145) — class `ReviewedQuestion`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `question_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 1158 |
| `stable_key` | String(128) | NO | `—` | — | 1161 |
| `chapter_id` | UUID | YES | `—` | `chapters.chapter_id` (SET NULL) | 1162 |
| `grade_min` | INTEGER | NO | `—` | — | 1165 |
| `grade_max` | INTEGER | NO | `—` | — | 1166 |
| `revision` | INTEGER | NO | `1` | — | 1167 |
| `payload` | JSONB | NO | `—` | — | 1168 |
| `review_status` | String(16) | NO | `'PENDING'` | — | 1169 |
| `reviewed_at` | DateTime(tz=True) | YES | `—` | — | 1170 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 1171 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 1174 |

**Indexes:** `ix_reviewed_questions_chapter_grade`(chapter_id)

**Unique constraints:** `uq_reviewed_questions_stable_key`(stable_key)

**CHECK constraints:** `ck_reviewed_questions_grade_range`: `grade_max >= grade_min`; `ck_reviewed_questions_status`: `review_status IN ('DRAFT','PENDING','APPROVED','REJECTED')`; `ck_reviewed_questions_grade_min`: `grade_min >= 1`


### `student_episodes`  (models.py:905, `__table_args__` at :909) — class `StudentEpisode`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `episode_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 921 |
| `student_id` | UUID | NO | `—` | `student_profiles.student_id` (RESTRICT) | 924 |
| `title` | String(255) | NO | `—` | — | 928 |
| `summary` | TEXT | NO | `—` | — | 929 |
| `occurred_at` | DateTime(tz=True) | NO | `—` | — | 930 |
| `event_ids` | JSONB | NO | `'[]'::jsonb` | — | 931 |
| `book_id` | UUID | YES | `—` | `books.book_id` (RESTRICT) | 934 |
| `chapter_id` | UUID | YES | `—` | `chapters.chapter_id` (RESTRICT) | 937 |
| `knowledge_point_ids` | JSONB | NO | `'[]'::jsonb` | — | 941 |
| `embedding` | VECTOR (no dim) | YES | `—` | — | 946 |
| `importance` | String(8) | NO | `—` | — | 947 |
| `tags` | JSONB | NO | `'[]'::jsonb` | — | 948 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 949 |

**Indexes:** `ix_student_episodes_student_occurred`(student_id)

**CHECK constraints:** `ck_student_episodes_importance`: `importance IN ('LOW','MEDIUM','HIGH')`


### `student_memories`  (models.py:767, `__table_args__` at :771) — class `StudentMemory`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `memory_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 792 |
| `student_id` | UUID | NO | `—` | `student_profiles.student_id` (RESTRICT) | 795 |
| `memory_type` | String(16) | NO | `—` | — | 799 |
| `content` | TEXT | NO | `—` | — | 800 |
| `tags` | JSONB | NO | `'[]'::jsonb` | — | 801 |
| `confidence` | String(8) | NO | `—` | — | 802 |
| `status` | String(16) | NO | `'ACTIVE'` | — | 803 |
| `evidence_ids` | JSONB | NO | `'[]'::jsonb` | — | 804 |
| `origin_candidate_id` | UUID | YES | `—` | `memory_candidates.candidate_id` (SET NULL) | 807 |
| `user_confirmed` | BOOLEAN | NO | `false` | — | 811 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 814 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 817 |
| `confirmed_at` | DateTime(tz=True) | YES | `—` | — | 820 |

**Indexes:** `ix_student_memories_student_status`(student_id, status); `ix_student_memories_student_updated`(student_id)

**CHECK constraints:** `ck_student_memories_type`: `memory_type IN ('PROFILE','PREFERENCE','LEARNING','EPISODIC')`; `ck_student_memories_status`: `status IN ('ACTIVE','DISPUTED','SUPERSEDED','REMOVED')`; `ck_student_memories_confidence`: `confidence IN ('LOW','MEDIUM','HIGH')`


### `student_preferences`  (models.py:167, `__table_args__` at :171) — class `StudentPreference`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `preference_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 190 |
| `student_id` | UUID | NO | `—` | `student_profiles.student_id` (CASCADE) | 193 |
| `preferred_explanation_style` | String(32) | NO | `—` | — | 198 |
| `preferred_difficulty` | String(16) | NO | `—` | — | 199 |
| `preferred_session_length` | String(16) | NO | `—` | — | 200 |
| `voice_preference` | JSONB | NO | `'{}'::jsonb` | — | 201 |
| `active_questioning_enabled` | BOOLEAN | NO | `true` | — | 204 |
| `daily_learning_minutes` | INTEGER | NO | `30` | — | 207 |
| `evidence_ids` | JSONB | NO | `'[]'::jsonb` | — | 210 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 213 |

**Indexes:** (only the primary key)

**Unique constraints:** (column-level UNIQUE, unnamed)(student_id)

**CHECK constraints:** `ck_student_preferences_session_length`: `preferred_session_length IN ('SHORT','MEDIUM','LONG')`; `ck_student_preferences_difficulty`: `preferred_difficulty IN ('EASY','MEDIUM','HARD')`; `ck_student_preferences_daily_minutes`: `daily_learning_minutes >= 0`; `ck_student_preferences_explanation_style`: `preferred_explanation_style IN ('EXAMPLE_BASED','VISUAL','STORY','DIRECT_DEFINITION','STEP_BY_STEP','CODE','INTERACTIVE')`


### `student_profiles`  (models.py:114, `__table_args__` at :118) — class `StudentProfile`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `student_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 131 |
| `user_id` | UUID | NO | `—` | `users.user_id` (CASCADE) | 134 |
| `nickname` | String(32) | NO | `—` | — | 139 |
| `avatar_url` | String(512) | YES | `—` | — | 140 |
| `grade` | INTEGER | NO | `—` | — | 141 |
| `birth_date` | DATE | YES | `—` | — | 142 |
| `language` | String(16) | NO | `'zh-CN'` | — | 143 |
| `learning_goal` | TEXT | YES | `—` | — | 144 |
| `current_teacher_role_id` | UUID | YES | `—` | `teacher_roles.role_id` (SET NULL) | 146 |
| `learning_days` | INTEGER | NO | `0` | — | 150 |
| `total_learning_minutes` | INTEGER | NO | `0` | — | 151 |
| `total_learning_seconds` | INTEGER | NO | `0` | — | 153 |
| `completed_books` | INTEGER | NO | `0` | — | 156 |
| `completed_chapters` | INTEGER | NO | `0` | — | 157 |
| `quiz_count` | INTEGER | NO | `0` | — | 158 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 159 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 162 |

**Indexes:** (only the primary key)

**Unique constraints:** (column-level UNIQUE, unnamed)(user_id)

**CHECK constraints:** `ck_student_profiles_grade`: `grade BETWEEN 1 AND 12`; `ck_student_profiles_completed_books`: `completed_books >= 0`; `ck_student_profiles_completed_chapters`: `completed_chapters >= 0`; `ck_student_profiles_total_minutes`: `total_learning_minutes >= 0`; `ck_student_profiles_learning_days`: `learning_days >= 0`; `ck_student_profiles_quiz_count`: `quiz_count >= 0`


### `teacher_roles`  (models.py:81, `__table_args__` at :85) — class `TeacherRole`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `role_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 90 |
| `name` | String(64) | NO | `—` | — | 93 |
| `description` | TEXT | YES | `—` | — | 94 |
| `persona` | JSONB | NO | `—` | — | 95 |
| `tone` | String(128) | NO | `—` | — | 96 |
| `teaching_style` | String(128) | NO | `—` | — | 97 |
| `avatar` | String(512) | YES | `—` | — | 98 |
| `sprite_manifest` | JSONB | NO | `—` | — | 99 |
| `voice_id` | String(128) | YES | `—` | — | 100 |
| `grade_rules` | JSONB | NO | `—` | — | 101 |
| `prompt_profile` | JSONB | YES | `—` | — | 102 |
| `interaction_style` | String(128) | YES | `—` | — | 103 |
| `enabled` | BOOLEAN | NO | `true` | — | 104 |
| `version` | INTEGER | NO | `1` | — | 105 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 106 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 109 |

**Indexes:** (only the primary key)

**Unique constraints:** `uq_teacher_roles_name`(name)

**CHECK constraints:** `ck_teacher_roles_version`: `version >= 1`


### `users`  (models.py:42, `__table_args__` at :46) — class `User`

| Column | Type | Null | Default | FK → target (ON DELETE) | L |
|---|---|---|---|---|---|
| `user_id` **[PK]** | UUID | NO | `gen_random_uuid()` | — | 63 |
| `username` | String(64) | NO | `—` | — | 66 |
| `email` | String(255) | YES | `—` | — | 67 |
| `phone` | String(32) | YES | `—` | — | 68 |
| `password_hash` | String(255) | NO | `—` | — | 69 |
| `user_type` | String(16) | NO | `—` | — | 70 |
| `status` | String(16) | NO | `'ACTIVE'` | — | 71 |
| `last_login_at` | DateTime(tz=True) | YES | `—` | — | 72 |
| `created_at` | DateTime(tz=True) | NO | `now()` | — | 73 |
| `updated_at` | DateTime(tz=True) | NO | `now()` | — | 76 |

**Indexes:** `uq_users_phone`(phone) UNIQUE; `uq_users_email`(email) UNIQUE

**Unique constraints:** (column-level UNIQUE, unnamed)(username)

**CHECK constraints:** `ck_users_user_type`: `user_type IN ('STUDENT','ADMIN')`; `ck_users_status`: `status IN ('ACTIVE','DISABLED')`


## 4. Migration catalog — 23 files on one linear chain

The revision graph was rebuilt **programmatically** from the `revision`/`down_revision` literals in every file, then cross-checked against `alembic history` and `alembic heads` on the live database.

> **VERDICT (CONFIRMED): single linear chain. One root `8468855342d3` (down_revision=None), one head `a7b8c9d0e1f2`. 23/23 revisions reachable, no branch points (>1 child), no orphaned revisions, no dangling `down_revision`, no cycles, no merge revisions. `branch_labels`/`depends_on` are `None` on all 23.**

| # | revision | down_revision | file | docstring | DDL operations emitted (chain order) | downgrade |
|---|---|---|---|---|---|---|
| 1 | `8468855342d3` | `<base>` | `8468855342d3_create_users_student_profiles_student_.py` | create users student_profiles student_preferences | `CREATE TABLE users`; `CREATE UNIQUE INDEX uq_users_email`; `CREATE UNIQUE INDEX uq_users_phone`; `CREATE TABLE student_profiles`; `CREATE TABLE student_preferences` | implemented |
| 2 | `b6e5c24af284` | `8468855342d3` | `b6e5c24af284_create_books_chapters_content_blocks_.py` | create books chapters content_blocks knowledge_points | `CREATE TABLE books`; `CREATE INDEX ix_books_grade_min_max`; `CREATE TABLE knowledge_points`; `CREATE TABLE chapters`; `CREATE TABLE content_blocks` | implemented |
| 3 | `52cd66eb864b` | `b6e5c24af284` | `52cd66eb864b_create_learning_sessions_learning_.py` | create learning_sessions learning_events book_progress | `CREATE TABLE learning_sessions`; `CREATE INDEX ix_learning_sessions_student_started`; `CREATE UNIQUE INDEX uq_learning_sessions_one_active`; `CREATE TABLE book_progress`; `CREATE TABLE learning_events`; `CREATE INDEX ix_learning_events_session`; `CREATE INDEX ix_learning_events_student_occurred`; `CREATE INDEX ix_learning_events_student_type` | implemented |
| 4 | `a3f1c2e4b5d6` | `52cd66eb864b` | `a3f1c2e4b5d6_align_learning_progress_indexes.py` | align learning progress index directions and coverage | `DROP INDEX ix_learning_sessions_student_started`; `CREATE INDEX ix_learning_sessions_student_started`; `DROP INDEX ix_learning_events_student_occurred`; `CREATE INDEX ix_learning_events_student_occurred`; `CREATE INDEX ix_learning_events_quiz_session`; `CREATE INDEX ix_learning_events_conversation` | implemented |
| 5 | `c4d5e6f7a8b9` | `a3f1c2e4b5d6` | `c4d5e6f7a8b9_create_conversations_messages_summaries.py` | create conversations, messages, and conversation_summaries | `CREATE TABLE conversations`; `CREATE INDEX ix_conversations_student_updated`; `CREATE INDEX ix_conversations_teacher_role`; `CREATE TABLE messages`; `CREATE TABLE conversation_summaries` | implemented |
| 6 | `d5e6f7a8b9c0` | `c4d5e6f7a8b9` | `d5e6f7a8b9c0_create_memory_domain.py` | create student memories, memory candidates, and memory evidence | `CREATE TABLE memory_candidates`; `CREATE INDEX ix_memory_candidates_student_status`; `CREATE INDEX ix_memory_candidates_status_created`; `CREATE TABLE student_memories`; `CREATE INDEX ix_student_memories_student_status`; `CREATE INDEX ix_student_memories_student_updated`; `CREATE TABLE memory_evidence`; `CREATE INDEX ix_memory_evidence_student_derived` | implemented |
| 7 | `e7f8a9b0c1d2` | `d5e6f7a8b9c0` | `e7f8a9b0c1d2_create_quiz_domain.py` | create quiz sessions, questions, answers, and interactions | `CREATE TABLE quiz_sessions`; `CREATE INDEX ix_quiz_sessions_student_created`; `CREATE INDEX ix_quiz_sessions_conversation`; `CREATE INDEX ix_quiz_sessions_book_chapter`; `CREATE TABLE quiz_questions`; `CREATE TABLE quiz_answers`; `CREATE INDEX ix_quiz_answers_session_question_created`; `CREATE TABLE quiz_interactions`; `CREATE INDEX ix_quiz_interactions_session_question_created`; `CREATE INDEX ix_quiz_interactions_message`; `CREATE INDEX ix_quiz_interactions_answer` | implemented |
| 8 | `f0e1d2c3b4a5` | `e7f8a9b0c1d2` | `f0e1d2c3b4a5_create_episodes_and_insights.py` | create student episodes and profile insights | `CREATE EXTENSION IF`; `CREATE TABLE student_episodes`; `CREATE INDEX ix_student_episodes_student_occurred`; `CREATE TABLE profile_insights`; `CREATE INDEX ix_profile_insights_student_status_valid` | implemented |
| 9 | `a2b3c4d5e6f7` | `f0e1d2c3b4a5` | `a2b3c4d5e6f7_create_knowledge_domain.py` | create knowledge resources and chunks with pgvector HNSW indexes | `CREATE TABLE knowledge_resources`; `CREATE INDEX ix_knowledge_resources_status_created`; `CREATE INDEX ix_knowledge_resources_uploaded_by`; `CREATE TABLE knowledge_chunks`; `CREATE INDEX ix_knowledge_chunks_embedding_hnsw`; `ALTER TABLE student_episodes`; `CREATE INDEX ix_student_episodes_embedding_hnsw` | implemented |
| 10 | `a1b2c3d4e5f6` | `a2b3c4d5e6f7` | `a1b2c3d4e5f6_create_admin_domain.py` | create admins and idempotency keys, backfill deferred FKs | `CREATE TABLE admins`; `CREATE TABLE idempotency_keys`; `CREATE INDEX ix_idempotency_keys_actor_expires`; `INSERT INTO admins`; `UPDATE books`; `UPDATE knowledge_resources`; `ALTER TABLE books`; `ALTER TABLE knowledge_resources` | implemented |
| 11 | `b1c2d3e4f5a6` | `a1b2c3d4e5f6` | `b1c2d3e4f5a6_create_teacher_roles.py` | create teacher_roles and backfill deferred FKs | `CREATE TABLE teacher_roles`; `INSERT INTO teacher_roles`; `UPDATE student_profiles`×2; `UPDATE conversations`; `UPDATE quiz_sessions`; `ALTER TABLE student_profiles`; `ALTER TABLE conversations`; `ALTER TABLE quiz_sessions` | implemented |
| 12 | `c7d8e9f0a1b2` | `b1c2d3e4f5a6` | `c7d8e9f0a1b2_allow_variable_embedding_dimensions.py` | allow mixed embedding dimensions for provider migration | `DROP INDEX ix_knowledge_chunks_embedding_hnsw`; `DROP INDEX ix_student_episodes_embedding_hnsw`; `ALTER TABLE knowledge_chunks`; `ALTER TABLE student_episodes` | implemented |
| 13 | `d6e7f8a9b0c1` | `c7d8e9f0a1b2` | `d6e7f8a9b0c1_create_background_jobs.py` | create PostgreSQL-backed background jobs table | `CREATE TABLE background_jobs`; `CREATE INDEX ix_background_jobs_status_created` | implemented |
| 14 | `e8f9a0b1c2d3` | `d6e7f8a9b0c1` | `e8f9a0b1c2d3_create_recommendations.py` | create student recommendations | `CREATE TABLE recommendations`; `CREATE INDEX ix_recommendations_student_status_created` | implemented |
| 15 | `b2c3d4e5f6a7` | `e8f9a0b1c2d3` | `b2c3d4e5f6a7_rename_teacher_roles_to_styles.py` | rename teacher roles to style names | `UPDATE teacher_roles`×2 | implemented |
| 16 | `c3d4e5f6a7b8` | `b2c3d4e5f6a7` | `c3d4e5f6a7b8_phase3_stats_settlements.py` | Phase 3: 阅读结算台账 + 学生统计秒数字段 + VOICE_SESSION_ENDED 事件类型 | `CREATE TABLE reading_settlements`; `ALTER TABLE student_profiles`; `UPDATE student_profiles`; `ALTER TABLE learning_events`×2 | implemented |
| 17 | `d4e5f6a7b8c9` | `c3d4e5f6a7b8` | `d4e5f6a7b8c9_phase5a_settlement_fk.py` | Phase 5-B-I：补齐 reading_settlements.session_id → learning_sessions 外键 | `ALTER TABLE reading_settlements` | implemented |
| 18 | `f1a2b3c4d5e6` | `d4e5f6a7b8c9` | `f1a2b3c4d5e6_add_recommendation_d9_fields.py` | add recommendation D9 traceability fields and EXPIRED status | `ALTER TABLE recommendations`×8 | implemented |
| 19 | `b2c3d4e6f789` | `f1a2b3c4d5e6` | `b2c3d4e6f789_add_next_attempt_at_to_background_jobs.py` | add next_attempt_at to background_jobs for retry backoff | `ALTER TABLE background_jobs` | implemented |
| 20 | `a4b5c6d7e8f9` | `b2c3d4e6f789` | `a4b5c6d7e8f9_add_chapter_completions.py` | add chapter_completions fact table (T13) | `CREATE TABLE chapter_completions`; `CREATE INDEX ix_chapter_completions_student_book`; `CREATE UNIQUE INDEX uq_chapter_completion_student_chapter`; `ALTER TABLE chapter_completions` | implemented |
| 21 | `a5b6c7d8e9f1` | `a4b5c6d7e8f9` | `a5b6c7d8e9f1_add_quiz_source_and_review_event.py` | Add T16 source FKs to quiz_sessions and QUIZ_REVIEW_COMPLETED event type. | `ALTER TABLE quiz_sessions`×4; `CREATE INDEX ix_quiz_sessions_source_quiz`; `ALTER TABLE learning_events`×2 | implemented |
| 22 | `a6b7c8d9e0f1` | `a5b6c7d8e9f1` | `a6b7c8d9e0f1_add_summary_covered_count.py` | Add message_covered_count to conversation_summaries (T20 20a). | `ALTER TABLE conversation_summaries` | implemented |
| 23 | `a7b8c9d0e1f2` | `a6b7c8d9e0f1` | `a7b8c9d0e1f2_add_reviewed_questions.py` | Add reviewed_questions table (T22b). | `CREATE TABLE reviewed_questions`; `CREATE INDEX ix_reviewed_questions_chapter_grade` | implemented |

### Untracked migrations (git status: `??`) — all 4 reachable and all 4 match the models

| revision | position in chain | git | content | drift vs model |
|---|---|---|---|---|
| `a4b5c6d7e8f9` | 20 of 23 | **UNTRACKED** | `CREATE TABLE chapter_completions` (7 cols, 3 FKs RESTRICT, 2 indexes, 1 CHECK) | **1 drift item** — see §5.2 |
| `a5b6c7d8e9f1` | 21 of 23 | **UNTRACKED** | `ADD COLUMN` `quiz_sessions.source_quiz_session_id` + `source_question_id`; 2 FKs (SET NULL); `CREATE INDEX ix_quiz_sessions_source_quiz`; drop+recreate `ck_learning_events_type` to admit `QUIZ_REVIEW_COMPLETED` | none |
| `a6b7c8d9e0f1` | 22 of 23 | **UNTRACKED** | `ADD COLUMN conversation_summaries.message_covered_count INTEGER NOT NULL DEFAULT 0` | none |
| `a7b8c9d0e1f2` | 23 of 23 (**head**) | **UNTRACKED** | `CREATE TABLE reviewed_questions` (11 cols, 1 FK SET NULL, 1 unique, 3 CHECKs, 1 index) | none |

All four are **additive and contain no data backfill and no destructive `UPDATE`**. `a6b7c8d9e0f1` adds a `NOT NULL DEFAULT 0` column, which is safe on a populated table (Postgres 11+ fills the default without a rewrite); `a7b8c9d0e1f2` and `a4b5c6d7e8f9` are `CREATE TABLE` only. The one exception to "strictly additive" is `a5b6c7d8e9f1`, which also drops and recreates the pre-existing `ck_learning_events_type` CHECK on `learning_events` (`:82-87`) — see §5.5.


## 5. Drift analysis — ORM models ↔ migrations ↔ live database

### 3.1 The three-way reconciliation

Every schema fact was checked in all three artifacts. The table below states the method and the result.

| # | Check | Method | Result | Verdict |
|---|---|---|---|---|
| D1 | Tables in models but never migrated | set(models) − set(migration DDL) | **∅** | CONFIRMED clean |
| D2 | Tables in migrations but with no ORM model | set(migration DDL) − set(models) | **∅** (only `alembic_version`, which is Alembic's bookkeeping table and correctly unmapped) | CONFIRMED clean |
| D3 | Tables in the live DB but not in models | `information_schema.tables` − models | **∅** | CONFIRMED clean |
| D4 | Columns in models with no migration/DB column | column-set diff per table | **∅ (0 of 368)** | CONFIRMED clean |
| D5 | Legacy columns in migrations/DB dropped from models | column-set diff per table | **∅** | CONFIRMED clean |
| D6 | Type mismatches (e.g. model `Integer` vs migration `String`) | normalised SQLAlchemy type object vs `information_schema.data_type`+`udt_name`+`character_maximum_length`, plus `DateTime.timezone` and `Vector.dim` read off the type objects themselves | **∅ (0 of 368)** | CONFIRMED clean |
| D7 | Nullability mismatches | `Mapped[X \| None]` / `nullable=` vs `is_nullable` | **∅ (0 of 368)** | CONFIRMED clean |
| D8 | Server-default mismatches | `server_default` vs `column_default` (cast suffixes + quoting normalised) | **∅** | CONFIRMED clean |
| D9 | FK target or `ondelete` mismatches | 58 model FKs vs 58 DB FKs compared as `(column, target, ondelete)` triples | **∅ in both directions** | CONFIRMED clean |
| D10 | Missing UNIQUE in either direction | model `UniqueConstraint` column-sets vs DB unique constraints **and** unique indexes | **1 item** — `chapter_completions` (see D16) | see D16 |
| D11 | Missing indexes in either direction | 34 model `Index` objects vs 85 DB indexes (`pg_indexes`) | **all 34 model indexes exist in the DB; every migration-created index exists in the DB** | CONFIRMED clean |
| D12 | CHECK constraints | 68 named CHECKs in migration DDL vs 68 in `pg_constraint` | **identical name sets, zero symmetric difference** | CONFIRMED clean |
| D13 | Tables created from base with no drops | parse `CREATE TABLE` / `DROP TABLE` over the full offline chain | **33 created, 0 dropped** | CONFIRMED clean |
| D14 | Final table set from migrations vs live DB | set comparison | **identical (33 = 32 app + `alembic_version`)** | CONFIRMED clean |
| D15 | Per-table column set after replaying all `ALTER TABLE … ADD/DROP COLUMN` vs live DB | full chain replay vs `db.json` | **every table matches exactly** | CONFIRMED clean |
| D16 | Alembic's own autogenerate diff | `compare_metadata(MigrationContext, Base.metadata)` against live DB | **2 entries = 1 discrepancy** | **REAL (benign)** |

### 3.2 The one real drift item (D16 / D10)

| item | model | migration | live DB | verdict |
|---|---|---|---|---|
| `chapter_completions` unique on `(student_id, chapter_id)` | `models.py:527-529` → `UniqueConstraint("student_id","chapter_id", name="uq_chapter_completion_student_chapter")` | `a4b5c6d7e8f9_add_chapter_completions.py:40-45` → `op.create_index("uq_chapter_completion_student_chapter", "chapter_completions", ["student_id","chapter_id"], unique=True)` | `CREATE UNIQUE INDEX uq_chapter_completion_student_chapter ON chapter_completions USING btree (student_id, chapter_id)` — a **unique index**, not a constraint | **DRIFT — representation only, benign (CONFIRMED)** |

**Impact:** uniqueness is enforced identically, so no data-integrity consequence. The practical cost is autogenerate churn: `alembic revision --autogenerate` will forever emit a paired `remove_index` + `add_constraint`, and blindly applying it would drop and recreate the object on a live table. Fixing it means either declaring an `Index(..., unique=True)` in `models.py` or changing the migration to `op.create_unique_constraint`.

### 3.3 Things that *look* like drift but are not (documented so they are not re-reported)

These were initially flagged by naive text diffing and then **disproved** by reading the actual objects. Recording them prevents a future auditor from re-raising them:

1. **"MODEL-ONLY index" on `ix_conversations_student_updated`, `ix_learning_events_student_occurred`, `ix_learning_sessions_student_started`, `ix_memory_evidence_student_derived`, `ix_profile_insights_student_status_valid`** — false positive. These models declare 2-column indexes whose second column is a SQL expression, e.g. `models.py:383-387`:
   ```python
   Index("ix_learning_sessions_student_started", "student_id", text("started_at DESC"))
   ```
   A text-diff parser sees only `student_id`; the DB correctly has `(student_id, started_at DESC)`. **No drift.**
2. **"DB-ONLY unique" on `users_username_key`, `student_profiles_user_id_key`, `student_preferences_student_id_key`, `knowledge_points_slug_key`** — these come from **column-level** `unique=True` (`models.py:66`, `:137`, `:196`, `:346`), which SQLAlchemy renders as an inline `UNIQUE` that PostgreSQL names `<table>_<column>_key`. They are represented in the model as unnamed `UniqueConstraint`s. **No drift.**
3. **"DB-ONLY index" on every `*_pkey` and `uq_*`** — primary keys and `UniqueConstraint` objects are not `Index` objects in SQLAlchemy, so they never appear in `Table.indexes`. **No drift.**
4. **`ix_learning_sessions_student_started` / `ix_learning_events_student_occurred` appear as "dropped"** in the offline chain — correct and intentional: `a3f1c2e4b5d6:22-35` drops them and recreates them with `DESC` ordering. Both exist in the live DB with `DESC`. **No drift.**
5. **All 74 `DateTime` columns "mismatching"** — an artifact of `str(DateTime())` hiding the `timezone` flag. Read off the type objects, **all 74 model columns are `timezone=True`** and all 74 DB columns are `timestamptz`. **No drift.**

### 3.4 Two autogenerate blind spots worth knowing (CONFIRMED)

`compare_metadata()` emitted two SQLAlchemy warnings that constrain how much the clean autogenerate result can be trusted, and both were therefore backstopped by the manual `information_schema` comparison above:

1. **`SAWarning: Did not recognize type 'vector' of column 'embedding'`** — the sync `psycopg2` connection Alembic uses does not know the `vector` type (it is not registered), so **`compare_type=True` cannot meaningfully compare vector columns**. Their equality was instead verified via `format_type(atttypid, atttypmod)` → both sides are dimension-less `vector`. Anyone running `alembic revision --autogenerate` will see this warning and must not "fix" the vector columns based on it.
2. **`SAWarning: Cannot correctly sort tables; there are unresolvable cycles between tables "quiz_questions, quiz_sessions" … Foreign key constraints involving these tables will not be considered`** — there is a genuine **circular FK** between `quiz_sessions` and `quiz_questions`:
   * `quiz_sessions.source_question_id → quiz_questions.question_id` (`models.py:1068-1071`, `a5b6c7d8e9f1:68-75`)
   * `quiz_questions.quiz_session_id → quiz_sessions.quiz_session_id` (`models.py:1111-1114`)

   **Consequence: autogenerate is blind to FK drift on these two tables.** The manual comparison (§3.1 D9) confirms 0 drift today, but a future FK change on either table will not be detected by autogenerate. It also means `Base.metadata.sorted_tables` / `create_all()` / naive `DROP TABLE` ordering cannot be used on this schema — inserts must be ordered manually (create the session with `source_question_id = NULL`, insert questions, then update).

### 3.5 The 4 untracked migrations — verified reachable and matching

`git status` shows exactly 4 untracked migration files; `git ls-files backend/alembic/versions/` returns **19** tracked files (19 + 4 = 23). All four are **positions 20–23**, i.e. the newest segment, and `a7b8c9d0e1f2` **is the head**.

| revision | chain position | git | upgrade() content | matches models? | downgrade |
|---|---|---|---|---|---|
| `a4b5c6d7e8f9` | 20 / 23 | **UNTRACKED** | `CREATE TABLE chapter_completions` — 7 columns, 3 FKs (all `RESTRICT`), `ix_chapter_completions_student_book`, unique index `uq_chapter_completion_student_chapter`, `ck_chapter_completions_source` | **models match except the unique-index-vs-constraint representation (§3.2)** | drops table + both indexes + check (data loss) |
| `a5b6c7d8e9f1` | 21 / 23 | **UNTRACKED** | `ADD COLUMN quiz_sessions.source_quiz_session_id`, `.source_question_id` (both nullable); 2 FKs `ON DELETE SET NULL`; `CREATE INDEX ix_quiz_sessions_source_quiz`; drop+recreate `ck_learning_events_type` adding `QUIZ_REVIEW_COMPLETED` | **yes — zero drift** | drops both columns (data loss) |
| `a6b7c8d9e0f1` | 22 / 23 | **UNTRACKED** | `ADD COLUMN conversation_summaries.message_covered_count INTEGER NOT NULL DEFAULT 0` | **yes — zero drift** | drops column |
| `a7b8c9d0e1f2` | 23 / 23 — **HEAD** | **UNTRACKED** | `CREATE TABLE reviewed_questions` — 11 columns, 1 FK `SET NULL`, `uq_reviewed_questions_stable_key`, 3 CHECKs, `ix_reviewed_questions_chapter_grade` | **yes — zero drift** | drops table (data loss) |

**All four contain no data backfill and no destructive DML.** Three (`a4b5c6d7e8f9`, `a6b7c8d9e0f1`, `a7b8c9d0e1f2`) are *strictly* additive. `a5b6c7d8e9f1` is additive in effect but **not strictly**: alongside its two new columns it also **drops and recreates** the pre-existing `ck_learning_events_type` CHECK on `learning_events` (`a5b6c7d8e9f1:82-87`) to admit the new `QUIZ_REVIEW_COMPLETED` value — so it mutates a constraint owned by an earlier migration (a name that has now been rewritten twice, first by `c3d4e5f6a7b8`). `a6b7c8d9e0f1` adds `NOT NULL DEFAULT 0`, which is safe on a populated table (PostgreSQL 11+ stores the default without rewriting the heap). **Verdict: CONFIRMED safe and correctly chained; the `a5b6c7d8e9f1` constraint rewrite is the only reason these four are not uniformly "pure additive".**

One documentation defect: `a4b5c6d7e8f9`'s docstring (lines 1-5) and `chapter_completions.source`'s CHECK allow `'LEGACY_EVENT'` and describe a "历史滚动事件回填" (legacy backfill), but **the migration contains no `op.execute` and performs no backfill at all**. The live table has 2 rows. CONFIRMED (documentation ≠ behaviour).

**Operational risk (CONFIRMED):** these 4 files are uncommitted while the live development database is *already stamped at their head*. A `git clean -fd` or a fresh clone would yield a 19-revision chain whose head is `b2c3d4e6f789`, while the live DB claims `a7b8c9d0e1f2` — Alembic would then report the DB as being at an **unknown revision** and every subsequent command would fail until the files are restored. This is the single most urgent housekeeping item in this audit.

---


## 6. Scripts & initialization (item 4)

All ten scripts live in `backend/app/scripts/`. Every one that touches the DB imports `app.infrastructure.database.session.async_session` (or `engine`), i.e. it reads `DATABASE_URL` from `backend/.env`.

### 4.1 Per-script table

| script | lines | what it does | idempotent? | needs DB? | other deps | referenced by |
|---|---:|---|---|---|---|---|
| `seed.py` | 230 | demo accounts + default teacher styles + E2E demo memory | **YES** | **YES** | — | `scripts/ci-e2e.sh:167`; `docs/01-repository-map.md`; `plan.md:45,56` |
| `import_library.py` | 422 | books/chapters/content_blocks/knowledge_points + knowledge docs → DB | **YES** | **YES** | **embedding provider (network)** for `--knowledge`/`--all` | `.github/workflows/ci.yml:53-55`; `scripts/ci.sh:115-123`; `scripts/ci-e2e.sh:154-164`; `plan.md:55,65` |
| `import_assessments.py` | 142 | `data/library/assessments/<slug>/<chapter>.json` → `reviewed_questions` | **YES** (`stable_key`) | **YES** | — | **only tests + docs** — `backend/tests/test_reviewed_assessments.py:114,141`; `docs/08-ai-system.md:302,307`; `docs/01-repository-map.md:118` |
| `ingest_knowledge.py` | 124 | CLI to ingest one file/dir or `--seed` corpus | **YES** | **YES** | **embedding provider (network)** | docs only — `docs/01-repository-map.md:119` (manual) |
| `reindex_embeddings.py` | 166 | re-embed existing resources after an embedding-provider switch (`--dry-run` available) | converges (skips already-correct dim) | **YES** | **embedding provider (network)** | `docs/acceptance/README.md:37` (manual) |
| `rebuild_memory.py` | 104 | recompute Memory Pipeline for a student (`--student`) | not formally; recompute | **YES** | — | `docs/01-repository-map.md:121` (manual) |
| `archive_noncorpus.py` | 112 | soft-archive non-corpus content: books → `ARCHIVED`, resources → `FAILED` | **YES** (`UPDATE … WHERE`) | **YES** | manifest file | `docs/01-repository-map.md:122` (manual, one-off) |
| `preview_data_governance.py` | 106 | **read-only** classification preview before archiving | n/a (read-only) | **YES** | manifest file | `docs/acceptance/README.md:39` (maintenance) |
| `validate_library.py` | 661 | structural validator R1-R? over `data/library/` | n/a (read-only) | **NO — explicitly DB-free** | — | `.github/workflows/ci.yml:53`; `scripts/ci.sh:116`; `scripts/ci-e2e.sh:155`; `plan.md:55,64` |
| `verify_s3.py` | 138 | MinIO/S3 put→get→exists connectivity check | non-destructive | **NO — needs MinIO, not Postgres** | S3/MinIO | `docs/01-repository-map.md:124` (manual) |

### 4.2 Idempotency evidence (CONFIRMED)

* **`seed.py`** — pure select-then-create for every entity: `select(User).where(User.username=="admin")` → create if `None` (`:51-61`); same for the `Admin` row (`:62-75`), for `xiaoming` (`:78-87`), for both `TeacherRole`s by fixed UUID (`:110-177`), and for the E2E `StudentMemory` matched on `content` (`:180-201`). The demo `MemoryEvidence` is only appended when `e2e_memory.evidence_ids` is empty (`:205-222`). **Safe to run repeatedly** — and deliberately so: the docstring says re-running restores the E2E memory that the `FORGET` test path removes (`:32`, `:105`).
* **`import_library.py`** — docstring `:10-11`: primary keys are **deterministic `uuid5`**, so "重复运行天然幂等" (naturally idempotent), then reconciled by "exists → update". Knowledge resources key on **`(source_url, storage_key)`** (`app/modules/knowledge/ingestion.py:225-230`, `storage_key_for()` at `:203-204` derives the key as a SHA-256 prefix of `source_url`). CI asserts exactly this: `plan.md:65` — "`import_library --all` 导入 25 本书…重复执行无新增重复数据".
  * ⚠️ **One deliberate destructive step (LIKELY risk):** `import_library.py:293-300` **deletes** content blocks belonging to the book being re-imported when their deterministic ID is no longer present in the source file. It is scoped to the re-imported chapter and to IDs this importer owns, and stale *chapters* are explicitly **kept with a warning** (`:306-308`). Still, re-importing a book after editing its Markdown **will silently drop trailing blocks**.
* **`import_assessments.py`** — upsert by `stable_key` (`:103`), documented at `:7-8`; the test at `tests/test_reviewed_assessments.py:141-142` runs the import **twice** and asserts the count does not double.
* **`ingest_knowledge.py`** — `ensure_admin()` at `:26-40` is a get-or-create; ingestion de-duplicates on `(source_url, storage_key)` inside `ingest_text`.
* **`archive_noncorpus.py`** — docstring says "幂等"; implemented as `UPDATE … SET status=…` guarded by `WHERE`, so re-running is a no-op.

### 4.3 Bootstrap order for a fresh database (CONFIRMED)

Derived from actual FK dependencies and CI's own sequence:

```bash
# 1. infrastructure
docker compose up -d postgres          # pgvector/pgvector:pg18, port 5432

# 2. schema  (MUST precede seed: seed writes teacher_roles/admins/student_profiles)
cd backend && uv run alembic upgrade head       # 23 revisions → a7b8c9d0e1f2

# 3. seed  (demo accounts + default teacher styles; idempotent)
uv run python -m app.scripts.seed

# 4. content  (validate FIRST — it is the gate; import is idempotent)
uv run python -m app.scripts.validate_library --all     # no DB needed; FAIL aborts
uv run python -m app.scripts.import_library --all       # books/chapters/blocks + knowledge

# 5. optional
uv run python -m app.scripts.import_assessments         # reviewed_questions (idempotent)
```

* Steps 1-2-4 are exactly what CI does (`.github/workflows/ci.yml:50` then `:53-55`); step 3 is added by the E2E path (`scripts/ci-e2e.sh:166-167`) and by `scripts/ci.sh:109-123`.
* **Why `seed` after `migrate` and not before:** `seed.py` inserts `TeacherRole`s (`:110-177`), an `Admin` row (`:62-75`) and a `StudentProfile` (`:88-95`) — all tables that only exist after migration.
* **Why `seed` is nonetheless *required* even though a migration already seeds teacher roles:** the migration `b1c2d3e4f5a6:91-125` seeds the two default styles and the `a1b2c3d4e5f6:120-127` backfill creates an `admins` row **only if a user named `admin` already exists** — which on a fresh DB it does not. `seed.py` closes that gap by creating *both* the `admin` user and its `Admin` row itself (`:51-76`), so the `admins` table is correctly populated and `books.created_by` / `knowledge_resources.uploaded_by` can be filled later. **Do not skip `seed`.** (CONFIRMED: live DB has the `admin` user *and* a matching `admins` row.)
* `import_assessments` is **not** wired into any startup/CI path — `docs/08-ai-system.md:307` states this explicitly ("没有被 `scripts/start.sh` / `ci.sh` / `ci-e2e.sh` / `.github/workflows/ci.yml` 中的任何一处调用"). The live DB therefore has only **5** `reviewed_questions`, and a fresh bootstrap will get **0** unless this step is run by hand. Step 5 is genuinely optional but silently absent from automation.

### 4.4 Demo users / students / admin created by `seed.py` (CONFIRMED)

| principal | username | password | source | what else is created |
|---|---|---|---|---|
| Admin | `admin` | **`admin123`** | **hardcoded** at `seed.py:57` | `admins` row: `role_level='SUPERVISOR'`, `display_name='系统管理员'`, `enabled=True` (`seed.py:68-75`) |
| Student | `xiaoming` | **`demo123`** | `seed.py:30` — `os.getenv("SEED_PASSWORD", "demo123")` | `student_profiles` (`nickname='小明'`, `grade=8`, `language='zh-CN'`, `:88-93`), `student_preferences` (`EXAMPLE_BASED`/`MEDIUM`/`SHORT`, `:96-103`), 1 `student_memories` + 1 `memory_evidence` (`:180-222`), and `current_teacher_role_id` → `…0001` (`:178-179`) |
| Teacher styles | *(not users)* | — | `seed.py:110-177` | 2 `teacher_roles` with **fixed UUIDs** `00000000-0000-0000-0000-000000000001` (`温暖鼓励`) and `…0002` (`严谨清晰`) — the same UUIDs the migration `b1c2d3e4f5a6` seeds |

**Security note (CONFIRMED):** `seed.py:36-44` prints a warning that these are local-demo-only credentials, but **both passwords are weak and `admin123` is hardcoded in the source** (`:57`). `ingest_knowledge.py:26-40` **creates the very same `admin`/`admin123` account independently**, so even a "content-only" bootstrap mints a known-password admin. Neither path forces a change. This is acceptable for local dev and unacceptable in any shared/production environment — the module docstring itself says so (`seed.py:38-39`).

**Cosmetic bug (CONFIRMED):** `seed.py:104` prints `"seed: 已创建 xiaoming（密码 {SEED_PASSWORD}，grade 8，昵称 小明）"` — a plain string, **not an f-string**, so it prints the literal text `{SEED_PASSWORD}` instead of the password. The message is also wrong by construction (it should interpolate the variable).

### 4.5 Data-state observation (LIKELY — operational)

The live `users` table holds **190 rows**, but only two are intentional (`admin`, `xiaoming`). The rest are test fixtures left behind by the test suite (`test_student`, `test_quiz_user`, `test_p2_ctx_user`, `test_role_admin`, `test_knowledge_admin`, `recommendation_student_065e49eb73`, `other_conversation_user`, …). Likewise `teacher_roles` holds 4 rows — the 2 seeded defaults plus `风格-p4_conv_5f0fa4` and `风格-p5_sse_6e5729` created by tests. **The tests run against the development database rather than a disposable one**, which is why `scripts/test-db.sh` exists (it operates on an isolated `shuangling_audit` DB and explicitly refuses to restore into `shuangling`, `scripts/test-db.sh:6-8,16,39-42`). Anyone re-running the E2E suite should be aware that the dev DB accumulates fixture rows.

---


## 7. Vector columns & similarity search (item 5)

### 5.1 How `VECTOR` is handled

There is **no `pgvector` Python package** in the dependency set. The type is a hand-rolled minimal `UserDefinedType`, defined inline in the models module:

```python
# app/infrastructure/database/models.py:25-39
class VECTOR(UserDefinedType):
    """Minimal pgvector type binding.  Columns are unbounded ``vector`` (no fixed
    dimension) so embeddings from different providers (64-dim mock, 768/1024-dim
    real) can coexist during re-index.  pgvector requires a fixed dimension for
    indexes, so no vector index is declared here; search filters rows to the
    query dimension (migration c7d8e9f0a1b2)."""
    def __init__(self, dimensions: int | None = None) -> None:
        self.dimensions = dimensions
    def get_col_spec(self, **kw):
        return f"VECTOR({self.dimensions})" if self.dimensions else "VECTOR"
```

* Declared as `VECTOR()` (**no dimension argument**) in exactly two places:
  * `models.py:946` — `StudentEpisode.embedding: Mapped[VECTOR | None]`
  * `models.py:1392` — `KnowledgeChunk.embedding: Mapped[VECTOR | None]`
* Both are **nullable** (`Mapped[... | None]`, no `nullable=False`), and both are nullable in the live DB. CONFIRMED.
* Because there is no `pgvector` package, **SQLAlchemy/Alembic cannot introspect the type** — this is the source of the `SAWarning: Did not recognize type 'vector'` in §5.4. It also means `alembic revision --autogenerate` will never propose a correct type change for these columns.

### 5.2 Where the extension is created — **in a migration, guarded, and correctly ordered** (CONFIRMED)

There is **exactly one** `CREATE EXTENSION` site in the entire repository:

```python
# alembic/versions/f0e1d2c3b4a5_create_episodes_and_insights.py:32
op.execute("CREATE EXTENSION IF NOT EXISTS vector")
```

* It is **guarded** with `IF NOT EXISTS`, and it is the **only** `IF NOT EXISTS` / `DO $$` guard among all raw statements in the 23 migrations.
* **Ordering is correct**: `f0e1d2c3b4a5` is chain position **8**; the first migration that *uses* the `VECTOR` type is `a2b3c4d5e6f7` (position **9**), which creates `knowledge_chunks.embedding VECTOR(64)` and both HNSW indexes. `f0e1d2c3b4a5` itself creates `student_episodes.embedding VECTOR` (offline DDL line 514), which is why the extension is created there rather than in the knowledge-domain migration.
* **No migration ever drops the extension** — not even `f0e1d2c3b4a5`'s own `downgrade()`.
* Live DB confirms: `vector` extension version **0.8.6** is installed. CONFIRMED.
* **Residual environment prerequisite:** `IF NOT EXISTS` guards against re-creation, not against *absence of the package*. On a PostgreSQL image without pgvector installed, this line fails and the whole upgrade aborts. The repo's `docker-compose.yml:3` uses `pgvector/pgvector:pg18`, so it works here; a managed/stock Postgres would not. LIKELY (environment-dependent).

### 5.3 Vector indexes — **there are NONE in the final schema** (CONFIRMED — the headline finding)

| step | migration:line | action |
|---|---|---|
| schema created *with* HNSW | `a2b3c4d5e6f7:161-168` | `op.create_index("ix_knowledge_chunks_embedding_hnsw", "knowledge_chunks", ["embedding"], postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"})` |
| schema created *with* HNSW | `a2b3c4d5e6f7:172-179` | `op.create_index("ix_student_episodes_embedding_hnsw", "student_episodes", ["embedding"], postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"})` |
| **both dropped** | **`c7d8e9f0a1b2:33-34`** | `for index_name, table_name in _EMBEDDING_INDEXES: op.drop_index(index_name, table_name=table_name)` |
| recreated **only on downgrade** | `c7d8e9f0a1b2:69-77` | inside `def downgrade()` — never in `upgrade()` |

In the full offline chain the two HNSW indexes appear at SQL lines **599** and **603** and are dropped at lines **750** and **752** — **no later `CREATE INDEX` restores them.**

Verified against the live database — **zero** ANN indexes exist:

```
$ SELECT indexdef FROM pg_indexes WHERE schemaname='public' AND indexdef ILIKE '%hnsw%' OR indexdef ILIKE '%ivfflat%';
(no rows)

knowledge_chunks indexes:  knowledge_chunks_pkey (btree), uq_knowledge_chunks_resource_index (btree)
student_episodes indexes:  student_episodes_pkey (btree), ix_student_episodes_student_occurred (btree)
```

* **No ivfflat index exists anywhere. No `gin`. No explicit `btree` DDL.** CONFIRMED.
* Note the mismatch between intent and artifact: `alembic history` still labels `a2b3c4d5e6f7` as *"create knowledge resources and chunks **with pgvector HNSW indexes**"*, and `models.py:944-945` explains the absence as deliberate ("不建向量索引（pgvector 索引要求固定维度）"). The removal **is** deliberate — `c7d8e9f0a1b2`'s docstring (`:10-11`) says HNSW was removed because pgvector needs a fixed dimension for vector indexes. So this is a **conscious trade-off, correctly documented** — but its consequence (every RAG query is a full scan) is easy to miss.
* **Dimension history** (there is no `vector(1024)`/`768`/`1536` anywhere in any migration):
  1. `f0e1d2c3b4a5` creates `student_episodes.embedding` as **unbounded `VECTOR`**.
  2. `a2b3c4d5e6f7:169-171` — `ALTER TABLE student_episodes ALTER COLUMN embedding TYPE vector(64)` (unbounded → fixed 64). **Unguarded**; fails if any existing row has ≠64 dims (no rows on a fresh DB, so safe there).
  3. `c7d8e9f0a1b2:36-43` — `ALTER TABLE knowledge_chunks|student_episodes ALTER COLUMN embedding TYPE vector USING embedding::vector` (**fixed → unbounded**). **This is the current state**, confirmed by `format_type()`: both columns report plain `vector` with no typmod, matching the model's `VECTOR()` (dims=None).
* ⚠️ **`c7d8e9f0a1b2`'s `downgrade()` destroys embeddings** (`:50-57`): it runs `UPDATE … SET embedding = NULL WHERE embedding IS NOT NULL AND vector_dims(embedding) <> 64` before narrowing back to `vector(64)`. On the current DB — where the corpus was re-indexed to **real 1024-dim** vectors — rolling back this single revision would **silently NULL every knowledge-chunk and episode embedding in the database**. This is the highest-severity downgrade in the set. CONFIRMED.

### 5.4 How similarity search works **without** an index — the actual query

The search lives in `app/modules/knowledge/service.py:127-202`. It is **raw SQL** (`text(...)`), not a Core/ORM construct, because the pgvector `<=>` operator is not known to SQLAlchemy:

```python
# app/modules/knowledge/service.py:132-170  (abridged; string concatenation preserved)
embedding = get_embedding(request.query)
embedding_value = "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"
embedding_dimension = len(embedding)
...
distance_expression = (
    "CASE WHEN vector_dims(kc.embedding) = :embedding_dimension "
    "THEN kc.embedding <=> CAST(:query_embedding AS vector) END"
)
sql = text(
    "SELECT kc.chunk_id, kc.resource_id, kc.chunk_index, kc.content, "
    "kc.content_type, kc.metadata, kc.knowledge_point_ids, kc.token_count, "
    "kc.status, kc.created_at, "
    f"{distance_expression} AS distance "
    "FROM knowledge_chunks kc "
    "JOIN knowledge_resources kr ON kr.resource_id = kc.resource_id "
    "WHERE kc.status = 'READY' AND kr.status = 'READY' "
    "AND kc.embedding IS NOT NULL "
    "AND vector_dims(kc.embedding) = :embedding_dimension "   # non-sargable filter
    + kp_filter                                                # optional JSONB EXISTS
    + similarity_filter                                        # optional <= max_distance
    + f" ORDER BY {distance_expression} "                      # full sort of all rows
    "LIMIT :limit"
)
result = await session.execute(sql, params)
```

Notes on the mechanism:

* The query embedding is **inlined as a literal string** and cast with `CAST(:query_embedding AS vector)`. Because the column is **unbounded** `vector`, a cast to unbounded `vector` works for any provider dimension — this is precisely why the column dimension was removed in `c7d8e9f0a1b2`.
* `vector_dims(kc.embedding) = :embedding_dimension` is how provider mixing is tolerated: 64-dim mock vectors and 1024-dim real vectors can coexist in one column, and each query only considers rows matching its own dimension. **This predicate is a function call, so it can never use an index** even if one existed.
* If no rows come back, the service falls back to an `ILIKE '%query%'` keyword scan (`:204-231`); when `min_similarity` is unset it additionally compares substring hits and re-sorts in Python (`:175-187`).

**EXPLAIN against the live database (no `ANALYZE`, so nothing was executed) — CONFIRMED sequential scan:**

```
Limit  (cost=205.42..205.43 rows=1)
  ->  Sort  (cost=205.42..205.43 rows=1)
        Sort Key: ((kc.embedding <=> '[0.1,0.2]'::vector))
        ->  Nested Loop  (cost=0.27..205.41 rows=1)
              ->  Seq Scan on public.knowledge_chunks kc  (cost=0.00..167.79 rows=5)
                    Filter: ((kc.embedding IS NOT NULL) AND ((kc.status)::text = 'READY'::text)
                             AND (vector_dims(kc.embedding) = 2))
              ->  Index Scan using knowledge_resources_pkey on public.knowledge_resources kr
                    Index Cond: (kr.resource_id = kc.resource_id)
                    Filter: ((kr.status)::text = 'READY'::text)
```

**Verdict (CONFIRMED): every semantic search performs a full sequential scan of `knowledge_chunks` and then sorts *all* surviving rows by cosine distance — an exact k-NN, `O(N)` per query, in the database, with no ANN acceleration.** At the current size (`knowledge_chunks` = **1153 rows**, `student_episodes` = **248 rows**) this is negligible (sub-millisecond), so it is **not a bug today**. It becomes the dominant cost as the corpus grows, and the migration set gives no path to fix it without a new migration: because the column is now dimension-less, an HNSW/IVFFlat index **cannot** be created on it at all — you would first have to pin the column back to the live dimension (e.g. `vector(1024)`), which re-introduces the provider-mixing problem the current design deliberately solved. **This is a real architectural corner that has been painted into, and it is worth flagging to whoever owns RAG performance.**

---


## 8. Data-integrity risks (item 6)

### 6.1 Nullable columns that the schema/code treats as non-null (CONFIRMED)

| column | model | declared | treated as | risk |
|---|---|---|---|---|
| `conversations.teacher_role_id` | `models.py:667-671` | **NULLABLE** + FK `RESTRICT` | comment says *"0-E 定义为非空，本任务因角色表尚未落地放宽为可空"* — the spec says NOT NULL, the schema relaxes it | Any code reading `conversation.teacher_role_id` without a `None` check can break. The relaxation was a bootstrap workaround; the role table now exists (`b1c2d3e4f5a6`), so the column can be tightened to `NOT NULL` — but nothing has done so. |
| `quiz_sessions.teacher_role_id` | `models.py:1051-1055` | **NULLABLE** | **the comment contradicts the code** | Comment at `:1051` reads *"本列可空且**不建 FK**"* (nullable and **no FK**), yet `:1052-1055` **does** declare `ForeignKey("teacher_roles.role_id", ondelete="RESTRICT")` — and the live DB **has** that FK (`fk_quiz_sessions_teacher_role`). The comment is stale and actively misleading. |
| `learning_events.conversation_id` | `models.py:463-464` | **NULLABLE, NO FK AT ALL** | comment: *"FK→conversations 延迟到 Phase 4 补"* | **The FK was never added.** Verified: `learning_events` has FKs to `books`, `chapters`, `content_blocks`, `learning_sessions`, `student_profiles` — but **not** to `conversations`. |
| `learning_events.quiz_session_id` | `models.py:465-466` | **NULLABLE, NO FK AT ALL** | comment: *"FK→quiz_sessions 延迟到 Phase 6 补"* | **The FK was never added** either. Same verification. |
| `idempotency_keys.actor_id` | `models.py:1457` | **NOT NULL, NO FK** | polymorphic actor (`actor_type IN ('STUDENT','ADMIN')`) | Intentional — a polymorphic FK is not expressible. Documented by the `actor_type` CHECK. |
| `users.email` / `users.phone` | `models.py:67-68` | NULLABLE | login identity | Handled correctly via **partial** unique indexes (`models.py:49-60`: `postgresql_where=text("email IS NOT NULL")`). Live DB matches. **No risk.** |
| `book_progress.chapter_id` / `.block_id` | `models.py:499-505` | NULLABLE | current position cursor | `block_id` is `ON DELETE SET NULL`; readers must tolerate NULL. |
| `student_episodes.book_id` / `.chapter_id` | `models.py:934-940` | NULLABLE | optional context | Fine. |
| `student_profiles.grade` | `models.py:141` | NOT NULL with `CHECK (grade BETWEEN 1 AND 12)` | — | Correctly constrained. |

**Verdict:** the two `learning_events` columns are the real finding — they are **indexed** (`ix_learning_events_conversation`, `ix_learning_events_quiz_session`, both created in `a3f1c2e4b5d6:36-47`) but **unconstrained**, so they can and eventually will hold UUIDs that reference nothing. Every "deferred FK" from the same era *was* backfilled by `a1b2c3d4e5f6` and `b1c2d3e4f5a6` — these two were simply missed. **LIKELY orphan risk, CONFIRMED missing constraint.**

### 6.2 Missing FK indexes — 25 of 58 FK columns have no leading index (CONFIRMED)

Measured directly against `pg_index`/`pg_attribute` on the live DB. Coverage means "the FK column is the **leading** column of some index".

**33 of 58 FK columns are indexed; 25 are not:**

```
book_progress.block_id                book_progress.book_id              book_progress.chapter_id
books.created_by                      chapter_completions.book_id        chapter_completions.chapter_id
knowledge_points.parent_id            learning_events.block_id           learning_events.book_id
learning_events.chapter_id            learning_sessions.book_id          learning_sessions.chapter_id
quiz_answers.question_id              quiz_answers.student_id            quiz_interactions.question_id
quiz_sessions.chapter_id              quiz_sessions.source_question_id   quiz_sessions.teacher_role_id
reading_settlements.book_id           reading_settlements.student_id     recommendations.related_book_id
student_episodes.book_id              student_episodes.chapter_id        student_memories.origin_candidate_id
student_profiles.current_teacher_role_id
```

**Impact (LIKELY — no evidence of current pain at this data volume):**
* Every `DELETE` of a `books`/`chapters`/`student_profiles` row must scan each child table to enforce the `RESTRICT` rule — 43 of the 58 FKs are `RESTRICT`, so this is the dominant deletion path.
* Parent-side joins and "all progress for this book/chapter" queries cannot use an index prefix.
* At current sizes (largest tables ≈ 2 000 rows) this is invisible; it becomes a real cost at scale. The `knowledge_points.parent_id` gap is the most notable, since it is a self-referencing tree (recursive traversal without an index on the parent).

### 6.3 Orphan relationships — JSONB used as a pseudo-table (CONFIRMED)

There is **no `relationship()` anywhere in `models.py`** — associations are held as JSONB arrays of UUID strings, with **no FK, no referential integrity, and no index**. This is the single largest structural integrity gap in the schema.

| JSONB column | model | holds | integrity |
|---|---|---|---|
| `learning_events.knowledge_point_ids` | `models.py:460-462` | `knowledge_points` UUIDs | none |
| `content_blocks.knowledge_point_ids` | `models.py:321-323` | `knowledge_points` UUIDs | none |
| `knowledge_chunks.knowledge_point_ids` | `models.py:1389-1391` | `knowledge_points` UUIDs | none |
| `quiz_questions.knowledge_point_ids` | `models.py:1128-1130` | `knowledge_points` UUIDs | none |
| `student_episodes.knowledge_point_ids` | `models.py:941-943` | `knowledge_points` UUIDs | none |
| `student_episodes.event_ids` | `models.py:931-933` | `learning_events` UUIDs | none |
| `memory_evidence.event_ids` | `models.py:894-896` | `learning_events` UUIDs | none |
| `student_memories.evidence_ids` | `models.py:804-806` | `memory_evidence` UUIDs | none |
| `memory_candidates.evidence_ids` | `models.py:856-858` | `memory_evidence` UUIDs | none |
| `profile_insights.evidence_ids` | `models.py:994-996` | `memory_evidence` UUIDs | none |
| `recommendations.evidence_ids` | `models.py:614-616` | mixed | none |
| `student_preferences.evidence_ids` | `models.py:210-212` | `memory_evidence` UUIDs | none |
| `books.source_ids` / `.tags` | `models.py:247,250` | D9 provenance | none |
| `quiz_sessions.questions_snapshot` | `models.py:1077` | **full question copies** | see below |
| `quiz_questions.options` / `.correct_answer` | `models.py:1118-1119` | structured answer | n/a |
| `reviewed_questions.payload` | `models.py:1168` | full question body | n/a |
| `conversations.recent_messages` | `models.py:678-680` | message copies | denormalised cache |
| `conversations.current_page_context` | `models.py:675-677` | UI state | n/a |
| `knowledge_chunks.metadata` | `models.py:1386-1388` | D9 provenance | n/a |

**Two concrete consequences:**

1. **`quiz_sessions.questions_snapshot` duplicates the `quiz_questions` table.** The live DB has **90 `quiz_sessions` but only 109 `quiz_questions`** — i.e. questions are *also* stored in the JSONB snapshot. `models.py:1141` says this is deliberate ("旧 quiz_sessions 的 questions_snapshot 保存原文，改题后不覆盖旧答卷" — old snapshots must not be overwritten when a question is edited), which is a legitimate audit requirement. But it means **the same question exists in two places with no consistency guarantee**, and `teacher_context.py:160` reads the count from the snapshot while `quiz_bank.py` reads the table. Any code that assumes they agree will eventually be wrong.

2. **The `knowledge_point_ids` arrays are filtered with `jsonb_array_elements_text`** (`app/modules/knowledge/service.py:144-147`) — a per-row JSONB expansion with no GIN index, on top of the already-sequential vector scan. This is the second unindexed access path in the RAG query.

### 6.4 Cascade-delete behaviour that can lose data (CONFIRMED)

Measured from `pg_constraint.delete_rule` on the live DB: **7 `CASCADE`, 8 `SET NULL`, 43 `RESTRICT`.**

**The 7 CASCADEs — each is a silent, recursive deletion:**

| parent → child | line | consequence |
|---|---|---|
| `users.user_id` → `student_profiles` | `models.py:136` | Deleting a user **destroys the whole student profile**. Mitigated in practice: `student_profiles` is `RESTRICT`-referenced by `learning_sessions`, `learning_events`, `quiz_answers`, `book_progress`, `chapter_completions`, `reading_settlements`, `student_memories`, `memory_candidates`, `memory_evidence`, `student_episodes`, `profile_insights`, `recommendations`, so a student with **any** activity cannot be deleted. Only a pristine student profile cascades away. |
| `student_profiles.student_id` → `student_preferences` | `models.py:195` | Preferences die with the profile. Same mitigation. |
| `books.book_id` → `chapters` | `models.py:282` | **⚠️ the dangerous chain** |
| `chapters.chapter_id` → `content_blocks` | `models.py:315` | **⚠️ `books → chapters → content_blocks` is a two-level CASCADE.** Deleting a book instantly destroys every chapter **and every content block** beneath it. Student-data tables (`book_progress`, `learning_sessions`, `learning_events`, `chapter_completions`, `quiz_sessions`, `reading_settlements`, `student_episodes`) are `RESTRICT`, so a book with any student activity is protected — but a **draft or unused book deletes cleanly and silently takes its entire content tree with it.** Note the asymmetry with `import_library.py:306-308`, which deliberately *keeps* stale chapters rather than deleting them. |
| `conversations.conversation_id` → `conversation_summaries` | `models.py:747` | Summary dies with the conversation. `messages` is `RESTRICT` on the same parent, so a conversation with messages **cannot** be deleted at all — only an empty conversation cascades. |
| `knowledge_resources.resource_id` → `knowledge_chunks` | `models.py:1381` | Deleting a resource destroys all its chunks **and their embeddings**. Recoverable only by re-ingesting (which needs the embedding provider). |
| `admins.user_id` → `admins` | `models.py:1419` | Deleting a user deletes the admin row. Guarded in practice by `books.created_by RESTRICT` and `knowledge_resources.uploaded_by RESTRICT`. |

**The 8 `SET NULL`s** silently nullify a reference rather than blocking — worth knowing because a NULL is easy to mistake for "never set":
`quiz_sessions.source_question_id`, `quiz_sessions.source_quiz_session_id`, `book_progress.block_id`, `recommendations.related_book_id`, `reviewed_questions.chapter_id`, `student_memories.origin_candidate_id`, `knowledge_points.parent_id`, `student_profiles.current_teacher_role_id`.

Two are notable:
* **`reviewed_questions.chapter_id ON DELETE SET NULL`** (`models.py:1162-1164`): deleting a chapter **orphans its reviewed questions** (they survive with `chapter_id=NULL`). Since the selector matches on `chapter_id == chapter_id` (`quiz_bank.py:206-209`), an orphaned question simply becomes permanently unselectable — quiet data loss of the "silently dead row" kind.
* **`book_progress.block_id ON DELETE SET NULL`**: a reader's current position silently resets to NULL when the block is deleted.

**Also destructive and not a cascade:** `import_library.py:293-300` **deletes** content blocks whose deterministic IDs are no longer present in the source file when a book is re-imported. Deliberate and scoped, but it is real data loss triggered by an edit to a Markdown file.

### 6.5 Operational/governance risks found in the scripts (CONFIRMED)

These are data-integrity risks in the wider sense (they destroy or duplicate rows), verified against the source:

1. **`archive_noncorpus.py` will archive legitimate content.** Its keep-rule is *only* `source_url LIKE 'local://library/knowledge/%'` (`:58` and again in the UPDATE at `:70-73`). Everything else is set to `status='FAILED', error='archived: test data'` — which includes **all** output of `ingest_knowledge.py` (that script writes `https://demo.shuangling.local/knowledge/<stem>`, `:76`) **and any genuine admin upload**. Running this one-off governance script in a live environment would silently disable RAG for every manually-uploaded document. It is documented as manual/one-off (`docs/01-repository-map.md:122`), which is the only thing protecting it.
2. **The `knowledge_resources` UPDATE is not idempotent in the strict sense.** Unlike the `books` branch (guarded by `status != 'ARCHIVED'`, `:97`), the resource UPDATE (`:70-73`) has **no status predicate**, so every run rewrites `status`, `error` and `updated_at` for every matching row.
3. **`import_library` and `ingest_knowledge` create different rows for the same content** — `local://library/knowledge/<slug>` (`import_library.py:330`) vs `https://demo.shuangling.local/knowledge/<stem>` (`ingest_knowledge.py:76`). Because the ingestion idempotency key is `(source_url, storage_key)` (`ingestion.py:225-230`), the same document ingested by both paths yields **two `knowledge_resources` rows with two sets of chunks** → duplicated RAG hits. LIKELY (depends on which paths are run) but structurally guaranteed by the two different URL schemes.
4. **`import_assessments` bumps `revision` on every run** — `:125` does `existing.revision = int(existing.revision or 1) + 1` unconditionally, so running it N times yields `revision = N` even when nothing changed. Confirmed live: the `imp-idempotent` row has `revision = 2` after the test imported it twice. Row *count* is stable (the stated goal) but the version counter is not.
5. **`reindex_embeddings` / `rebuild_memory` recreate rows.** Both use a `force_reprocess=True` path that deletes and recreates chunks (`ingestion.py:262-266`) or supersedes and recreates `profile_insights` (`pipeline.py:527-551`). They converge to correct *content*, but **primary keys change**, so anything holding a `chunk_id`/`insight_id` across a rebuild is invalidated.
6. **The shipped reviewed questions can never be served (CONFIRMED — functional gap).**
   * `import_assessments.py:96` reads `question.get("review_status", "DRAFT")` — **per question only**.
   * All 3 shipped JSON files (13 questions total) carry `review_status` at the **top level** of the file and **none** per question (verified: 0 of 4, 0 of 4, 0 of 5).
   * Therefore **every one of the 13 questions imports as `DRAFT`**, and the selector requires `review_status == 'APPROVED'` (`quiz_bank.py:206-209`) → **none can ever be selected.**
   * Compounding it: the importer derives `chapter_id` only from a top-level `chapter_id` key (`:87-90`), which the shipped JSONs do not have (they use `slug` + `chapter`). So all 13 also land with **`chapter_id = NULL`**, making them unselectable on two independent counts.
   * Live DB corroborates: `reviewed_questions` holds **5 rows, all test fixtures** (`cap-approved`, `cap-draft`, `cap-pending`, `cap-rejected`, `imp-idempotent`) — the real assessments have **never been imported** into the dev database, and `import_assessments` is not wired into CI (§6.3). The `skipped_no_chapter` counter is dead code — it is initialised at `:72` and returned at `:128` but never incremented, so the docstring's "找不到时跳过该题并告警" is unimplemented.
7. **Production code depends on a script.** `app/modules/content/assets.py:16` does `from app.scripts.validate_library import LIB_ROOT` — a runtime module importing a CLI script for a path constant. It works, but it means `validate_library.py` cannot be moved/removed without breaking the content module, and importing it drags the script's module-level code into the app.

### 6.6 Risk register (ranked)

| # | risk | severity | confidence |
|---|---|---|---|
| R1 | **4 untracked migrations while the live DB is already stamped at `a7b8c9d0e1f2`** — a `git clean`/fresh clone leaves a 19-revision chain whose head (`b2c3d4e6f789`) is *behind* the DB, making every Alembic command fail with "unknown revision" | **HIGH** | CONFIRMED |
| R2 | `c7d8e9f0a1b2.downgrade()` **NULLs every non-64-dim embedding** — on this DB, all real 1024-dim vectors | **HIGH** (only if downgraded) | CONFIRMED |
| R3 | `archive_noncorpus.py` archives every non-`local://` resource, including genuine admin uploads | **HIGH** (manual script) | CONFIRMED |
| R4 | Zero vector indexes → all RAG search is a sequential scan; and the dimension-less column makes adding one impossible without another migration | MEDIUM (perf, not correctness) | CONFIRMED |
| R5 | `b1c2d3e4f5a6` was retro-edited after being applied → migrations are not byte-reproducible across environments | MEDIUM (hygiene) | CONFIRMED |
| R6 | `learning_events.conversation_id` / `quiz_session_id` have indexes but **no FK** → orphan rows | MEDIUM | CONFIRMED |
| R7 | The 13 shipped reviewed questions import as `DRAFT` + `chapter_id=NULL` → unreachable; importer not in CI | MEDIUM | CONFIRMED |
| R8 | 25 of 58 FK columns unindexed | LOW (today) | CONFIRMED |
| R9 | `books → chapters → content_blocks` two-level CASCADE silently destroys content trees for books with no student activity | LOW–MEDIUM | CONFIRMED |
| R10 | Duplicate `knowledge_resources` from `import_library` vs `ingest_knowledge` (two URL schemes) | LOW–MEDIUM | LIKELY |
| R11 | `chapter_completions` unique-index-vs-unique-constraint → permanent autogenerate churn | LOW | CONFIRMED |
| R12 | Hardcoded `admin123` (`seed.py:57`, duplicated `ingest_knowledge.py:36`) | LOW locally / HIGH if shipped | CONFIRMED |
| R13 | Circular FK `quiz_sessions ↔ quiz_questions` makes autogenerate blind to FK drift on those two tables | LOW | CONFIRMED |
| R14 | `seed.py:104` prints literal `{SEED_PASSWORD}` (missing f-prefix) | COSMETIC | CONFIRMED |

---

## 9. Recommendations (ordered, no code changed)

1. **Commit the 4 untracked migrations immediately** (R1). Until they are in git, the repository cannot reproduce the database it is running against.
2. **Never run `alembic downgrade` past `c7d8e9f0a1b2`** (R2) without first exporting `knowledge_chunks.embedding` / `student_episodes.embedding`; the downgrade silently discards them.
3. **Add `NOT NULL` + FK constraints for `learning_events.conversation_id` and `.quiz_session_id`** in a new migration (R6) — after backfilling/cleaning orphans. This is the last outstanding "deferred FK" from the phase-4/6 comments.
4. **Decide the vector-index policy explicitly** (R4): either pin the columns to the live provider dimension (`vector(1024)`) and create an HNSW index, or accept sequential scan and document a row-count threshold at which it must be revisited. Note the `vector_dims(...) = :dim` predicate in the query would block index use even if one existed — it must be removed as part of any ANN migration.
5. **Fix `import_assessments`** (R7) to read the top-level `review_status`/`chapter_id` and to resolve chapters from `slug` + `chapter`, then wire it into `ci.sh` / `ci-e2e.sh`; otherwise the reviewed-question feature is dead on every fresh environment.
6. **Resolve the `chapter_completions` unique object** (R11) — either declare `Index(..., unique=True)` in the model or switch the migration to `op.create_unique_constraint` — so autogenerate goes quiet.
7. **Add the 25 missing FK indexes** (R8) in a single index-only migration, mirroring the style of `a3f1c2e4b5d6`.
8. **Ship a break-glass README for the destructive scripts** (R3, R5): `archive_noncorpus`, `reindex_embeddings`, `rebuild_memory` all mutate production-shaped data. In particular, widen `archive_noncorpus`'s keep-rule beyond the single `local://` prefix before it is ever run outside this dev box.
9. **Rotate the demo credentials** for any non-local environment (R12) and remove the duplicated `admin123` literal from `ingest_knowledge.py`.
10. **Add a CI gate for schema drift** — run the same `compare_metadata()` check used in §5 and fail the build if it reports anything beyond a known-allowlist, so the next drift is caught automatically rather than by audit.

---
