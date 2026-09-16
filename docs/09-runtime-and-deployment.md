# 09 · 运行与部署

> 本文件回答：「从全新环境开始，要怎样才能真正启动完整系统？」
> 并记录声明与实际的差异、缺失的依赖、启动顺序、配置漂移。

---

## 0. 当前这台机器的实际运行状态（实测 2026-09-16 08:56）

| 组件 | 状态 | 证据 |
| --- | --- | --- |
| PostgreSQL 18 + pgvector 0.8.6 | ✅ healthy | 容器 `shuangling-postgres`，`:5432`，扩展 `vector 0.8.6` |
| Redis 7 | ✅ healthy | 容器 `shuangling-redis`，`:6379` |
| MinIO | ✅ healthy | 容器 `shuangling-minio`，`:9000-9001` —— **但应用未使用**（`STORAGE_BACKEND=local`） |
| 后端 API | ✅ 运行中 | `uv run uvicorn app.main:app --host 0.0.0.0 --port 8002`（pid 40865，启动于 08:26） |
| 后台 Worker | ✅ 运行中 | `uv run python -m app.jobs.worker`（pid 40900，启动于 08:26） |
| 前端 dev server | ✅ 运行中 | `vite --port 5174 --strictPort`（pid 40923） |
| Docker Compose api 服务 | ❌ **不存在** | compose 只有 postgres / redis / minio / worker |
| Docker Compose worker 服务 | ⚠️ 未作为容器运行 | 带 `profiles: ["worker"]`，`docker compose up` 不会启动 |

**系统是活的**：`/health` 返回 `{"status":"ok"}`，`/api/v1/ping` 正常，
`/metrics` 有 144 条请求计数，学生账号登录并读取全部核心接口成功（见 `docs/15` §运行实测）。

---

## 1. 工具链（实测版本）

| 工具 | 本机 | CI 声明 | 备注 |
| --- | --- | --- | --- |
| Python | 3.12（`.venv`） | 3.12（`uv:python3.12-bookworm-slim`） | `pyproject.toml` 要求 `>=3.12,<3.13` |
| uv | 0.12.3 | `astral-sh/setup-uv@v6` | 后端包管理器 |
| Node | **v24.19.0** | **22** | ⚠️ 版本漂移（可接受但未声明） |
| pnpm | **11.7.0** | `11.7.0`（已 pin） | 一致 |
| Docker | 29.1.3 | — | |
| Playwright | chromium | 只装 chromium | `playwright.config.ts` 注释说明刻意只依赖 chromium |

---

## 2. 三条启动路径（互不相同）

### 2.1 `bash scripts/start.sh`（文档推荐的一键启动）

```
1/7 docker compose up -d postgres          ← 默认**不启动 redis / minio**
2/7 alembic upgrade head
3/7 uvicorn :8002  (setsid, pid→backend/.server.pid)
4/7 python -m app.jobs.worker (setsid, pid→backend/.worker.pid)
5/7 pnpm dev --port 5174 (setsid, pid→frontend/.server.pid)
6/7 validate_library --all → import_library --all
7/7 检查演示账号 → 必要时 seed
```

`--with-minio` 会额外启动 redis + minio；`--backend-only` 跳过前端。
脚本还会尝试用 `xdg-open` 打开浏览器，并（有 `wmctrl` 时）把浏览器窗口带到前台。

### 2.2 `bash scripts/ci.sh`（本地质量门禁，11 步）

```
依赖检查 → 后端环境准备(mock) → postgres → redis → alembic upgrade head
→ validate_library → import_library → 启动 Worker → pytest
→ 停 Worker → pnpm install --frozen-lockfile → vitest → build → ci-e2e.sh
```

### 2.3 `bash scripts/ci-e2e.sh`（E2E）

复用 service container（若 `DATABASE_URL` 已设）或 `docker compose up -d postgres redis` →
在 `:8002` 起 mock 后端 → 起 Worker → `validate_library` → `import_library` → `seed` →
`pnpm run test:e2e`（Playwright 自起 `:5175` 的 vite）。

### 2.4 GitHub Actions（`.github/workflows/ci.yml`）

3 个并行 job，各自带 postgres + redis service container。
**不复用 `scripts/ci.sh`**，而是内联自己的步骤。
⚠️ 该 workflow **从未在本机实际触发过**（`docs/plans/current-phase.md:34` 自述）；
且按 `docs/10-testing.md` §1，其 `backend` job **当前必然失败**。

---

## 3. 全新环境的正确 bootstrap 顺序

