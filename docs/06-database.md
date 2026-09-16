# 06 · 数据库与数据模型

> 证据来自 `.audit/C-database.md`（1353 行，含 32 表列级清单、23 迁移目录、三方漂移对账、风险登记）。
> 对账方法：ORM metadata ↔ 线上库 `information_schema` ↔ Alembic 离线 DDL **三方交叉验证**，
> 并额外运行 Alembic 自身的 `compare_metadata()`。

---

## 0. 最重要的结论：**Schema 本身是健康的**

这是本次审计中**最出乎意料的好消息**。三方对账结果：

| 检查 | 结果 |
| --- | --- |
| 表：模型有、迁移无 | **∅** |
| 表：迁移有、模型无 | **∅**（仅 `alembic_version`，Alembic 自身账簿） |
| 表：线上有、模型无 | **∅** |
| 列：模型有、迁移/库无 | **0 / 368** |
| 列：迁移/库有、模型已删（legacy 字段） | **∅** |
| 类型不匹配 | **0 / 368**（74 个 `DateTime` 全部两侧都是 `timezone=True`） |
| 可空性不匹配 | **0 / 368** |
| server_default 不匹配 | **∅** |
| FK 目标 / `ondelete` 不匹配 | **∅**（58 个 FK 双向一致） |
| 缺索引 | 34 个模型 `Index` **全部存在**于库 |
| CHECK 约束 | 68 vs 68，**名称集合完全相同** |
| 从 base 全量重放建表 | 33 张建、**0 张删** |
| 重放后每表列集合 vs 线上库 | **逐表完全一致** |
| `alembic compare_metadata()` | **2 条 = 1 个良性差异** |

**结论：`models.py` ≡ 线上数据库 ≡ `alembic upgrade head`。**
不存在 schema drift、migration drift、legacy 字段、未使用表或孤儿关系。

---

## 1. 迁移链

- **23 个迁移文件，单条线性链**，一个根（`8468855342d3`），**恰好一个 head（`a7b8c9d0e1f2`）**，
  零分支点、零孤儿、零悬挂引用、零环。
- 线上库 `alembic_version` = `a7b8c9d0e1f2`（实测），与 head 一致。
- 新增（未提交）的 4 个迁移是链上的第 20–23 位，**全部可达且与模型一致**：
  `a4b5c6d7e8f9`（chapter_completions）、`a5b6c7d8e9f1`（quiz 来源 FK + 复习事件）、
  `a6b7c8d9e0f1`（摘要 covered_count）、`a7b8c9d0e1f2`（reviewed_questions）。
- 从全新库执行 `alembic upgrade head` **安全**（离线渲染 exit 0，无迁移引用后建对象）。

### ⚠️ 唯一的真实漂移（良性）

| 项 | 模型 | 迁移 | 线上库 | 判定 |
| --- | --- | --- | --- | --- |
| `chapter_completions` 的 `(student_id, chapter_id)` 唯一性 | `UniqueConstraint`（`models.py:527-529`） | `op.create_index(..., unique=True)`（`a4b5c6d7e8f9:40-45`） | **唯一索引**（非约束） | 表示差异，**唯一性强制完全相同，无完整性影响** |

代价：`alembic revision --autogenerate` 会永远生成一对 `remove_index` + `add_constraint`；
盲目套用会在线表上删了重建该对象。修复：模型改为 `Index(..., unique=True)`，或迁移改为 `create_unique_constraint`。

### 已排除的 5 个「假漂移」（记录下来避免重复报告）

1. `ix_*_student_started` 等 5 个索引看似「模型独有」——实际模型用了 SQL 表达式列
   （`Index("ix_learning_sessions_student_started", "student_id", text("started_at DESC"))`），
   文本 diff 只看到第一列。库中正确存在 `(student_id, started_at DESC)`。
2. `users_username_key` 等 4 个「库独有唯一约束」——来自列级 `unique=True`，PG 自动命名。**无漂移**。
3. 所有 `*_pkey` / `uq_*` 看似「库独有索引」——主键与 UniqueConstraint 不是 SQLAlchemy 的 `Index` 对象。**无漂移**。
4. `ix_learning_sessions_student_started` 看似「被删」——`a3f1c2e4b5d6:22-35` 故意删除并带 `DESC` 重建。**有意为之**。
5. 74 个 `DateTime` 看似类型不匹配——`str(DateTime())` 隐藏了 `timezone` 标志；实际两侧都是 `timestamptz`。**无漂移**。

