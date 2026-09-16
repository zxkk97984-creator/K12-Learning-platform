"""AI 评分输出的业务校验。

移植 dai-experiment-platform `app/services/ai_score_validation.py:7-99`，
保留其全部有效规则：
- `rubric_version` 必须与锁定 rubric 一致（防止模型用示例版本号）
- A 维度的 `criterion_id` 必须真实存在于 rubric
- Q 维度只能是 Q1–Q4
- **每一条引用的代码行号必须真实存在于学生代码中**（抗幻觉的关键）
- `level` 只能是 complete / partial / missing
- 跨维度重复扣分检测（同一 reason_code + 行号重叠）

并修掉 dai 的一个缺口：未知 `criterion_id` 时 dai 直接 `continue`，
**跳过了行号检查**；这里先记录错误，行号检查仍然执行。

注意：本模块只做「格式与自洽性」校验，**不做分数上界钳制**——那在 scoring.py。
"""

from __future__ import annotations

from typing import Any

VALID_LEVELS = ("complete", "partial", "missing")
QUALITY_CRITERION_IDS = {"Q1", "Q2", "Q3", "Q4"}


def detect_cross_dimension_duplicates(
    a_items: list[dict], q_items: list[dict]
) -> list[dict]:
    """检测 A 与 Q 之间对同一问题的重复扣分（dai ai_score_validation.py:72-99）。"""
    duplicates: list[dict] = []
    for a_item in a_items:
        a_reason = a_item.get("reason_code")
        if not a_reason:
            continue
        a_lines = set(a_item.get("code_lines") or [])
        for q_item in q_items:
            q_reason = q_item.get("reason_code")
            if not q_reason:
                continue
            q_lines = set(q_item.get("code_lines") or [])
            if a_reason == q_reason and a_lines & q_lines:
                duplicates.append(
                    {
                        "a_criterion": a_item.get("criterion_id"),
                        "q_criterion": q_item.get("criterion_id"),
                        "reason_code": a_reason,
                        "overlapping_lines": sorted(a_lines & q_lines),
                    }
                )
    return duplicates


def _check_items(
    items: Any, *, allowed_ids: set[str], label: str, code_lines: set[int], errors: list[str]
) -> list[dict]:
    if not isinstance(items, list):
        errors.append(f"{label} 维度的 items 不是数组")
        return []
    checked: list[dict] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{label} 第 {index + 1} 项不是对象")
            continue
        criterion_id = item.get("criterion_id")
        known = criterion_id in allowed_ids
        if not known:
            errors.append(f"未知的{label}评分项 id: {criterion_id}")
        # 即使 id 未知也继续检查行号与等级：dai 在这里直接 continue，
        # 导致未知 id 的条目可以携带任意伪造行号而不被发现。
        for line in item.get("code_lines") or []:
            if not isinstance(line, int) or line not in code_lines:
                errors.append(f"{label}评分项 {criterion_id} 引用了不存在的代码行 {line}")
        if item.get("level") not in VALID_LEVELS:
            errors.append(f"{label}评分项 {criterion_id} 的等级非法: {item.get('level')}")
        checked.append(item)
    return checked


def validate_ai_output(
    rubric: dict[str, Any],
    ai_result: dict[str, Any],
    code_lines: list[int],
) -> list[str]:
    """校验 AI 评分输出，返回错误列表（空列表表示通过）。"""
    errors: list[str] = []

    rubric_version = rubric.get("rubric_version")
    ai_version = ai_result.get("rubric_version")
    if rubric_version is not None and ai_version is not None and rubric_version != ai_version:
        errors.append(f"Rubric 版本不匹配：期望 {rubric_version}，实际 {ai_version}")

    valid_lines = {line for line in code_lines if isinstance(line, int)}
    algorithm_criteria = rubric.get("algorithm_criteria") or []
    algorithm_ids = {
        str(item.get("id")) for item in algorithm_criteria if isinstance(item, dict) and item.get("id")
    }

    algorithm = ai_result.get("algorithm")
    if not isinstance(algorithm, dict):
        errors.append("缺少 algorithm 维度")
        a_items: list[dict] = []
    else:
        a_items = _check_items(
            algorithm.get("items"),
            allowed_ids=algorithm_ids,
            label="算法",
            code_lines=valid_lines,
            errors=errors,
        )

    code_quality = ai_result.get("code_quality")
    if not isinstance(code_quality, dict):
        errors.append("缺少 code_quality 维度")
        q_items: list[dict] = []
    else:
        q_items = _check_items(
            code_quality.get("items"),
            allowed_ids=QUALITY_CRITERION_IDS,
            label="代码质量",
            code_lines=valid_lines,
            errors=errors,
        )

    for duplicate in detect_cross_dimension_duplicates(a_items, q_items):
        errors.append(
            f"跨维度重复扣分：A 的 {duplicate['a_criterion']} 与 Q 的 "
            f"{duplicate['q_criterion']} 使用相同 reason_code="
            f"{duplicate['reason_code']} 且代码行重叠 {duplicate['overlapping_lines']}"
        )

    return errors


def extract_student_feedback(ai_result: dict[str, Any]) -> dict[str, Any]:
    """只取学生可见的反馈字段（白名单）。

    dai 的 `build_student_grading_breakdown` 尽管注释写着「只返回安全字段」，
    实际把 `test_groups` / `algorithm_score` / `final_score_100` 一起交给了学生。
    这里改为显式白名单：反馈文案 + 带证据的评分项（含行号，便于前端定位）。
    """
    raw = ai_result.get("student_feedback")
    feedback = raw if isinstance(raw, dict) else {}

    def _strings(key: str) -> list[str]:
        value = feedback.get(key)
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if isinstance(item, (str, int, float))]

    suggestions: list[dict] = []
    for item in feedback.get("code_suggestions") or []:
        if isinstance(item, dict) and item.get("diff"):
            suggestions.append(
                {"title": str(item.get("title") or "代码改进建议"), "diff": str(item["diff"])}
            )

    return {
        "strengths": _strings("strengths"),
        "issues": _strings("issues"),
        "suggestions": _strings("suggestions"),
        "code_suggestions": suggestions,
        "uncertainties": [str(u) for u in (ai_result.get("uncertainties") or [])],
    }


def extract_dimension_items(ai_result: dict[str, Any]) -> list[dict]:
    """扁平化 A/Q 评分项，供前端逐条展示（含证据与行号）。"""
    items: list[dict] = []
    for key, label in (("algorithm", "算法"), ("code_quality", "代码质量")):
        dimension = ai_result.get(key)
        if not isinstance(dimension, dict):
            continue
        for item in dimension.get("items") or []:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "dimension": label,
                    "criterion_id": str(item.get("criterion_id") or ""),
                    "criterion": str(item.get("criterion") or ""),
                    "level": str(item.get("level") or ""),
                    "evidence": str(item.get("evidence") or ""),
                    "code_lines": [n for n in (item.get("code_lines") or []) if isinstance(n, int)],
                    "deduction_reason": item.get("deduction_reason"),
                }
            )
    return items
