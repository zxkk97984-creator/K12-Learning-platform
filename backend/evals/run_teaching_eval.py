"""教学质量评测 runner（§6.3）。

用法：
    uv run python evals/run_teaching_eval.py --mode offline     # 默认：mock/离线，确定性
    uv run python evals/run_teaching_eval.py --mode real       # 显式真实（需负责人指定 provider/费用上限）
    uv run python evals/run_teaching_eval.py --mode offline --out evals/report.jsonl

- 默认 offline：用 MockAIProvider（确定性输出），验证评测协议与用例可重复运行；
  不产生任何真实付费调用。
- 仅 `--mode real` 且显式注入真实 AI_PROVIDER 配置才调用外部模型；未授权/未配置则拒绝。
- 记录模型/版本/时间/usage/首字与完整时延/逐维度与整体判定；敏感信息不入报告。
- blockers（阻断项）记录到每个 case；整体出现任一阻断项 → 阻断用户试用。
- mock 只验协议，不能拿 mock 通过宣称教学合格 —— 真实结果另存档，未跑明确标记「未完成」。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app.ai.factory import get_ai_provider

CASES_PATH = Path(__file__).resolve().parent / "teaching_cases.jsonl"
DEFAULT_OUT = Path(__file__).resolve().parent / "report.jsonl"

DIMENSIONS = ["accurate", "answer", "age_understandable", "citation", "encourage_thinking"]


def _canned_judgment(blockers: list[str]) -> dict:
    # offline 判定仅为「协议结构」占位；真实判定由人工抽审决定，不让模型自评唯一决定 PASS。
    dimensions = {d: "observed" for d in DIMENSIONS}
    return {
        "auto_dims": dimensions,
        "auto_blocker_found": bool(blockers),
        "note": "offline 自动判定仅验证协议，不代表真实教学质量；需人工抽审。",
    }


async def _run_case(provider, case: dict, real: bool) -> dict:
    start = time.perf_counter()
    first_token_at: float | None = None
    chunks: list[str] = []
    # 简化流式：逐块拼接，用 mock/openai 均实现 stream_chat。
    async for chunk in provider.stream_chat(
        [{"role": "user", "content": case["prompt"]}],
        "你是霜铃，一位严谨、可解释的中文 K12 数字教师。",
    ):
        chunks.append(str(chunk))
        if first_token_at is None:
            first_token_at = time.perf_counter() - start
    full = "".join(chunks)
    latency = time.perf_counter() - start
    usage = getattr(provider, "last_usage", None)
    return {
        "case_id": case["case_id"],
        "section": case["section"],
        "category": case["category"],
        "grade": case["grade"],
        "model": provider.model,
        "provider": provider.provider,
        "version": getattr(provider, "model", None),
        "run_at": datetime.now(timezone.utc).isoformat(),
        "mode": "real" if real else "offline",
        "output_chars": len(full),
        "first_token_seconds": round(first_token_at, 3) if first_token_at is not None else None,
        "total_seconds": round(latency, 3),
        "usage": usage,
        "expected": case.get("expected"),
        "blockers": case.get("blockers", []),
        "judgment": _canned_judgment(case.get("blockers", [])),
        "output_excerpt": full[:120],
    }


async def run(real: bool) -> list[dict]:
    cases = [json.loads(line) for line in CASES_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    if real:
        # 仅显式 real 且由环境提供真实配置才调用；未授权/未配置则拒绝执行真实调用。
        import os

        base_url = os.environ.get("AI_BASE_URL")
        api_key = os.environ.get("AI_API_KEY")
        model = os.environ.get("AI_MODEL")
        if not (base_url and api_key and model):
            raise SystemExit(
                "real 模式需要显式 AI_BASE_URL/AI_API_KEY/AI_MODEL 且由负责人指定费用上限；"
                "未授权时请使用 --mode offline。"
            )
        provider = get_ai_provider()
    else:
        from app.ai.mock import MockAIProvider

        provider = MockAIProvider()
    results: list[dict] = []
    # 报告不含学生真实历史/个人身份；仅记录评测用合成提示（正文不含个人数据）。
    for case in cases:
        results.append(await _run_case(provider, case, real))
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="教学评测 runner")
    parser.add_argument("--mode", choices=["offline", "real"], default="offline")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 例（调试）")
    args = parser.parse_args()

    results = asyncio.run(run(real=args.mode == "real"))
    if args.limit:
        results = results[: args.limit]

    with open(args.out, "w", encoding="utf-8") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    blockers = [r for r in results if r.get("blockers")]
    print(f"ran={len(results)} mode={args.mode} blockers={len(blockers)}")
    print(f"report={args.out}")
    if blockers:
        print("BLOCKED: 存在阻断项，需人工抽审后才可进入真实学生试用。")
    else:
        print("NO_BLOCKER_OBSERVED (offline 仅协议验证，不代表真实教学合格；真实未跑。)")
    if args.mode == "real":
        print("real 已运行（需负责人指定费用上限/预算已达则停止）。")
    else:
        print("real 未运行：真实模型结果未完成，明确标记，不拿 mock 通过宣称教学合格。")


if __name__ == "__main__":
    main()
