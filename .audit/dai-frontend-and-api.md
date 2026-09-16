# DAI Experiment Platform — Editor / Run / Judge Reuse Audit

**Target audited:** `/home/zxk/Projects/dai-experiment-platform`
**Scope:** `frontend/src` (editor + run/submit UX) and `backend/app/api/` + `backend/app/models/__init__.py` (judge / execution / AI-grading APIs and schema)
**Goal:** determine what can be lifted into a *different React project* to reimplement an online code editor + run + judge UX.
**Method:** source-only reading. No README claims were used as evidence.

---

## 0. Headline findings (read this first)

1. **The frontend is Vue 3, not React.** `frontend/package.json:32` — `"vue": "^3.5.13"`, `:31` — `"pinia"`, `:38` — `@vitejs/plugin-vue`. There is **no React anywhere** in the repo — `grep -i react frontend/package.json` returns nothing, and the only `react` matches in `frontend/src` are Vue's own `reactive()` API calls (e.g. `components/admin/environment/EnvironmentEditorPanel.vue:36-51`), not the React framework. Every `.vue` SFC must be translated or replaced; nothing is a drop-in React component.
2. **The editor library is CodeMirror 6, not Monaco and not Ace.** Exactly **three** source files import `@codemirror/*` — `components/notebook/CodeCell.vue`, `components/ai/CodeViewer.vue`, `components/teacher/question-editor/QeCodeEditor.vue` (plus their two test files) — against `@codemirror/*` v6 (`frontend/package.json:19-23,28`). `components/notebook/StudioEditor.vue` reuses `CodeCell` rather than importing CodeMirror itself (`StudioEditor.vue:601-602`), and `components/common/CodeBlock.vue` is a plain `<pre>`. No `monaco`, no `@monaco-editor/*`, no `ace-builds` in dependencies or in `frontend/package-lock.json`.
3. **There are two entirely separate "run" stacks**, and conflating them is the biggest reuse trap:
   - **Notebook/kernel stack** — persistent Jupyter `ipykernel` in a Docker container, CodeMirror editor, cell-level execute → `POST /api/v1/experiments/records/{record_id}/cells/{cell_id}/execute`, returns **Jupyter IOPub outputs** (stream / execute_result / display_data / error, incl. `image/png`). This is the "run + plots" UX.
   - **Judge stack** — one-shot `docker run … python -m pytest` in an ephemeral sandbox, **plain `<textarea>` editor** (no CodeMirror at all), self-test → `POST /api/v1/judge/questions/{qid}/sample-run`, submit → `POST /api/v1/judge/submissions` + **1 Hz polling**. Returns only `{output, status, execution_time_ms}` — **no stdout/stderr split, no images, no cell outputs**.
4. **Nothing is SSE or WebSocket.** The only `StreamingResponse` in the whole backend is a media-download route (`backend/app/api/storage_media.py:15,243`). Both stacks use plain JSON request/response; the judge stack adds client-side `setInterval` polling.
5. **The single genuinely standalone-reusable backend endpoint is `POST /api/v1/judge/questions/{question_id}/sample-run`** — but even it is gated on assignment/course/enrollment, not truly standalone. Everything else is bound to dai's `Assignment → JudgeQuestion → Submission` or `ExperimentRecord → NotebookTemplateVersion` graph.
6. **The AI grading API has no "send code, get grade" endpoint at all.** Every AI-grading write path is `{grade_id}`- or `{kind}/{question_id}`-addressed and teacher/admin-only. Code enters the grader only from the DB.
7. **No prompt is ever persisted.** The LLM prompt templates live in `backend/app/services/ai_prompts.py` and are built at runtime; only `raw_response` (the completion) is stored. dai cannot reconstruct the exact prompt behind a historical grade — if the K-12 project wants reproducible grading audits, **add a `prompt_snapshot` column**, which dai lacks.

### 0.1 Quick reference — the exact contract to reimplement

```
EDITOR LIBRARY   CodeMirror 6   @codemirror/view 6.43.6, /state 6.7.1, /commands 6.10.4,
                                /lang-python 6.2.1, /theme-one-dark 6.1.3, codemirror 6.0.2
                                (+ @codemirror/language 6.12.4, @lezer/highlight 1.2.3 — undeclared!)
                                NO monaco, NO ace. Python only. No Ctrl+Enter binding.

NOTEBOOK RUN     POST /api/v1/experiments/records/{record_id}/cells/{cell_id}/execute
                 req  {"code": "..."}                    (ExperimentCellExecuteRequest)
                 res  {"outputs":[{msg_type,content}], "execution_time_ms":int|null,
                       "execution_count":int, "diagnostic":obj|null}
                 Jupyter IOPub msg_type ∈ stream | execute_result | display_data | error
                 sync blocking HTTP · 409 KERNEL_BUSY · persists outputs server-side

JUDGE SELF-TEST  POST /api/v1/judge/questions/{question_id}/sample-run
                 req  {"question_id": int, "code": "..."}   (SubmissionCreate)
                 res  {"output": "<stdout>\n<stderr>", "status": "...",
                       "execution_time_ms": int, "diagnostic": obj|null}
                 sync blocking HTTP · NO images · stdout/stderr NOT separable
                 status ∈ accepted|wrong_answer|runtime_error|time_limit_exceeded|
                          system_error|no_public_cases

JUDGE SUBMIT     POST /api/v1/judge/submissions          -> 201 SubmissionRead{id,status:"queued"}
                 then poll  GET /api/v1/judge/submissions/{id}/result   every 1000ms, max 120x
                 terminal  status ∈ accepted|graded|wrong_answer|runtime_error|
                                    time_limit_exceeded|system_error
                 (in grading_mode=="active", keep polling past "graded" until
                  grading_breakdown != null — CodeGrade and Submission commit separately)
                 async: Redis judge:queue -> worker -> docker run ... pytest
                 status machine: grading_status pending|queued|running|completed|system_error

AUTH             every endpoint: Authorization: Bearer <JWT>  (OAuth2PasswordBearer)
                 base path /api/v1 · no API-key/anonymous path anywhere
                 ai-grading/* additionally requires role ∈ {teacher, admin}

TRANSPORT        no SSE, no WebSocket anywhere. Plain JSON + client-side setInterval polling.
```

---

## 1. Code editor component(s)

### 1.1 Library and version

**CodeMirror 6 exclusively.** Declared in `frontend/package.json`:

| Line | Package | Declared | Resolved in `package-lock.json` |
|---|---|---|---|
| `:19` | `@codemirror/commands` | `^6.10.4` | `6.10.4` |
| `:20` | `@codemirror/lang-python` | `^6.2.1` | `6.2.1` |
| `:21` | `@codemirror/state` | `^6.7.1` | `6.7.1` |
| `:22` | `@codemirror/theme-one-dark` | `^6.1.3` | `6.1.3` |
| `:23` | `@codemirror/view` | `^6.43.6` | `6.43.6` |
| `:28` | `codemirror` (meta-package) | `^6.0.2` | `6.0.2` |

Transitive-but-imported: `@codemirror/language` `6.12.4`, `@lezer/highlight` `1.2.3`, `@lezer/python` `1.1.19` — note these are **imported directly by source but not declared in `package.json`** (they resolve only because `codemirror` hoists them; see `CodeCell.vue:74-75`). That is a latent dependency-hygiene bug worth fixing when porting.

Search evidence for absence of the other libraries: `grep -rniE "monaco|codemirror|@monaco-editor|\bace\b" frontend/src` returns only the four components below plus their tests. No `monaco` key anywhere in `package-lock.json`.

### 1.2 Component inventory

| Component | Lines | Role | Editor? |
|---|---|---|---|
| `frontend/src/components/notebook/CodeCell.vue` | 444 | **Student notebook code cell** — the "运行" UX | CodeMirror 6, editable, light theme |
| `frontend/src/components/notebook/StudioEditor.vue` | 763 | Teacher notebook template editor (reuses `CodeCell` at `:601-602`) | delegates to `CodeCell` |
| `frontend/src/components/teacher/question-editor/QeCodeEditor.vue` | 273 | Teacher judge-question authoring editor | CodeMirror 6, editable, oneDark |
| `frontend/src/components/ai/CodeViewer.vue` | 326 | Read-only code viewer w/ evidence-line highlight | CodeMirror 6, `editable=false` |
| `frontend/src/components/common/CodeBlock.vue` | 174 | Static `<pre>` + copy button, no CodeMirror | none |
| `frontend/src/views/student/AssignmentDetailView.vue` | 1282 | **Student judge/assignment page** | raw `<textarea>` + hand-rolled gutter |

#### (a) `CodeCell.vue` — the primary reusable editor

**Props** (`CodeCell.vue:11-18`):
```js
cell:            { type: Object, required: true },   // { id, source, outputs, student_editable }
executionCount:  { type: Number, default: null },
disabled:        { type: Boolean, default: false },
isExecuting:     { type: Boolean, default: false },
readonly:        { type: Boolean, default: false },
```
**Emits** (`:20`): `['execute', 'update:source']` — `execute` carries `cell.id`; `update:source` carries `(cell.id, source)`.

**Language config** — hard-coded Python, no `language` prop: `python()` extension at `:143`, imported at `:66` (`@codemirror/lang-python`).

**Theme** — a bespoke *light* theme, not oneDark:
- `daiLightTheme` via `EditorView.theme({...}, { dark: false })` at `:83-109`; colors come from CSS custom properties (`var(--surface)`, `var(--fg)`, `var(--accent)`, `var(--border)`).
- `daiLightHighlight` via `HighlightStyle.define([...])` at `:112-129`, with tags pulled from `@lezer/highlight` (`:68`).
- The old oneDark import was **removed** — comment at `:82` explicitly says "不再是 oneDark 深色".

**Value control** — local `ref` + two-way watch, not `v-model`:
- Local `code = ref(props.cell.source || '')` at `:25`.
- Child→parent: `watch(code, ...)` at `:29-33` emits `update:source` with `{ flush: 'sync' }`, guarded by `!props.readonly` and a `syncingFromParent` re-entrancy flag.
- Parent→child: `watch(() => props.cell.source, ...)` at `:36-58` diffs against the CodeMirror doc and dispatches a **full-document replace** (`changes: {from:0, to:doc.length, insert}`) at `:47-53`. This is O(n) and destroys cursor/undo history on every external write — a real weakness if ported to a collaborative/autosave-heavy app.
- CodeMirror→local: `EditorView.updateListener` at `:131-135` sets `code.value = update.state.doc.toString()` on `docChanged`.

**Key EditorState extensions** (`:137-150`): `lineNumbers()`, `highlightActiveLine()`, `drawSelection()`, `python()`, `daiLightTheme`, `syntaxHighlighting(daiLightHighlight)`, `keymap.of([...defaultKeymap, indentWithTab])`, `updateListener`, `EditorView.editable.of(!props.readonly)`.

**Dynamic loading + graceful fallback** — all CodeMirror modules are `await import(...)`ed inside `initCodeMirror()` (`:61-77`), invoked from `onMounted` (`:160`). On failure, `cmLoaded=false` and the template falls back to a plain `<textarea v-model="code">` (`:223-231`). Teardown `cmView.destroy()` at `:162-167`. Changing `readonly` **destroys and rebuilds the whole editor** (`:198-205`) — another porting smell.

**Run wiring** — a button in the toolbar, not a keybinding:
```html
<button class="btn-run" @click="handleRun" :disabled="disabled || isExecuting">
  {{ isExecuting ? '运行中...' : '运行' }}
</button>
```
(`:237-242`), with `handleRun()` at `:192-195` emitting `execute`. **There is no Ctrl/Cmd+Enter or Shift+Enter run shortcut.** The only keymap is `defaultKeymap` + `indentWithTab` (`:146`). Verified by grep across `components/notebook`, `components/teacher/question-editor`, `components/ai` and the student views: no `Mod-Enter`, `Ctrl-Enter` or `Shift-Enter` binding exists anywhere.

**Autosave** — not in the component. `CodeCell` only emits `update:source`; persistence lives in the Pinia store (§6).