---

## 2. 数据模型（32 张表）

按领域分组（完整列级清单见 `.audit/C-database.md` §3）：

| 领域 | 表 |
| --- | --- |
| 身份 | `users`、`admins`、`student_profiles`、`student_preferences`、`teacher_roles` |
| 内容 | `books`、`chapters`、`content_blocks`、`knowledge_points` |
| 学习 | `learning_sessions`、`learning_events`、`book_progress`、`chapter_completions`、`reading_settlements` |
| 对话 | `conversations`、`messages`、`conversation_summaries` |
| 记忆/画像 | `student_memories`、`memory_candidates`、`memory_evidence`、`student_episodes`、`profile_insights` |
| 测验 | `quiz_sessions`、`quiz_questions`、`quiz_answers`、`quiz_interactions`、`reviewed_questions` |
| 知识库 | `knowledge_resources`、`knowledge_chunks` |
| 个性化 | `recommendations` |
| 基础设施 | `background_jobs`、`idempotency_keys` |

### 2.1 关键设计约定（不要破坏）

| 约定 | 说明 |
| --- | --- |
| **无 `relationship()`** | `models.py` 全篇只有 `ForeignKey` 列，跨表一律显式 SQL。避免 async 惰性加载陷阱（`worker.py:45-52` 记载了真实事故根因） |
| **无 `mastery`/`score`/`percent` 数字列** | `models.py:333` 注释明示；`profile_insights.level` 用 5 档中文定性枚举 |
| **幂等靠唯一约束** | `reading_settlements.session_id` 主键、`quiz_answers(session,question,attempt)`、`chapter_completions(student,chapter)`、`reviewed_questions.stable_key` |
| **append-only 表** | `learning_events`（应用层约定）、`messages`（应用层约定） |
| **软删除保审计** | `student_memories.status ∈ ACTIVE/DISPUTED/SUPERSEDED/REMOVED`；唯一允许物理删除的是 `idempotency_keys` |
| **pgvector 无维度列** | `VECTOR` 无维度，兼容多 provider；代价是无索引（见 §4） |
| **延时 FK** | `learning_events.conversation_id` / `quiz_session_id` 只有索引**无 FK**（注释称「延迟到 Phase 4/6 补」，至今未补） |
| **书完成 = 章节完成集合** | 由 `chapter_completions` 判定，非「滚动到末块」 |

---

## 3. 线上数据现状（实测 2026-09-16）

| 表 | 行数 | 备注 |
| --- | --- | --- |
| `books` | 130 | **PUBLISHED 69（其中 43 是测试夹具）** / ARCHIVED 63 / DRAFT 6 |
| `chapters` | 164 | PUBLISHED 159 / DRAFT 5 |
| `content_blocks` | 2018 | |
| `users` | 159 | ADMIN 48 / STUDENT 106（含大量测试账号） |
| `admins` | 3 | |
| `student_profiles` | 110 | |
| `knowledge_resources` | 488 | READY 102 / **FAILED 395**（382 条 `archived: test data`） |
| `knowledge_chunks` | 1136 | **636×64 维 + 467×1024 维 + 33 无向量** |
| `messages` | 495 | |
| `conversations` | 103 | |
| `conversation_summaries` | 1 | |
| `learning_events` | 437 | |
| `learning_sessions` | 159 | |
| `chapter_completions` | **2** | 新能力，几乎未使用 |
| `reviewed_questions` | **5** | **全部是测试夹具**（`cap-approved` 等）；真实词库从未导入 |
| `student_memories` | 48 | |
| `student_episodes` | 239 | **0 个 embedding** |
| `profile_insights` | 921 | |
| `recommendations` | 194 | |
| `quiz_sessions` | 61 | provider 分布见 `docs/08` §5.2 |
| `background_jobs` | 691 | 含一条伪造 job_type `rollback_poison_<uuid>` |
| `idempotency_keys` | **8442** | 无清理策略 |