```bash
# 0) 前置：Docker / uv / pnpm / Node 22+ / Playwright chromium
# 1) 依赖服务（pgvector 镜像是硬要求）
docker compose up -d postgres redis          # minio 仅在需要 S3 时
# 2) 后端环境
cd backend
cp .env.example .env                          # ★ JWT_SECRET 必填，无默认值
#    最小可用：AI_PROVIDER=mock / EMBEDDING_PROVIDER=mock / VOICE_PROVIDER=mock
# 3) 建库（必须早于 seed）
uv run alembic upgrade head
# 4) 演示账号与演示记忆
uv run python -m app.scripts.seed
# 5) 内容初始化（幂等；validate 是导入的前置门禁）
uv run python -m app.scripts.validate_library --all
uv run python -m app.scripts.import_library --all
# 6) 审校题库 —— ★ 当前有 bug 且无人调用，见 docs/12 P1-3
#    uv run python -m app.scripts.import_assessments
# 7) 启动
uv run uvicorn app.main:app --host 0.0.0.0 --port 8002     # 终端 A
uv run python -m app.jobs.worker                            # 终端 B（必须！）
# 8) 前端
cd ../frontend && pnpm install
VITE_API_PROXY_TARGET=http://127.0.0.1:8002 pnpm dev --port 5174
```

**顺序约束（已验证）**
1. **`alembic upgrade head` 必须早于 `seed`** —— 迁移 `a1b2c3d4e5f6:120-141` 的 admin 回填
   需要一个已存在的 `admin` 用户（空库上是无害 no-op）。
2. **`validate_library` 必须早于 `import_library`** —— 四个脚本都把它作为门禁（校验不过就拒绝导入）。
3. **Worker 必须单独启动** —— API 进程不会启动它（`main.py:31-34` 的 lifespan 是空的）。

**凭据**：学生 `xiaoming` / `demo123`（grade 8）；管理员 `admin` / `admin123`
（硬编码于 `seed.py:57`，并重复于 `ingest_knowledge.py:36`）。

---

## 4. 环境变量

唯一有效的模板是 **`backend/.env.example`**（47 行，覆盖全部配置项）。

⚠️ **根目录 `.env.example` 是过期的**：使用旧变量名 `LLM_PROVIDER / LLM_API_KEY / LLM_BASE_URL / LLM_MODEL`，
与 `config.py` 的 `AI_*` **完全不匹配**，且**无任何代码读取它**（全仓检索仅命中历史 task 文档）。

### 关键变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://shuangling:***@localhost:5432/shuangling` | |
| `JWT_SECRET` | **无默认**（必填） | `ENVIRONMENT=prod` 时若为 `dev-*`/`change-me` → **启动失败** |
| `ENVIRONMENT` | `dev` | `dev\|test\|prod` |
| `AI_PROVIDER` | `mock` | 工作区 `.env` 实为 `openai_compatible`（DeepSeek） |
| `AI_BASE_URL`/`AI_API_KEY`/`AI_MODEL` | 空/mock | |
| `AI_THINKING_MODE` | `auto` | `.env.example` 建议长文本教学对话设 `disabled` |
| `EMBEDDING_PROVIDER` | `mock` | 工作区实为 `openai_compatible`，`EMBEDDING_DIMENSION=1024` |
| `EMBEDDING_API_KEY` | 空 | 未设时回退到 `ALIYUN_DASHSCOPE_API_KEY`（见 `config.py:95-100`） |
| `VOICE_PROVIDER` | `mock` | 工作区实为 `aliyun` |
| **`TTS_PROVIDER`** | **`none`** | 未配置 → 语音接口返回 `TTS_UNAVAILABLE`（有意，不返回假音频） |
| `STORAGE_BACKEND` | `local` | `s3` 时需 5 个 S3 变量 |
| `REDIS_ENABLED` | `true` | 不可用时自动降级为进程内 |
| `WORKER_*` | poll 1.0 / max_attempts 3 / running_ttl 600 / backoff 2–300 | |
| `SUMMARY_MESSAGE_THRESHOLD` | 20 | 触发（有缺陷的）摘要生成 |
| `CONTEXT_WINDOW_TOKEN_BUDGET` | 3000 | 按字符估算，非真实分词 |
| `RATE_LIMIT_*` | enabled / 600 / 30 | |

---

## 5. 配置漂移清单