**Output rendering** — in-component, §3.

#### (b) `QeCodeEditor.vue` — teacher authoring editor
Props `modelValue/placeholder/height/fullscreen` (`:9-15`), emits `update:modelValue`/`update:fullscreen` (`:17`). CodeMirror 6 with **oneDark** (`:62,85`) and a draggable resize + fullscreen. Same dynamic-import + textarea fallback pattern (`:95`, `:144-151`). Still Python-only (`:60`). Used by `views/teacher/QuestionEditView.vue`.

#### (c) `CodeViewer.vue` — read-only viewer
Props `code/filename/highlightLines/activeLine` (`:8-15`); `EditorView.editable.of(false)` (`:96`); dark theme (`:47`); exposes `scrollToLine`/`focusLine` via `defineExpose` (`:165`); falls back to a read-only `<pre>` (`:239-240`). This is the most *self-contained* editor component (no store coupling, no run wiring) and is the cleanest candidate to port.

#### (d) `AssignmentDetailView.vue` — the judge page uses a textarea, not CodeMirror
```html
<div class="editor-gutter" id="code-gutter"><pre>{{ lineNumbers }}</pre></div>
<textarea id="code-editor" class="editor-textarea" v-model="code"
          @scroll="syncScroll" @keydown.tab.prevent="code += '    '"
          spellcheck="false" :disabled="currentCompleted"></textarea>
```
(`:461-474`). Line numbers are a computed string join (`:29-42`), scroll sync is manual (`:203-207`), Tab inserts four spaces. **Any expectation that dai's judge page has a syntax-highlighted editor is wrong** — it does not.

---

## 2. Run / execute flow from the browser

### 2.1 Notebook "运行" (cell execute) — persistent kernel

| Step | Evidence |
|---|---|
| Button | `CodeCell.vue:237-242` (`运行`) |
| Handler | `CodeCell.vue:192-195` → `emit('execute', cell.id)` |
| Parent | `NotebookPlayer.vue:99-101` `handleRun` → `store.executeCell(cellId)` |
| Store | `stores/experiment.js:244-265` `executeCell` |
| API client | `api/experiments.js:29-31` `experimentsAPI.executeCell` |
| **HTTP** | **`POST /api/v1/experiments/records/{record_id}/cells/{cell_id}/execute`** |
| Base URL | `api/client.js:12` `baseURL: '/api/v1'` (axios, `withCredentials: true` at `:15`) |
| Request body | `{ "code": "<source>" }` — `experiments.js:30`; schema `ExperimentCellExecuteRequest` (`backend/app/schemas/__init__.py:1032-1038`, single field `code: str` with a size validator) |
| Response | `ExperimentCellExecuteResponse` (`backend/app/schemas/__init__.py:1041-1046`): `{ outputs: list[dict], execution_time_ms: int|null, execution_count: int, diagnostic: ImportDiagnosticRead|null }` |
| Transport | **Plain HTTP POST, synchronous, blocking.** No SSE, no WebSocket, no job id. |
| Backend handler | `backend/app/api/experiments.py:632-732` `execute_cell` |

Backend behavior worth knowing when porting:
- `:640-643` loads `ExperimentRecord` and enforces access; `:645-657` validates the cell against the pinned `NotebookTemplateVersion` (rejects unknown/hidden/non-code cells and blocks source edits on read-only cells with `403 CELL_READONLY`).
- `:659-660` rejects code > 50 000 chars (`CODE_TOO_LONG`).
- `:679-694` static import-policy pre-check → `422 IMPORT_NOT_ALLOWED` / `500 IMPORT_NOT_INSTALLED`.
- `:698-709` `get_kernel_manager().get_or_create_session(record_id, ...)` then `km.execute(record_id, payload.code)`; `RuntimeError` → **`409 KERNEL_BUSY`**.
- `:714-725` persists `record.cells_outputs[cell_id] = {execution_count, outputs, execution_time_ms}` and commits — **outputs are server-persisted per cell**.
- Kernel execution itself: `backend/app/services/kernel_manager.py:401-487` — Redis mutex `kernel:lock:{record_id}` (`:409-419`), then `docker exec -i <container> python /opt/dai/kernel_runner.py` with `{"code": ...}` on **stdin** so student code never appears in argv (`:427-438`), hard timeout `KERNEL_HARD_TIMEOUT` (on timeout the container is destroyed *and rebuilt*, `:440-455`).
- Actual Jupyter IOPub collection: `backend/docker/kernel/kernel_runner.py:38-63` — `BlockingKernelClient.execute(code)`, loop `get_iopub_msg` until `status == idle`, keeping `msg_type ∈ {stream, display_data, execute_result, error}` as `{"msg_type": mt, "content": content}` and UTF-8-decoding `bytes` in `content["data"]` (`:51-55`).

**Interrupt / restart / run-all** (same stack): `experimentsAPI.interrupt` → `POST /experiments/records/{id}/interrupt` (`api/experiments.js:34-36`; backend `experiments.py:838`), `restart` → `POST /experiments/records/{id}/restart` (`:39-41`; backend `:854`), and `executeAllCells()` (`stores/experiment.js:267-271`) which just awaits `executeCell` sequentially client-side — no batch endpoint. Server-side interrupt is `docker exec <c> kill -INT 1` (`kernel_manager.py:489-495`).

### 2.2 Judge "自测" (self-test / sample run) — ephemeral pytest

| Step | Evidence |
|---|---|
| UI | Two buttons: `自测` (`AssignmentDetailView.vue:599-609`) and `提交` (`:610-614`) |
| Handler | `handleSelfTest()` `AssignmentDetailView.vue:211-235` |
| API | `api/judge.js:8` `sampleRun(questionId, data)` |
| **HTTP** | **`POST /api/v1/judge/questions/{question_id}/sample-run`** |
| Request | `{ "question_id": <int>, "code": "<source>" }` (`AssignmentDetailView.vue:222-225`; schema `SubmissionCreate` `backend/app/schemas/__init__.py:656-658`) |
| Response | `SampleRunResponse` (`backend/app/schemas/__init__.py:686-692`): `{ output: str, status: str, execution_time_ms: int, diagnostic: ImportDiagnosticRead|null }` |
| Transport | **Synchronous plain HTTP POST.** Comment at `AssignmentDetailView.vue:210` says it outright: `// sample-run 同步返回结果，无需轮询` |
| Backend | `backend/app/api/judge.py:258-...` `sample_run` |

Backend notes (`judge.py:258-...`): rejects non-students (`403`); requires published assignment **and** published course **and** an active `CourseEnrollment` row (`NOT_ENROLLED`); enforces deadline (`require_assignment_before_deadline`, `:32-40`); if the question has **no** `public_cases` it returns `status="no_public_cases"` without running anything; otherwise it **synthesizes a pytest file on the fly** (`test_code += "def test_public_cases(): ..."` with `assert {function_name}({args}) == {repr(expected)}`) and runs `_run_docker_pytest(...)` once (`backend/app/worker/judge_worker.py:101-140`). It deliberately does **not** create a `Submission`, does not consume an attempt, and never touches hidden tests.

Key detail for reuse: **`output` is a single concatenated string** — `output=f"{stdout}\n{stderr}"` — so stdout and stderr are *not* separable by the client. Status vocabulary comes from `_status_from_pytest` (`judge_worker.py:62-72`): `accepted | time_limit_exceeded | wrong_answer | runtime_error | system_error`.

### 2.3 Judge "提交" (submit) — queued + polling

| Step | Evidence |
|---|---|
| Handler | `handleSubmit()` `AssignmentDetailView.vue:238-264` |
| API | `api/judge.js:4` `submit(data)` |
| **HTTP** | **`POST /api/v1/judge/submissions`** → **`201 Created`** |
| Request | `{ "question_id": <int>, "code": "<source>" }` (`AssignmentDetailView.vue:251`; `SubmissionCreate`, `schemas/__init__.py:656-658`) |
| Response | `SubmissionRead` (`schemas/__init__.py:666-683`) — `id, question_id, student_id, code, status, stdout, stderr, score, result_details, tests_passed, tests_total, execution_time_ms, grading_breakdown, diagnostic`. On create, `status="queued"`, `grading_status="pending"` (`judge.py:105-113`) |
| Backend | `backend/app/api/judge.py:65-129` `create_submission` |

`create_submission` gates (all in `judge.py`): student-only (`:73-74`), question exists (`:76-77`), assignment published (`:79-80`), audience/enrollment check (`:82-91`), deadline (`:92`), `max_attempts` counted from prior `Submission` rows (`:94-102`), then freezes the effective environment version + import-policy snapshot onto the row (`:105-120`, with `require_runnable_version` at `:109`), `db.add` `:121`, commit/refresh `:122-124`, and finally the **single queue entry point** `enqueue_job(db, job_type="assignment", object_id=submission.id)` (`:126-127`, imported lazily at `:126`); returns at `:129`.

**Async machinery** (this is the important architectural bit):
- `backend/app/services/judge_queue.py:47-...` `enqueue_job` — atomic `UPDATE … WHERE grading_status='pending'` claiming, then `LPUSH`/`RPUSH` onto Redis list `judge:queue` (`judge_queue.py:26`). DB is the source of truth; Redis only wakes workers (`:1-8`). `MAX_ATTEMPTS = 3` (`:34`).
- Worker: `backend/app/worker/judge_worker.py:574` `process_submission` → `_v1_judge_submission` (`:419`) or `_legacy_judge_submission` (`:334`) → `_run_docker_pytest` (`:101-140`) which is `docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges --read-only --tmpfs /tmp:exec,size=64m --cpus <n> --memory <n>m --pids-limit 50 --user 1000:1000 -v <workdir>:/work:ro -w /work <image> python -m pytest -q -p no:cacheprovider <testfile>`.
- Task-1 statuses: `grading_status ∈ {pending, queued, running, completed, system_error}` (`models/__init__.py:577-578`); result `status ∈ {queued, running, accepted, wrong_answer, runtime_error, time_limit_exceeded, system_error, graded}`.

**Polling contract (client-side, not server-pushed):**
- `pollSubmitResult()` `AssignmentDetailView.vue:314-339`: `setInterval(..., 1000)` calling `judgeAPI.getResult(submissionId)` → **`GET /api/v1/judge/submissions/{submission_id}/result`** (`api/judge.js:7`; backend `judge.py:222-245`), response = `SubmissionRead`.
- `MAX_POLL_COUNT = 120` (`:27`) → ~2 minutes then toast `判题超时，请重试` (`:332-337`).
- Termination predicate `isSubmissionComplete()` `:303-312`: terminal errors (`wrong_answer`, `runtime_error`, `time_limit_exceeded`, `system_error`, `:56`) end immediately; in `grading_mode === 'active'` the code deliberately **keeps polling past `graded` until `grading_breakdown` is non-null** (`:306-310`) because `CodeGrade` and `Submission` are written in two transactions. In `legacy` mode it stops on `accepted`/`graded`.
- Because polling is client-driven, **there is no server-side long-poll/SSE endpoint to reuse** — any port must reimplement the interval loop.

### 2.4 Exam variant (third path, for completeness)
`views/student/ExamView.vue:313` → `examsAPI.sampleRun(examId, question.id, {code})` → `POST /api/v1/exams/{exam_id}/questions/{question_id}/sample-run` (`api/exams.js:30`; backend `backend/app/api/exams.py:451-...`). Request schema `ExamSampleRunRequest` has **only `code`** — the question identity comes from the URL (`schemas/__init__.py:695-702`). Response is the same `SampleRunResponse`. Exam submission is a whole-paper submit (`POST /exams/{id}/submit`, `api/exams.js:15`; backend `exams.py:565`) and the ExamView editor is again a raw `<textarea>` (`ExamView.vue:566`).

