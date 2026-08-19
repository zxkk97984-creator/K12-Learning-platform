import base64
import binascii
import json
import logging
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    Book,
    Chapter,
    Conversation,
    LearningEvent,
    Message,
    QuizAnswer,
    QuizInteraction,
    QuizQuestion,
    QuizSession,
    StudentProfile,
)
from app.modules.quiz.skill import QuizGenerationContext, QuizSkill
from app.modules.quiz.schemas import (
    CreateQuizSessionRequest,
    QuizAnswerDTO,
    QuizHintDTO,
    QuizInteractionDTO,
    QuizPageMeta,
    QuizQuestionDTO,
    QuizSessionDTO,
    QuizSessionListItemDTO,
    SubmitQuizAnswerRequest,
)
from app.skills.registry import get_skill


logger = logging.getLogger(__name__)


MAX_ATTEMPTS = 3


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _encode_cursor(created_at: datetime, entity_id: UUID) -> str:
    payload = json.dumps([created_at.isoformat(), str(entity_id)])
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = json.loads(
            base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        )
        if not isinstance(raw, list) or len(raw) != 2:
            raise ValueError("invalid cursor")
        created_at = datetime.fromisoformat(raw[0])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return created_at, UUID(raw[1])
    except (
        binascii.Error,
        UnicodeDecodeError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise _error(422, "VALIDATION_ERROR", "invalid cursor") from exc


def _session_list_dto(quiz_session: QuizSession) -> QuizSessionListItemDTO:
    return QuizSessionListItemDTO.model_validate(quiz_session)


def _session_dto(quiz_session: QuizSession) -> QuizSessionDTO:
    return QuizSessionDTO.model_validate(quiz_session)


def _question_dto(
    question: QuizQuestion,
    *,
    reveal_answer: bool,
) -> QuizQuestionDTO:
    data: dict[str, Any] = {
        "question_id": question.question_id,
        "quiz_session_id": question.quiz_session_id,
        "question_order": question.question_order,
        "question_type": question.question_type,
        "stem": question.stem,
        "options": question.options or [],
        "source_context": question.source_context,
        "interaction_policy": question.interaction_policy or {
            "allow_hint": True,
            "max_hint_level": 3,
        },
        "knowledge_point_ids": question.knowledge_point_ids or [],
    }
    if reveal_answer:
        data["correct_answer"] = question.correct_answer
        data["explanation"] = question.explanation
    return QuizQuestionDTO.model_validate(data)


def _answer_dto(answer: QuizAnswer) -> QuizAnswerDTO:
    return QuizAnswerDTO.model_validate(answer)


def _interaction_dto(interaction: QuizInteraction) -> QuizInteractionDTO:
    return QuizInteractionDTO.model_validate(interaction)


class QuizService:
    """Quiz lifecycle service with immutable question snapshots and audit writes."""

    def __init__(self, skill: QuizSkill | None = None) -> None:
        self.skill = skill or cast(QuizSkill, get_skill("quiz"))

    async def _get_profile(
        self, session: AsyncSession, user_id: UUID
    ) -> StudentProfile:
        profile = (
            await session.execute(
                select(StudentProfile).where(StudentProfile.user_id == user_id)
            )
        ).scalar_one_or_none()
        if profile is None:
            raise _error(404, "STUDENT_PROFILE_NOT_FOUND", "student profile not found")
        return profile

    async def _get_owned_session(
        self,
        session: AsyncSession,
        user_id: UUID,
        quiz_session_id: UUID,
    ) -> QuizSession:
        profile = await self._get_profile(session, user_id)
        quiz_session = await session.get(QuizSession, quiz_session_id)
        if quiz_session is None:
            raise _error(404, "QUIZ_NOT_FOUND", "quiz session not found")
        if quiz_session.student_id != profile.student_id:
            raise _error(403, "FORBIDDEN", "quiz session does not belong to student")
        return quiz_session

    async def _get_owned_question(
        self,
        session: AsyncSession,
        user_id: UUID,
        quiz_session_id: UUID,
        question_id: UUID,
    ) -> tuple[QuizSession, QuizQuestion, StudentProfile]:
        quiz_session = await self._get_owned_session(session, user_id, quiz_session_id)
        profile = await self._get_profile(session, user_id)
        question = (
            await session.execute(
                select(QuizQuestion).where(
                    QuizQuestion.quiz_session_id == quiz_session_id,
                    QuizQuestion.question_id == question_id,
                )
            )
        ).scalar_one_or_none()
        if question is None:
            raise _error(404, "QUESTION_NOT_FOUND", "question not found")
        return quiz_session, question, profile

    async def create_session(
        self,
        session: AsyncSession,
        user_id: UUID,
        request: CreateQuizSessionRequest,
    ) -> QuizSessionDTO:
        profile = await self._get_profile(session, user_id)
        conversation = await session.get(Conversation, request.conversation_id)
        if conversation is None:
            raise _error(404, "CONVERSATION_NOT_FOUND", "conversation not found")
        if conversation.student_id != profile.student_id:
            raise _error(403, "FORBIDDEN", "conversation does not belong to student")
        if conversation.status == "DELETED":
            raise _error(409, "QUIZ_INVALID_STATUS", "deleted conversation cannot create quiz")

        book_id = request.book_id
        chapter_id = request.chapter_id
        if book_id is not None and await session.get(Book, book_id) is None:
            raise _error(404, "BOOK_NOT_FOUND", "book not found")
        if chapter_id is not None:
            chapter = await session.get(Chapter, chapter_id)
            if chapter is None:
                raise _error(404, "CHAPTER_NOT_FOUND", "chapter not found")
            if book_id is not None and chapter.book_id != book_id:
                raise _error(422, "VALIDATION_ERROR", "chapter does not belong to book")
            book_id = book_id or chapter.book_id

        chapter_title = None
        if chapter_id is not None:
            chapter = await session.get(Chapter, chapter_id)
            chapter_title = chapter.title if chapter is not None else None
        title = f"{chapter_title} · 随堂测验" if chapter_title else "霜铃随堂测验"
        context = QuizGenerationContext(
            student_id=profile.student_id,
            teacher_role_id=conversation.teacher_role_id or profile.current_teacher_role_id,
            conversation_id=request.conversation_id,
            book_id=book_id,
            chapter_id=chapter_id,
            quiz_kind=request.quiz_kind,
            question_count=request.question_count,
            difficulty=request.difficulty,
            title=title,
        )
        await self.skill.generate(session, context)
        quiz_session = context.generated_session
        if quiz_session is None:
            raise RuntimeError("QuizSkill did not create a quiz session")
        now = quiz_session.created_at
        session.add(
            LearningEvent(
                student_id=profile.student_id,
                event_type="QUIZ_CREATED",
                occurred_at=now,
                book_id=book_id,
                chapter_id=chapter_id,
                conversation_id=request.conversation_id,
                quiz_session_id=quiz_session.quiz_session_id,
                payload={"quiz_kind": request.quiz_kind, "question_count": request.question_count},
                created_at=now,
            )
        )
        await session.commit()
        await session.refresh(quiz_session)
        return _session_dto(quiz_session)

    async def list_sessions(
        self,
        session: AsyncSession,
        user_id: UUID,
        *,
        cursor: str | None,
        limit: int,
        quiz_kind: str | None,
        status: str | None,
        book_id: UUID | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> tuple[list[QuizSessionListItemDTO], QuizPageMeta]:
        profile = await self._get_profile(session, user_id)
        query = select(QuizSession).where(QuizSession.student_id == profile.student_id)
        if quiz_kind is not None:
            query = query.where(QuizSession.quiz_kind == quiz_kind)
        if status is not None:
            query = query.where(QuizSession.status == status)
        if book_id is not None:
            query = query.where(QuizSession.book_id == book_id)
        if date_from is not None:
            query = query.where(QuizSession.created_at >= date_from)
        if date_to is not None:
            query = query.where(QuizSession.created_at <= date_to)
        if cursor is not None:
            cursor_created_at, cursor_id = _decode_cursor(cursor)
            query = query.where(
                tuple_(QuizSession.created_at, QuizSession.quiz_session_id)
                < (cursor_created_at, cursor_id)
            )
        query = query.order_by(
            QuizSession.created_at.desc(), QuizSession.quiz_session_id.desc()
        ).limit(limit + 1)
        rows = (await session.execute(query)).scalars().all()
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = (
            _encode_cursor(page[-1].created_at, page[-1].quiz_session_id)
            if has_more and page
            else None
        )
        return [_session_list_dto(row) for row in page], QuizPageMeta(
            next_cursor=next_cursor, has_more=has_more
        )

    async def get_session(
        self, session: AsyncSession, user_id: UUID, quiz_session_id: UUID
    ) -> QuizSessionDTO:
        quiz_session = await self._get_owned_session(session, user_id, quiz_session_id)
        return _session_dto(quiz_session)

    async def list_questions(
        self, session: AsyncSession, user_id: UUID, quiz_session_id: UUID
    ) -> list[QuizQuestionDTO]:
        quiz_session = await self._get_owned_session(session, user_id, quiz_session_id)
        questions = (
            await session.execute(
                select(QuizQuestion)
                .where(QuizQuestion.quiz_session_id == quiz_session_id)
                .order_by(QuizQuestion.question_order.asc())
            )
        ).scalars().all()
        answered_ids = {
            row[0]
            for row in (
                await session.execute(
                    select(QuizAnswer.question_id).where(
                        QuizAnswer.quiz_session_id == quiz_session_id
                    )
                )
            ).all()
        }
        reveal_all = quiz_session.status in {"COMPLETED", "ABANDONED"}
        return [
            _question_dto(
                question,
                reveal_answer=reveal_all or question.question_id in answered_ids,
            )
            for question in questions
        ]

    async def _next_interaction_sequence(
        self, session: AsyncSession, quiz_session_id: UUID
    ) -> int:
        current = (
            await session.execute(
                select(func.max(QuizInteraction.sequence)).where(
                    QuizInteraction.quiz_session_id == quiz_session_id
                )
            )
        ).scalar_one()
        return (current or 0) + 1

    async def _next_message_sequence(
        self, session: AsyncSession, conversation_id: UUID
    ) -> int:
        current = (
            await session.execute(
                select(func.max(Message.sequence)).where(
                    Message.conversation_id == conversation_id
                )
            )
        ).scalar_one()
        return (current or 0) + 1

    async def _find_answer_replay(
        self,
        session: AsyncSession,
        quiz_session_id: UUID,
        question_id: UUID,
        submitted_answer: dict[str, Any],
        idempotency_key: str | None,
    ) -> QuizAnswer | None:
        answers = (
            await session.execute(
                select(QuizAnswer)
                .where(
                    QuizAnswer.quiz_session_id == quiz_session_id,
                    QuizAnswer.question_id == question_id,
                )
                .order_by(QuizAnswer.attempt_no.desc())
            )
        ).scalars().all()
        if idempotency_key is not None:
            interactions = (
                await session.execute(
                    select(QuizInteraction)
                    .where(
                        QuizInteraction.quiz_session_id == quiz_session_id,
                        QuizInteraction.question_id == question_id,
                        QuizInteraction.interaction_type == "ANSWER_SUBMIT",
                    )
                    .order_by(QuizInteraction.sequence.desc())
                )
            ).scalars().all()
            for interaction in interactions:
                if (interaction.payload or {}).get("idempotency_key") != idempotency_key:
                    continue
                if (interaction.payload or {}).get("submitted_answer") != submitted_answer:
                    raise _error(
                        409,
                        "IDEMPOTENCY_KEY_REUSED",
                        "idempotency key was reused with a different answer",
                    )
                if interaction.answer_id is not None:
                    return await session.get(QuizAnswer, interaction.answer_id)
        elif answers and answers[0].submitted_answer == submitted_answer:
            # Compatibility fallback for clients that have not started sending
            # Idempotency-Key yet: an identical latest submission is a replay.
            return answers[0]
        return None

    def _is_answer_correct(
        self, question: QuizQuestion, submitted: dict[str, Any]
    ) -> bool:
        return self.skill.grade(question, submitted)

    async def _current_hint_level(
        self, session: AsyncSession, quiz_session_id: UUID, question_id: UUID
    ) -> int:
        interactions = (
            await session.execute(
                select(QuizInteraction).where(
                    QuizInteraction.quiz_session_id == quiz_session_id,
                    QuizInteraction.question_id == question_id,
                    QuizInteraction.interaction_type == "HINT_REQUEST",
                )
            )
        ).scalars().all()
        return max(
            [int((item.payload or {}).get("hint_level", 0)) for item in interactions]
            or [0]
        )

    async def submit_answer(
        self,
        session: AsyncSession,
        user_id: UUID,
        quiz_session_id: UUID,
        question_id: UUID,
        request: SubmitQuizAnswerRequest,
        idempotency_key: str | None,
    ) -> tuple[QuizAnswerDTO, bool]:
        quiz_session, question, profile = await self._get_owned_question(
            session, user_id, quiz_session_id, question_id
        )
        replay = await self._find_answer_replay(
            session,
            quiz_session_id,
            question_id,
            request.answer,
            idempotency_key,
        )
        if replay is not None:
            return _answer_dto(replay), True
        if quiz_session.status != "ACTIVE":
            code = "QUIZ_FINALIZED" if quiz_session.status == "COMPLETED" else "QUIZ_NOT_ACTIVE"
            raise _error(409, code, "quiz session is not accepting answers")

        current_hint_level = await self._current_hint_level(
            session, quiz_session_id, question_id
        )
        # The client field is informational only.  The persisted interaction
        # history is authoritative so a client cannot inflate hint usage.
        hint_level = current_hint_level
        attempt_no = (
            await session.execute(
                select(func.max(QuizAnswer.attempt_no)).where(
                    QuizAnswer.quiz_session_id == quiz_session_id,
                    QuizAnswer.question_id == question_id,
                )
            )
        ).scalar_one()
        attempt_no = (attempt_no or 0) + 1
        is_correct = self._is_answer_correct(question, request.answer)
        is_final = is_correct or attempt_no >= MAX_ATTEMPTS
        now = datetime.now(timezone.utc)
        answer = QuizAnswer(
            answer_id=uuid4(),
            quiz_session_id=quiz_session_id,
            question_id=question_id,
            student_id=profile.student_id,
            submitted_answer=request.answer,
            is_correct=is_correct,
            attempt_no=attempt_no,
            hint_level_at_submit=hint_level,
            is_final=is_final,
            submitted_at=now,
            created_at=now,
        )
        session.add(answer)
        await session.flush()

        sequence = await self._next_interaction_sequence(session, quiz_session_id)
        submit_payload: dict[str, Any] = {
            "submitted_answer": request.answer,
            "attempt_no": attempt_no,
        }
        if idempotency_key is not None:
            submit_payload["idempotency_key"] = idempotency_key
        session.add(
            QuizInteraction(
                quiz_session_id=quiz_session_id,
                question_id=question_id,
                interaction_type="ANSWER_SUBMIT",
                payload=submit_payload,
                answer_id=answer.answer_id,
                sequence=sequence,
                created_at=now,
            )
        )
        session.add(
            QuizInteraction(
                quiz_session_id=quiz_session_id,
                question_id=question_id,
                interaction_type="ANSWER_RESULT",
                payload={"is_correct": is_correct, "attempt_no": attempt_no},
                answer_id=answer.answer_id,
                sequence=sequence + 1,
                created_at=now,
            )
        )
        session.add(
            LearningEvent(
                student_id=profile.student_id,
                event_type="ANSWER_CORRECT" if is_correct else "ANSWER_WRONG",
                occurred_at=now,
                book_id=quiz_session.book_id,
                chapter_id=quiz_session.chapter_id,
                conversation_id=quiz_session.conversation_id,
                quiz_session_id=quiz_session_id,
                payload={
                    "answer_id": str(answer.answer_id),
                    "question_id": str(question_id),
                    "attempt_no": attempt_no,
                },
                created_at=now,
            )
        )

        all_answers = (
            await session.execute(
                select(QuizAnswer).where(
                    QuizAnswer.quiz_session_id == quiz_session_id
                )
            )
        ).scalars().all()
        all_questions = (
            await session.execute(
                select(QuizQuestion.question_id).where(
                    QuizQuestion.quiz_session_id == quiz_session_id
                )
            )
        ).scalars().all()
        final_question_ids = {
            item.question_id for item in all_answers if item.is_final
        }
        hints_used = (
            await session.execute(
                select(func.count(QuizInteraction.interaction_id)).where(
                    QuizInteraction.quiz_session_id == quiz_session_id,
                    QuizInteraction.interaction_type == "HINT_REQUEST",
                )
            )
        ).scalar_one()
        quiz_session.result_summary = {
            "correct": sum(1 for item in all_answers if item.is_correct and item.is_final),
            "total": len(all_questions),
            "hints_used": int(hints_used),
        }
        if all_questions and final_question_ids >= set(all_questions):
            quiz_session.status = "COMPLETED"
            quiz_session.completed_at = now
            quiz_session.ai_feedback = (
                "答对了，概念和例子连得很好。"
                if is_correct
                else "这次完成了尝试，可以回看解析并总结规律。"
            )
        quiz_session.updated_at = now
        await session.commit()
        await session.refresh(answer)
        try:
            from app.modules.memory.pipeline import MemoryPipeline

            await MemoryPipeline().process_student(session, profile.student_id)
        except Exception:  # pragma: no cover - grading must not break on telemetry
            logger.warning("memory pipeline failed after quiz answer", exc_info=True)
        return _answer_dto(answer), False

    async def _find_hint_replay(
        self,
        session: AsyncSession,
        quiz_session_id: UUID,
        question_id: UUID,
        idempotency_key: str | None,
    ) -> QuizHintDTO | None:
        if idempotency_key is None:
            return None
        request_interactions = (
            await session.execute(
                select(QuizInteraction).where(
                    QuizInteraction.quiz_session_id == quiz_session_id,
                    QuizInteraction.question_id == question_id,
                    QuizInteraction.interaction_type == "HINT_REQUEST",
                )
            )
        ).scalars().all()
        for request_interaction in request_interactions:
            payload = request_interaction.payload or {}
            if payload.get("idempotency_key") != idempotency_key:
                continue
            response_interaction = (
                await session.execute(
                    select(QuizInteraction).where(
                        QuizInteraction.quiz_session_id == quiz_session_id,
                        QuizInteraction.question_id == question_id,
                        QuizInteraction.interaction_type == "HINT_RESPONSE",
                        QuizInteraction.sequence == request_interaction.sequence + 1,
                    )
                )
            ).scalar_one_or_none()
            if response_interaction is None:
                return None
            response_payload = response_interaction.payload or {}
            return QuizHintDTO(
                hint_level=int(response_payload["hint_level"]),
                hint_text=str(response_payload["hint_text"]),
                max_hint_level=int(response_payload["max_hint_level"]),
                interaction_id=response_interaction.interaction_id,
            )
        return None

    async def request_hint(
        self,
        session: AsyncSession,
        user_id: UUID,
        quiz_session_id: UUID,
        question_id: UUID,
        idempotency_key: str | None,
    ) -> tuple[QuizHintDTO, bool]:
        quiz_session, question, profile = await self._get_owned_question(
            session, user_id, quiz_session_id, question_id
        )
        replay = await self._find_hint_replay(
            session, quiz_session_id, question_id, idempotency_key
        )
        if replay is not None:
            return replay, True
        if quiz_session.status != "ACTIVE":
            code = "QUIZ_FINALIZED" if quiz_session.status == "COMPLETED" else "QUIZ_NOT_ACTIVE"
            raise _error(409, code, "quiz session is not accepting hints")

        policy = question.interaction_policy or {"allow_hint": True, "max_hint_level": 3}
        if not policy.get("allow_hint", True):
            raise _error(409, "QUIZ_HINT_NOT_ALLOWED", "hints are not allowed for this question")
        max_hint_level = int(policy.get("max_hint_level", 3))
        hint_level = await self._current_hint_level(
            session, quiz_session_id, question_id
        ) + 1
        if hint_level > max_hint_level:
            raise _error(409, "QUIZ_HINT_LIMIT_REACHED", "maximum hint level reached")

        hint_text = self.skill.hint(question, hint_level)
        now = datetime.now(timezone.utc)
        request_sequence = await self._next_interaction_sequence(
            session, quiz_session_id
        )
        request_payload: dict[str, Any] = {"hint_level": hint_level}
        if idempotency_key is not None:
            request_payload["idempotency_key"] = idempotency_key
        hint_message = Message(
            message_id=uuid4(),
            conversation_id=quiz_session.conversation_id,
            role="TEACHER",
            type="HINT",
            content=hint_text,
            metadata_={
                "quiz_session_id": str(quiz_session_id),
                "question_id": str(question_id),
                "hint_level": hint_level,
            },
            sequence=await self._next_message_sequence(
                session, quiz_session.conversation_id
            ),
            created_at=now,
        )
        session.add(hint_message)
        await session.flush()
        request_interaction = QuizInteraction(
            quiz_session_id=quiz_session_id,
            question_id=question_id,
            interaction_type="HINT_REQUEST",
            payload=request_payload,
            sequence=request_sequence,
            created_at=now,
        )
        session.add(request_interaction)
        await session.flush()
        response_interaction = QuizInteraction(
            quiz_session_id=quiz_session_id,
            question_id=question_id,
            interaction_type="HINT_RESPONSE",
            payload={
                "hint_level": hint_level,
                "hint_text": hint_text,
                "max_hint_level": max_hint_level,
                "request_interaction_id": str(request_interaction.interaction_id),
            },
            message_id=hint_message.message_id,
            sequence=request_sequence + 1,
            created_at=now,
        )
        session.add(response_interaction)
        session.add(
            LearningEvent(
                student_id=profile.student_id,
                event_type="HINT_REQUESTED",
                occurred_at=now,
                book_id=quiz_session.book_id,
                chapter_id=quiz_session.chapter_id,
                conversation_id=quiz_session.conversation_id,
                quiz_session_id=quiz_session_id,
                payload={
                    "question_id": str(question_id),
                    "hint_level": hint_level,
                },
                created_at=now,
            )
        )
        conversation = await session.get(Conversation, quiz_session.conversation_id)
        if conversation is not None:
            conversation.last_message_at = now
        await session.commit()
        await session.refresh(response_interaction)
        return (
            QuizHintDTO(
                hint_level=hint_level,
                hint_text=hint_text,
                max_hint_level=max_hint_level,
                interaction_id=response_interaction.interaction_id,
            ),
            False,
        )

    async def list_answers(
        self, session: AsyncSession, user_id: UUID, quiz_session_id: UUID
    ) -> list[QuizAnswerDTO]:
        await self._get_owned_session(session, user_id, quiz_session_id)
        rows = (
            await session.execute(
                select(QuizAnswer)
                .where(QuizAnswer.quiz_session_id == quiz_session_id)
                .order_by(QuizAnswer.question_id.asc(), QuizAnswer.attempt_no.asc())
            )
        ).scalars().all()
        return [_answer_dto(row) for row in rows]

    async def list_interactions(
        self, session: AsyncSession, user_id: UUID, quiz_session_id: UUID
    ) -> list[QuizInteractionDTO]:
        await self._get_owned_session(session, user_id, quiz_session_id)
        rows = (
            await session.execute(
                select(QuizInteraction)
                .where(QuizInteraction.quiz_session_id == quiz_session_id)
                .order_by(QuizInteraction.sequence.asc())
            )
        ).scalars().all()
        return [_interaction_dto(row) for row in rows]