> ⚠️ 上表中的测试夹具数量直接来自 **P0-1**（测试直连开发库）。这不是数据模型问题，是流程问题。

---

## 4. 向量列与检索

| 项 | 现状 |
| --- | --- |
| 扩展 | pgvector **0.8.6** 已安装（实测） |
| 列 | `knowledge_chunks.embedding`、`student_episodes.embedding`，均为**无维度 `vector`** |
| **向量索引** | **零个**。HNSW 在 `a2b3c4d5e6f7:161-179` 创建，在 `c7d8e9f0a1b2:33-34` **被删除且从未重建**（重建只写在 downgrade 里） |
| 检索计划 | `EXPLAIN` 确认生产查询是 **`Seq Scan on knowledge_chunks`** |
| 维度过滤 | `service.py` 的 `vector_dims(kc.embedding) = :embedding_dimension` **本身就会阻止索引使用** |

**判断**：
- 在 1153 行的规模下顺序扫描完全可接受，**今天不是性能问题**。
- 但「无维度列」使加索引在结构上不可能 —— 必须有额外迁移先锁定维度。
- 且 636 个 64 维 chunk 因维度过滤**永久不可达**（见 `docs/12-known-issues.md` P1-5）。

---

## 5. 级联与外键风险

### 5.1 7 个 CASCADE（静默递归删除）

| 父 → 子 | 后果 |
| --- | --- |
| `users` → `student_profiles` | 删用户销毁整个学生档案。**实际被保护**：`student_profiles` 被 12 张表 `RESTRICT` 引用，有任意活动的学生无法删除 |
| `student_profiles` → `student_preferences` | 同上受保护 |
| **`books` → `chapters`** | ⚠️ **危险链** |
| **`chapters` → `content_blocks`** | ⚠️ **两级 CASCADE**：删一本书瞬间摧毁其全部章节**与全部内容块**。有学生活动的书被 `RESTRICT` 保护，但**草稿/未使用的书会静默带走整棵内容树** |
| `conversations` → `conversation_summaries` | `messages` 对同父是 `RESTRICT`，所以有消息的会话根本无法删除 |
| `knowledge_resources` → `knowledge_chunks` | 删资源销毁全部分块**及其向量**，只能靠重新 ingest 恢复 |
| `admins.user_id` → `admins` | 被 `books.created_by` / `knowledge_resources.uploaded_by` 的 `RESTRICT` 间接保护 |

> 与 `import_library.py:306-308` 形成对照：导入器**故意保留**过期章节而不删除，说明作者对内容树删除是谨慎的。

### 5.2 8 个 `SET NULL`（静默置空，容易被误认为「从未设置」）

其中两个值得注意：
- **`reviewed_questions.chapter_id ON DELETE SET NULL`** —— 删章节会把审校题变成孤儿（`chapter_id=NULL`），
  而选择器按 `chapter_id` 匹配 → 该题**永久不可被选中**（「静默死行」型数据丢失）。
- `book_progress.block_id ON DELETE SET NULL` —— 读者当前位置静默重置。

### 5.3 其他破坏性操作

- `import_library.py:293-300`：重新导入一本书时**删除**源文件中已不存在的确定性 ID 内容块。
  有意为之且范围受控，但这是「编辑一个 Markdown 文件」即可触发的真实数据丢失。
- `reindex_embeddings` / `rebuild_memory`：走 `force_reprocess` 路径**删除重建** chunk / supersede 重建 insight。
  内容收敛正确，但**主键会变**，任何跨重建持有 `chunk_id`/`insight_id` 的引用都会失效。

---

## 6. Seed 与数据初始化

### 6.1 正确的 bootstrap 顺序（已验证）

```bash
docker compose up -d postgres          # 需要 pgvector/pgvector:pg18
cd backend
uv run alembic upgrade head            # ★ 必须先于 seed
uv run python -m app.scripts.seed      # 演示账号 + 演示记忆
uv run python -m app.scripts.validate_library --all
uv run python -m app.scripts.import_library --all
uv run python -m app.scripts.import_assessments   # ← 可选，且当前有 bug（见 §7）
```