### 2.5 Studio preview variant (teacher-side kernel run)
`stores/studio.js:326-345` → `studioAPI.previewRun(templateId, {cell_id})` → `POST /api/v1/studio/templates/{id}/preview/run` (`api/studio.js:42`; backend `backend/app/api/studio.py:296-310`), response `StudioPreviewRunResponse { outputs: list[dict], execution_time_ms }` (`backend/app/schemas/studio.py:159-161`). Note this request carries **only `cell_id`** — the source comes from the saved draft server-side, unlike the student path which posts `code`. Interrupt/reset at `studio.py:313-336`.

---

## 3. Output rendering

### 3.1 Wire format (both paths)
The kernel path emits **Jupyter IOPub** shape: `[{ "msg_type": "stream"|"display_data"|"execute_result"|"error", "content": {...iopub content...} }]`, produced by `backend/docker/kernel/kernel_runner.py:49-56` and passed through unchanged by `kernel_manager.py:462-475` and `experiments.py:716-732`. For `display_data`/`execute_result` the `content.data` map is UTF-8 decoded, so `image/png` arrives as a base64 **string** (`kernel_runner.py:51-55`).

The judge path emits **no structured outputs at all** — just `SampleRunResponse.output` (pre-concatenated stdout+stderr) and, after judging, `SubmissionRead.stdout` / `.stderr` / `.result_details` (`models/__init__.py:585-588`).

### 3.2 Is there a shared renderer component? **No.**
There is **no** `OutputRenderer`/`CellOutput`/`NotebookOutput` component anywhere in `frontend/src`. Output rendering is duplicated inline in at least three places, each with different logic:

**(a) `CodeCell.vue:169-190` + template `:248-265`** — the only renderer that understands Jupyter outputs:
```js
function getOutputs()      { return props.cell.outputs?.outputs || [] }                    // :169-172
function outputType(output){ return output?.msg_type || output?.output_type || 'stream' }  // :174-176
function outputText(output){
  if (output.text) return output.text
  if (output.content?.text) return output.content.text
  if (output.content?.ename) return `${output.content.ename}: ${output.content.evalue}\n${(output.content.traceback||[]).join('\n')}`
  return JSON.stringify(output)                                                            // :178-185
}
function outputImageData(output){
  const data = output?.data || output?.content?.data || {}
  return data['image/png'] || null                                                          // :187-190
}
```
Template branches (`:249-265`): `stream` → `<pre class="output-stream">` with `output-stderr` class when `output.name === 'stderr' || output.content?.name === 'stderr'` (`:254`); `error` → `<pre class="output-error">` (`:256`); otherwise if `outputImageData` → `<img :src="'data:image/png;base64,' + …">` (`:257-262`); else `<pre>` fallback (`:263`).

**Substantive gaps in this renderer** (important for a reuse decision):
- `execute_result` and `display_data` carrying `text/plain` (the common case: `x = 42` → `execute_result`) hit the `JSON.stringify(output)` branch and render **raw JSON**, not the value. `outputText` never consults `content.data['text/plain']`.
- `text/html` results (pandas DataFrames, matplotlib `_repr_html_`) are **not rendered** — they fall through to JSON.
- Only `image/png` is handled (`:189`); `image/jpeg`, `image/svg+xml`, `application/json` are ignored.
- `display_data`'s `transient`/`metadata` are discarded.
- There is **no `clear_output` handling** and no output-cap/virtualization: `.output-area` just gets `max-height: 400px; overflow-y: auto` (`:402-408`).
- Each output is keyed by array index (`:250` `:key="i"`), so streamed re-renders are not stable.

**Interpretation:** the shape is right (`msg_type`/`content` is the real Jupyter protocol) but the renderer is a thin, incomplete 20-line function. Treat it as a *specification* of the wire format, not as reusable code.

**(b) `NotebookPlayer.vue`** — renders no outputs itself; it only passes `:cell`/`:execution-count` down to `CodeCell` (`:208-220`) and shows a submit status bar (`:192-203`).

**(c) `AssignmentDetailView.vue:507-543`** — judge output is a fake terminal: a `terminal-panel` with three decorative dots and a `terminal-header`, then a status line built from static maps `TEST_STATUS_ICON` / `TEST_STATUS_LABEL` / `TEST_STATUS_CLASS` (`:58-60`) plus a diagnostic line (`:524-527`). It renders **status text only** — it never displays the pytest stdout body, even though `SampleRunResponse.output` contains it (it is simply not bound in the template). Submit results (`:554-590`) render `SUBMIT_STATUS_LABEL[status]` (`:62`) and delegate AI scores to `StudentAIGradingResult`.

**(d) `StudentAIGradingResult.vue`** (228 lines) — the AI-grade renderer, props `{ breakdown, heading }` (`:4-13`). It hard-codes dai's rubric dimensions and max scores: `functional 60 / algorithm 20 / robustness 10 / quality 10` (`:15-23`). It *is* a reasonably self-contained presentational component (no store/API imports) and it is reused in more than one view, so it is the closest thing to a shared renderer in the codebase — but its weightings and field names are dai-specific (§5, §7e).

**(e) `MarkdownCell.vue`** — markdown cells only: `marked.parse` + `sanitizeHtml` (`:18-19`), rendered with `v-html` (`:34`). Sanitization via DOMPurify wrapper `utils/sanitize.js` (dep at `package.json:29`).

### 3.3 Reusable standalone?
**No — not as code.** There is no standalone renderer to lift. What *is* reusable is the **contract**: `[{msg_type, content}]` with Jupyter IOPub semantics. A React port should write a fresh `OutputRenderer` (~100 lines) that correctly handles `stream`/`execute_result`/`display_data`(`text/plain`, `text/html`, `image/png`)/`error`, plus a separate plain-text/status renderer for the judge path. Porting `CodeCell.vue`'s functions verbatim would inherit the JSON-dump bug for `execute_result`.

---

## 4. Backend APIs worth reusing

Mounting chain (verified): every router is created with its own prefix (e.g. `backend/app/api/judge.py:28` `APIRouter(prefix="/judge", …)`, `ai_grading.py:40` `prefix="/ai-grading"`, `jupyter.py:9` `prefix="/jupyter"`, `notebooks.py:13` `prefix="/notebooks"`, `experiments.py:52` `prefix="/experiments"`, `studio.py:39` `prefix="/studio"`), aggregated in `backend/app/api/__init__.py:27-49` under `api_router = APIRouter(prefix="/api/v1")`, and included at `backend/app/main.py:359`. So `/api/v1` is the real base and `api/client.js:12` matches.

Auth primitives: `get_current_user` (`backend/app/dependencies.py:70-85`) validates a JWT access token (OAuth2 bearer, `dependencies.py:15`), checks Redis `blacklist:{jti}` (`:64`), loads the `User`, requires `status == "active"`, and compares `sv` against `user.session_version` (`:81-83`). `require_roles(*roles)` (`:86-92`) raises `403 FORBIDDEN`. There is **no API-key or anonymous path** on any of these routers.

### 4.1 `backend/app/api/judge.py` — complete inventory (6 routes)

| # | Method + path | Line | Auth | Request | Response |
|---|---|---|---|---|---|
| 1 | `POST /api/v1/judge/submissions` | `:65` (dec), `:66` (def) | `get_current_user` `:70`, then **in-body `role != "student"` → 403** `:73-74`; assignment published `:79-80`; audience/enrollment `:82-91`; deadline `:92` | `SubmissionCreate` `{question_id: int, code: str}` (`schemas/__init__.py:656-658`) | `SubmissionRead`, **201** (`schemas/__init__.py:666-683`) |
| 2 | `GET /api/v1/judge/submissions` | `:131`/`:132` | `get_current_user` `:135`; row filtering by role `:141-157` | query `page`,`page_size` via `pagination` dep | `PaginatedResponse` (`schemas/__init__.py:39-43`) |
| 3 | `GET /api/v1/judge/submissions/{submission_id}` | `:160`/`:161` | `get_current_user` `:164` + `can_view_submission` `:166` (owner / owning teacher / admin; `:50-62`) | path | `SubmissionRead` + promoted `diagnostic` (`_with_diagnostic` `:247-255`) |
| 4 | `GET /api/v1/judge/submissions/{submission_id}/teacher` | `:172`/`:173` | `get_current_user` `:176` + **`role not in (teacher, admin)` → 403** `:180-181` + `can_view_submission` `:183` | path | `TeacherJudgeSubmissionRead` (`schemas/unified_submissions.py`) — adds student/question/assignment/course context and `ai_grade_id/ai_score/ai_needs_review/ai_review_reason` (`:214-217`) |
| 5 | `GET /api/v1/judge/submissions/{submission_id}/result` | `:222`/`:223` | `get_current_user` `:226` + `can_view_submission` `:228` | path | `SubmissionRead`; for students, attaches `grading_breakdown` from an `active`+`completed` `CodeGrade` (`:231-240`) |
| 6 | `POST /api/v1/judge/questions/{question_id}/sample-run` | `:258`/`:259` | `get_current_user` `:264` + **student-only** `:267-268` + body/path id match `:270-271` + question exists `:272-274` + published assignment `:276-278` + published course `:279-281` + **active `CourseEnrollment` required** `:282-290` + deadline `:291` | `SubmissionCreate` (body `question_id` must equal path) `:270-272` | `SampleRunResponse` (`schemas/__init__.py:686-692`) |

### 4.2 `backend/app/api/ai_grading.py` — complete inventory (13 routes)

All handlers are sync `def`; **no route sets `status_code=`**, so all return 200. Local guard `_teacher_or_admin` at `:43-45`.

| # | Method + path | Line (dec/def) | Auth | Request schema | Response |
|---|---|---|---|---|---|
| 1 | `GET /api/v1/ai-grading/status` | `:48`/`:49` | `require_roles("admin","teacher")` `:51` | — | `AIServiceStatus {enabled, ready}` (`schemas/__init__.py:49-51`) |
| 2 | `GET /api/v1/ai-grading/questions/{kind}/{question_id}/config` | `:170`/`:171` | `get_current_user` `:174` + `_teacher_or_admin` `:176` | — | raw dict `{grading_mode, teacher_constraints, reference_solution, test_groups, score_cap_rules, hidden_tests}` `:187-194` |
| 3 | `PUT /api/v1/ai-grading/questions/{kind}/{question_id}/config` | `:197`/`:198` | as #2 + `_ensure_course_teacher` `:206` + `ensure_scoring_editable` `:207` | `AIQuestionConfigUpdate` (`schemas/ai_grading.py:60-73`) | `{ok, grading_mode}` `:225` |
| 4 | `GET /api/v1/ai-grading/questions/{kind}/{question_id}/rubrics` | `:230`/`:231` | `get_current_user` `:234` + `_teacher_or_admin` `:236` | — | `{items: [...]}` `:244-249` |
| 5 | `POST /api/v1/ai-grading/questions/{kind}/{question_id}/rubrics/generate` | `:252`/`:253` | `get_current_user` `:256` + `_teacher_or_admin` `:260`; rate limit `:269` | — | `{id, version, status, rubric_json}` `:305` — **synchronous inline LLM** |
| 6 | `POST /api/v1/ai-grading/questions/{kind}/{question_id}/test-groups/generate` | `:308-311`/`:312` | `get_current_user` `:316` + `_teacher_or_admin` `:326`; rate limit `:335` | `TestGroupsGenerateRequest \| None` (`schemas/ai_grading.py:79-88`) | `TestGroupsGenerateResponse` (`schemas/ai_grading.py:103-111`) — **sync LLM + judge container preflight** |
| 7 | `PATCH /api/v1/ai-grading/rubrics/{rubric_id}` | `:409`/`:410` | `get_current_user` `:413` + `_teacher_or_admin` `:415` | `RubricDocument` (`schemas/ai_grading.py:130-168`) | `{id, status}` `:430` |
| 8 | `POST /api/v1/ai-grading/rubrics/{rubric_id}/lock` | `:433`/`:434` | `get_current_user` `:437` + `_teacher_or_admin` `:439` | — | `{id, status, locked_at}` `:454` |
| 9 | `GET /api/v1/ai-grading/grades` | `:583`/`:584` | `get_current_user` `:592` + `_teacher_or_admin` `:595` | query `kind, question_id, student_id, student_name, status` `:585-589` + `pagination` `:590` | `PaginatedResponse` |
| 10 | `GET /api/v1/ai-grading/grades/{grade_id}` | `:651`/`:652` | `get_current_user` `:655` + `_teacher_or_admin` `:657` + inline fail-closed course check `:663-688` | — | raw dict `:735-760` incl. `status` `:737`, `ai_result` `:744`, `raw_response` `:744`, `student_code` `:745`, `last_error`/`attempt_count` `:748`, `overrides` `:754-759` |
| 11 | `POST /api/v1/ai-grading/grades/{grade_id}/retry` | `:763`/`:764` | `get_current_user` `:767` + `_teacher_or_admin` `:770` + `_check_grade_permission` `:777` | — | `{ok, grade_id, status}` `:792` — **queue ack only** |
| 12 | `POST /api/v1/ai-grading/grades/{grade_id}/override` | `:795`/`:796` | `get_current_user` `:800` + `_teacher_or_admin` `:802` + `_check_grade_permission` `:809` | `GradeOverrideCreate` (`schemas/ai_grading.py:252-264`): `algorithm_score?`, `quality_score?`, `final_score_100?`, **`reason: str` required**; validator ≥1 score | `{ok, grade_id, original, replacement}` `:882` |
| 13 | `POST /api/v1/ai-grading/questions/{kind}/{question_id}/regrade` | `:885`/`:886` | `get_current_user` `:890` + `_teacher_or_admin` `:893` + `_ensure_course_teacher` `:895` | — | `{ok, total, queued}` `:994` — bulk queue ack |

