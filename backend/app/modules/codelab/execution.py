"""确定性判题（F/R 维度）—— CodeLab 的「正确性权威」。

移植 dai-experiment-platform `app/worker/judge_worker.py:259-327` 的
`run_test_groups` + `_calculate_fr`，抽成不依赖任何 ORM 的纯函数，
只接 「学生代码 + 测试组列表 + 沙箱环境」 三样东西。

**在此处修掉一个 dai 的诚实性缺口**：学生代码有语法错误时，`from user_code import *`
会让 pytest 以「收集错误」结束，插件报告 0/0/0/0；而 dai 的计分把「分母为 0」
一律当成系统错误，学生于是看到「系统错误」而不是「你的代码有语法错误」。
这里先用 AST 预检：解析失败直接判定 `FAILED / F=0 / R=0` 并把语法错误说明清楚，
既更快也更诚实。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.modules.codelab import sandbox
from app.modules.codelab.scoring import DeterministicSystemError, calculate_group_score
from app.modules.codelab.static_analysis import analyze_python

logger = logging.getLogger("shuangling.codelab.execution")


@dataclass
class DeterministicGrade:
    available: bool
    functional_score: float = 0.0
    robustness_score: float = 0.0
    groups: list[dict] = field(default_factory=list)
    system_errors: list[str] = field(default_factory=list)
    syntax_error: str | None = None


def _normalize_groups(test_groups: list[dict] | None) -> list[dict]:
    groups: list[dict] = []
    for raw in test_groups or []:
        if not isinstance(raw, dict):
            continue
        tests = raw.get("tests")
        group_id = raw.get("id")
        dimension = raw.get("dimension")
        if not group_id or not isinstance(tests, str) or not tests.strip():
            continue
        if dimension not in ("F", "R"):
            continue
        try:
            max_score = float(raw.get("max_score", 0))
        except (TypeError, ValueError):
            continue
        if max_score <= 0:
            continue
        groups.append(
            {
                "id": str(group_id),
                "name": str(raw.get("name") or group_id),
                "dimension": dimension,
                "max_score": max_score,
                "tests": tests,
            }
        )
    return groups


def grade_deterministic(
    code: str,
    test_groups: list[dict] | None,
    *,
    work_root: Path,
    host_work_root: Path,
    judge_image: str,
    timeout_seconds: int,
    memory_limit_mb: int,
    cpu_limit: float,
) -> DeterministicGrade:
    """跑完全部测试组，汇总 F/R 分数。

    没有配置测试组 → `available=False`，调用方据此走 review_only 模式。
    """
    groups = _normalize_groups(test_groups)
    if not groups:
        return DeterministicGrade(available=False)

    # AST 预检：语法错误时 pytest 只会给出「收集错误 + 0 计数」，
    # 直接在这里给出准确的判定，不把学生代码的问题伪装成系统错误。
    analysis = analyze_python(code)
    if not analysis["parseable"]:
        return DeterministicGrade(
            available=True,
            functional_score=0.0,
            robustness_score=0.0,
            groups=[],
            syntax_error=str(analysis["syntax_error"]),
        )

    functional = 0.0
    robustness = 0.0
    details: list[dict] = []
    system_errors: list[str] = []

    for group in groups:
        counts, _stdout, stderr = sandbox.run_pytest_group(
            code,
            group["tests"],
            work_root=work_root,
            host_work_root=host_work_root,
            image=judge_image,
            timeout_seconds=timeout_seconds,
            memory_limit_mb=memory_limit_mb,
            cpu_limit=cpu_limit,
        )
        if counts is None:
            # 无法解析结果 = 该组系统错误（超时 / 环境问题），不扣学生分
            system_errors.append(f"测试组 {group['id']} 未能返回结果")
            if stderr:
                logger.warning(
                    "codelab judge group failed", extra={"group": group["id"], "stderr": stderr[:500]}
                )
            details.append({**{k: group[k] for k in ("id", "name", "dimension", "max_score")},
                            "score": None, "counts": None, "system_error": True})
            continue
        try:
            score = calculate_group_score(group["max_score"], counts)
        except DeterministicSystemError as exc:
            system_errors.append(f"测试组 {group['id']}: {exc}")
            details.append({**{k: group[k] for k in ("id", "name", "dimension", "max_score")},
                            "score": None, "counts": counts, "system_error": True})
            continue

        details.append(
            {
                "id": group["id"],
                "name": group["name"],
                "dimension": group["dimension"],
                "max_score": group["max_score"],
                "score": score,
                "counts": counts,
                "system_error": False,
            }
        )
        if group["dimension"] == "F":
            functional += score
        else:
            robustness += score

    return DeterministicGrade(
        available=True,
        functional_score=round(functional, 4),
        robustness_score=round(robustness, 4),
        groups=details,
        system_errors=system_errors,
    )
