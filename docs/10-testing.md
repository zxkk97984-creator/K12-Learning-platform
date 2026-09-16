# 10 · 测试体系

> 证据来自 `.audit/D-testing.md`（870 行）+ 实跑结果。**本次审计未修改任何源码或测试。**

---

## 0. 实测数字（2026-09-16）

| 套件 | 文件 | 用例数 | 结果 |
| --- | --- | --- | --- |
| 后端 pytest（默认，指向**开发库**） | 40 + `conftest.py` | **384 collected**（0 skipped / 0 xfail） | **2 failed / 382 passed**，59.9s |
| 后端 pytest（**全新库**，复刻 CI 顺序） | 同上 | 384 | **1 failed / 383 passed**，62.0s |
| 后端 pytest（同一库，**第二次**运行） | 同上 | 384 | **384 passed / 0 failed**，53.8s |
| 前端 Vitest | 49 | **258** | **258 passed / 0 failed**，5.1s |
| 前端 `tsc --noEmit` | — | 169 文件 | **0 错误**（`strict` + `noUnusedLocals`） |
| 前端 `vite build` | — | 164 模块 | **成功**（主包 272.64 kB / gzip 85.57 kB） |
| Playwright E2E | 11 spec | 33（4 projects） | **未执行**（会写入开发库） |

> **基线文档声称「384 passed / 0 failed」**（`docs/plans/current-phase.md:14`）。
> 实测该数字**只在已被污染的库上第二次运行时**成立。首次在干净库上跑必然 1 红。

---

## 1. 🔴 CI 的 backend job 目前是**确定性红色**

复刻 `ci.yml` 的完全相同顺序于全新数据库：

```
alembic upgrade head      → OK
validate_library --all    → PASS（books=25）
import_library --all      → books=25 knowledge=56
pytest -q                 → 1 failed, 383 passed   ← 确定失败
```

失败用例：`tests/test_content_ai_visibility.py::TestChapterSourceVisibility::test_published_chapter_loads_source`
（`assert source is not None`，`:169`）

**根因（顺序 bug，不是 flaky）**
- `TestChapterSourceVisibility` 是该文件**第一个类**（`:159`），4 个方法**不接收 `client` fixture**
- 造数据的 `_ensure()` 只在模块级 `client` fixture 中被调用（`:129-133`），
  而该 fixture 直到后面的 `TestQuizApiVisibility`（`:185+`）才第一次实例化
- **证明**：夹具书 `b3000000-…-0001` 的行时间戳创建于运行**期间**、失败**之后**
- 在同一（已变脏的）库上重跑该用例 → 通过

**第二个失败（仅开发库）**：`tests/test_async_memory_consolidation.py:350` `assert 404 == 201`。
夹具书 `b6000000-…-00a1` 处于 `ARCHIVED`。
根因见 §4：`archive_noncorpus.py` 归档了测试夹具书。

---

## 2. 测试基础设施：**基本不存在**

`backend/tests/conftest.py` 全文 **11 行**：

```python
import os
os.environ["ENVIRONMENT"] = "test"
os.environ.setdefault("TTS_PROVIDER", "mock")
os.environ["AI_PROVIDER"] = "mock"
os.environ["AI_MODEL"] = "mock-model"
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["VOICE_PROVIDER"] = "mock"
os.environ["REDIS_ENABLED"] = "false"
os.environ["JWT_SECRET"] = "test-only-32bytes-jwt-secret-0123456789"
```

**它没有做的事**：
| 缺失 | 后果 |
| --- | --- |
| **不设置 `DATABASE_URL`** | pydantic-settings 读 `backend/.env` → **直连开发者真实数据库** |
| 无 fixture（0 个） | 无统一的 client / db / 用户夹具 |
| 无 schema create/drop | 依赖「跑之前先 `alembic upgrade head`」，且**永不清库** |
| 无事务回滚 / truncate | 测试之间的隔离靠各模块手写 `_ensure*()` 造数器 |
| 无 `.env.test` | 没有任何测试环境配置分离 |
| 无 Redis/MinIO | `REDIS_ENABLED=false`；CI 里明明起了 Redis 却被绕过 |

**项目自己知道这个风险**：`scripts/audit-check.sh:30-49` **硬性拒绝**在 `DATABASE_URL` 未设置、
或与开发库同名时运行。但 **`pytest` 没有这道守卫**，且 `audit-check.sh` **从未被任何 CI 脚本调用**。

