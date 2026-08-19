import base64
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    Book,
    BookProgress,
    Chapter,
    LearningEvent,
    LearningSession,
    StudentProfile,
)
from app.modules.learning.schemas import (
    BookProgressDTO,
    CreateLearningEventRequest,
    CreateLearningSessionRequest,
    EventPageDTO,
    EventPageMeta,
    LearningEventDTO,
    LearningSessionDTO,
    PatchLearningSessionRequest,
    UpsertBookProgressRequest,
)

logger = logging.getLogger(__name__)


def _encode_cursor(occurred_at: datetime, event_id: UUID) -> str:
    payload = json.dumps([occurred_at.isoformat(), str(event_id)])
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = json.loads(base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8"))
        occurred_at = datetime.fromisoformat(raw[0])
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)
        return occurred_at, UUID(raw[1])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "VALIDATION_ERROR", "message": "invalid cursor"},
        ) from exc


class LearningService:
    """学习进度 Domain Service（Router 只做编排，SQL 在此层）。"""

    async def _get_student_id(self, session: AsyncSession, user_id: UUID) -> UUID:
        """users.user_id -> student_profiles.student_id（learning 表 FK 指向后者）。"""
        result = await session.execute(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "STUDENT_PROFILE_NOT_FOUND",
                    "message": "student profile not found",
                },
            )
        return profile.student_id

    async def create_session(
        self,
        session: AsyncSession,
        user_id: UUID,
        request: CreateLearningSessionRequest,
    ) -> LearningSessionDTO:
        student_id = await self._get_student_id(session, user_id)
        book = await session.get(Book, request.book_id)
        if book is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "BOOK_NOT_FOUND", "message": "book not found"},
            )
        chapter = await session.get(Chapter, request.chapter_id)
        if chapter is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "CHAPTER_NOT_FOUND", "message": "chapter not found"},
            )
        if chapter.book_id != request.book_id:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "VALIDATION_ERROR",
                    "message": "chapter does not belong to book",
                },
            )

        now = datetime.now(timezone.utc)
        # Domain 不变量：同一学生最多一个 ACTIVE 时段（先关闭旧会话）
        result = await session.execute(
            select(LearningSession).where(
                LearningSession.student_id == student_id,
                LearningSession.status == "ACTIVE",
            )
        )
        for active in result.scalars().all():
            active.ended_at = now
            active.duration_seconds = max(0, int((now - active.started_at).total_seconds()))
            active.status = "ENDED"

        learning_session = LearningSession(
            student_id=student_id,
            book_id=request.book_id,
            chapter_id=request.chapter_id,
            started_at=now,
            entry_route=request.entry_route,
        )
        session.add(learning_session)
        await session.commit()
        await session.refresh(learning_session)
        return LearningSessionDTO.model_validate(learning_session)

    async def patch_session(
        self,
        session: AsyncSession,
        user_id: UUID,
        session_id: UUID,
        request: PatchLearningSessionRequest,
    ) -> LearningSessionDTO:
        student_id = await self._get_student_id(session, user_id)
        learning_session = await session.get(LearningSession, session_id)
        if learning_session is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "LEARNING_SESSION_NOT_FOUND",
                    "message": "learning session not found",
                },
            )
        if learning_session.student_id != student_id:
            raise HTTPException(
                status_code=403,
                detail={"code": "FORBIDDEN", "message": "not your learning session"},
            )
        if learning_session.status != "ACTIVE":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "LEARNING_SESSION_INVALID_STATUS",
                    "message": "only ACTIVE sessions can be closed",
                },
            )
        learning_session.status = request.status
        learning_session.ended_at = datetime.now(timezone.utc)
        learning_session.duration_seconds = max(
            0,
            int(
                (
                    learning_session.ended_at - learning_session.started_at
                ).total_seconds()
            ),
        )
        await session.commit()
        await session.refresh(learning_session)
        return LearningSessionDTO.model_validate(learning_session)

    async def create_event(
        self,
        session: AsyncSession,
        user_id: UUID,
        request: CreateLearningEventRequest,
    ) -> LearningEventDTO:
        student_id = await self._get_student_id(session, user_id)
        if request.session_id is not None:
            learning_session = await session.get(LearningSession, request.session_id)
            if learning_session is None or learning_session.student_id != student_id:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "code": "FORBIDDEN",
                        "message": "learning session does not belong to student",
                    },
                )
        event = LearningEvent(
            student_id=student_id,
            session_id=request.session_id,
            event_type=request.event_type,
            occurred_at=request.occurred_at,
            book_id=request.book_id,
            chapter_id=request.chapter_id,
            block_id=request.block_id,
            knowledge_point_ids=[str(kp) for kp in request.knowledge_point_ids],
            conversation_id=request.conversation_id,
            quiz_session_id=request.quiz_session_id,
            payload=request.payload,
        )
        session.add(event)
        await session.commit()
        await session.refresh(event)
        try:
            from app.modules.memory.pipeline import MemoryPipeline

            await MemoryPipeline().process_student(session, student_id)
        except Exception:  # pragma: no cover - telemetry must not break writes
            logger.warning("memory pipeline failed after learning event", exc_info=True)
        return LearningEventDTO.model_validate(event)

    async def get_progress(self, session: AsyncSession, user_id: UUID) -> list[BookProgressDTO]:
        student_id = await self._get_student_id(session, user_id)
        rows = (
            (
                await session.execute(
                    select(BookProgress)
                    .where(BookProgress.student_id == student_id)
                    .order_by(BookProgress.updated_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return [BookProgressDTO.model_validate(row) for row in rows]

    async def get_book_progress(
        self, session: AsyncSession, user_id: UUID, book_id: UUID
    ) -> BookProgressDTO | None:
        student_id = await self._get_student_id(session, user_id)
        book = await session.get(Book, book_id)
        if book is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "BOOK_NOT_FOUND", "message": "book not found"},
            )
        progress = (
            await session.execute(
                select(BookProgress).where(
                    BookProgress.student_id == student_id,
                    BookProgress.book_id == book_id,
                )
            )
        ).scalar_one_or_none()
        return BookProgressDTO.model_validate(progress) if progress is not None else None

    async def upsert_book_progress(
        self,
        session: AsyncSession,
        user_id: UUID,
        book_id: UUID,
        request: UpsertBookProgressRequest,
    ) -> BookProgressDTO:
        student_id = await self._get_student_id(session, user_id)
        book = await session.get(Book, book_id)
        if book is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "BOOK_NOT_FOUND", "message": "book not found"},
            )

        if request.chapter_id is not None:
            chapter = await session.get(Chapter, request.chapter_id)
            if chapter is None or chapter.book_id != book_id:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "VALIDATION_ERROR",
                        "message": "chapter does not belong to book",
                    },
                )

        progress = (
            await session.execute(
                select(BookProgress).where(
                    BookProgress.student_id == student_id,
                    BookProgress.book_id == book_id,
                )
            )
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)

        if progress is None:
            status = request.status or "READING"
            progress = BookProgress(
                student_id=student_id,
                book_id=book_id,
                chapter_id=request.chapter_id,
                block_id=request.block_id,
                status=status,
                position_percent=request.position_percent
                if request.position_percent is not None
                else 0,
                last_read_at=now,
                started_at=now if status != "NOT_STARTED" else None,
                completed_at=now if status == "COMPLETED" else None,
            )
            session.add(progress)
        else:
            if request.chapter_id is not None:
                progress.chapter_id = request.chapter_id
            if request.block_id is not None:
                progress.block_id = request.block_id
            if request.status is not None:
                progress.status = request.status
                progress.completed_at = now if request.status == "COMPLETED" else None
            if request.position_percent is not None:
                progress.position_percent = request.position_percent
            if progress.started_at is None and progress.status != "NOT_STARTED":
                progress.started_at = now
            progress.last_read_at = now

        await session.commit()
        await session.refresh(progress)
        return BookProgressDTO.model_validate(progress)

    async def list_events(
        self,
        session: AsyncSession,
        user_id: UUID,
        *,
        cursor: str | None,
        limit: int,
        event_type: str | None,
    ) -> EventPageDTO:
        student_id = await self._get_student_id(session, user_id)
        query = select(LearningEvent).where(LearningEvent.student_id == student_id)
        if event_type:
            query = query.where(LearningEvent.event_type == event_type)
        if cursor is not None:
            cursor_occurred_at, cursor_event_id = _decode_cursor(cursor)
            query = query.where(
                tuple_(LearningEvent.occurred_at, LearningEvent.event_id)
                < (cursor_occurred_at, cursor_event_id)
            )
        query = (
            query.order_by(LearningEvent.occurred_at.desc(), LearningEvent.event_id.desc())
            .limit(limit + 1)
        )
        rows = (await session.execute(query)).scalars().all()
        has_more = len(rows) > limit
        events = rows[:limit]
        next_cursor = (
            _encode_cursor(events[-1].occurred_at, events[-1].event_id)
            if has_more and events
            else None
        )
        return EventPageDTO(
            items=[LearningEventDTO.model_validate(event) for event in events],
            meta=EventPageMeta(next_cursor=next_cursor, has_more=has_more),
        )
