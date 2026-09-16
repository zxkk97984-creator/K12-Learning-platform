import base64
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.infrastructure.database.models import (
    Book,
    BookProgress,
    Chapter,
    ChapterCompletion,
    LearningEvent,
    LearningSession,
    QuizSession,
    ReadingSettlement,
    StudentProfile,
)

# 单次会话计入时长的上限（秒）：防止客户端崩溃后长期未关闭的会话
# 在下次自动关闭时把数小时的墙钟时间一次性记入统计。
MAX_SESSION_CREDIT_SECONDS = 4 * 3600
from app.jobs.queue import enqueue_memory_consolidation
from app.modules.learning.schemas import (
    BookProgressDTO,
    ChapterCompletionDTO,
    CreateLearningEventRequest,
    CreateLearningSessionRequest,
    EventPageDTO,
    EventPageMeta,
    LearningEventDTO,
    LearningSessionDTO,
    PatchLearningSessionRequest,
    UpsertBookProgressRequest,
)


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

    @staticmethod
    async def _credit_reading_stats(
        session: AsyncSession, learning_session: LearningSession, now: datetime
    ) -> int:
        """关闭一个学习会话时的真实时长结算（幂等）。

        - reading_settlements 以 session_id 为主键：重复结算（重复 PATCH、
          自动关闭竞态、重放）只会成功一次，其余被唯一约束挡下；
        - BookProgress.total_seconds 只在首次结算成功时累加真实时长；
        - 学生统计同步更新：total_learning_seconds 精确累计，
          total_learning_minutes 为其整分钟派生值；
        - learning_days 按「当日首次结算」判定，一天多次学习不重复加天。
        返回本次实际入账的秒数（0 表示该会话此前已结算过）。
        """
        duration = max(0, int((now - learning_session.started_at).total_seconds()))
        credit_seconds = min(duration, MAX_SESSION_CREDIT_SECONDS)

        ledger = pg_insert(ReadingSettlement).values(
            session_id=learning_session.session_id,
            student_id=learning_session.student_id,
            book_id=learning_session.book_id,
            settled_seconds=credit_seconds,
        )
        result = await session.execute(
            ledger.on_conflict_do_nothing(index_elements=["session_id"])
        )
        if result.rowcount != 1:
            return 0

        progress = (
            await session.execute(
                select(BookProgress).where(
                    BookProgress.student_id == learning_session.student_id,
                    BookProgress.book_id == learning_session.book_id,
                )
            )
        ).scalar_one_or_none()
        # 仅当该学生已有此书的阅读进度时才累加时长；
        # 从未通过正常阅读流程产生进度的直接会话不凭空创建进度行，
        # 避免 API 直连调用污染书架初始状态。
        if progress is not None:
            progress.total_seconds = (progress.total_seconds or 0) + credit_seconds
            progress.last_read_at = now

        profile = (
            await session.execute(
                select(StudentProfile).where(
                    StudentProfile.student_id == learning_session.student_id
                )
            )
        ).scalar_one()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        settled_today = await session.execute(
            select(func.count(ReadingSettlement.session_id)).where(
                ReadingSettlement.student_id == learning_session.student_id,
                ReadingSettlement.created_at >= midnight,
                ReadingSettlement.session_id != learning_session.session_id,
            )
        )
        prior_today = int(settled_today.scalar_one())
        if prior_today == 0:
            profile.learning_days = (profile.learning_days or 0) + 1
        profile.total_learning_seconds = (profile.total_learning_seconds or 0) + credit_seconds
        profile.total_learning_minutes = profile.total_learning_seconds // 60
        return credit_seconds

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
            await self._credit_reading_stats(session, active, now)

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
        await self._credit_reading_stats(session, learning_session, learning_session.ended_at)
        await session.commit()
        await session.refresh(learning_session)
        return LearningSessionDTO.model_validate(learning_session)


    @staticmethod
    async def _refresh_completion_counters(
        session: AsyncSession, student_id: UUID, event_type: str
    ) -> None:
        """CHAPTER_FINISHED / BOOK_FINISHED 事件驱动重算完成计数。

        直接从事件流 COUNT(DISTINCT ...) 重算而非 +1：
        重复事件、乱序到达都不会导致计数虚高（天然幂等）。
        """
        if event_type not in ("CHAPTER_FINISHED", "BOOK_FINISHED"):
            return
        profile = (
            await session.execute(
                select(StudentProfile).where(StudentProfile.student_id == student_id)
            )
        ).scalar_one_or_none()
        if profile is None:
            return
        if event_type == "CHAPTER_FINISHED":
            chapters_done = await session.execute(
                select(func.count(func.distinct(LearningEvent.chapter_id))).where(
                    LearningEvent.student_id == student_id,
                    LearningEvent.event_type == "CHAPTER_FINISHED",
                )
            )
            profile.completed_chapters = int(chapters_done.scalar_one())
        else:
            books_done = await session.execute(
                select(func.count(func.distinct(LearningEvent.book_id))).where(
                    LearningEvent.student_id == student_id,
                    LearningEvent.event_type == "BOOK_FINISHED",
                )
            )
            profile.completed_books = int(books_done.scalar_one())


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
        if request.event_type == "QUIZ_REVIEW_COMPLETED":
            # 复习完成幂等：同一 request_id 只记一次；quiz_session 必须是当前学生的。
            request_id = (request.payload or {}).get("request_id")
            if request_id:
                existing = (
                    await session.execute(
                        select(LearningEvent).where(
                            LearningEvent.student_id == student_id,
                            LearningEvent.event_type == "QUIZ_REVIEW_COMPLETED",
                            LearningEvent.payload["request_id"].astext == str(request_id),
                        )
                    )
                ).scalars().first()
                if existing is not None:
                    return LearningEventDTO.model_validate(existing)
            if request.quiz_session_id is not None:
                quiz = await session.get(QuizSession, request.quiz_session_id)
                if quiz is None or quiz.student_id != student_id:
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "code": "FORBIDDEN",
                            "message": "quiz session does not belong to student",
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
        await self._refresh_completion_counters(session, student_id, request.event_type)
        # 记忆整合改为异步：job 行与事件同事务落库（原子交接，失败则整体失败），
        # 由 Worker 消费并自带重试；HTTP 路径不再同步执行 MemoryPipeline。
        await enqueue_memory_consolidation(session, student_id)
        await session.commit()
        await session.refresh(event)
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

    async def mark_chapter_completed(
        self,
        session: AsyncSession,
        user_id: UUID,
        chapter_id: UUID,
        *,
        source: str = "EXPLICIT",
    ) -> ChapterCompletionDTO:
        """T13 主动"完成本章"（幂等）。

        - 章节与其父书须 PUBLISHED（可见性 T02/T03）；
        - 唯一约束 (student_id, chapter_id) 幂等：重复提交计数一次；
        - 不把"滚动到末尾"算作完成，也不回填历史滚动事件为主动完成；
        - 书籍"已完成" = 本书所有 PUBLISHED 章节均已在此表完成。
        """
        student_id = await self._get_student_id(session, user_id)
        chapter = await session.get(Chapter, chapter_id)
        if chapter is None or chapter.status != "PUBLISHED":
            raise HTTPException(
                status_code=404,
                detail={"code": "CHAPTER_NOT_FOUND", "message": "chapter not found"},
            )
        book = await session.get(Book, chapter.book_id)
        if book is None or book.status != "PUBLISHED":
            raise HTTPException(
                status_code=404,
                detail={"code": "BOOK_NOT_FOUND", "message": "book not found"},
            )

        now = datetime.now(timezone.utc)
        stmt = pg_insert(ChapterCompletion).values(
            student_id=student_id,
            chapter_id=chapter_id,
            book_id=book.book_id,
            completed_at=now,
            source=source if source in ("EXPLICIT", "LEGACY_EVENT") else "EXPLICIT",
        )
        result = await session.execute(
            stmt.on_conflict_do_nothing(index_elements=["student_id", "chapter_id"])
        )
        is_new = bool(result.rowcount == 1)

        # 更新该生本书的"当前阅读位置"到本章（不影响完成态）。
        progress = (
            await session.execute(
                select(BookProgress).where(
                    BookProgress.student_id == student_id,
                    BookProgress.book_id == book.book_id,
                )
            )
        ).scalar_one_or_none()
        if progress is not None:
            progress.chapter_id = chapter_id
            progress.last_read_at = now
        elif is_new:
            session.add(
                BookProgress(
                    student_id=student_id,
                    book_id=book.book_id,
                    chapter_id=chapter_id,
                    status="READING",
                    position_percent=0,
                    last_read_at=now,
                    started_at=now,
                )
            )

        # 诚实完成口径：只统计本书的已发布章节，且只认 fact 表。
        published_count = int(
            (
                await session.execute(
                    select(func.count(Chapter.chapter_id)).where(
                        Chapter.book_id == book.book_id,
                        Chapter.status == "PUBLISHED",
                    )
                )
            ).scalar_one()
        )
        completed_rows = await session.execute(
            select(func.count(func.distinct(ChapterCompletion.chapter_id))).where(
                ChapterCompletion.student_id == student_id,
                ChapterCompletion.book_id == book.book_id,
                ChapterCompletion.chapter_id.in_(
                    select(Chapter.chapter_id).where(
                        Chapter.book_id == book.book_id,
                        Chapter.status == "PUBLISHED",
                    )
                ),
            )
        )
        completed_count = int(completed_rows.scalar_one())
        book_completed = published_count > 0 and completed_count >= published_count

        await session.commit()
        completion = (
            await session.execute(
                select(ChapterCompletion).where(
                    ChapterCompletion.student_id == student_id,
                    ChapterCompletion.chapter_id == chapter_id,
                )
            )
        ).scalar_one()
        return ChapterCompletionDTO(
            chapter_id=chapter_id,
            book_id=book.book_id,
            completed_at=completion.completed_at,
            source=completion.source,
            book_completed=book_completed,
            completed_chapters=completed_count,
            published_chapters=published_count,
        )

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