| # | 漂移 | 证据 | 影响 |
| --- | --- | --- | --- |
| 1 | 根 `.env.example` 变量名与代码不符 | `LLM_*` vs `AI_*` | 新环境搭建被误导 |
| 2 | `README.md` 说 `docker compose up -d postgres redis`，而 `start.sh` 默认只起 postgres | `start.sh` 注释「默认只起 postgres，MVP 用不上 redis/minio」 | 限流静默降级为进程内 |
| 3 | MinIO 在 compose 里且 healthy，但 `STORAGE_BACKEND=local` | `backend/.env` | 声明的基础设施未被使用 |
| 4 | `worker` compose 服务被 profile 门控 | `profiles: ["worker"]` | `docker compose up` 得不到 Worker |
| 5 | `main.py:31-34` 注释「当前无任何外部依赖」 | 实际依赖 DB / Redis / Worker | 误导 |
| 6 | Node 本机 24 vs CI 22 | `.github/workflows/ci.yml:139` | 潜在行为差异 |
| 7 | 文档声称基线跑在隔离库 `shuangling_audit`；`ci.sh` 实际用 `backend/.env` 的库 | `scripts/ci.sh:70-98` | 数字不可复现 |
| 8 | `docker-compose.yml` 的 worker 挂载 `./backend/storage:/app/storage`，但 API 不在容器里 | — | 仅容器 Worker 场景有意义 |
| 9 | `backend/.server.pid` / `.worker.pid` 存在且指向**正在运行**的进程 | 实测 pid 匹配 | 正常 |
| 10 | `start.sh` 的「容器已在运行则跳过」守卫**永不匹配** | 守卫 `^k12.*postgres\|-postgres-1$` vs 实际名 `shuangling-postgres`（实测不匹配） | 死逻辑（当前无害） |
| 11 | `stop.sh` 只 `docker compose stop postgres`，不停 redis/minio | 而 `start.sh --with-minio` 会启动它们 | 容器残留 |

---

## 6. 缺失的能力（部署完整度）

| 能力 | 状态 |
| --- | --- |
| 生产部署编排（compose api 服务 / k8s / systemd） | ❌ **完全没有** |
| 反向代理 / TLS / nginx / Caddy | ❌ 不存在 |
| 前端静态产物托管 | ❌ 只跑 `vite dev`；`dist/` 存在但无任何托管配置 |
| `infra/` 目录 | ❌ 只有 `.gitkeep` |
| 数据库迁移的部署自动化 | ⚠️ 只有脚本手动 `alembic upgrade head` |
| 备份 / 恢复演练 | ⚠️ `scripts/test-db.sh` 提供 pg_dump/pg_restore 能力，但**无任何调用方、无演练记录** |
| 密钥管理 | ❌ 明文 `.env`（已被 gitignore）；无 vault/secrets manager |
| 监控告警 | ❌ 无 Prometheus/Grafana/Loki；`/metrics` 是**进程内**文本，多副本无法聚合（`docs/plans/current-phase.md:38` 自述待定） |
| 日志聚合 | ❌ 只有 stdout（`/tmp/k12-backend.log`、`/tmp/k12-worker.log`） |
| 队列积压告警 | ❌ 无（与 `docs/12` P1-2 叠加） |
| 健康检查深度 | ⚠️ `/health` **不检查 DB/Redis/Worker**（`main.py:152-155` 注释明示「不依赖数据库」） |
| 优雅关闭 / 零停机 | ❌ 无 |
| 灰度 / 回滚策略 | ❌ 无 |

**判断**：这是一个**开发环境完备、生产化几乎为零**的项目。
`prototypes/`、`infra/`(空)、无部署脚本三者叠加，说明「生产化」从未真正开始。

---

## 7. 运行实测记录（本次审计）

```
GET  /health                         → {"status":"ok"}
GET  /api/v1/ping                    → {"data":{"pong":true},"meta":{}}
GET  /metrics                        → http_requests_total{method="GET",status="200",env="dev"} 142
                                       process_uptime_seconds 1803.68（仅 HTTP 指标，无 AI/队列指标）
GET  http://127.0.0.1:5174           → HTTP 200
POST /api/v1/auth/login (xiaoming)   → 200，access_token 195 字符
GET  /api/v1/me                      → 200（student_id / 昵称「小明」/ grade 8）
GET  /api/v1/me/preferences          → 200
GET  /api/v1/me/progress             → 200（1898 B）
GET  /api/v1/me/learning-next        → 200（type=CONTINUE_QUIZ）
GET  /api/v1/me/recommendations      → 200（846 B，带 reason/evidence_ids）
GET  /api/v1/me/memories             → 200（30140 B）
GET  /api/v1/me/insights             → 200（16662 B）
GET  /api/v1/me/episodes             → 200（11791 B）
GET  /api/v1/me/agent.md             → 200（125065 B，真实 Markdown）
GET  /api/v1/teacher-roles           → 200（2 个风格）
GET  /api/v1/conversations           → 200
GET  /api/v1/quiz-sessions?limit=3   → 200
GET  /api/v1/books?limit=3           → 200（★ 第一本是「审校测试书」= 测试夹具，见 docs/12 P0-2）
POST /api/v1/auth/login (admin)      → 未实测（密码硬编码 admin123，本次未使用）
Worker                               → pid 40900 运行中；累计 272+259+105 次 success
```

**结论**：**系统确实能跑，主链路确实通**。问题不在「能不能启动」，而在
「启动起来的数据是脏的、CI 是红的、AI 层有结构性缺陷、生产化是零」。
