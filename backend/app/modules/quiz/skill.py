from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import QuizQuestion, QuizSession
from app.modules.quiz.quiz_bank import QUIZ_BANK, QuizBankQuestion, select_questions


SKILL_VERSION = "quiz-v1"
MODEL_INFO = {"provider": "quiz-bank", "model": "quiz-bank-v1"}
MAX_HINT_LEVEL = 3


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
        question_rows: list[QuizQuestion] = []
        snapshot: list[dict[str, Any]] = []

        for order, bank_question in enumerate(bank_questions, start=1):
            question_id = uuid4()
            source_context = {
                "bank_id": bank_question.bank_id,
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
                question_type=bank_question.question_type,
                stem=bank_question.stem,
                options=bank_question.options,
                correct_answer=bank_question.correct_answer,
                explanation=bank_question.explanation,
                source_context=source_context,
                interaction_policy=interaction_policy,
                knowledge_point_ids=list(bank_question.knowledge_point_ids),
                created_at=now,
            )
            question_rows.append(question)
            snapshot.append(
                {
                    "question_id": str(question_id),
                    "quiz_session_id": str(quiz_session_id),
                    "question_order": order,
                    "question_type": bank_question.question_type,
                    "stem": bank_question.stem,
                    "options": bank_question.options,
                    "correct_answer": bank_question.correct_answer,
                    "explanation": bank_question.explanation,
                    "source_context": source_context,
                    "interaction_policy": interaction_policy,
                    "knowledge_point_ids": list(bank_question.knowledge_point_ids),
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
            model_info=self.model_info,
            skill_version=self.skill_version,
            created_at=now,
            updated_at=now,
        )
        session.add(quiz_session)
        await session.flush()
        session.add_all(question_rows)
        context.generated_session = quiz_session
        return question_rows

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
