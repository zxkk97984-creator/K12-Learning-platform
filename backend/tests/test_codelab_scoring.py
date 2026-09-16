"""CodeLab 评分逻辑单测（纯函数，不依赖数据库 / Docker）。

重点覆盖从 dai 移植时**修掉的三个已复现缺陷**的回归用例：
(a) 无上界 —— 一个声称 A=999 的 AI 输出不得产出 1009 分
(b) 无测试-LLM 一致性校验 —— 测试全失败 + 高算法分必须转人工
(c) 分数上限不可由 AI 自报触发 —— 本轮不实现 score_cap_rules
"""

import pytest

from app.modules.codelab.scoring import (
    ALGORITHM_MAX,
    FUNCTIONAL_MAX,
    QUALITY_MAX,
    ROBUSTNESS_MAX,
    TOTAL_MAX,
    DeterministicSystemError,
    calculate_group_score,
    clamp,
    correctness_status,
    detect_test_llm_contradiction,
    merge_scores,
)


class TestClamp:
    def test_clamps_into_range(self):
        assert clamp(999, 0, 20) == 20
        assert clamp(-5, 0, 20) == 0
        assert clamp(7.5, 0, 20) == 7.5

    def test_rejects_nan_and_inf(self):
        assert clamp(float("nan"), 0, 20) == 0
        assert clamp(float("inf"), 0, 20) == 0
        assert clamp(float("-inf"), 0, 20) == 0

    def test_rejects_non_numeric(self):
        assert clamp("abc", 0, 20) == 0
        assert clamp(None, 0, 20) == 0


class TestCorrectnessStatus:
    def test_not_verified_without_tests(self):
        assert (
            correctness_status(f=0, r=0, deterministic_available=False) == "NOT_VERIFIED"
        )

    def test_passed_when_all_deterministic_points_earned(self):
        assert (
            correctness_status(
                f=FUNCTIONAL_MAX, r=ROBUSTNESS_MAX, deterministic_available=True
            )
            == "PASSED"
        )

    def test_partial_on_partial_credit(self):
        assert (
            correctness_status(f=30, r=5, deterministic_available=True) == "PARTIAL"
        )

    def test_failed_at_zero(self):
        assert correctness_status(f=0, r=0, deterministic_available=True) == "FAILED"

    def test_llm_scores_cannot_change_correctness(self):
        """正确性判定只看 F/R，签名里根本没有 A/Q —— 这是有意的。"""
        import inspect

        params = inspect.signature(correctness_status).parameters
        assert "a" not in params and "q" not in params


class TestMergeScores:
    def test_full_marks_with_tests(self):
        merged = merge_scores(
            f=FUNCTIONAL_MAX, a=ALGORITHM_MAX, r=ROBUSTNESS_MAX, q=QUALITY_MAX,
            deterministic_available=True,
        )
        assert merged.final_score_100 == TOTAL_MAX == 100.0

    def test_defect_a_regression_score_never_exceeds_100(self):
        """dai 缺陷 (a)：A=999 曾被接受并算出 final_score_100 = 1009。"""
        merged = merge_scores(
            f=60, a=999, r=10, q=999, deterministic_available=True
        )
        assert merged.a == ALGORITHM_MAX
        assert merged.q == QUALITY_MAX
        assert merged.final_score_100 == 100.0

    def test_defect_a_regression_negative_scores_clamped(self):
        merged = merge_scores(f=-50, a=-50, r=-50, q=-50, deterministic_available=True)
        assert merged.final_score_100 == 0.0

    def test_no_final_score_without_tests(self):
        """无测试组时不得给出总分 —— 「未验证正确性」不能看起来像 100 分制成绩。"""
        merged = merge_scores(f=0, a=20, r=0, q=10, deterministic_available=False)
        assert merged.final_score_100 is None
        assert merged.a == 20.0 and merged.q == 10.0

    def test_within_range_total_matches_sum(self):
        merged = merge_scores(f=45, a=15, r=8, q=7, deterministic_available=True)
        assert merged.raw_total == 75.0
        assert merged.final_score_100 == 75.0


class TestTestLlmContradiction:
    def test_defect_b_regression_all_tests_failed_high_algorithm(self):
        """dai 缺陷 (b)：F=0 且 AI 声称满分算法分时，dai 直接标记 graded。"""
        reason = detect_test_llm_contradiction(
            deterministic_available=True, f=0, r=0, a=20
        )
        assert reason is not None and "不一致" in reason

    def test_no_flag_when_tests_pass(self):
        assert (
            detect_test_llm_contradiction(deterministic_available=True, f=60, r=10, a=20)
            is None
        )

    def test_no_flag_when_algorithm_score_is_low(self):
        assert (
            detect_test_llm_contradiction(deterministic_available=True, f=0, r=0, a=5)
            is None
        )

    def test_no_flag_without_deterministic_tests(self):
        """没有测试就谈不上「与测试矛盾」，此时走 NOT_VERIFIED 语义。"""
        assert (
            detect_test_llm_contradiction(deterministic_available=False, f=0, r=0, a=20)
            is None
        )


class TestCalculateGroupScore:
    def test_proportional_partial_credit(self):
        assert calculate_group_score(30, {"passed": 2, "failed": 1, "errors": 0}) == 20.0

    def test_skipped_excluded_from_denominator(self):
        assert (
            calculate_group_score(30, {"passed": 3, "failed": 0, "errors": 0, "skipped": 5})
            == 30.0
        )

    def test_zero_denominator_is_a_system_error(self):
        """测试文件本身无法被收集时，不能算学生 0 分，应记系统错误。"""
        with pytest.raises(DeterministicSystemError):
            calculate_group_score(30, {"passed": 0, "failed": 0, "errors": 0})

    def test_all_failed_scores_zero(self):
        assert calculate_group_score(30, {"passed": 0, "failed": 4, "errors": 0}) == 0.0
