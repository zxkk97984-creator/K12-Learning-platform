"""CodeLab 评分：维度钳制、合并、正确性判定。

维度模型移植自 dai-experiment-platform（F60 + A20 + R10 + Q10）：

    F  功能正确性  60  ← 确定性 pytest 测试组
    R  鲁棒性      10  ← 确定性 pytest 测试组
    A  算法质量    20  ← LLM（rubric 约束）
    Q  代码质量    10  ← LLM（Q1-Q4 固定 3/3/2/2）

**在移植时修掉了 dai 的三个已复现缺陷**（见 .audit/dai-AI-grading.md §6）：

(a) 无上界：dai 的 `GradeDimension.dimension_score` 只有 `ge=0`，一个返回 A=999
    的响应能通过校验并算出 `final_score_100 = 1009`。
    这里三道防线：`_clamp` 逐项钳制 → `merge_scores` 再钳制 → DB CHECK 兜底。
(b) 无「测试 vs LLM」一致性校验：dai 在 F=0（测试全失败）时仍接受 AI 给出的
    满分算法分并标记 graded。这里 `correctness_status` **只由确定性测试决定**，
    且测试全失败却拿到高 A 分时会强制 `needs_teacher_review`。
(c) 分数上限只由 AI 自报的 `triggered_cap_rule_ids` 触发：本轮**不实现**
    score_cap_rules，去掉这个概念而不是修补它。
"""

from __future__ import annotations

from dataclasses import dataclass

FUNCTIONAL_MAX = 60.0
ROBUSTNESS_MAX = 10.0
ALGORITHM_MAX = 20.0
QUALITY_MAX = 10.0
TOTAL_MAX = FUNCTIONAL_MAX + ROBUSTNESS_MAX + ALGORITHM_MAX + QUALITY_MAX

# 正确性判定阈值
PASSED_RATIO = 0.999
PARTIAL_RATIO = 0.0

# 测试全失败时，算法分超过该比例即视为「与测试结果矛盾」，转人工复核
CONTRADICTION_ALGORITHM_RATIO = 0.5


@dataclass(frozen=True)
class MergedScore:
    f: float
    a: float
    r: float
    q: float
    raw_total: float
    final_score_100: float | None


def clamp(value: float, low: float, high: float) -> float:
    """把任意数值钳制到 [low, high]。NaN / inf 归到 low。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return low
    if number != number or number in (float("inf"), float("-inf")):
        return low
    return max(low, min(high, number))


def correctness_status(
    *, f: float, r: float, deterministic_available: bool
) -> str:
    """正确性**只**由确定性测试决定，绝不采纳 LLM 的判断。

    无测试组时返回 NOT_VERIFIED —— 这是「不得只靠 LLM 给出看似权威的总分」
    在代码层的落点。
    """
    if not deterministic_available:
        return "NOT_VERIFIED"
    earned = clamp(f, 0.0, FUNCTIONAL_MAX) + clamp(r, 0.0, ROBUSTNESS_MAX)
    possible = FUNCTIONAL_MAX + ROBUSTNESS_MAX
    if possible <= 0:
        return "NOT_VERIFIED"
    ratio = earned / possible
    if ratio >= PASSED_RATIO:
        return "PASSED"
    if ratio > PARTIAL_RATIO:
        return "PARTIAL"
    return "FAILED"


def merge_scores(
    *,
    f: float | None,
    a: float | None,
    r: float | None,
    q: float | None,
    deterministic_available: bool,
) -> MergedScore:
    """合并四个维度。

    有测试组时给出 `final_score_100`；**无测试组时 `final_score_100` 为 None**
    —— 「未验证正确性」的作业不应得到一个看起来权威的总分。
    """
    f_val = clamp(f or 0.0, 0.0, FUNCTIONAL_MAX)
    r_val = clamp(r or 0.0, 0.0, ROBUSTNESS_MAX)
    a_val = clamp(a or 0.0, 0.0, ALGORITHM_MAX)
    q_val = clamp(q or 0.0, 0.0, QUALITY_MAX)
    raw = round(f_val + a_val + r_val + q_val, 4)
    if not deterministic_available:
        return MergedScore(f_val, a_val, r_val, q_val, raw, None)
    # 即使各维度都已在范围内，总和仍显式再钳一次：防止未来新增维度时漏掉
    return MergedScore(f_val, a_val, r_val, q_val, raw, round(clamp(raw, 0.0, TOTAL_MAX), 4))


def detect_test_llm_contradiction(
    *, deterministic_available: bool, f: float, r: float, a: float
) -> str | None:
    """检测「测试全失败但 LLM 给出高分算法评价」的矛盾（修复 dai 缺陷 b）。

    这不改变分数（A 仍是 A），但必须转人工复核 —— 否则一个幻觉的算法分
    会让学生在没有通过任何测试的情况下看到一个体面的总分。
    """
    if not deterministic_available:
        return None
    earned = clamp(f, 0.0, FUNCTIONAL_MAX) + clamp(r, 0.0, ROBUSTNESS_MAX)
    if earned > 0:
        return None
    if clamp(a, 0.0, ALGORITHM_MAX) > ALGORITHM_MAX * CONTRADICTION_ALGORITHM_RATIO:
        return (
            "自动测试全部未通过，但 AI 给出的算法评价明显偏高，二者不一致，"
            "需要人工复核后再作为最终结果。"
        )
    return None


def calculate_group_score(max_score: float, counts: dict) -> float:
    """单个测试组得分 = 满分 × 通过数 / (通过 + 失败 + 错误)。

    逐字移植 dai `deterministic_scoring.py:26-31`：skipped 不计入分母；
    分母为 0（例如测试文件本身无法被收集）抛 `DeterministicSystemError`，
    由调用方记为该组的**系统错误**而不是学生扣分。
    """
    denominator = int(counts.get("passed", 0)) + int(counts.get("failed", 0)) + int(
        counts.get("errors", 0)
    )
    if denominator <= 0:
        raise DeterministicSystemError("测试组没有可计分用例")
    return round(float(max_score) * int(counts.get("passed", 0)) / denominator, 4)


class DeterministicSystemError(RuntimeError):
    """测试组系统错误 —— 不是学生的错。"""
