import asyncio
from collections.abc import AsyncIterator, Sequence
import json
import re
from typing import Any

from app.ai.base import AIProvider
from app.ai.json_utils import OPERATION_MAX_TOKENS


class MockAIProvider(AIProvider):
    """Deterministic Chinese teaching provider for local development and tests."""

    provider = "mock"

    def __init__(
        self,
        model: str = "mock-model",
        *,
        chunk_size: int = 8,
        delay_seconds: float = 0.03,
        max_tokens: int = 512,
    ) -> None:
        self.model = model
        self.chunk_size = max(1, chunk_size)
        self.delay_seconds = max(0.0, delay_seconds)
        self.max_tokens = max(1, max_tokens)

    @staticmethod
    def _reply_for(content: str) -> str:
        if "训练数据" in content:
            return (
                "训练数据就是用来教会模型的一组例子。它可以包含文字、图片或数字，"
                "模型会从这些例子中发现规律，再把规律用于新的问题。"
            )
        if any(keyword in content for keyword in ("为什么出错", "报错", "错误", "出错")):
            return (
                "遇到错误时，可以先复现问题，再检查输入、步骤和错误提示。"
                "把大问题拆成小步骤，通常更容易找到真正的原因。"
            )
        if any(keyword in content for keyword in ("出题", "题目", "练习")):
            return (
                "当然可以。先确定练习的知识点和难度，再用一个问题检验理解，"
                "最后配上简短提示，而不是直接公布答案。"
            )
        if any(keyword in content for keyword in ("解释", "讲给我听", "怎么理解")):
            return (
                "我们先抓住核心概念，再用一个生活中的例子说明，最后用自己的话复述一遍。"
            )
        return (
            "这是个很好的问题。我们可以先明确已知条件，再一步一步推理，"
            "最后用一个小例子检查结论。"
        )

    @staticmethod
    def _reference_reply(system_prompt: str) -> str | None:
        marker = "【知识库参考】"
        if marker not in system_prompt:
            return None
        content: str | None = None
        source: str | None = None
        in_reference = False
        for line in system_prompt.splitlines():
            if line.strip() == marker:
                in_reference = True
                continue
            if not in_reference:
                continue
            if line.startswith("- 内容："):
                content = line[len("- 内容：") :].strip()
            elif line.startswith("- 来源："):
                source = line[len("- 来源：") :].strip()
            elif line.startswith("【"):
                break
        if not content:
            return None
        snippet = content[:140]
        return f"根据知识库资料：{snippet}（参考：{source or '知识库'}）"

    async def stream_chat(
        self,
        history: Sequence[dict[str, Any]],
        system_prompt: str,
    ) -> AsyncIterator[str]:
        content = ""
        for message in reversed(history):
            if message.get("role") in {"user", "student", "STUDENT"}:
                content = str(message.get("content", ""))
                break
        reply = (
            self._reference_reply(system_prompt) or self._reply_for(content)
        )[: self.max_tokens]
        for start in range(0, len(reply), self.chunk_size):
            await asyncio.sleep(self.delay_seconds)
            yield reply[start : start + self.chunk_size]

    # ── 结构化 JSON：CodeLab 评分 ────────────────────────────────
    #
    # 关键设计：mock **不返回固定假数据**，而是从 prompt 中解析出真实的
    # rubric / 行号 / 静态分析结果，再据此生成一份**能通过 validate_ai_output
    # 全部校验**的输出。这样 CI 在 AI_PROVIDER=mock 下会真实走完整条校验链路，
    # 而不是绕过它。

    DEFAULT_QUALITY_CRITERIA = [
        {"id": "Q1", "name": "可读性与命名", "points": 3},
        {"id": "Q2", "name": "代码结构", "points": 3},
        {"id": "Q3", "name": "重复与冗余", "points": 2},
        {"id": "Q4", "name": "接口、规范与安全", "points": 2},
    ]

    @staticmethod
    def _tag_payload(text: str, tag: str) -> Any | None:
        match = re.search(rf"<{tag}>\s*(.*?)\s*</{tag}>", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _code_line_numbers(text: str) -> list[int]:
        """从 `<untrusted_student_code>` 中还原服务端生成的行号。"""
        match = re.search(
            r"<untrusted_student_code>\s*(.*?)\s*</untrusted_student_code>", text, re.DOTALL
        )
        if not match:
            return []
        numbers: list[int] = []
        for line in match.group(1).splitlines():
            head = line.split("|", 1)[0].strip()
            if head.isdigit():
                numbers.append(int(head))
        return numbers

    def _mock_rubric(self) -> dict[str, Any]:
        return {
            "rubric_version": 1,
            "question_type": "编程任务",
            "learning_objective": "完成题目要求的功能实现",
            "explicit_requirements": [],
            "teacher_constraints": [],
            "accepted_strategies": ["任何满足题目要求的正确实现"],
            "algorithm_criteria": [
                {"id": f"A{i}", "name": f"算法要点 {i}", "points": points}
                for i, points in enumerate([5, 5, 5, 5], start=1)
            ],
            "quality_criteria": list(self.DEFAULT_QUALITY_CRITERIA),
            "uncertain_items": [],
        }

    def _mock_grading(self, user_content: str) -> dict[str, Any]:
        rubric = self._tag_payload(user_content, "locked_rubric") or self._mock_rubric()
        static = self._tag_payload(user_content, "static_analysis") or {}
        lines = self._code_line_numbers(user_content)

        # 语法错误时如实给出 missing，让学生能看到「失败」形态的界面
        parseable = bool(static.get("parseable", True))
        level = "complete" if parseable else "missing"
        cited = lines[:1] if lines else []

        algorithm_items = []
        for criterion in rubric.get("algorithm_criteria", []):
            max_score = float(criterion.get("points", 0))
            algorithm_items.append(
                {
                    "criterion_id": criterion["id"],
                    "criterion": criterion.get("name", ""),
                    "level": level,
                    "score": max_score if level == "complete" else 0.0,
                    "max_score": max_score,
                    "code_lines": cited,
                    "evidence": "根据代码本体判断（mock provider）" if parseable
                    else "代码无法解析，未能体现该评分项",
                    "reason_code": None if parseable else "syntax_error",
                    "deduction_reason": None if parseable else "代码存在语法错误",
                }
            )
        quality_items = []
        for criterion in rubric.get("quality_criteria", self.DEFAULT_QUALITY_CRITERIA):
            max_score = float(criterion.get("points", 0))
            quality_items.append(
                {
                    "criterion_id": criterion["id"],
                    "criterion": criterion.get("name", ""),
                    "level": level,
                    "score": max_score if level == "complete" else 0.0,
                    "max_score": max_score,
                    "code_lines": cited,
                    "evidence": "命名与结构清晰（mock provider）" if parseable
                    else "语法错误导致无法评估代码质量",
                    "reason_code": None if parseable else "syntax_error",
                    "deduction_reason": None if parseable else "代码存在语法错误",
                }
            )

        algorithm_max = sum(float(c.get("points", 0)) for c in rubric.get("algorithm_criteria", []))
        quality_max = sum(
            float(c.get("points", 0))
            for c in rubric.get("quality_criteria", self.DEFAULT_QUALITY_CRITERIA)
        )
        return {
            "rubric_version": rubric.get("rubric_version", 1),
            "algorithm": {
                "dimension_score": sum(item["score"] for item in algorithm_items),
                "dimension_max": algorithm_max,
                "items": algorithm_items,
            },
            "code_quality": {
                "dimension_score": sum(item["score"] for item in quality_items),
                "dimension_max": quality_max,
                "items": quality_items,
            },
            "triggered_cap_rule_ids": [],
            "uncertainties": [],
            "needs_teacher_review": not parseable,
            "review_reason": None if parseable else "代码无法解析，建议人工确认",
            "student_feedback": {
                "strengths": ["代码能够运行并完成基本的输入输出"] if parseable
                else ["已经写出了代码结构"],
                "issues": [] if parseable else ["代码存在语法错误，程序无法运行"],
                "suggestions": ["可以尝试给变量起更有意义的名字，并补上关键步骤的注释"],
                "code_suggestions": [],
            },
        }

    async def chat_json(
        self,
        messages: Sequence[dict[str, str]],
        *,
        operation: str,
    ) -> dict[str, Any]:
        if operation not in OPERATION_MAX_TOKENS:
            raise ValueError(
                f"AI 操作 {operation!r} 未登记 completion 预算（OPERATION_MAX_TOKENS）"
            )
        user_content = "\n".join(
            str(m.get("content", "")) for m in messages if m.get("role") == "user"
        )
        if operation == "codelab_rubric":
            return self._mock_rubric()
        if operation == "codelab_grading":
            return self._mock_grading(user_content)
        raise ValueError(f"mock provider 未实现操作: {operation}")
