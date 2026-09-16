"""CodeLab AI 输出校验单测（纯函数，不依赖数据库 / Docker）。

对应 dai `tests` 中 validator 的覆盖意图，并补上移植时修掉的缺口：
dai 在遇到未知 criterion_id 时直接 `continue`，跳过了行号检查。
"""

from app.modules.codelab.static_analysis import analyze_python
from app.modules.codelab.validation import (
    detect_cross_dimension_duplicates,
    extract_student_feedback,
    validate_ai_output,
)

RUBRIC = {
    "rubric_version": 3,
    "algorithm_criteria": [
        {"id": "A1", "name": "思路", "points": 10},
        {"id": "A2", "name": "边界", "points": 10},
    ],
    "quality_criteria": [
        {"id": "Q1", "name": "命名", "points": 3},
        {"id": "Q2", "name": "结构", "points": 3},
        {"id": "Q3", "name": "冗余", "points": 2},
        {"id": "Q4", "name": "规范", "points": 2},
    ],
}


def _result(**overrides) -> dict:
    base = {
        "rubric_version": 3,
        "algorithm": {
            "dimension_score": 20,
            "dimension_max": 20,
            "items": [
                {
                    "criterion_id": "A1",
                    "criterion": "思路",
                    "level": "complete",
                    "score": 10,
                    "max_score": 10,
                    "code_lines": [1],
                    "evidence": "使用了循环",
                    "reason_code": None,
                    "deduction_reason": None,
                }
            ],
        },
        "code_quality": {
            "dimension_score": 10,
            "dimension_max": 10,
            "items": [
                {
                    "criterion_id": "Q1",
                    "criterion": "命名",
                    "level": "complete",
                    "score": 3,
                    "max_score": 3,
                    "code_lines": [2],
                    "evidence": "命名清晰",
                    "reason_code": None,
                    "deduction_reason": None,
                }
            ],
        },
        "student_feedback": {
            "strengths": ["结构清楚"],
            "issues": [],
            "suggestions": ["补充注释"],
            "code_suggestions": [{"title": "加注释", "diff": "--- a\n+++ b\n@@ -1 +1 @@\n"}],
        },
    }
    base.update(overrides)
    return base


class TestValidateAiOutput:
    def test_valid_output_passes(self):
        assert validate_ai_output(RUBRIC, _result(), [1, 2, 3]) == []

    def test_rubric_version_mismatch(self):
        errors = validate_ai_output(RUBRIC, _result(rubric_version=1), [1, 2, 3])
        assert any("版本不匹配" in e for e in errors)

    def test_unknown_algorithm_criterion_rejected(self):
        result = _result()
        result["algorithm"]["items"][0]["criterion_id"] = "A9"
        errors = validate_ai_output(RUBRIC, result, [1, 2, 3])
        assert any("未知的算法评分项" in e for e in errors)

    def test_quality_id_must_be_q1_to_q4(self):
        result = _result()
        result["code_quality"]["items"][0]["criterion_id"] = "Q9"
        errors = validate_ai_output(RUBRIC, result, [1, 2, 3])
        assert any("未知的代码质量评分项" in e for e in errors)

    def test_hallucinated_line_number_rejected(self):
        """抗幻觉的核心：引用的行号必须真实存在于学生代码中。"""
        result = _result()
        result["algorithm"]["items"][0]["code_lines"] = [99]
        errors = validate_ai_output(RUBRIC, result, [1, 2, 3])
        assert any("不存在的代码行 99" in e for e in errors)

    def test_invalid_level_rejected(self):
        result = _result()
        result["algorithm"]["items"][0]["level"] = "excellent"
        errors = validate_ai_output(RUBRIC, result, [1, 2, 3])
        assert any("等级非法" in e for e in errors)

    def test_unknown_criterion_still_checks_line_numbers(self):
        """移植时修掉的缺口：dai 对未知 id 直接 continue，跳过了行号检查。"""
        result = _result()
        result["algorithm"]["items"][0]["criterion_id"] = "A9"
        result["algorithm"]["items"][0]["code_lines"] = [99]
        errors = validate_ai_output(RUBRIC, result, [1, 2, 3])
        assert any("未知的算法评分项" in e for e in errors)
        assert any("不存在的代码行 99" in e for e in errors)

    def test_missing_dimension_rejected(self):
        result = _result()
        del result["algorithm"]
        errors = validate_ai_output(RUBRIC, result, [1, 2, 3])
        assert any("缺少 algorithm" in e for e in errors)