`kind` is hard-limited to `"assignment" | "exam"` (`ai_grading.py:126`, `:463-464`).

**Is AI grading synchronous?** Split:
- **Grading itself is queued/async.** Producers set `CodeGrade.status="pending"` and call `enqueue_ai_grade(db, redis_client, grade_id)` (`ai_grading.py:790`, `:990`; also fired by the judge worker after deterministic judging, `worker/judge_worker.py:568`). `enqueue_ai_grade` (`services/ai_grading_queue.py:24-45`) does a conditional `pending→queued` UPDATE then `rpush` onto Redis `judge:ai:queue` (`config.py:97`). Consumer `process_ai_grade` (`worker/judge_worker.py:897-951`) claims `queued→running`, calls `DeepSeekClient` + `grade_code_submission`, sets `completed` or `fail_ai_grade` (retry ≤3 → terminal `review_required`). Stale recovery in `ai_grading_queue.py:139-243`.
- **The de-facto job-status poll is `GET /ai-grading/grades/{grade_id}`** (`ai_grading.py:651`) exposing `status`/`attempt_count`/`last_error` — teacher/admin only. Students poll a *different* endpoint, `GET /judge/submissions/{id}/result`.
- **Rubric generation (`:252`) and test-group generation (`:308`) are synchronous inline LLM calls** in the request thread, with user-level rate limiting 5/60 s and fail-closed `503 AI_RATE_LIMIT_UNAVAILABLE` on Redis failure (`:57-77`).

**LLM provider:** external DeepSeek via `DeepSeekClient` (`services/ai_client.py:90`), OpenAI-compatible `POST {ai_base_url}/v1/chat/completions` (`ai_client.py:63-68`). Config env-prefixed `DAI_` (`config.py:19`): `ai_enabled=False` `:86`, `ai_base_url="https://aihub.codingpython.cn"` `:87`, `ai_api_key` `:88`, `ai_model="deepseek-v4-flash"` `:89`, `ai_timeout_seconds=60` `:90`, `ai_max_retries=3` `:91`, `ai_queue_name="judge:ai:queue"` `:97`. Prompts are **not** in the API file — they live in `services/ai_prompts.py` (`build_rubric_messages:119`, `build_test_group_messages:36`, `build_grading_messages:161`); the code-grading prompt is built only in the worker path (`services/ai_grading_service.py:64-78`).

**Streaming:** none. No `StreamingResponse`, SSE, or WebSocket anywhere in `backend/app` except the unrelated media route (`api/storage_media.py:15,243`). All AI-grading routes are plain JSON.

### 4.3 `backend/app/api/jupyter.py` — complete inventory (3 routes, mostly dead)

| # | Method + path | Line | Auth | Request | Response |
|---|---|---|---|---|---|
| 1 | `GET /api/v1/jupyter/entry` | `:12`/`:13` | `get_current_user` `:15` | — | `JupyterEntryResponse {iframe_url}` (`schemas/__init__.py:1167`). **`503 JUPYTER_DISABLED`** unless `settings.jupyter_enabled` (`:17-18`); default is `False` (`config.py:49`) |
| 2 | `GET /api/v1/jupyter/templates` | `:22`/`:23` | `get_current_user` `:23` | — | **always `410 JUPYTER_TEMPLATES_RETIRED`** (`:24-28`) |
| 3 | `POST /api/v1/jupyter/templates/{template_id}/copy` | `:31`/`:32` | `get_current_user` `:32` | — | **always `410`** (`:33-37`) |

**Verdict on jupyter.py: NOT REUSABLE / effectively retired.** It is a one-line iframe-URL handoff to an externally-hosted JupyterLab, disabled by default, and two of its three routes are hard-coded 410 tombstones. dai's real notebook execution does **not** go through JupyterLab — it goes through `kernel_manager` + the `experiments` router. Relatedly, `backend/app/api/notebooks.py:18-25` is a catch-all tombstone returning `410 DEPRECATED` with `Deprecation: true` and `Sunset: 2026-09-01` headers for the entire `/api/v1/notebooks/*` tree.

### 4.4 Standalone-reusable vs domain-coupled

**Standalone-reusable (take code + language, return outputs) — realistically only two, and both are partially coupled:**

| Endpoint | Coupling that must be cut |
|---|---|
| `POST /api/v1/judge/questions/{question_id}/sample-run` | Takes `{question_id, code}`. Needs `JudgeQuestion` (for `function_name`, `public_cases`, limits, env) + `Assignment` + `Course` + `CourseEnrollment` + deadline. To reuse: replace the question lookup with a caller-supplied `{code, test_code or public_cases, function_name, timeout, memory, image}` payload. The *executor* it calls — `worker/judge_worker.py:101-140 _run_docker_pytest` — **is genuinely standalone** (pure function of `(workdir, settings, timeout, memory, image_ref)` → `(stdout, stderr, returncode, elapsed_ms)`) and is the single most valuable backend artifact to lift. |
| `POST /api/v1/experiments/records/{record_id}/cells/{cell_id}/execute` | Body is `{code}` (standalone!), but access, cell validation, import policy and **output persistence** are all bound to `ExperimentRecord` + `NotebookTemplateVersion`. To reuse: cut the record/version layer and keep only `get_or_create_session(record_id, …)` + `km.execute(record_id, code)` (`services/kernel_manager.py:353-487`) — also a clean, reusable unit given Docker + Redis. |

**Coupled to dai's exam/course/submission domain — do not attempt to reuse as-is:**
- `POST /judge/submissions` — `Assignment.status=="published"`, `CourseEnrollment.status=="enrolled"`, `student_in_assignment_audience`, `question.max_attempts`, deadline (`judge.py:75-104`).
- `GET /judge/submissions*` (all three) — `can_view_submission` walks `Submission→JudgeQuestion→Assignment→Course.teacher_id` (`judge.py:50-62`).
- `POST /judge/submissions/{id}/teacher` — additionally reads `CodeGrade` (`judge.py:200-217`).
- `POST /exams/{exam_id}/questions/{qid}/sample-run` and `POST /exams/{id}/submit` — exam session/audience/submission state machine (`exams.py:451`, `:565`).
- `POST /experiments/records/*` (execute/submit/interrupt/restart) — `ExperimentRecord` ownership + template version pinning (`experiments.py:632-732`, `:877-997`).
- **All 13 `/ai-grading/*` routes** — model imports at `ai_grading.py:16-19` (`Assignment, CodeGrade, Course, Exam, ExamAnswer, ExamQuestion, ExamSubmission, GradeOverride, JudgeQuestion, QuestionRubric, Submission, User`); `kind ∈ {assignment, exam}` (`:126`); every path embeds `{kind}/{question_id}` or `{grade_id}`; `_teacher_course_ids` / `_ensure_course_teacher` / `_ensure_assignment_scoring_editable` all resolve course ownership (`:98-137`); success paths write back into `Submission.score/status` (`:868-869`) and `ExamAnswer.score/grading_status` (`:873-874`).
- `POST /studio/templates/*` — all routes use `require_roles("admin","teacher")` via `studio_user` (`studio.py:40`) and `get_managed_template` ownership (`:141`).

**Notably absent:** there is **no** endpoint anywhere that accepts `{code, language}` and returns run output without a domain object. `language` is never a parameter — Python is hard-coded end-to-end (`@codemirror/lang-python`; `python -m pytest`; `image_ref or settings.judge_image`).

---

## 5. Data model for submissions / judge / grading

Source: `backend/app/models/__init__.py` (1586 lines). It is the **only** module in `app/models/`, so this is the complete model surface.

Shared conventions:
```python
# :15 — control-plane PK: BIGINT on MySQL, INTEGER rowid-alias on SQLite
BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")

# :39-45 — inherited by every model below EXCEPT NotebookTemplateVersion (:879)
#          and ProfileVersionPackage (:1405)
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())   # :40
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())     # :41-45
```
```python
# :18-36 — python-side INSERT default used by every environment_version_id FK below.
# Lazily binds the newest *available* 'basic' profile version; returns None when the
# test DB has no seed, which then violates the NOT NULL constraint on those columns.
def resolve_basic_env_version_id(context) -> int | None:
    return context.connection.execute(text(
        "SELECT ev.id FROM environment_versions ev"
        " JOIN environment_profiles ep ON ep.id = ev.profile_id"
        " WHERE ep.slug = 'basic' AND ev.status = 'available'"
        "   AND ev.image_digest IS NOT NULL"
        " ORDER BY ev.version_number DESC LIMIT 1")).scalar()
```

Type inventory (from the import at `:3`): **no `JSONB`, no `Numeric`, no `LargeBinary`, no `Enum`.** All scores are `Float`; all structured payloads are `JSON` (MySQL JSON / SQLite TEXT-as-JSON). `Base` has no `metadata.naming_convention`, so `unique=True` emits an unnamed constraint and `index=True` emits `ix_<table>_<column>`.

`ondelete` inventory (scoped tables): `CASCADE` on `assignment_audience_classes.assignment_id` (`:502`), `assignment_audience_students.assignment_id/.student_id` (`:518-519`), `exam_audience_*` (`:667`, `:683-684`), `studio_asset_manifest*` (`:940`, `:943`, `:974`), `environment_drafts.profile_id` (`:1497`). `RESTRICT` on `studio_asset_manifest_entries.storage_object_id` (`:977`) and the `environment_publications` composite FKs (`:1551`, `:1557`, `:1569`). **Every other FK has no `ondelete`** → engine default (NO ACTION on MySQL). For a port this matters: deleting a `Submission` will **not** cascade to `CodeGrade`.

**Two negative findings worth stating explicitly:** the strings `kernel` and `test_case` appear **nowhere** in the models file. There is no `kernels` table and no `test_cases` table. Kernel sessions are pure in-memory + Redis state (`backend/app/services/kernel_manager.py:29 KernelSession`, `:100 KernelManager` — that module imports no models at all), and test cases live as JSON/text columns (`judge_questions.public_cases`, `.hidden_tests`, `.test_groups`).

### 5.1 `JudgeQuestion` — `judge_questions` (`:527-561`)