**迁移必须早于 seed**：迁移 `a1b2c3d4e5f6:120-141` 的 admin 回填需要已存在 `admin` 用户
（在空库上是无害的 no-op，不是错误）。

### 6.2 凭据（硬编码）

| 账号 | 密码 | 位置 | 备注 |
| --- | --- | --- | --- |
| `xiaoming`（学生，grade 8） | `demo123` | `seed.py:30`，可用 `SEED_PASSWORD` 覆盖 | |
| `admin`（管理员） | **`admin123`** | `seed.py:57`，**并在 `ingest_knowledge.py:36` 重复硬编码** | 非本地环境必须轮换 |

### 6.3 脚本幂等性

| 脚本 | 幂等 | 备注 |
| --- | --- | --- |
| `seed.py` | ✅ | |
| `validate_library.py` | ✅（只读校验） | |
| `import_library.py` | ✅ | 但会删除源中已移除的内容块 |
| `import_assessments.py` | 行数幂等 ✅ / **`revision` 不幂等** ❌ | `:125` 无条件 `revision += 1`，跑 N 次得 `revision = N`（实测 `imp-idempotent` 行 revision=2） |
| `archive_noncorpus.py` | ❌ | 见 §7 |
| `reindex_embeddings.py` | 内容收敛，**主键会变** | |
| `rebuild_memory.py` | 内容收敛，**主键会变** | |
| `ingest_knowledge.py` | ✅（按 `(source_url, storage_key)`） | |

---

## 7. 风险登记（按严重度）

| # | 风险 | 严重度 | 置信度 |
| --- | --- | --- | --- |
| **R1** | **4 个迁移未提交，而线上库已 stamped 到它们的 head** → `git clean` / 全新 clone 后链 head 变成 `b2c3d4e6f789`（**落后于数据库**），任何 Alembic 命令都会以 "unknown revision" 失败 | **HIGH** | CONFIRMED |
| **R2** | `c7d8e9f0a1b2.downgrade()` 会把**所有非 64 维** embedding 置 NULL —— 在本库上就是全部真实的 1024 维向量 | **HIGH**（仅在 downgrade 时） | CONFIRMED |
| **R3** | `archive_noncorpus.py` 的保留规则只有 `source_url LIKE 'local://library/knowledge/%'`（`:58,70-73`），**其余一律标记 `FAILED='archived: test data'`** —— 这包括 `ingest_knowledge.py` 的全部产物（它写 `https://demo.shuangling.local/knowledge/<stem>`）**以及任何真实的后台上传**。在活库上运行它会**静默关闭这些文档的 RAG** | **HIGH**（手动脚本） | CONFIRMED |
| R4 | 零向量索引 → 全部 RAG 检索为顺序扫描；无维度列使加索引在结构上不可能 | MEDIUM（性能） | CONFIRMED |
| R5 | `b1c2d3e4f5a6` 在**被应用之后又被回溯修改**（commit `bce24e9` 把种子从 `shuangling`/`strict-mentor` 改成 `温暖鼓励`/`严谨清晰`），使 `b2c3d4e5f6a7` 在全新重放时成为 no-op | MEDIUM（卫生） | CONFIRMED |
| R6 | `learning_events.conversation_id` / `quiz_session_id` **有索引无 FK**（最后两个未回填的「延时 FK」）→ 可能产生孤儿行 | MEDIUM | CONFIRMED |
| R7 | 出厂的 13 道审校题**永远不可能被选中**（详见 §8） | MEDIUM | CONFIRMED |
| R8 | 58 个 FK 列中 **25 个没有前导索引** | LOW（当前规模） | CONFIRMED |
| R9 | `books → chapters → content_blocks` 两级 CASCADE，对无学生活动的书会静默摧毁内容树 | LOW–MEDIUM | CONFIRMED |
| R10 | `import_library` 与 `ingest_knowledge` 对同一文档使用**不同 URL 方案**（`local://library/knowledge/<slug>` vs `https://demo.shuangling.local/knowledge/<stem>`），而幂等键是 `(source_url, storage_key)` → **同一文档可能产生两条 `knowledge_resources` 与两套 chunk，导致 RAG 重复命中** | LOW–MEDIUM | LIKELY |
| R11 | `chapter_completions` 唯一索引 vs 唯一约束 → 永久 autogenerate churn | LOW | CONFIRMED |
| R12 | 硬编码 `admin123`（`seed.py:57`，重复于 `ingest_knowledge.py:36`） | 本地 LOW / 出厂 HIGH | CONFIRMED |
| R13 | `quiz_sessions ↔ quiz_questions` **循环 FK** 使 autogenerate 对该两表的 FK 漂移**完全失明**；也使 `create_all()` / 朴素 `DROP TABLE` 排序不可用 | LOW | CONFIRMED |
| R14 | `seed.py:104` 打印字面量 `{SEED_PASSWORD}`（漏了 f 前缀） | COSMETIC | CONFIRMED |