class TestCrossDimensionDuplicates:
    def test_detects_same_reason_and_overlapping_lines(self):
        a_items = [{"criterion_id": "A1", "reason_code": "poor_readability", "code_lines": [4, 5]}]
        q_items = [{"criterion_id": "Q1", "reason_code": "poor_readability", "code_lines": [5, 6]}]
        duplicates = detect_cross_dimension_duplicates(a_items, q_items)
        assert len(duplicates) == 1
        assert duplicates[0]["overlapping_lines"] == [5]

    def test_no_duplicate_when_lines_disjoint(self):
        a_items = [{"criterion_id": "A1", "reason_code": "x", "code_lines": [1]}]
        q_items = [{"criterion_id": "Q1", "reason_code": "x", "code_lines": [9]}]
        assert detect_cross_dimension_duplicates(a_items, q_items) == []

    def test_no_duplicate_without_reason_code(self):
        a_items = [{"criterion_id": "A1", "reason_code": None, "code_lines": [1]}]
        q_items = [{"criterion_id": "Q1", "reason_code": None, "code_lines": [1]}]
        assert detect_cross_dimension_duplicates(a_items, q_items) == []

    def test_duplicate_surfaces_as_validation_error(self):
        result = _result()
        result["algorithm"]["items"][0]["reason_code"] = "dup"
        result["algorithm"]["items"][0]["code_lines"] = [5]
        result["code_quality"]["items"][0]["reason_code"] = "dup"
        result["code_quality"]["items"][0]["code_lines"] = [5]
        errors = validate_ai_output(RUBRIC, result, [1, 2, 5])
        assert any("跨维度重复扣分" in e for e in errors)


class TestStudentFeedbackWhitelist:
    def test_only_safe_fields_are_exposed(self):
        feedback = extract_student_feedback(_result())
        assert set(feedback) == {
            "strengths",
            "issues",
            "suggestions",
            "code_suggestions",
            "uncertainties",
        }

    def test_no_internal_fields_leak(self):
        """隐藏测试 / 参考答案 / 原始评分对象绝不能出现在学生反馈里。"""
        payload = _result()
        payload["test_groups"] = [{"tests": "import secret"}]
        payload["reference_solution"] = "def solve(): return 42"
        feedback = extract_student_feedback(payload)
        dumped = str(feedback)
        assert "secret" not in dumped
        assert "reference_solution" not in dumped
        assert "return 42" not in dumped

    def test_missing_feedback_degrades_to_empty(self):
        feedback = extract_student_feedback({})
        assert feedback["strengths"] == []
        assert feedback["code_suggestions"] == []

    def test_code_suggestions_require_diff(self):
        payload = _result()
        payload["student_feedback"]["code_suggestions"] = [
            {"title": "无 diff"},
            {"title": "有 diff", "diff": "--- a\n+++ b\n"},
        ]
        feedback = extract_student_feedback(payload)
        assert len(feedback["code_suggestions"]) == 1


class TestStaticAnalysis:
    def test_parses_valid_code(self):
        result = analyze_python("def f(x):\n    return x + 1\n")
        assert result["parseable"] is True
        assert result["function_count"] == 1
        assert result["line_count"] == 2

    def test_reports_syntax_error_without_executing(self):
        result = analyze_python("def f(x)\n    return x\n")
        assert result["parseable"] is False
        assert result["syntax_error"]

    def test_does_not_execute_student_code(self):
        """静态分析必须是只读的：这段代码若被执行会显著改变结果。"""
        result = analyze_python("raise RuntimeError('must not run')\n")
        assert result["parseable"] is True
        assert result["function_count"] == 0

    def test_counts_nesting(self):
        nested = "def f():\n    for i in range(3):\n        if i:\n            while i:\n                i -= 1\n"
        assert analyze_python(nested)["max_nesting"] >= 3