```python
id:                    Integer, primary_key=True                                        # :530
assignment_id:         ForeignKey("assignments.id"), index=True                          # :531
title:                 String(200)                                                       # :532
description:           Text, nullable                                                    # :533
function_name:         String(120)                                                       # :534
signature:             String(255), nullable                                             # :535
starter_code:          Text, nullable                                                    # :536
public_cases:          JSON, default=list        # visible sample tests                  # :537
hidden_tests:          Text                      # pytest source, REQUIRED               # :538
time_limit_ms:         Integer, default=10000                                            # :539
memory_limit_mb:       Integer, default=256                                              # :540
max_attempts:          Integer, nullable, default=None                                   # :541
# ── AI grading config ──
grading_mode:          String(20), default="legacy", index=True   # legacy|shadow|active  # :543
teacher_constraints:   JSON, default=dict                                                # :544
reference_solution:    Text, nullable                                                    # :545
test_groups:           JSON, default=list                                                # :546
score_cap_rules:       JSON, default=list                                                # :547
# ── environment binding ──
environment_version_id: BigInteger, ForeignKey("environment_versions.id"), nullable=True, index=True  # :552-555
import_policy_mode:    String(16), nullable=False, default="inherit"  # inherit|unrestricted|restricted  # :556-558
allowed_imports:       JSON, nullable=False, default=list                                # :559
assignment:            relationship(back_populates="questions")                          # :561
```
`environment_version_id = NULL` means "inherit the assignment default" (`:549-551`).

### 5.2 `Submission` — `submissions` (`:564-604`) — **the core judge table**

```python
__table_args__ = (
    Index("ix_submissions_gs_updated",  "grading_status", "updated_at"),                 # :567
    Index("ix_submissions_gs_finished", "grading_status", "finished_at"),                # :568
)
id:               Integer, primary_key=True                                              # :571
question_id:      ForeignKey("judge_questions.id"), index=True                            # :572
student_id:       ForeignKey("users.id"), index=True                                      # :573
code:             Text                                                                    # :574
status:           String(40), default="queued", index=True                                # :575
# ── judge queue state machine ──
grading_status:   String(20), default="pending"   # pending|queued|running|completed|system_error  # :577-578
attempt_count:    Integer, default=0                                                       # :579
queued_at:        DateTime(timezone=True), nullable                                        # :580
started_at:       DateTime(timezone=True), nullable                                        # :581
finished_at:      DateTime(timezone=True), nullable                                        # :582
last_error:       Text, nullable                                                           # :583
# ── judge result ──
stdout:           Text, nullable                                                           # :585
stderr:           Text, nullable                                                           # :586
score:            Float, nullable                                                          # :587
result_details:   JSON, nullable          # ← per-test JSON, incl. {"diagnostic": {...}}   # :588
tests_passed:     Integer, nullable                                                        # :589
tests_total:      Integer, nullable                                                        # :590
execution_time_ms:Integer, nullable                                                        # :591
# ── environment snapshot ──
environment_version_id:      BigInteger, ForeignKey("environment_versions.id"), nullable=False,
                             default=resolve_basic_env_version_id, index=True             # :594-597
import_policy_mode_snapshot: String(16), nullable=False, default="unrestricted"            # :598-600
allowed_imports_snapshot:    JSON, nullable=False, default=list                            # :601
question: relationship()                                                                   # :603
student:  relationship()                                                                   # :604
```
Note `result_details` is where the **import diagnostic** is lifted from for the student API (`judge.py:247-255`, reading `result_details["diagnostic"]`).

### 5.3 `CodeGrade` — `code_grades` (`:1110-1149`) — **the AI grading payload table**

```python
__table_args__ = (
    CheckConstraint("(submission_id IS NULL) != (exam_answer_id IS NULL)",
                    name="ck_code_grade_xor_target"),                                       # :1114-1117
    Index("ix_code_grades_review_status", "needs_teacher_review", "status"),                # :1118
)
id:                 Integer, primary_key=True                                               # :1121
submission_id:      ForeignKey("submissions.id"),  nullable=True, unique=True               # :1122-1124
exam_answer_id:     ForeignKey("exam_answers.id"), nullable=True, unique=True               # :1125-1127
rubric_id:          ForeignKey("question_rubrics.id")                                       # :1128
mode:               String(20)                          # legacy|shadow|active              # :1129
status:             String(30), default="pending", index=True                              # :1130
functional_score:   Float, default=0                                                        # :1131
algorithm_score:    Float, nullable                                                         # :1132
robustness_score:   Float, default=0                                                        # :1133
quality_score:      Float, nullable                                                         # :1134
raw_total:          Float, nullable                                                         # :1135
score_cap:          Float, nullable                                                         # :1136
final_score_100:    Float, nullable                                                         # :1137
scaled_score:       Float, nullable                                                         # :1138
deterministic_details: JSON, default=dict    # ← deterministic test-group results          # :1139
static_analysis:       JSON, default=dict    # ← AST/static signal                          # :1140
ai_result:             JSON, nullable        # ← *** PRIMARY AI GRADING PAYLOAD ***          # :1141
raw_response:          Text, nullable        # ← raw LLM completion text                     # :1142
needs_teacher_review:  Boolean, default=False                                               # :1143
review_reason:         Text, nullable                                                       # :1144
attempt_count:         Integer, default=0                                                   # :1145
queued_at / started_at / finished_at : DateTime(timezone=True), nullable                    # :1146-1148
last_error:            Text, nullable                                                       # :1149
```

**AI-grading payload columns, precisely:** `ai_result` (JSON, `:1141`) and `raw_response` (Text, `:1142`) carry the model output; `deterministic_details` (JSON, `:1139`) and `static_analysis` (JSON, `:1140`) carry the non-LLM evidence; the seven numeric score columns (`:1131-1138`) are the materialised score. The *exact* `ai_result` sub-keys consumed downstream are visible in `services/student_ai_results.py:33-56`:
```python
ai = cg.ai_result or {}
feedback = ai.get("student_feedback", {}) or {}
return { "functional_score": cg.functional_score, "algorithm_score": cg.algorithm_score,
         "robustness_score": cg.robustness_score, "quality_score": cg.quality_score,
         "raw_total": cg.raw_total, "score_cap": cg.score_cap,
         "final_score_100": cg.final_score_100, "scaled_score": cg.scaled_score,
         "strengths":  feedback.get("strengths", []),   "issues": feedback.get("issues", []),
         "suggestions":feedback.get("suggestions", []), "code_suggestions": feedback.get("code_suggestions", []),
         "algorithm_items": _safe_items(ai, "algorithm"),
         "quality_items":   _safe_items(ai, "code_quality"),
         "test_groups": (cg.deterministic_details or {}).get("groups", []) or [] }
```
⇒ `ai_result.student_feedback.{strengths,issues,suggestions,code_suggestions}`, `ai_result.algorithm`, `ai_result.code_quality`. This is exactly the `grading_breakdown` object the React port would need to render.

### 5.4 `QuestionRubric` — `question_rubrics` (`:1081-1107`)

```python
__table_args__ = (
    CheckConstraint("(judge_question_id IS NULL) != (exam_question_id IS NULL)",
                    name="ck_rubric_xor_target"),                                            # :1085-1088
    UniqueConstraint("judge_question_id", "version", name="uq_rubric_judge_version"),        # :1089
    UniqueConstraint("exam_question_id",  "version", name="uq_rubric_exam_version"),         # :1090
)
id:               Integer, primary_key=True                                                  # :1093
judge_question_id:ForeignKey("judge_questions.id"), nullable=True, index=True                # :1094-1096
exam_question_id: ForeignKey("exam_questions.id"),  nullable=True, index=True                # :1097-1099
version:          Integer                                                                    # :1100
status:           String(20), default="draft", index=True                                    # :1101
source_hash:      String(64)                                                                 # :1102
source_snapshot:  JSON                                                                       # :1103
rubric_json:      JSON     # ← the generated rubric                                            # :1104
model_name:       String(120)                                                                # :1105
raw_response:     Text, nullable                                                             # :1106
locked_at:        DateTime(timezone=True), nullable                                           # :1107
```

### 5.5 `GradeOverride` — `grade_overrides` (`:1152-1161`)

```python
id:                  Integer, primary_key=True                                               # :1156
code_grade_id:       ForeignKey("code_grades.id"), index=True                                # :1157
original_snapshot:   JSON                                                                    # :1158
replacement_snapshot:JSON                                                                    # :1159
reason:              Text                                                                    # :1160
reviewer_id:         ForeignKey("users.id")                                                  # :1161
```
Immutable audit trail. It also inherits `TimestampMixin`. Docstring `:1153` states it is immutable and must never cascade-delete.

### 5.6 `SchedulerLease` — `scheduler_leases` (`:730-744`) — **the one fully generic table**

```python
task_name:    Mapped[str] = mapped_column(String(80), primary_key=True)   # :741
owner_id:     Mapped[str] = mapped_column(String(120))                    # :742
lease_until:  Mapped[datetime] = mapped_column(DateTime(timezone=True))   # :743
heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))   # :744
```
Zero foreign keys, zero domain columns. It is the multi-instance lease guarding the stale-job recovery sweepers (`services/ai_grading_queue.py:139-243`, driven from `worker/judge_worker.py:958-976`). **Lift verbatim** if you run more than one worker.

### 5.7 Exam grading tables (the *other* consumer of `CodeGrade`/`QuestionRubric`)

These exist only because `code_grades`/`question_rubrics` are XOR-polymorphic. If the K-12 port does not need exams, deleting them also removes the XOR constraints.

**`ExamSubmission` — `exam_submissions` (`:692-727`)**
```python
__table_args__ = (UniqueConstraint("exam_id","student_id", name="uq_exam_student"),                       # :702
                  Index("ix_exam_submissions_status_expires","status","expires_at"),                      # :703
                  CheckConstraint("status IN ('started','submitted','grading','graded','review_required')",
                                  name="ck_exam_submission_status"))                                       # :704-706
id: Integer PK; exam_id: FK exams.id, index; student_id: FK users.id, index                              # :709-711
status: String(30)="started", index                                                                      # :712
score: Float|null                                                                                        # :714
started_at / expires_at / last_saved_at / submitted_at / graded_at: DateTime(tz)|null                     # :715-720
submission_reason: String(30)|null          # e.g. "time_expired"                                         # :718
review_reason: Text|null; review_required_at: DateTime(tz)|null                                           # :722-723
```
Note the comment at `:693`: a JSON `answers` column was **deliberately removed**; `exam_answers` rows are the single source of truth.

**`ExamQuestion` — `exam_questions` (`:760-790`)** — CHECK-enforced `question_type IN ('single_choice','multi_choice','fill_blank','code')` (`:764-767`). Carries its own copy of the AI-grading config: `grading_mode` `:784`, `teacher_constraints` `:785`, `reference_solution` `:786`, `test_groups` `:787`, `score_cap_rules` `:788`, plus `public_cases` `:779`, `hidden_tests` `:780`, `time_limit_ms` `:781`, `memory_limit_mb` `:782`. **The AI config block is duplicated between `judge_questions` and `exam_questions`** — a normalisation opportunity in a port.

**`ExamAnswer` — `exam_answers` (`:793-827`)**
```python
__table_args__ = (UniqueConstraint("submission_id","question_id", name="uq_exam_answer_q"),               # :797
                  Index("ix_exam_answers_gs_updated","grading_status","updated_at"))                       # :798
id: Integer PK; submission_id: FK exam_submissions.id, index; question_id: FK exam_questions.id, index   # :801-803
selected_options: JSON|null; code_answer: Text|null; text_answers: JSON|null                              # :804-806
version: Integer=1, server_default="1"        # optimistic concurrency                                    # :807
score / tests_passed / tests_total: nullable                                                              # :808-810
grading_status: String(20)="pending"; attempt_count: Integer=0                                            # :812, :814
queued_at / started_at / finished_at: DateTime(tz)|null; last_error: Text|null                            # :815-818
result_details: JSON|null                     # deterministic judge result                                  # :820
system_error: Text|null                                                                                   # :821
manual_score_reason: Text|null; manual_score_at: DateTime(tz)|null                                        # :823-824
```
`ExamAnswer.code_answer` (`:805`) is the second code source the AI grader reads (`services/ai_grading_service.py:37-40`).

**`ExamGrade` — `exam_grades` (`:747-757`)**: `UniqueConstraint("exam_id","student_id")` `:749`; `exam_id` FK `:752`; `student_id` FK `:753`; `score: Float = 0` `:754`.