`tests/test_learning_api.py:207-208` 的注释自认：「共享开发库中可能残留其它测试模块的进度行」。

> ⚠️ **`scripts/test-db.sh` 不是测试库搭建脚本** —— 它只是手动 `shuangling_audit` 库的
> backup/restore 工具，**没有任何东西调用它**。

---

## 3. 测试如何运行（三种环境互不相同）

| 环境 | DATABASE_URL 来源 | 数据库状态 |
| --- | --- | --- |
| 本地裸跑 `uv run pytest` | `backend/.env` | **开发者真实开发库**（159 users / 103 conversations / 8442 idempotency_keys） |
| 本地 `bash scripts/ci.sh` | 从 `backend/.env` 解析并 **export** | 同上 → **会污染开发库** |
| GitHub CI（`ci.yml`） | workflow `env:` | service container 全新库 |
| 文档声称的基线 | 隔离库 `shuangling_audit` | 与上面三者都不同 |

→ **同一套测试，四种数据状态**。这解释了「本地绿 / CI 红」以及基线数字不可复现。

---

## 4. `archive_noncorpus.py` 归档了测试夹具书（跨模块污染）

`app/scripts/archive_noncorpus.py:84,98` 归档所有非语料书，留了一个逃生口
`book_id::text not like '5e3%0000%'`。
但 **17 个测试夹具书的 UUID 全部使用 `bN000000-…` 约定**，没有一个匹配该逃生口
→ **全部 17 本都可被归档**。当前有 3 本夹具书被**非预期地**置为 `ARCHIVED`
（`b1000000-…`、`b2000000-…`、`b6000000-…00a1`），并直接导致上述第二个测试失败。

配套问题：三个 `_ensure*()` 造数器是 **create-if-absent 且不修复 status**，
所以一旦夹具被归档，测试就**永久失败**（除非手工改库）。

---

## 5. 覆盖率缺口

### 后端**完全无测试**的模块
- `app/infrastructure/metrics_registry.py`（0 引用）
- `app/infrastructure/observability.py`（0 引用）
- `GET /metrics` 端点
- `S3ObjectStorage.put/get/exists`（只测了 `sign_request` 与缺配置分支）
- `app/scripts/archive_noncorpus.py`、`preview_data_governance.py`、`reindex_embeddings.py`

### 前端无测试
`MemoriesPage`、`LoginPage`、`ReaderPage` 本体、`features/memory/`、`features/feedback/`、
`features/voice/audio-capture.ts`、`features/quiz/lib.ts`、`QuickActions`、`ConversationPanelContent`、
`CompanionPanel`/`CompanionPetPicker`/`useCompanionDock`/`useSpriteFrame`、
`app/providers/query.ts`（`shouldRetry`/`retryDelay`）。
`AdminDashboard`、`AdminLayout` **既无单测也无 e2e**。

### 无覆盖率工具
无 pytest-cov、无 vitest coverage、CI 中**无 ruff / mypy / eslint**。
（本地存在 `.ruff_cache/`，但 ruff 不在 `pyproject.toml` 依赖中。）

---

## 6. 「测试剧场」清单（测试通过但不验证生产路径）

| 位置 | 问题 |
| --- | --- |
| `test_ai_provider.py:159,206` | monkeypatch 手写 `FakeClient`。**从未执行**：`_http_proxy_url()`（测试中 0 引用）、HTTP ≥400 分支（`openai_compatible.py:88-92`）、真实 client 构造、`last_usage` 捕获 |
| 全套后端测试 | 唯一出现过的假状态码是 **200**（`test_ai_provider.py:138,184`、`test_embedding.py:38,96`）→ **零错误路径 HTTP 测试** |
| `test_redis_lock.py:1,12` | docstring 自认「in-memory fake」；CI 真起了 Redis（`ci.yml:25-33`）却被绕过 |
| `test_phase4_platform.py:55-95` | `S3ObjectStorage.put/get/exists` 从未被调用；工厂测试只断言「返回了实例」 |
| `test_content_cache.py:1` | 「database and Redis are both replaced with fakes」 |
| `AdminPages.test.ts:33` | mock 掉**整个** `@/shared/api/admin-service`，再在 `:162` 断言组件调用了这个 mock → **任何接线错误都能通过**（服务被删/改名/URL 写错都照样绿） |
| `test_smoke.py:22` | `test_validation_error_uses_envelope` 没测 422：断言 200 并检查 404 信封 → **名不副实** |
| `mocks/services/*.test.ts`、`ResourceState.test.tsx` | 测的是**死代码**（共 11 个用例） |

