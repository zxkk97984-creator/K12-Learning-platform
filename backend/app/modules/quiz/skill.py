from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_ai_provider
from app.config import settings
from app.infrastructure.database.models import QuizQuestion, QuizSession
from app.modules.quiz.chapter_source import (
    ChapterSourceData,
    generate_chapter_questions,
    load_chapter_source,
)
from app.modules.quiz.quiz_bank import QUIZ_BANK, QuizBankQuestion, select_questions


SKILL_VERSION = "quiz-v2"
MODEL_INFO = {"provider": "quiz-bank", "model": "quiz-bank-v1"}
CHAPTER_MODEL_INFO = {"provider": "quiz-skill", "model": "chapter-content-v2"}
MAX_HINT_LEVEL = 3

logger = logging.getLogger(__name__)

_CHOICE_TYPES = ("SINGLE_CHOICE", "TRUE_FALSE")


def _valid_choice_options(options: Any) -> bool:
    return (
        isinstance(options, list)
        and bool(options)
        and all(
            isinstance(option, dict) and option.get("key") and option.get("text")
            for option in options
        )
    )


def _is_valid_question(item: Any, required: set[str]) -> bool:
    """按题型校验 LLM 输出：四种题型均可，结构必须可判分。"""
    if not isinstance(item, dict) or not required.issubset(item):
        return False
    question_type = item.get("question_type")
    correct_answer = item.get("correct_answer")
    knowledge_point_ids = item.get("knowledge_point_ids")
    if not isinstance(knowledge_point_ids, list):
        return False
    if not isinstance(correct_answer, dict):
        return False
    if question_type in _CHOICE_TYPES:
        if not _valid_choice_options(item.get("options")):
            return False
        return bool(correct_answer.get("key"))
    if question_type == "MULTIPLE_CHOICE":
        if not _valid_choice_options(item.get("options")):
            return False
        keys = correct_answer.get("keys")
        return isinstance(keys, list) and len(keys) > 0
    if question_type == "FILL_BLANK":
        value = correct_answer.get("value")
        return isinstance(value, str) and value.strip() != ""
    return False


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
    # 对话链路（页面感知出题）必须严格：无内容即报错；
    # 直连 API/管理路径保持旧行为：可审计地回退内置题库。
    allow_bank_fallback: bool = True
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

        # ---- 题目来源解析（Phase 2-B）----
        # 携带章节上下文时：LLM 优先，其次基于本章真实内容确定性生成；
        # 两者都失败必须显式抛错（由调用方转成 QUIZ_SKILL_ERROR），绝不
        # 静默回退到与章节无关的训练数据题库。
        # 未携带章节时：保持原有内置题库路径（与章节无关的通用测验）。
        chapter_source: ChapterSourceData | None = None
        bank_fallback_reason: str | None = None
        if context.chapter_id is not None:
            chapter_source = await load_chapter_source(
                session, context.book_id, context.chapter_id
            )
            if chapter_source is None:
                from app.infrastructure.database.models import Chapter as _Chapter

                chapter_row = await session.get(_Chapter, context.chapter_id)
                if chapter_row is None or not context.allow_bank_fallback:
                    # 章节不存在，或调用方要求严格语义（对话链路）：
                    # 必须显式失败，绝不静默给出与章节无关的题目。
                    state = "不存在" if chapter_row is None else "缺少可出题的内容"
                    raise ValueError(
                        f"当前章节{state}，无法生成相关题目："
                        f"chapter_id={context.chapter_id}"
                    )
                bank_fallback_reason = "chapter_content_unavailable"
                logger.warning(
                    "chapter %s lacks quiz-able content; "
                    "falling back to bank (audited)",
                    context.chapter_id,
                )

        bank_questions = select_questions(context.difficulty, context.question_count)
        llm_items = (
            None
            if bank_fallback_reason
            else await self._try_llm_generate(context, chapter_source)
        )
        session_model_info = self.model_info
        generation_kind = "bank_fallback" if bank_fallback_reason else "bank"
        if llm_items is not None:
            source_items: list[Any] = llm_items
            session_model_info = {
                "provider": "openai_compatible",
                "model": settings.ai_model,
            }
            generation_kind = "llm"
        elif chapter_source is not None:
            source_items = generate_chapter_questions(
                chapter_source, count=context.question_count
            )
            session_model_info = dict(CHAPTER_MODEL_INFO)
            generation_kind = "chapter_deterministic"
        else:
            source_items = bank_questions

        question_rows: list[QuizQuestion] = []
        snapshot: list[dict[str, Any]] = []

        for order, item in enumerate(source_items, start=1):
            is_dict = isinstance(item, dict)
            question_type = item["question_type"] if is_dict else item.question_type
            stem = item["stem"] if is_dict else item.stem
            options = item["options"] if is_dict else item.options
            correct_answer = (
                item["correct_answer"] if is_dict else item.correct_answer
            )
            explanation = (
                item["explanation"] if is_dict else item.explanation
            )
            knowledge_point_ids = (
                item["knowledge_point_ids"]
                if is_dict
                else list(item.knowledge_point_ids)
            )
            if generation_kind in ("bank", "bank_fallback"):
                source_context = {
                    "bank_id": item.bank_id,
                    "book_id": str(context.book_id) if context.book_id is not None else None,
                    "chapter_id": (
                        str(context.chapter_id) if context.chapter_id is not None else None
                    ),
                    "generation": generation_kind,
                }
                if bank_fallback_reason:
                    source_context["fallback_reason"] = bank_fallback_reason
            else:
                source_context = {
                    "generation": generation_kind,
                    "source": "chapter_content",
                    "book_id": str(chapter_source.book_id) if chapter_source else None,
                    "chapter_id": (
                        str(chapter_source.chapter_id) if chapter_source else None
                    ),
                    "chapter_title": chapter_source.chapter_title if chapter_source else None,
                    "book_title": chapter_source.book_title if chapter_source else None,
                }
            interaction_policy = {"allow_hint": True, "max_hint_level": MAX_HINT_LEVEL}
            question = QuizQuestion(
                question_id=uuid4(),
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
                    "question_id": str(question.question_id),
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
        self,
        context: QuizGenerationContext,
        chapter_source: ChapterSourceData | None = None,
    ) -> list[dict[str, Any]] | None:
        """Ask the real LLM for JSON questions; fall back per source policy.

        携带章节上下文时，prompt 注入本章真实内容节选；LLM 失败/输出非法
        返回 None，由调用方走本章确定性生成（而非章节无关题库）。
        """
        if settings.ai_provider.strip().lower() != "openai_compatible":
            return None
        type_spec = (
            "question_type(SINGLE_CHOICE/MULTIPLE_CHOICE/TRUE_FALSE/FILL_BLANK)"
        )
        if chapter_source is not None:
            sections = list(chapter_source.section_keys)
            excerpt_lines = []
            for i, text in enumerate(chapter_source.texts[:8]):
                section = sections[i] if i < len(sections) else ""
                excerpt_lines.append(f"- [{section or '正文'}] {text}")
            kp_line = (
                "、".join(kp["name"] for kp in chapter_source.knowledge_points)
                or "暂无"
            )
            prompt = (
                "你是 K12 出题助手。请只依据下面的真实章节内容出题，"
                "严格输出 JSON 数组，每项包含："
                f"{type_spec}、stem、options(数组，每项 key/text；FILL_BLANK 可为空数组)、"
                "correct_answer(SINGLE_CHOICE/TRUE_FALSE 含 key；MULTIPLE_CHOICE 含 keys 数组；"
                "FILL_BLANK 含 value 字符串)、explanation、knowledge_point_ids(可使用空数组)。"
                f"难度：{context.difficulty}；题数：{context.question_count}；"
                "题型需覆盖至少两种。\n"
                f"【章节】《{chapter_source.book_title}》·{chapter_source.chapter_title}\n"
                f"【知识点】{kp_line}\n"
                "【内容节选】\n" + "\n".join(excerpt_lines)
            )
        else:
            prompt = (
                "请生成 K12 随堂测验题目，严格输出 JSON 数组，每项包含："
                f"{type_spec}、stem、options(数组，每项 key/text)、"
                "correct_answer(对象含 key 或 keys/value)、explanation、knowledge_point_ids。"
                f"难度：{context.difficulty}；题数：{context.question_count}；知识点主题：{context.title}。"
            )
        try:
            chunks = []
            async for chunk in get_ai_provider().stream_chat([], prompt):
                chunks.append(chunk)
            data = self._parse_llm_questions("".join(chunks))
        except Exception:
            logger.warning("quiz LLM generation failed; falling back", exc_info=True)
            return None
        if data is None:
            logger.warning("quiz LLM output invalid; falling back")
            return None
        # 缺口 3：合法题数必须足额。LLM 只给出 1-2 道而请求 3 道时，
        # 若截断接受会导致 result_summary.total 与实际题数不一致；
        # 视为本次输出不可用，交由调用方按来源策略回退
        # （章节上下文 → 确定性生成；无章节 → 内置题库）。
        if len(data) < context.question_count:
            logger.warning(
                "quiz LLM returned %d valid questions but %d requested; "
                "treating output as unusable",
                len(data),
                context.question_count,
            )
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