### 5.8 Which columns carry the AI grading payload — exact definitions

**Per-submission grade — `code_grades`:**
```python
1139:    deterministic_details: Mapped[dict] = mapped_column(JSON, default=dict)      # NOT NULL
1140:    static_analysis:       Mapped[dict] = mapped_column(JSON, default=dict)      # NOT NULL
1141:    ai_result:             Mapped[dict | None] = mapped_column(JSON, nullable=True)
1142:    raw_response:          Mapped[str | None] = mapped_column(Text, nullable=True)
1143:    needs_teacher_review:  Mapped[bool] = mapped_column(default=False)           # Boolean inferred
1144:    review_reason:         Mapped[str | None] = mapped_column(Text, nullable=True)
```
- `ai_result` (`:1141`) — the **validated** model output, written as `grade.ai_result = ai_result.model_dump()` (`services/ai_grading_service.py:139`). Its schema is `AIGradeResponse` (`backend/app/schemas/ai_grading.py:220-247`): `rubric_version`, an `algorithm` dimension object and a `code_quality` dimension object (each with per-item `criterion_id / criterion / level / score / max_score / code_lines / evidence / reason_code / deduction_reason`), `triggered_cap_rule_ids`, `uncertainties`, `needs_teacher_review`, `review_reason`, and `student_feedback{strengths, issues, suggestions, code_suggestions[].diff}`.
- `raw_response` (`:1142`) — raw LLM text **before** validation (`ai_grading_service.py:140`, set from the pre-parse string).
- `deterministic_details` (`:1139`) — written as `{"groups": details, "system_errors": all_errs}` (`worker/judge_worker.py:563`, `:864`); source of `tests_passed`/`tests_total` (`api/exams.py:1123`). Its `groups` list is surfaced to students as `grading_breakdown.test_groups` (`services/student_ai_results.py:38,55`).
- `static_analysis` (`:1140`) — AST signals from `services/static_analysis.py`; **also fed back into the grading prompt** (`services/ai_prompts.py:166,197-199`).
- Numeric materialisation: `functional_score` `:1131`, `algorithm_score` `:1132`, `robustness_score` `:1133`, `quality_score` `:1134`, `raw_total` `:1135`, `score_cap` `:1136`, `final_score_100` `:1137`, `scaled_score` `:1138` — all `Float`, no precision type.
- Promotion into the domain row happens **only in `active` mode and only when no review is needed**: `sub.score = merged.final_score_100; sub.status = "graded"` (`ai_grading_service.py:148-153`). In `shadow` mode the official score is untouched — that is the whole point of the mode.

**Rubric generation payload — `question_rubrics`:**
```python
1102:    source_hash:     Mapped[str] = mapped_column(String(64))        # NOT NULL — ties rubric to question content
1103:    source_snapshot: Mapped[dict] = mapped_column(JSON)             # NOT NULL — the question snapshot sent to the LLM
1104:    rubric_json:     Mapped[dict] = mapped_column(JSON)             # NOT NULL — the validated rubric document
1105:    model_name:      Mapped[str] = mapped_column(String(120))       # NOT NULL
1106:    raw_response:    Mapped[str | None] = mapped_column(Text, nullable=True)
```
`rubric_json` validates against `RubricDocument` (`backend/app/schemas/ai_grading.py:130-168`): `algorithm_criteria` must total **20**, `quality_criteria` must total **10** with ids exactly `{Q1,Q2,Q3,Q4}`.

**Override audit — `grade_overrides`:** `original_snapshot` (`:1158`) and `replacement_snapshot` (`:1159`) are NOT NULL `JSON`; `reason` (`:1160`) NOT NULL `Text`; `reviewer_id` (`:1161`) NOT NULL FK. This is the only place a score change is recorded immutably.

**AI config on the question (prompt *inputs*)** — `judge_questions`: `teacher_constraints` (`:544`), `reference_solution` (`:545`), `test_groups` (`:546`; each group `{id, name, dimension ∈ {F,R}, max_score, tests}`, F-sum 60 / R-sum 10 enforced in `schemas/ai_grading.py:37-54`), `score_cap_rules` (`:547`; `condition_code ∈ {off_topic, hardcoded_public_examples, required_algorithm_missing, required_complexity_missing, dangerous_operation}` + `cap` + `description`), `public_cases` (`:537`), `hidden_tests` (`:538`), `grading_mode` (`:543`).

**Notable absence — no prompt is ever persisted.** The only `prompt` column in the file is `ExamQuestion.prompt` (`:773`), which is the exam *question text*. LLM prompts are built at runtime (`services/ai_prompts.py:36,119,161`) and discarded, so `raw_response` can be recovered without its prompt. If you want reproducible grading audits in the new project, **add a `prompt_snapshot` column** — dai cannot reconstruct one.

### 5.9 Status / enum vocabularies (all string-typed; only 4 are DB-CHECK-enforced)

| Column(s) | Vocabulary | Enforcement |
|---|---|---|
| `judge_questions.grading_mode` `:543`, `exam_questions.grading_mode` `:784` | `legacy` \| `shadow` \| `active` | Pydantic `Literal` (`schemas/ai_grading.py:63`) |
| `submissions.grading_status` `:577`, `exam_answers.grading_status` `:812` | `pending` \| `queued` \| `running` \| `completed` \| `system_error` | comment only (`:578`, `:813`) |
| `submissions.status` `:575` | `queued` (default) → `running` → `accepted` \| `wrong_answer` \| `runtime_error` \| `time_limit_exceeded` \| `system_error` \| `graded` | comment only; set by `worker/judge_worker.py:62-72` |
| `code_grades.status` `:1130` | `pending` → `queued` → `running` → `completed` \| `review_required` | comment/default only |
| `question_rubrics.status` `:1101` | `draft` → `locked` | comment/default only |
| `exam_submissions.status` `:712` | `started` \| `submitted` \| `grading` \| `graded` \| `review_required` | **CHECK** `:704-706` |
| `exam_questions.question_type` `:772` | `single_choice` \| `multi_choice` \| `fill_blank` \| `code` | **CHECK** `:764-767` |
| `environment_drafts.state` `:1509` | `editing` \| `building` \| `ready` \| `failed` | **CHECK** `:1489` |
| `environment_publications.action` `:1577` | `publish` \| `rollback` \| `migration_baseline` | **CHECK** `:1560` |
| `import_policy_mode` family `:453,556,861,905,598` | `unrestricted` \| `restricted` (+ `inherit` at question level `:557`) | comment only |
| `assignments.status` `:443`, `exams.status` `:616` | `draft` → `published` | comment/default only |
| `assignments.audience_mode` `:458`, `exams.audience_mode` `:626` | `all_enrolled` \| `selected_classes` \| `whitelist_only` | `services/audience_service.py:26-29` |
| `environment_versions.status` `:1360` | `draft` \| `queued` \| `building` \| `available` \| `failed` \| `inactive` | comment `:1361` |
| `environment_build_jobs.status` `:1443` | `queued` \| `building` \| `succeeded` \| `failed` \| `timed_out` | comment `:1444` |


### 5.10 Notebook / experiment execution tables

**`NotebookTemplate` — `notebook_templates` (`:833-876`)**
```python
__table_args__ = (ForeignKeyConstraint(["current_version_id"], ["notebook_template_versions.id"],
                  use_alter=True, name="fk_template_current_version"),)                      # :839-842
id: Integer PK; name: String(200); description: Text|null; status: String(20)="draft"        # :845-848
current_version_id: Integer, nullable                                                        # :849
owner_id: ForeignKey("users.id")                                                             # :850
draft_cells: JSON, default=list; draft_revision: Integer=1; draft_metadata: JSON, default=dict  # :851-853
draft_assets_dir: String(500), nullable                                                      # :854
draft_environment_version_id: BigInteger FK environment_versions.id, nullable=False,
                              default=resolve_basic_env_version_id, index=True               # :857-860
draft_import_policy_mode: String(16), nullable=False, default="unrestricted"                 # :861-863
draft_allowed_imports:    JSON, nullable=False, default=list                                 # :864
```

**`NotebookTemplateVersion` — `notebook_template_versions` (`:879-914`)** — the immutable published snapshot the runner validates cells against:
```python
__table_args__ = (UniqueConstraint("template_id","version_number", name="uq_version_number_per_template"),  # :883
                  Index("ix_template_versions_environment_version_id","environment_version_id"),)        # :884
id: Integer PK                                                                               # :887
template_id: ForeignKey("notebook_templates.id"), index=True                                 # :888
version_number: Integer                                                                      # :889
sha256: String(64)                                                                           # :890
cells: JSON, default=list          # ← immutable cell list (id/type/source/order/…)          # :891
cell_order: JSON, default=list                                                               # :892
notebook_metadata: JSON (column name "metadata"), default=dict                               # :893
assets_dir: String(500), nullable                                                            # :894
published_at: DateTime(timezone=True), nullable, server_default=func.now()                   # :895-897
published_by_id: ForeignKey("users.id")                                                      # :898
environment_version_id: BigInteger FK environment_versions.id, nullable=False,
                        default=resolve_basic_env_version_id                                  # :901-904
import_policy_mode: String(16), nullable=False, default="unrestricted"                       # :905-907
allowed_imports:    JSON, nullable=False, default=list                                       # :908
```

**`ExperimentModule` — `experiment_modules` (`:988-1001`)**
```python
id: Integer PK; name: String(200); description: Text|null; entry_url: String(500)|null        # :991-994
template_id: ForeignKey("notebook_templates.id"), nullable=True                               # :995
owner_id: ForeignKey("users.id"), nullable=True, index=True                                   # :996
status: String(30)="draft", index=True; due_at: DateTime(tz), nullable                        # :997-998
```

**`ExperimentRecord` — `experiment_records` (`:1007-1044`)** — student notebook state + **cells/outputs as JSON**:
```python
__table_args__ = (UniqueConstraint("lesson_id","student_id", name="uq_record_lesson_student"),    # :1011
                  UniqueConstraint("module_id","student_id", name="uq_record_module_student"),    # :1012
                  CheckConstraint("(lesson_id IS NULL) != (module_id IS NULL)", name="ck_record_entry_type"))  # :1013-1016
id: Integer PK                                                                                # :1019
lesson_id: ForeignKey("lessons.id"), nullable=True, index=True                                 # :1020
module_id: ForeignKey("experiment_modules.id"), nullable=True, index=True                      # :1021
template_version_id: ForeignKey("notebook_template_versions.id")                               # :1022
student_id: ForeignKey("users.id"), index=True                                                 # :1023
status: String(30)="started"                                                                   # :1024
cells_sources:  JSON, default=dict    # {cell_id: source}                                      # :1025
cells_outputs:  JSON, default=dict    # {cell_id: {outputs, execution_count, execution_time_ms}}  # :1026
record_revision: Integer=1            # optimistic concurrency                                 # :1027
started_at / submitted_at / completed_at: DateTime(tz), nullable                                # :1028-1030
environment_version_id: BigInteger FK environment_versions.id, nullable=False,
                        default=resolve_basic_env_version_id, index=True                        # :1033-1036
```

**`ExperimentSubmission` — `experiment_submissions` (`:1047-1075`)**
```python
__table_args__ = (UniqueConstraint("record_id","attempt_number", name="uq_experiment_submission_attempt"),       # :1055
                  UniqueConstraint("record_id","client_request_id", name="uq_experiment_submission_idempotency"))  # :1056
id: Integer PK                                                                                  # :1059
record_id: ForeignKey("experiment_records.id"), index=True                                       # :1060
attempt_number: Integer=1                                                                        # :1061
client_request_id: String(36), nullable=True, index=True    # UUID, idempotency key              # :1062
cells_snapshot:   JSON, default=dict      # immutable                                            # :1063
outputs_snapshot: JSON, nullable          # immutable                                            # :1064
submitted_at: DateTime(tz), server_default=func.now()                                            # :1065-1067
score: Float|null; feedback: Text|null                                                           # :1069-1070
reviewed_by_id: ForeignKey("users.id"), nullable=True; reviewed_at: DateTime(tz), nullable       # :1071-1072
```

