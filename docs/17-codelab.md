# 17 · CodeLab（在线编程教学工具）

> Phase 1：把 dai-experiment-platform 已验证的在线编程能力接入霜铃，形成
> **编辑代码 → 运行 → 查看结果 → AI 编程评价** 的完整可用闭环。
> 本文档记录实际实现、安全边界、评分口径与已知限制。

---

## 1. 它是什么

CodeLab 是霜铃的一项**教学工具**：学生在浏览器里编写 Python，代码在**一次性 Docker 沙箱**中执行，
输出（stdout / stderr / traceback / matplotlib 图表）回传前端；随后可以请求一次 **AI 编程评价**，
得到「是否完成任务 / 算法与代码质量分 / 关键错误 / 改进建议 / 具体 diff」。

它**不是**独立平台：没有题库编辑器、没有考试编排、没有环境构建、没有多语言。
这四项都是刻意排除的范围（见 §8）。

### 数据模型（3 张表）

| 表 | 作用 | 关键约束 |
| --- | --- | --- |
| `code_tasks` | 编程任务定义（文件导入，按 `slug` 幂等） | `slug` 唯一；`test_groups` / `reference_solution` 是**教师侧私有数据** |
| `code_runs` | 每次沙箱执行的记录 | `(student_id, created_at DESC)` 索引 |
| `code_reviews` | AI 对某次 run 的评价 | `run_id` 唯一（同一 run 只评一次）；`final_score_100` 有 **CHECK 0–100** |

迁移：`b3c4d5e6f7a8_create_codelab_domain.py`。**不修改任何既有表**。

### API（5 个端点，全部 `require_student`）

| 方法 路径 | 说明 |
| --- | --- |
| `GET /api/v1/codelab/tasks` | 任务列表（仅 PUBLISHED） |
| `GET /api/v1/codelab/tasks/{task_id}` | 任务详情（**不含** 隐藏测试 / 标准答案） |
| `POST /api/v1/codelab/runs` | 运行代码（同步，移出事件循环），201 |
| `POST /api/v1/codelab/reviews` | 请求 AI 评价（同步，不依赖 Worker），201 |
| `GET /api/v1/codelab/reviews/{review_id}` | 读取评价结果 |

错误码：`CODELAB_DISABLED`、`CODELAB_UNAVAILABLE`、`CODELAB_BUSY`、`CODELAB_RATE_LIMITED`、
`CODELAB_TASK_NOT_FOUND`、`CODELAB_RUN_NOT_FOUND`、`CODELAB_REVIEW_NOT_FOUND`、`CODELAB_CODE_TOO_LONG`。

---

## 2. 完整调用链

```
[浏览器] /codelab/:taskId  CodeLabPage
   │  ① 选任务   GET /codelab/tasks / {task_id}
   │  ② 编辑     CodeEditor（CodeMirror 6，动态 import，Ctrl/⌘+Enter 运行）
   │  ③ 运行     POST /codelab/runs  {task_id, code}
   ▼
[后端] codelab/router.py → CodeLabService.create_run
   ├ 校验任务可见性 + 代码长度上限
   ├ anyio.to_thread.run_sync(sandbox.run_python)    ← 阻塞调用移出事件循环
   │    └ docker run --rm  <一次性沙箱>  python /opt/codelab/runner.py
   │         ├ 学生代码经 stdin JSON 传入（不进 argv）
   │         ├ runner 以**子进程**执行 user_code.py（隔离 os._exit / 段错误）
   │         ├ 收集 stdout / stderr / 异常 / 图片 → JSON 信封
   │         └ 硬超时 → docker rm -f
   ├ 落库 code_runs（outputs JSONB）
   └ 返回 {status, outputs[], execution_time_ms, exit_code}
   ▼
[浏览器] CodeOutputPanel 渲染 stream(stdout/stderr) / error / display_data(png)
   │  ④ 请求评价 POST /codelab/reviews {run_id}
   ▼
[后端] CodeLabService.create_review → _execute_review
   ├ ① 确定性判题（F/R）  grade_deterministic → 每个测试组一次 docker+pytest
   ├ ② 静态分析（AST，只读，不执行代码）
   ├ ③ Rubric：任务已锁定则复用；否则由 LLM 生成一次并写回 code_tasks
   ├ ④ LLM 评分（A/Q）  provider.chat_json(operation="codelab_grading")
   ├ ⑤ 校验 → 钳制 → 合并
   └ 落库 code_reviews
   ▼
[浏览器] AiReviewPanel 渲染正确性结论 / 各维度分 / 测试组明细 / 教学反馈 / 评分依据
```

**RAG、记忆、推荐、学习事件本轮完全没有接入**（§8）。

---

## 3. 从 dai 复用了什么

### 逐字沿用

