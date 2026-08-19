from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_ai_provider
from app.config import settings
from app.infrastructure.database.models import QuizQuestion, QuizSession
from app.modules.quiz.quiz_bank import QUIZ_BANK, QuizBankQuestion, select_questions


SKILL_VERSION = "quiz-v1"
MODEL_INFO = {"provider": "quiz-bank", "model": "quiz-bank-v1"}
MAX_HINT_LEVEL = 3


def _is_valid_question(item: Any, required: set[str]) -> bool:
    if not isinstance(item, dict) or not required.issubset(item):
        return False
    if item.get("question_type") != "SINGLE_CHOICE":
        return False
    options = item.get("options")
    if not isinstance(options, list) or not options:
        return False
    if not all(
        isinstance(option, dict) and option.get("key") and option.get("text")
        for option in options
    ):
        return False
    correct_answer = item.get("correct_answer")
    if not isinstance(correct_answer, dict) or not correct_answer.get("key"):
        return False
    return isinstance(item.get("knowledge_point_ids"), list)


@dataclass
class QuizGenerationContext:
    """Validated input and request-scoped output for QuizSkill.generate."""

    student_id: UUID
    conversation_id: UUID
    teacher_role_id: UUID | None = None
    book_id: UUID | None = None
    chapter_id: UUID | None = None
    quiz_kind: str = "CHAPTER_QUIZ"
    question_count: int = 3
    difficulty: str = "MEDIUM"
    title: str = "霜铃随堂测验"
    generated_session: QuizSession | None = field(default=None, init=False, repr=False)