### 5.11 `Assignment` — `assignments` (`:436-491`) — the coupling root for the judge path
```python
id: Integer PK; course_id: ForeignKey("courses.id"), index=True                                  # :439-440
title: String(200); description: Text|null; status: String(30)="draft", index=True               # :441-443
due_at / published_at: DateTime(tz), nullable                                                    # :444-445
created_by_id: ForeignKey("users.id"), nullable=True                                             # :446
environment_version_id: BigInteger FK environment_versions.id, nullable=False,
                        default=resolve_basic_env_version_id, index=True                          # :449-452
import_policy_mode: String(16), nullable=False, default="unrestricted"                            # :453-455
allowed_imports:    JSON, nullable=False, default=list                                            # :456
audience_mode: String(20)="all_enrolled", server_default="all_enrolled", nullable=False, index=True  # :458-460
```

### 5.12 `EnvironmentVersion` — `environment_versions` (`:1337-1402`) — how the sandbox image is resolved
```python
__table_args__ = (UniqueConstraint("profile_id","version_number", name="uq_env_version_per_profile"),  # :1346
                  UniqueConstraint("profile_id","id", name="uq_env_version_profile_id"),               # :1347
                  Index("ix_env_versions_profile_id","profile_id"), Index("ix_env_versions_status","status"))  # :1348-1349
id: BIGINT_PK PK                                                                                  # :1352
profile_id: BigInteger FK environment_profiles.id, nullable=False                                  # :1353-1355
version_number: Integer, nullable=False                                                           # :1356
source_version_id: BigInteger FK environment_versions.id (self), nullable                          # :1357-1359
status: String(20)="draft"   # draft|queued|building|available|failed|inactive                     # :1360-1361
build_mode: String(16)="legacy"                                                                    # :1362-1364
base_image_ref: String(255), nullable=False                                                        # :1365
image_tag:  String(255), nullable; image_digest: String(255), nullable                             # :1366-1367
python_version: String(32)="3.12"                                                                  # :1368-1370
minimum_memory_mb: Integer, nullable=False                                                         # :1371
manifest_sha256: CHAR(64), nullable=False; dockerfile_sha256: CHAR(64), nullable                    # :1372-1373
requested_spec: JSON, nullable=False, default={"schema_version":1,"python_packages":[],"system_packages":[]}  # :1374-1378
resolved_spec:  JSON, nullable; resolution_lock: JSON, nullable; resolution_lock_sha256: CHAR(64)|null  # :1379-1381
resolved_packages: JSON, nullable                                                                  # :1384
created_by_id: FK users.id|null; available_at / first_published_at: DateTime(tz)|null               # :1385-1387
first_published_by_id: FK users.id|null                                                            # :1388-1390
```
`image_digest` (`:1367`) is what `resolve_run_image_ref()` hands to `docker run` — i.e. the immutable sandbox image reference.

### 5.12b The rest of the environment cluster ("cluster-generic")

`EnvironmentVersion` is not standalone: it is one member of a 7-table control plane that builds and publishes the immutable sandbox images. If the K-12 port keeps the environment-catalogue idea, port the cluster as a unit — it only depends on `users`.

| Table | Class line | Table name line | Key shape |
|---|---|---|---|
| `PackageCatalog` | `:1268` | `:1276` | `UniqueConstraint(normalized_name, locked_version, source_key)` `:1277-1279`; `BIGINT_PK` `:1281`; `import_names` JSON `:1285`; `source_key ∈ {pypi, pytorch_cpu}` `:1287`; self-FK `supersedes_id` `:1289-1291` |
| `EnvironmentProfile` | `:1301` | `:1304` | `UniqueConstraint(slug)` `:1306`; self-referential composite FK to `environment_versions(profile_id, id)` with `use_alter=True` `:1309-1314`; `status ∈ {active, inactive}` `:1321` |
| `EnvironmentVersion` | `:1337` | `:1344` | see above — `image_digest` `:1367` is the frozen sandbox ref |
| `ProfileVersionPackage` | `:1405` | `:1411` | pure join table; **composite PK** `(environment_version_id, package_catalog_id)` `:1413-1418`; no `TimestampMixin` |
| `EnvironmentBuildJob` | `:1425` | `:1433` | `status ∈ {queued,building,succeeded,failed,timed_out}` `:1443-1444`; lease fields `worker_id`/`lease_token`/`lease_until`/`heartbeat_at` `:1453-1457`; self-FK `retry_of_id` `:1450-1452`; `log_text` `:1458` |
| `EnvironmentDraft` | `:1473` | `:1476` | `profile_id` is the **PK** `:1496-1498`; `state ∈ {editing,building,ready,failed}` CHECK `:1489`; composite FKs to `environment_versions` `:1478-1487` |
| `EnvironmentPublication` | `:1542` | `:1545` | two composite `ondelete="RESTRICT"` FKs to `environment_versions` `:1547-1558`; `action ∈ {publish,rollback,migration_baseline}` CHECK `:1560` |

Two design ideas here are worth copying even if you do not copy the tables: (a) **immutable version rows** — once `status='available'`, package set, base image, resource params and `image_digest` are frozen (`:1338-1341`), so a historical submission always re-runs against exactly the image it was judged with; (b) **`EnvironmentBuildJob`'s lease/heartbeat/retry state machine** (`:1449-1457`) is generic for any long async build.

### 5.12c Per-table reuse verdict (compact)

| Table | Verdict |
|---|---|
| `scheduler_leases` `:730` | **Fully self-contained** — zero FKs, zero domain columns. Lift verbatim. |
| `question_rubrics` `:1081` | **Best reuse candidate** — payload columns are domain-neutral; drop the XOR FK pair `judge_question_id` `:1094` / `exam_question_id` `:1097` and it is a standalone versioned rubric store. |
| `code_grades` `:1110` | **Payload generic, identity entangled** — everything lifts except the XOR FKs `submissions.id` `:1122` / `exam_answers.id` `:1125` and `rubric_id` `:1128`. |
| `grade_overrides` `:1152` | **Pattern generic, FKs not** — the audit trio `:1158-1160` is reusable; drop `code_grades.id` `:1157`. |
| `judge_questions` `:527` | **Core portable** — drop `assignment_id` `:531` and `environment_version_id` `:553`; the execution core (`function_name`, `signature`, `starter_code`, `public_cases`, `hidden_tests`, limits, AI config) lifts cleanly. |
| `submissions` `:564` | **Core portable** — drop `question_id` `:572`, `student_id` `:573`, `environment_version_id` `:594-597`; queue state machine + result columns `:577-591` are generic. |
| `environment_*` / `package_catalog` | **Cluster-generic** — port as a unit; only depends on `users`. |
| `notebook_templates` `:833`, `notebook_template_versions` `:879` | **Entangled** (FKs to `users.id`, `environment_versions.id`, plus the deferred self-FK `:839-842`); the immutable `cells`/`cell_order` snapshot pattern is portable. |
| `experiment_records` `:1007` | **Most entangled table in the file** — FKs to `lessons.id` `:1020`, `experiment_modules.id` `:1021`, `notebook_template_versions.id` `:1022`, `users.id` `:1023`, `environment_versions.id` `:1033-1036`, plus the lesson-XOR-module CHECK `:1013`. |
| `experiment_submissions` `:1047` | **Entangled** (FKs to `experiment_records.id` `:1060`, `users.id` `:1071`); the idempotency pattern `:1056`/`:1062` is generic. |
| `assignments` `:436`, `assignment_audience_*` `:493`/`:508` | **Entangled** — the whole course/teaching-class audience graph. |
| `exams` `:610`, `exam_*` `:658`-`:827` | **Entangled** — drop entirely unless the K-12 port needs exams; doing so also removes both XOR constraints from `code_grades`/`question_rubrics`. |
| `studio_asset_manifests*` `:917`/`:954` | **Entangled** — depends on `storage_objects` + template/version FKs. |

### 5.13 Which tables are load-bearing for a rerun in a new project

The **minimum viable set** for "run code + judge + AI grade" is: `users` (or substitute your own identity), `submissions` (5.2), `judge_questions` (5.1), `code_grades` (5.3), `question_rubrics` (5.4), `grade_overrides` (5.5), `environment_versions` (5.12). Everything else (`assignments`, `courses`, `course_enrollments`, `assignment_audience_*`, `notebook_templates*`, `experiment_*`, `exams`, `exam_*`) exists to answer *"may this user submit this question right now, and who owns it"* — a concern a K-12 platform will almost certainly model differently.

Also note: `CodeGrade` and `QuestionRubric` are **polymorphic via XOR FKs** (`:1114-1117`, `:1085-1088`) to serve both `submissions` and `exam_answers`. If you only need the judge path, you can drop `exam_answer_id` and the `ck_code_grade_xor_target` CHECK, and drop `exam_question_id` + `ck_rubric_xor_target`, making both tables linear and much easier to port.

---

## 6. Frontend state / data layer

**No react-query, no Redux — this is Vue 3 + Pinia + axios.**

| Concern | Module | Notes |
|---|---|---|
| HTTP client | `frontend/src/api/client.js` (133 lines) | axios instance, `baseURL: '/api/v1'` `:12`, `withCredentials: true` `:15` (HttpOnly refresh cookie), 30 s timeout `:14`. Request interceptor injects `Authorization: Bearer <accessToken>` from the Pinia auth store `:19-25`. Response interceptor implements **401 → cookie refresh → single-flight retry queue** with a `sessionGeneration` guard against logout races (`:41-131`). Endpoint modules import this default export. |
| Judge endpoints | `frontend/src/api/judge.js` (9 lines) | `submit`, `list`, `get`, `getResult`, `sampleRun`. Fully generic — a thin, easily transliterated wrapper. |
| Notebook endpoints | `frontend/src/api/experiments.js` (73 lines) | `ensureForLesson`/`ensureForModule`/`getRecordDetail`/`saveCells`/`executeCell`/`interrupt`/`restart`/`submitRecord`/`listSubmissions`/`getSubmission`/`updateReview` + module CRUD. |
| AI grading endpoints | `frontend/src/api/aiGrading.js` (20 lines) | `getStatus`/`getConfig`/`updateConfig`/`listRubrics`/`generateRubric`/`generateTestGroups`/`updateRubric`/`lockRubric`/`listGrades`/`getGrade`/`retryGrade`/`overrideGrade`/`regradeQuestion`. Note the deliberate long timeouts for the synchronous LLM calls: `timeout: 200000` `:10` and `timeout: 300000` `:12`. |
| Studio endpoints | `frontend/src/api/studio.js` (45 lines) | incl. `previewRun`/`previewInterrupt`/`previewReset` `:42-44`. |
| Notebook store | `frontend/src/stores/experiment.js` (371 lines) | **The most valuable frontend artifact.** Owns cells, dirty-tracking, autosave, optimistic concurrency, execute, submit. |
| Studio store | `frontend/src/stores/studio.js` (423 lines) | Teacher-side draft/version/preview state. |
| Auth store | `frontend/src/stores/auth.js` | In-memory access token + `sessionGeneration`. |
| App store | `frontend/src/stores/app.js` | `showToast` used for all error surfacing. |
| Route guards | `frontend/src/router/index.js` + `stores/experiment.js:219-231` `canNavigate()` | Unsaved-changes guard. |
| HTML sanitizer | `frontend/src/utils/sanitize.js` | DOMPurify wrapper used by `MarkdownCell` and the assignment description (`AssignmentDetailView.vue:9,47`). |
| Request de-dup | `frontend/src/utils/latestRequest.js` | `createLatestRequestGuard()` used in `ExperimentView.vue:23,36-47` to drop stale list responses. |

