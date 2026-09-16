# T23 · 教学质量与真实服务评测（§6.3）

> 日期：2026-09-07。任务 T23（M，依赖：T14、T20、T22）。

## 交付内容

- **固定案例**：`backend/evals/teaching_cases.jsonl`，**37 例**，覆盖：
  - 小学/初中/高中各 10 例（解释/举例/纠错/提示）。
  - 边界场景 7 例：无检索证据、上下文切换、错题讲解、错误前提、内容内恶意指令、长对话、模型超时。
- **评测脚本**：`backend/evals/run_teaching_eval.py`，支持 `--mode offline`（默认）与 `--mode real`。
  - 默认 offline：用 `MockAIProvider`（确定性输出）跑全部案例，**不产生任何真实付费调用**，仅验证评测协议与用例可重复运行。
  - `--mode real`：仅当显式提供 `AI_BASE_URL/AI_API_KEY/AI_MODEL`（且由负责人指定费用上限）才调用外部模型；未授权/未配置则拒绝（`--mode real` 输出 `real 需要显式配置...`）。**真实调用未执行**。
  - 逐例记录：case_id/section/category/grade/model/provider/version/run_at/mode/output_chars/first_token_seconds/total_seconds/usage/expected/blockers/judgment/output_excerpt。
  - **敏感信息不入报告**：不使用真实学生历史/个人身份；仅评测用合成提示。
- **验收对应**：①≥30 例可重复运行（37 例，offline 全跑通，`ran=37`）；②任一阻断项（blockers）→ 阻断进入真实学生试用；③mock 与真实结果分栏（每行 `mode` 字段；真实未跑明确标记）。人工抽审决定最终 PASS，不让模型自评唯一决定。

## 运行结果（offline，协议验证）

```bash
cd backend
PYTHONPATH=. uv run python evals/run_teaching_eval.py --mode offline --out /tmp/teaching_report.jsonl
# ran=37 mode=offline blockers=0
# NO_BLOCKER_OBSERVED (offline 仅协议验证，不代表真实教学合格；真实未跑。)
# real 未运行：真实模型结果未完成，明确标记，不拿 mock 通过宣称教学合格。
```

## 阻断项说明

- **真实付费模型调用未执行**：按用户约束"真实付费模型调用...已有明确授权与预算的按授权执行；否则完成代码、工具、离线验证及交付材料，并如实列为待外部验收"。真实教学评测需负责人指定 provider 与费用上限后另行运行，其结果**不得以 mock 通过宣称教学合格**。
- offline 的自动判定仅为协议结构占位（`auto_blocker_found`/`note` 说明），**不代表真实教学质量**；PASS 由人工抽审真实输出决定。

## tasks/todo.md 状态

实现完成 / 部分验收（offline 协议验证通过；真实模型评测待外部授权与费用上限，如实列待外部）。