| 资产 | dai 位置 | 霜铃位置 |
| --- | --- | --- |
| **Docker 沙箱安全参数** | `kernel_manager.py:248-272`、`judge_worker.py:115-125` | `sandbox.py:_base_docker_args` |
| **pytest 结果计数插件** | `judge_worker.py:145-157` `PLUGIN_CODE` | `sandbox_assets/result_plugin.py`（仅改标记名） |
| **结果解析** | `judge_worker.py:159-178`（`re.search`，非行首匹配） | `sandbox.py:parse_result_counts` |
| **分组计分公式** | `deterministic_scoring.py:26-31` | `scoring.py:calculate_group_score` |
| **AI 输出校验规则** | `ai_score_validation.py:7-99` | `validation.py:validate_ai_output` |
| **跨维度重复扣分检测** | `ai_score_validation.py:72-99` | `validation.py:detect_cross_dimension_duplicates` |
| **评分 / Rubric system prompt** | `ai_prompts.py:215-334` | `prompts.py`（逐字，含注入防御） |
| **JSON 提取与错误脱敏** | `ai_client.py:43-74` | `ai/json_utils.py` |
| **每操作 token 预算 fail-closed 注册表** | `ai_client.py:24-31` | `ai/json_utils.py:OPERATION_MAX_TOKENS` |
| **重试 / 退避 / 400 降级 / usage 采集** | `ai_client.py:106-314` | `openai_compatible.py:chat_json`（改为 async） |
| **CodeMirror 库选型与扩展组合** | `CodeCell.vue:65-146` | `CodeEditor.tsx`（框架无关的包，重写为 React） |
| **输出 wire 契约** `{msg_type, content}` | Jupyter IOPub / `CodeCell.vue` | `CodeOutputPanel.tsx` + `schemas.py:CodeOutputDTO` |
| **沙箱镜像** | `dai-kernel-python` / `dai-judge-python` | `CODELAB_RUN_IMAGE` / `CODELAB_JUDGE_IMAGE` |

### 适配后复用

| 资产 | 为什么需要改 |
| --- | --- |
| `kernel_manager` 的会话管理 | dai 用常驻 ipykernel + Redis 会话 + 环境版本 label。CodeLab 的任务形态是「实现函数 + 跑测试」，每次运行本就是独立脚本 → 改为**一次性 `docker run --rm`**，把 638 行会话管理压到约 300 行，且同一个原语同时服务「运行」和「判题」 |
| `DeepSeekClient.chat_json` | dai 是同步 `httpx.Client`；霜铃是 async → 改为 `httpx.AsyncClient`，逻辑（重试/退避/脱敏/JSON 提取）逐字保留 |
| `_run_docker_pytest` / `run_test_groups` | 强耦合 dai 的 `Submission`/`JudgeQuestion` → 抽成纯函数，只接 `(code, tests, 沙箱参数)` |
| `analyze_python` | dai 依赖 ruff / radon，霜铃无此依赖 → **只保留 AST 部分**（零新依赖），`diagnostics` 字段留作将来挂点 |
| `CodeCell.vue` / `StudentAIGradingResult.vue` | Vue 3 SFC → **逻辑与配置移植，渲染用 React 重写** |

### 没有复用（明确排除）

dai 的用户/鉴权系统、课程/作业/考试领域模型、`unified_submission_service`、
environment-builder v2（1318 行 + 866 行 UI）、Studio 课件编辑器、
`api/ai_grading.py`（994 行，强耦合 `CodeGrade`）、MySQL / boto3 / python-jose / passlib / Vue / Pinia / axios。

---

## 4. AI 评分如何工作

### 维度模型（F60 + A20 + R10 + Q10）

| 维度 | 含义 | 满分 | 产出方 |
| --- | --- | --- | --- |
| **F** | 功能正确性 | 60 | **确定性 pytest**（Docker） |
| **R** | 鲁棒性 | 10 | **确定性 pytest**（Docker） |
| **A** | 算法质量 | 20 | LLM（rubric 约束） |
| **Q** | 代码质量 | 10 | LLM（Q1–Q4 固定 3/3/2/2） |

> ⚠️ **维度归属必须记准：只有 A 与 Q 是 LLM 维度。**
> **F 与 R 都来自确定性 pytest，R 不是 LLM 维度。**
> 代码位置：`execution.py:grade_deterministic` 按 `dimension ∈ {F,R}` 分别累加
> `functional_score` / `robustness_score`；`service.py:_execute_review` 把它们直接传给
> `merge_scores(f=..., r=...)`，而 `a` / `q` 取自 `ai_result`。
> `tests/test_codelab_api.py::TestDimensionSources` 锁死这条接线。

`S = min(F + A + R + Q, 100)`。**LLM 被 prompt 明令禁止返回 F/R 与总分**（system prompt 规则 2、3），
总分只由后端计算。