---

## 7. 测试体系里**做得好**的部分（不要回退）

- E2E 是**真端到端**：`e2e/helpers.ts:19-25` 走真实 `POST /api/v1/auth/login`，
  `:31-49` 用真实 `PATCH /conversations/{id}` 归档会话，`:52+` 用真实 `PUT /me/progress/{bookId}` 造进度。
  **零 mock。**
- 前端单测质量高且含**对抗性断言**：
  - `intents.test.ts` 断言**没有任何 intent 包含写死的书/章/数量/日期事实**
  - `unauthorized.test.ts` 断言 REST **与** SSE 两条路径都派发 401
  - `http.test.ts` 覆盖信封解包、`ApiError` 字段、`requestId`/`retryAfterMs`、AbortSignal 透传
  - `sse.test.ts` 覆盖 CRLF、跨 chunk 的多字节 UTF-8 拆分、心跳注释跳过
  - `conversation-store.test.ts` 覆盖 SSE 聚合、错误气泡、缺气泡清理、历史合并
  - `account-switch.test.tsx` 覆盖 epoch 隔离与按用户分键
  - `QuizDetailPage.test.tsx` 断言答卷页**零写入**
  - `MarkdownMessage.test.tsx` 覆盖 XSS（`javascript:` 拒绝、原始 HTML 转义）
- `ChatComposer.test.ts`（13 例）覆盖语音：麦克风渲染/隐藏、无权限降级、PCM base64 + audio_end、
  TTS 音量/语速、实时 screen-context 推送、QUESTION_ASKED 关联、ENDED 恰好一次。

---

## 8. CI 工作流（`.github/workflows/ci.yml`，227 行）

3 个 job，**并行、无 `needs:`**，各自 `uv sync` / `pnpm install`（重复劳动）：

| job | 内容 |
| --- | --- |
| `backend` | uv sync → `alembic upgrade head` → 内容初始化 → `pytest -q` → Worker 启动冒烟 → **入队一个 `memory_consolidation` 并断言到终态**（T25a，做得好） |
| `frontend` | pnpm install → `pnpm test` → `pnpm build` |
| `e2e` | uv sync → alembic → pnpm install → playwright install → `bash scripts/ci-e2e.sh` |

**问题**
| 问题 | 证据 |
| --- | --- |
| **当前必然失败** | 见 §1 |
| 声明的失败诊断产物**永不产生** | `ci.yml:219-227` 上传 `/tmp/shuangling-*.log`，但 `ci-e2e.sh` 的 EXIT trap 已 `rm -f` 它们；`if-no-files-found: ignore` 把这件事藏住 |
| Playwright HTML 报告路径不存在 | `ci.yml:217` 上传 `playwright-report/**/*.html`，但 `playwright.config.ts:11` 是 `reporter: [['list']]` |
| 无 lint / 类型检查 | 后端没有 ruff/mypy（本地有 `.ruff_cache` 但未声明依赖）；前端 `tsc` 只在 `pnpm build` 里顺带跑 |
| 未跑 `alembic check` | 无法发现 schema 漂移（而实测漂移确实几乎为零，见 `docs/06`） |
| 未跑 `import_assessments` | 见 `docs/12` P1-3 |
| 与 `scripts/ci.sh` 重复 | 两套内容重叠但独立维护，易漂移 |
| 未在本机实际触发过 | `docs/plans/current-phase.md:34` 自述 |

---

## 9. 结论

| 维度 | 评价 |
| --- | --- |
| **测试数量** | 充足（后端 384 + 前端 258 + E2E 33） |
| **测试质量** | **不均衡**：前端单测与 E2E 质量高；后端集成测试可用，但**环境隔离为零**、错误路径几乎未覆盖 |
| **测试可信度** | **低**：CI 恒红；基线数字不可复现；核心 AI 适配器的错误分支从未被执行 |
| **环境一致性** | **差**：开发库 / ci.sh / GitHub CI / 文档声称的隔离库 —— 四种不同数据 |
| **覆盖率可见性** | **无**（无任何覆盖率工具） |

**最关键的判断**：这些测试**不能**证明系统在生产链路里是正确的。
它们能证明「在开发者那台已经跑起来的机器上、用 mock provider、对着一份被污染的数据库，
功能大体可用」—— 这仍然有价值，但离「可发布」还有明显距离。