class QuizSkill:
    """Deterministic Quiz Skill boundary for generation, grading and hints.

    The Skill owns quiz-specific question semantics.  Persistence remains in
    the caller's transaction, so QuizService can append LearningEvent in the
    same transaction as the generated session.
    """

    name = "quiz"
    skill_version = SKILL_VERSION
    model_info = MODEL_INFO

    async def generate(
        self,
        session: AsyncSession,
        context: QuizGenerationContext,
    ) -> list[QuizQuestion]:
        """Generate and stage an ACTIVE quiz, returning its question rows.

        The created QuizSession is exposed as ``context.generated_session`` so
        the public method keeps the requested ``list[Question]`` shape while
        allowing the domain service to attach LearningEvent atomically.
        """
        if not 1 <= context.question_count <= 10:
            raise ValueError("question_count must be between 1 and 10")

        now = datetime.now(timezone.utc)
        quiz_session_id = uuid4()
        bank_questions = select_questions(context.difficulty, context.question_count)
        llm_items = await self._try_llm_generate(context)
        source_items = llm_items if llm_items is not None else bank_questions
        session_model_info = self.model_info
        if llm_items is not None:
            session_model_info = {
                "provider": "openai_compatible",
                "model": settings.ai_model,
            }
        question_rows: list[QuizQuestion] = []
        snapshot: list[dict[str, Any]] = []

        for order, bank_question in enumerate(source_items, start=1):
            question_id = uuid4()
            question_type = (
                bank_question["question_type"]
                if isinstance(bank_question, dict)
                else bank_question.question_type
            )
            stem = bank_question["stem"] if isinstance(bank_question, dict) else bank_question.stem
            options = (
                bank_question["options"]
                if isinstance(bank_question, dict)
                else bank_question.options
            )
            correct_answer = (
                bank_question["correct_answer"]
                if isinstance(bank_question, dict)
                else bank_question.correct_answer
            )
            explanation = (
                bank_question["explanation"]
                if isinstance(bank_question, dict)
                else bank_question.explanation
            )
            knowledge_point_ids = (
                bank_question["knowledge_point_ids"]
                if isinstance(bank_question, dict)
                else bank_question.knowledge_point_ids
            )
            source_context = {
                "bank_id": bank_question.get("bank_id", "llm")
                if isinstance(bank_question, dict)
                else bank_question.bank_id,
                "book_id": str(context.book_id) if context.book_id is not None else None,
                "chapter_id": (
                    str(context.chapter_id) if context.chapter_id is not None else None
                ),
            }
            interaction_policy = {"allow_hint": True, "max_hint_level": MAX_HINT_LEVEL}
            question = QuizQuestion(
                question_id=question_id,
                quiz_session_id=quiz_session_id,
                question_order=order,
                question_type=question_type,
                stem=stem,
                options=options,
                correct_answer=correct_answer,
                explanation=explanation,
                source_context=source_context,
                interaction_policy=interaction_policy,
                knowledge_point_ids=list(knowledge_point_ids),
                created_at=now,
            )
            question_rows.append(question)
            snapshot.append(
                {
                    "question_id": str(question_id),
                    "quiz_session_id": str(quiz_session_id),
                    "question_order": order,
                    "question_type": question_type,
                    "stem": stem,
                    "options": options,
                    "correct_answer": correct_answer,
                    "explanation": explanation,
                    "source_context": source_context,
                    "interaction_policy": interaction_policy,
                    "knowledge_point_ids": list(knowledge_point_ids),
                }
            )

        quiz_session = QuizSession(
            quiz_session_id=quiz_session_id,
            student_id=context.student_id,
            conversation_id=context.conversation_id,
            teacher_role_id=context.teacher_role_id,
            book_id=context.book_id,
            chapter_id=context.chapter_id,
            title=context.title,
            quiz_kind=context.quiz_kind,
            status="ACTIVE",
            questions_snapshot=snapshot,
            result_summary={
                "correct": 0,
                "total": context.question_count,
                "hints_used": 0,
            },
            duration_seconds=0,
            ai_feedback=None,
            model_info=session_model_info,
            skill_version=self.skill_version,
            created_at=now,
            updated_at=now,
        )
        session.add(quiz_session)
        await session.flush()
        session.add_all(question_rows)
        context.generated_session = quiz_session
        return question_rows

    async def _try_llm_generate(
        self, context: QuizGenerationContext
    ) -> list[dict[str, Any]] | None:
        """Ask the real LLM for JSON questions; fall back to quiz bank on any failure."""
        if settings.ai_provider.strip().lower() != "openai_compatible":
            return None
        prompt = (
            "请生成 K12 随堂测验题目，严格输出 JSON 数组，每项包含："
            "question_type(SINGLE_CHOICE)、stem、options(数组，每项 key/text)、"
            "correct_answer(对象含 key)、explanation、knowledge_point_ids。"
            f"难度：{context.difficulty}；题数：{context.question_count}；知识点主题：{context.title}。"
        )
        try:
            chunks = []
            async for chunk in get_ai_provider().stream_chat([], prompt):
                chunks.append(chunk)
            data = self._parse_llm_questions("".join(chunks))
        except Exception:
            return None
        if data is None:
            return None
        return data[: context.question_count]

    @staticmethod
    def _parse_llm_questions(text: str) -> list[dict[str, Any]] | None:
        """Parse an LLM JSON array, tolerating markdown code fences."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("[")
            end = cleaned.rfind("]")
            if start == -1 or end <= start:
                return None
            try:
                data = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                return None
        if not isinstance(data, list) or not data:
            return None
        required = {
            "question_type",
            "stem",
            "options",
            "correct_answer",
            "explanation",
            "knowledge_point_ids",
        }
        valid = [item for item in data if _is_valid_question(item, required)]
        return valid or None

    @staticmethod
    def _question_values(
        question: QuizQuestion | QuizBankQuestion,
    ) -> tuple[str, dict[str, Any]]:
        if isinstance(question, QuizBankQuestion):
            return question.question_type, question.correct_answer
        return question.question_type, question.correct_answer or {}

    def grade(
        self,
        question: QuizQuestion | QuizBankQuestion,
        answer: dict[str, Any],
    ) -> bool:
        """Grade an answer using the stored question, never client truth."""
        question_type, correct = self._question_values(question)
        if question_type == "MULTIPLE_CHOICE":
            return sorted(answer.get("keys", [])) == sorted(correct.get("keys", []))
        if question_type == "FILL_BLANK":
            return str(answer.get("value", "")).strip().casefold() == str(
                correct.get("value", "")
            ).strip().casefold()
        return str(answer.get("key", "")).strip().casefold() == str(
            correct.get("key", "")
        ).strip().casefold()

    @staticmethod
    def _find_bank_question(
        question: QuizQuestion | QuizBankQuestion,
    ) -> QuizBankQuestion | None:
        if isinstance(question, QuizBankQuestion):
            return question
        bank_id = (question.source_context or {}).get("bank_id")
        return next((item for item in QUIZ_BANK if item.bank_id == bank_id), None)

    def hint(self, question: QuizQuestion | QuizBankQuestion, level: int) -> str:
        """Return the requested layered hint without exposing DB internals."""
        if not 1 <= level <= MAX_HINT_LEVEL:
            raise ValueError("hint level must be between 1 and 3")
        bank_question = self._find_bank_question(question)
        if bank_question is not None:
            return bank_question.hints[level - 1]
        return f"先回到题干，找出它要求你判断的关键规律（提示 {level}）。"