**Autosave design** (`stores/experiment.js`) — genuinely reusable *design*, not code:
- Debounce: `scheduleDebounce()` sets a **1200 ms** timer → `flushSave()` (`:135-139`).
- Safety net: `_startSafety()` runs `setInterval(..., 30000)` and force-flushes if still dirty (`:39-46`).
- **Serial drain loop with revision-based optimistic concurrency**: `_drainDirtySources()` (`:142-195`) repeatedly PUTs the current `dirtySources` map with `recordRevision`, updates `recordRevision` from the response (`:157`), and only deletes entries whose value is unchanged since the request (`:177-183`) — so edits made *during* an in-flight save are preserved rather than clobbered. `REVISION_CONFLICT` sets a sticky `conflict` flag that blocks further autosave until reload (`:160-165`, `:129`).
- Navigation guard: `canNavigate()` (`:219-231`) flushes and `window.confirm`s if the flush failed; wired in `NotebookPlayer.vue:57-63` (`onBeforeRouteLeave`), `:66-80` (`onBeforeRouteUpdate`) and `:87-95` (`beforeunload`).
- API shape: `PUT /api/v1/experiments/records/{record_id}/cells` with `{ cells: {cell_id: source}, record_revision }` (`api/experiments.js:21-26`; schema `ExperimentCellsSaveRequest` `backend/app/schemas/__init__.py:1026-1029`).

**Submit idempotency** (`stores/experiment.js:287-338`): generates `crypto.randomUUID()` once (`:300-302`), flushes pending edits first (`:291-297`), POSTs `{client_request_id}` (`:306-309`), and **deliberately keeps the same id on network failure so a retry is idempotent** (`:331` comment) — cleared only on success (`:323`). Matches the DB unique constraint `uq_experiment_submission_idempotency` (`models/__init__.py:1056`) and the server-side double-check in `experiments.py:896-925`.

**Notebook run state** (`stores/experiment.js:244-265`): a single `executingCellId` ref drives the whole UI (`CodeCell` `disabled`/`isExecuting` via `NotebookPlayer.vue:214-216`), and error handling maps `IMPORT_NOT_ALLOWED` / `IMPORT_NOT_INSTALLED` / `ENVIRONMENT_IMAGE_MISSING` to a **synthesized error output** rather than a toast (`:236-242`, `:258-259`), while `409` becomes the toast `'Kernel 正忙，请等待'` (`:260`).

**Judge polling state is NOT in a store** — it lives as component-local refs in `AssignmentDetailView.vue` (`submitResult`, `submitPolling`, `submitPollTimer`, `submitPollCount`, `MAX_POLL_COUNT`, `:27`, `:64-67`, `:266-267`, `:314-343`). This is the weakest part of the frontend: polling, terminal-state classification, and completion predicates are entangled with a 1282-line view component.

**Ports cleanly:** `api/client.js`'s interceptor logic (as a `fetch`/axios wrapper), all five `api/*.js` endpoint maps (pure path+payload dictionaries), and the autosave/idempotency *algorithms*. **Does not port:** every `.vue` file and anything Pinia-shaped. `utils/sanitize.js`, `utils/latestRequest.js`, `utils/format.js`, `utils/status.js` are framework-agnostic and copy verbatim.

---

## 7. Reusability verdict

| # | Artifact | Verdict | Why |
|---|---|---|---|
| **a** | **Editor component** (`CodeCell.vue`, `QeCodeEditor.vue`, `CodeViewer.vue`) | **REWRITE** (logic ADAPT) | The *library choice* is right and directly transferable: CodeMirror 6 has first-class React bindings (`@uiw/react-codemirror`), and the exact npm set to install is `@codemirror/{view,state,commands,lang-python,language,theme-one-dark}` + `@lezer/highlight` (`package.json:19-23,28`; note `@codemirror/language` and `@lezer/highlight` are **undeclared** despite being imported at `CodeCell.vue:74-75` — declare them explicitly when porting). But the components themselves are Vue SFCs and cannot be reused. Worse, the two-way binding is structurally poor: full-document replace on external change (`CodeCell.vue:47-53`) kills undo history and cursor position, and a `readonly` flip destroys and rebuilds the entire editor (`:198-205`). The theme *tokens* (`:83-129`) and the dynamic-import-with-textarea-fallback pattern (`:61-77`, `:223-231`) are worth copying conceptually. Python-only, no `language` prop — add one. |
| **b** | **Output renderer** | **REWRITE** | There is **no shared renderer component** to reuse (grep confirms no `OutputRenderer`/`CellOutput` anywhere). Rendering is duplicated across `CodeCell.vue:248-265` (Jupyter-shaped, 4 branches), `AssignmentDetailView.vue:507-543` (fake terminal, status text only), and `MarkdownCell.vue` (markdown only). The `CodeCell` implementation is also **buggy for the most common case**: `execute_result`/`display_data` with `text/plain` falls through to `JSON.stringify(output)` because `outputText()` (`:178-185`) never reads `content.data['text/plain']`, and `text/html` is not rendered at all. Only `image/png` is supported (`:189`). Reuse the **wire contract**, not the code: `[{msg_type, content}]` per Jupyter IOPub, exactly as produced by `backend/docker/kernel/kernel_runner.py:49-56`. |
| **c** | **Run API** | **ADAPT** | `POST /api/v1/judge/questions/{qid}/sample-run` is the closest to standalone (body is `{question_id, code}`; returns `{output, status, execution_time_ms, diagnostic}`), and `POST /api/v1/experiments/records/{rid}/cells/{cid}/execute` also takes a bare `{code}`. But both are gated on dai domain objects (assignment/course/enrollment for the former, `judge.py:276-291`; record+template-version ownership for the latter, `experiments.py:640-657`). **What genuinely ports: the executor functions** — `worker/judge_worker.py:101-140 _run_docker_pytest` (pure `(workdir, settings, timeout, memory, image_ref) → (stdout, stderr, rc, ms)`, already hardened with `--network none --cap-drop ALL --read-only --pids-limit 50 --user 1000:1000`) and `services/kernel_manager.py:353-487` + `docker/kernel/kernel_runner.py` for the persistent-kernel variant. Wrap either behind a new `POST /run {code, language, tests?}` and drop the domain lookups. |
| **d** | **Submit / judge API** | **ADAPT (heavy)** | `POST /api/v1/judge/submissions` + `GET /judge/submissions/{id}/result` + 1 Hz client polling (`AssignmentDetailView.vue:314-339`) is a clean, correct async-judge pattern (atomic queue claim in `services/judge_queue.py:47-...`, DB as source of truth, Redis only as a wakeup, 3-attempt retry). The **contract** should be copied: 201-with-`id` → poll → terminal status. The **implementation** cannot be lifted: `create_submission` is ~60 lines of enrollment/deadline/max-attempt/audience gating (`judge.py:73-127`), and `Submission.question_id`/`student_id` FKs (`models:572-573`) hard-wire it to dai's `JudgeQuestion`+`User`. Also consider replacing the 1 Hz `setInterval` with SSE or a backoff — 120 requests per submission is wasteful and the completion predicate is subtle (`AssignmentDetailView.vue:303-312`). |
| **e** | **AI grading API** | **NOT_REUSABLE** | **No endpoint accepts code or language.** All 13 `/api/v1/ai-grading/*` routes are `{grade_id}`- or `{kind}/{question_id}`-addressed, import 12 domain models (`ai_grading.py:16-19`), hard-limit `kind ∈ {assignment, exam}` (`:126`), enforce teacher-course ownership (`:98-137`), and write back into `Submission.score/status` and `ExamAnswer.score/grading_status` (`:868-874`). The actual grading function `grade_code_submission` (`services/ai_grading_service.py:21-24`) loads its inputs from the DB, so it is not standalone either. Only `GET /ai-grading/status` (`:48-54`, returns `{enabled, ready}`) is domain-free. **Reusable value is the design, not the code:** the two-phase deterministic-then-LLM scoring pipeline, the `pending→queued→running→completed|review_required` state machine with stale recovery (`services/ai_grading_queue.py:139-243`), the `DeepSeekClient` OpenAI-compatible wrapper (`services/ai_client.py:90`), the prompt templates (`services/ai_prompts.py`), and the numeric score-validation layer (`services/ai_score_validation.py`). A K-12 port should expose a fresh `POST /ai-grade {code, language, rubric?}` that reuses `ai_client.py` + `ai_prompts.py` + the queue mechanics behind a thin new adapter. Two behavioural details to preserve: the official score is overwritten **only** in `active` mode and only when `needs_teacher_review` is false (`services/ai_grading_service.py:148-153`; `shadow` leaves the old score intact by design), and the grader silently degrades when `ai_ready` is false — the worker does not even construct a client (`worker/judge_worker.py:905-916`) and the two generate endpoints return `503 AI_NOT_READY` before any network call (`:265-266`, `:330-331`). |
| **f** | **Data model** | **ADAPT** (subset) | Take the **minimum viable six tables** and drop the FK fan-out: `submissions` (`models:564-604`), `judge_questions` (`:527-561`), `code_grades` (`:1110-1149`), `question_rubrics` (`:1081-1107`), `grade_overrides` (`:1152-1161`), `environment_versions` (`:1337-1402`). Two concrete simplifications: (1) because `code_grades` and `question_rubrics` are **XOR-polymorphic** to serve the exam path too (`:1114-1117`, `:1085-1088`), you can delete `exam_answer_id`/`exam_question_id` and the two CHECK constraints, making both tables linear; (2) `submissions.environment_version_id` is `nullable=False` with a `default=resolve_basic_env_version_id` (`:594-597`) — a hard dependency on dai's environment catalogue that a new project must either port or replace with a simple `image_ref` string column. The AI payload is well-factored and worth preserving verbatim: JSON `code_grades.ai_result` + `raw_response` (`:1141-1142`), `deterministic_details`/`static_analysis` (`:1139-1140`), seven numeric score columns (`:1131-1138`), with the consumer contract documented in `services/student_ai_results.py:33-56`. Two caveats: add the missing `prompt_snapshot` column (§5.8), and note that `submissions.environment_version_id` has **no `ondelete`**, so deleting a submission will orphan its `CodeGrade` row. If notebooks are in scope, `notebook_templates`/`notebook_template_versions`/`experiment_records`/`experiment_submissions` (`:833-914`, `:1007-1075`) are a solid design — `cells_sources`/`cells_outputs` as JSON (`:1025-1026`), `record_revision` optimistic concurrency (`:1027`), and `client_request_id` idempotency (`:1062`) — but `ExperimentRecord`'s XOR `lesson_id`/`module_id` CHECK (`:1013-1016`) and `template_version_id` FK must be re-modelled. |

### Migration shortlist, in order of payoff
1. **`backend/app/worker/judge_worker.py:101-140`** `_run_docker_pytest` — copy nearly verbatim; it is the actual sandbox and carries the security flags.
2. **`backend/app/services/kernel_manager.py` + `backend/docker/kernel/kernel_runner.py`** — copy if you want persistent-kernel notebooks with plots; requires Docker + Redis + a container image with `ipykernel`.
3. **`backend/app/services/ai_client.py` + `ai_prompts.py` + `ai_score_validation.py` + `ai_grading_queue.py`** — copy as an isolated "AI grading engine" package, then write a new thin `POST /ai-grade` in front of it.
4. **DB**: `submissions`, `judge_questions`, `code_grades`, `question_rubrics`, `grade_overrides` — port with the XOR FKs removed.
5. **`frontend/src/api/client.js` + `api/{judge,experiments,aiGrading}.js`** — transliterate to a React API layer; the interceptor/refresh logic is the valuable part.
6. **`stores/experiment.js:135-231` autosave + revision drain + idempotent submit** — reimplement the algorithms in a React hook.
7. **CodeMirror 6 + a new output renderer** — install the same packages; write the renderer fresh against the IOPub contract.

### Explicit non-goals
`backend/app/api/jupyter.py` (iframe handoff, disabled by default, two 410 tombstones), `backend/app/api/notebooks.py` (catch-all 410), `frontend/src/components/ai/StudentAIGradingResult.vue` (hard-coded dai rubric weights 60/20/10/10 at `:15-23`), and `backend/app/api/studio.py` (teacher template CRUD, `require_roles("admin","teacher")` at `studio.py:40`).