### 确定性优先（本轮的核心约束）

- `correctness_status` **只由 F/R 决定**（`scoring.py` 的签名是
  `correctness_status(*, f, r, deterministic_available)` —— 参数里根本没有 a/q）。
- **没有 `test_groups` 的任务**：`correctness_status = NOT_VERIFIED`，**`final_score_100 = null`**，
  前端显示「本题没有自动测试，因此不给出总分」，只展示 A/Q 及其各自满分（20 / 10）。
- 学生响应只含白名单字段：`test_groups`（隐藏测试）与 `reference_solution` 在 **DTO 层**就不可达。

### 移植时修掉的 dai 三个已复现缺陷

| # | dai 的缺陷 | CodeLab 的修复 |
| --- | --- | --- |
| **a** | `dimension_score` 无上界 → A=999 能通过校验，算出 `final_score_100 = 1009` | ① Pydantic 上限 ② `merge_scores` 逐维钳制 ③ `min(raw, 100)` ④ **DB CHECK 0–100** |
| **b** | 无「测试 vs LLM」一致性校验 → F=0 全失败但 AI 声称满分仍标记 `graded` | `detect_test_llm_contradiction()`：确定性得分为 0 而 A > 50% 满分 → 强制 `needs_teacher_review` |
| **c** | 分数上限只由 AI 自报的 `triggered_cap_rule_ids` 触发 | **本轮不实现 `score_cap_rules`**（去掉概念而不是修补它） |

另修：dai 在未知 `criterion_id` 时跳过行号校验（这里仍校验）；dai 的学生接口
泄露 `test_groups` / `final_score_100`（这里显式白名单）。

### 教学化输出

`correctness_status`（是否完成任务）/ `student_feedback.{strengths, issues, suggestions, code_suggestions}` /
逐条评分依据（criterion + level + evidence + **真实代码行号**）/ `needs_teacher_review` + 原因。

---

## 5. 安全边界

**真正的隔离边界是 `docker run` 的参数**，不是应用层判断。

| 措施 | 值 |
| --- | --- |
| 网络 | `--network none`（**实测**：学生代码 `socket.create_connection` 抛 `OSError`） |
| 权限 | `--cap-drop ALL` + `--security-opt no-new-privileges` |
| 文件系统 | `--read-only` + `--tmpfs /tmp:exec,size=64m`（**实测**：写 `/` 抛 `OSError`） |
| 用户 | `--user 1000:1000`（**实测**：`os.getuid() == 1000`） |
| 资源 | `--cpus 1` / `--memory 256m` / `--pids-limit 50`（**实测**：分配 900MB 被 OOM 杀死，exit -9） |
| 超时 | 外层 `subprocess timeout` → `docker rm -f`；内层 runner 再设 1 秒更短的超时以给出可读报错（**实测**：死循环 → `TIMEOUT`，无残留容器） |
| 代码传递 | 经 **stdin JSON**，不进 argv（避免进程列表泄露） |
| 输入上限 | 代码 ≤ 50KB；输出 stdout/stderr 截断至 64KB |
| 并发 | 线程级 `BoundedSemaphore`（默认 2）→ 超出返回 `CODELAB_BUSY` |
| 频次 | 每学生每分钟 20 次（复用霜铃限流器，Redis 不可用时进程内降级**仍然强制**） |
| 归属 | 所有 run / review 校验 `student_id`；越权与不存在同样返回 404（不泄露存在性） |
| 提示注入 | 学生代码/题目包在 `<untrusted_student_code>` / `<question>`，system prompt 明确声明为**数据非指令**；**行号由服务端生成** |
| 输出校验 | criterion 必须属于 rubric、**行号必须真实存在**、level 枚举合法、无跨维度重复扣分、分数有界 |
| 数据泄露 | `test_groups` / `reference_solution` **在 DTO 层不可达**，并有测试断言 |

**绝不降级**：Docker 不可用或镜像缺失 → `503 CODELAB_UNAVAILABLE`，**不会**回退到宿主机执行学生代码（有测试覆盖）。
`CODELAB_ENABLED=false`（默认）时端点直接 503，不影响既有启动流程与测试。

---

## 6. 配置

```bash
CODELAB_ENABLED=false                          # 默认关
CODELAB_RUN_IMAGE=dai-kernel-python:latest     # 运行：含 matplotlib/numpy/pandas/sklearn
CODELAB_JUDGE_IMAGE=dai-judge-python:latest    # 判题：含 pytest
CODELAB_RUN_TIMEOUT_SECONDS=10
CODELAB_JUDGE_TIMEOUT_SECONDS=20
CODELAB_MEMORY_LIMIT_MB=256
CODELAB_CPU_LIMIT=1.0
CODELAB_MAX_CODE_BYTES=50000
CODELAB_MAX_OUTPUT_BYTES=65536
CODELAB_MAX_CONCURRENT=2
CODELAB_WORK_DIR=storage/codelab
CODELAB_HOST_WORK_DIR=                         # 空 = 同上（API 未容器化时一致）
CODELAB_RATE_LIMIT_PER_MINUTE=20
AI_JSON_TIMEOUT_SECONDS=120                    # 结构化 JSON 调用（评分）超时
AI_MAX_RETRIES=3
```