---

## 8. ⚠️ R7：审校题库「即使接上也永远选不出来」

这是对 `docs/12-known-issues.md` P1-3 的**重要加深**。

除了「`import_assessments.py` 没有被任何启动/CI 链路调用」之外，
**导入器本身还有两个 bug，使得即便接上也无效**：

| 问题 | 证据 |
| --- | --- |
| 导入器按**每题**读 `review_status` | `import_assessments.py:96` `question.get("review_status", "DRAFT")` |
| 而出厂的 3 个 JSON（共 13 题）把 `review_status` 写在**文件顶层**，没有一题写在题内 | 实测：0/4、0/4、0/5 |
| → **13 题全部以 `DRAFT` 导入** | |
| 选择器要求 `review_status == 'APPROVED'` | `quiz_bank.py:206-209` |
| → **一题都不可能被选中** | |
| 且导入器只从**顶层** `chapter_id` 键推导章节 | `:87-90`，而 JSON 用的是 `slug` + `chapter` |
| → 13 题**同时**落到 `chapter_id = NULL`，**在第二个独立维度上也不可选** | |
| `skipped_no_chapter` 计数器是死代码 | 在 `:72` 初始化、`:128` 返回，但**从未自增**；docstring 里承诺的「找不到时跳过该题并告警」未实现 |
| 线上库佐证 | `reviewed_questions` 5 行**全是测试夹具**（`cap-approved`/`cap-draft`/`cap-pending`/`cap-rejected`/`imp-idempotent`） |

**含义**：T22b「审校题源」在**代码层、数据层、运行时层三个层面都不通**。
修复需要：改导入器读顶层字段 + 从 `slug`+`chapter` 解析章节 + 把 `import_assessments` 接入内容初始化链路 +
修正 JSON 或导入器使其产出 `APPROVED`。

---

## 9. 建议（按顺序，本阶段未执行）

1. **立即提交 4 个未提交迁移**（R1）。在它们进入 git 之前，仓库无法复现它正在运行的数据库。
2. 在未导出 `knowledge_chunks.embedding` / `student_episodes.embedding` 之前，
   **绝不执行 `alembic downgrade` 跨过 `c7d8e9f0a1b2`**（R2）。
3. 补 `learning_events.conversation_id` / `quiz_session_id` 的 FK（R6，需先回填/清理孤儿）。
4. 明确向量索引策略（R4）：要么把列锁定到 provider 维度并建 HNSW，要么接受顺序扫描并记录行数阈值；
   注意查询里的 `vector_dims(...) = :dim` 谓词会阻止任何索引使用，必须一并移除。
5. 修 `import_assessments`（R7）并接入 `ci.sh` / `ci-e2e.sh`。
6. 统一 `chapter_completions` 的唯一对象表示（R11），让 autogenerate 安静。
7. 加一次纯索引迁移补 25 个缺失 FK 索引（R8），风格参照 `a3f1c2e4b5d6`。
8. 为破坏性脚本（`archive_noncorpus` / `reindex_embeddings` / `rebuild_memory`）补一份 break-glass 说明；
   **在活库上运行 `archive_noncorpus` 之前必须放宽其保留规则**（R3）。
9. 非本地环境轮换演示凭据，并移除 `ingest_knowledge.py` 中重复的 `admin123`（R12）。
10. **加一道 CI schema-drift 门禁**：跑 `compare_metadata()` 并在出现非白名单差异时失败，
    让下一次漂移被自动发现而不是靠审计。