> ⚠️ **两个镜像都必须存在**：dai 的 kernel 镜像有 matplotlib 无 pytest，judge 镜像有 pytest 无 matplotlib
> （**已实测确认**），因此不能合并成一个。

---

## 7. 如何新增一个编程任务

1. 写 `backend/data/codelab/tasks/<slug>.json`
2. `test_groups` 约定：`dimension ∈ {F,R}`、**F 组合计 60**、**R 组合计 10**、`id` 全局唯一、`tests` 为可被 pytest 收集的代码
3. 校验并导入：`uv run python -m app.scripts.import_code_tasks [--slug <slug>]`（校验不过整体拒绝导入）
4. 导入是幂等的（按 `slug` upsert），且**不覆盖已锁定的 rubric**

`status` 设为 `PUBLISHED` 学生才可见。`rubric` 留空会让首次评审时由 LLM 生成一次并写回任务（之后复用）。

---

## 8. 明确留到下一阶段的能力（本轮**不做**）

| 能力 | 为什么推迟 |
| --- | --- |
| CodeLab → 学习事件 → Memory Pipeline | 契约稳定前不扩散影响面（`classify_event` 对未知类型返回 None，接入是 1 行，但语义要先定） |
| Profile / Recommendation 联动 | 同上 |
| AI 教师主动调用 CodeLab | 需要先定「如何触发」，避免复制 `QUIZ_INTENT_KEYWORDS` 那类关键词劫持（已被记为 P1-8 缺陷） |
| 任务 CRUD / 教师题目编辑器 | Phase 1 用文件 + 幂等导入（与霜铃既有内容管线一致），成本最低 |
| 运行历史列表 / 草稿自动保存 | 闭环可用即可；刷新丢失当前输出是已知限制 |
| 多语言（JavaScript 等） | 仅 Python |
| 常驻 kernel / 变量跨次持久化 | 一次性容器已覆盖任务型场景；dai 的 `kernel_runner.py` 路径已保留为将来可选 |
| 环境构建 / 自定义镜像 | dai 的 environment-builder v2 是完整课程编排系统，明确排除 |
| 教师覆盖评分 / 人工复核工作流 | `needs_teacher_review` 已落库，但无人工作台 |
| 移动端底部导航入口 | 底部导航 4 项被 T17 验收与 E2E 断言锁定；`/codelab` 目前只进桌面导航 |
| 学习事件 / 试用数据策略联动 | 同上 |

---

## 9. 已知问题

1. **真实 LLM Provider 尚未验收**：当前 `backend/.env` 里的 DeepSeek API Key 已失效
   （实测返回 `Authentication Fails`），因此真实模型路径**未跑通**。

   > mock Provider + 真实 Docker 判题链路**已验证**；
   > 真实 LLM Provider 的**评分质量与 Prompt 配合尚待有效 Key 验收**。

   拆开说清楚「已验证」与「未验证」的边界，避免误读：

   - **已验证**：`AI_PROVIDER=mock` 下的完整调用链（提交 → 沙箱判题 → F/R 落分 →
     LLM 维度接线 → 总分与 `correctness_status` 落库 → 前端呈现），
     判题走**真实 Docker 隔离**；F/R 的确定性打分、沙箱安全边界均有自动化测试覆盖。
   - **未验证**：A（算法）、Q（代码质量）两个 LLM 维度的**实际打分质量**，
     以及 rubric prompt 与真实模型的**配合效果**——都需要有效 Key 才能验收。
   - 附带提到：401 已被正确识别为不可重试错误（未出现重试风暴），
     但**错误处理可用 ≠ 评分质量已验证**。
   - **因此不得把 CodeLab 描述为「已完全验证」。**
2. **摘要/记忆等既有问题不受影响也不受益**：CodeLab 未接入它们。
3. **Worker 依赖为零**：评审是同步的（移出事件循环），刻意不依赖霜铃目前不稳的 Worker 启动链路。
   代价是与请求生命周期绑定；将来任务量上来时应改为 `background_jobs`（`code_reviews.status` 状态机已为此预留）。
4. **镜像 tag 未按 digest 固定**（`dai-kernel-python:latest`）。生产化时应 pin digest，
   配置项已可替换。
5. **`codelab_host_work_dir` 在 API 容器化后必须显式设置**，否则 bind mount 会失败
   （配置项与注释已就位）。
