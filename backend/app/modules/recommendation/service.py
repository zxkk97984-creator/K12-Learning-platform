from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    Book,
    BookProgress,
    QuizAnswer,
    QuizSession,
    Recommendation,
    StudentProfile,
)


RecommendationType = Literal["CONTINUE_READING", "REVIEW_WEAK", "READ_NEXT"]


@dataclass(frozen=True)
class BookProgressSignal:
    progress_id: UUID
    book_id: UUID
    book_title: str
    status: str
    position_percent: int
    last_read_at: datetime | None
    completed_at: datetime | None
    grade_min: int | None = None
    grade_max: int | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuizAnswerSignal:
    answer_id: UUID
    book_id: UUID
    book_title: str
    is_correct: bool


@dataclass(frozen=True)
class BookCandidate:
    book_id: UUID
    title: str
    description: str | None
    grade_min: int
    grade_max: int
    tags: tuple[str, ...]
    is_started: bool


@dataclass(frozen=True)
class RecommendationDraft:
    recommendation_type: RecommendationType
    title: str
    description: str
    reason: str
    evidence_ids: list[str]
    related_book_id: UUID | None


def _recent_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _matching_candidate(
    completed: BookProgressSignal,
    candidates: list[BookCandidate],
) -> BookCandidate | None:
    available = [
        candidate
        for candidate in candidates
        if not candidate.is_started and candidate.book_id != completed.book_id
    ]
    if not available:
        return None

    completed_tags = set(completed.tags)
    same_tag = [
        candidate
        for candidate in available
        if completed_tags and completed_tags.intersection(candidate.tags)
    ]
    if same_tag:
        return same_tag[0]

    if completed.grade_min is not None and completed.grade_max is not None:
        adjacent_grade = [
            candidate
            for candidate in available
            if candidate.grade_min <= completed.grade_max + 1
            and candidate.grade_max >= completed.grade_min - 1
        ]
        if adjacent_grade:
            return adjacent_grade[0]

    return available[0]


def build_recommendation_drafts(
    *,
    progress_signals: list[BookProgressSignal],
    quiz_answer_signals: list[QuizAnswerSignal],
    completed_progress_signals: list[BookProgressSignal],
    book_candidates: list[BookCandidate],
    recent_quiz_limit: int = 10,
) -> list[RecommendationDraft]:
    """Generate explainable recommendations without I/O or external services."""

    drafts: list[RecommendationDraft] = []

    # R1: latest in-progress book keeps a student in an active learning loop.
    in_progress = sorted(
        (
            progress
            for progress in progress_signals
            if progress.status == "READING" and progress.position_percent < 100
        ),
        key=lambda progress: _recent_datetime(progress.last_read_at),
        reverse=True,
    )
    if in_progress:
        progress = in_progress[0]
        drafts.append(
            RecommendationDraft(
                recommendation_type="CONTINUE_READING",
                title=f"继续阅读《{progress.book_title}》",
                description=(
                    f"你已经完成这本书的 {progress.position_percent}%，从上次位置继续最顺畅。"
                ),
                reason=(
                    f"最近一次阅读记录显示你已完成《{progress.book_title}》的 "
                    f"{progress.position_percent}%，保持当前节奏能减少重新熟悉内容的成本。"
                ),
                evidence_ids=[str(progress.progress_id)],
                related_book_id=progress.book_id,
            )
        )

    # R2: group the latest answers by book and surface the lowest-accuracy book.
    grouped_answers: dict[UUID, list[QuizAnswerSignal]] = {}
    for answer in quiz_answer_signals[:recent_quiz_limit]:
        grouped_answers.setdefault(answer.book_id, []).append(answer)
    weak_groups: list[tuple[float, list[QuizAnswerSignal]]] = []
    for answers in grouped_answers.values():
        accuracy = sum(answer.is_correct for answer in answers) / len(answers)
        if accuracy < 0.6:
            weak_groups.append((accuracy, answers))
    if weak_groups:
        accuracy, answers = min(weak_groups, key=lambda item: item[0])
        book_title = answers[0].book_title
        percentage = round(accuracy * 100)
        drafts.append(
            RecommendationDraft(
                recommendation_type="REVIEW_WEAK",
                title=f"复习《{book_title}》的关键概念",
                description="用一小段复习把最近测验中不稳的概念重新连起来。",
                reason=(
                    f"最近 {len(answers)} 次相关测验的正确率约为 {percentage}%，"
                    "先复习再继续挑战，理解会更稳。"
                ),
                evidence_ids=[str(answer.answer_id) for answer in answers],
                related_book_id=answers[0].book_id,
            )
        )

    # R3: completion opens a same-topic or adjacent-grade next step.
    completed = sorted(
        completed_progress_signals,
        key=lambda progress: _recent_datetime(progress.completed_at),
        reverse=True,
    )
    if completed:
        completed_progress = completed[0]
        candidate = _matching_candidate(completed_progress, book_candidates)
        if candidate is not None:
            drafts.append(
                RecommendationDraft(
                    recommendation_type="READ_NEXT",
                    title=f"读下一本：《{candidate.title}》",
                    description=candidate.description or "沿着刚完成的内容继续探索。",
                    reason=(
                        f"你最近完成了《{completed_progress.book_title}》，"
                        f"《{candidate.title}》在主题或难度上衔接自然，适合作为下一步。"
                    ),
                    evidence_ids=[
                        str(completed_progress.progress_id),
                        str(completed_progress.book_id),
                    ],
                    related_book_id=candidate.book_id,
                )
            )

    return drafts


class RecommendationService:
    async def _student_id(self, session: AsyncSession, user_id: UUID) -> UUID:
        student_id = (
            await session.execute(
                select(StudentProfile.student_id).where(StudentProfile.user_id == user_id)
            )
        ).scalar_one_or_none()
        if student_id is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "STUDENT_PROFILE_NOT_FOUND",
                    "message": "student profile not found",
                },
            )
        return student_id

    async def _build_signals(
        self, session: AsyncSession, student_id: UUID
    ) -> tuple[
        list[BookProgressSignal],
        list[QuizAnswerSignal],
        list[BookProgressSignal],
        list[BookCandidate],
    ]:
        progress_rows = (
            await session.execute(
                select(BookProgress, Book)
                .join(Book, Book.book_id == BookProgress.book_id)
                .where(BookProgress.student_id == student_id)
            )
        ).all()
        progress_signals = [
            BookProgressSignal(
                progress_id=progress.progress_id,
                book_id=progress.book_id,
                book_title=book.title,
                status=progress.status,
                position_percent=progress.position_percent,
                last_read_at=progress.last_read_at,
                completed_at=progress.completed_at,
                grade_min=book.grade_min,
                grade_max=book.grade_max,
                tags=tuple(tag for tag in book.tags if isinstance(tag, str)),
            )
            for progress, book in progress_rows
        ]
        completed_progress_signals = [
            progress
            for progress in progress_signals
            if progress.status == "COMPLETED" and progress.completed_at is not None
        ]

        answer_rows = (
            await session.execute(
                select(QuizAnswer, QuizSession, Book)
                .join(
                    QuizSession,
                    QuizSession.quiz_session_id == QuizAnswer.quiz_session_id,
                )
                .join(Book, Book.book_id == QuizSession.book_id)
                .where(
                    QuizAnswer.student_id == student_id,
                    QuizSession.book_id.is_not(None),
                )
                .order_by(QuizAnswer.created_at.desc())
                .limit(10)
            )
        ).all()
        quiz_answer_signals = [
            QuizAnswerSignal(
                answer_id=answer.answer_id,
                book_id=quiz_session.book_id,
                book_title=book.title,
                is_correct=answer.is_correct,
            )
            for answer, quiz_session, book in answer_rows
            if quiz_session.book_id is not None
        ]

        started_book_ids = {
            progress.book_id
            for progress in progress_signals
            if progress.status != "NOT_STARTED"
        }
        books = (
            await session.execute(
                select(Book).where(Book.status == "PUBLISHED").order_by(Book.created_at.asc())
            )
        ).scalars().all()
        book_candidates = [
            BookCandidate(
                book_id=book.book_id,
                title=book.title,
                description=book.description,
                grade_min=book.grade_min,
                grade_max=book.grade_max,
                tags=tuple(tag for tag in book.tags if isinstance(tag, str)),
                is_started=book.book_id in started_book_ids,
            )
            for book in books
        ]
        return (
            progress_signals,
            quiz_answer_signals,
            completed_progress_signals,
            book_candidates,
        )

    async def generate_for_student(
        self, session: AsyncSession, student_id: UUID
    ) -> list[Recommendation]:
        signals = await self._build_signals(session, student_id)
        drafts = build_recommendation_drafts(
            progress_signals=signals[0],
            quiz_answer_signals=signals[1],
            completed_progress_signals=signals[2],
            book_candidates=signals[3],
        )

        dismissed_rows = (
            await session.execute(
                select(Recommendation.recommendation_type, Recommendation.related_book_id)
                .where(
                    Recommendation.student_id == student_id,
                    Recommendation.status == "DISMISSED",
                    Recommendation.reason.like("% · 学生已忽略"),
                )
            )
        ).all()
        dismissed_keys = {
            (recommendation_type, str(related_book_id))
            for recommendation_type, related_book_id in dismissed_rows
        }
        drafts = [
            draft
            for draft in drafts
            if (draft.recommendation_type, str(draft.related_book_id)) not in dismissed_keys
        ]

        now = datetime.now(timezone.utc)
        await session.execute(
            update(Recommendation)
            .where(
                Recommendation.student_id == student_id,
                Recommendation.status == "ACTIVE",
            )
            .values(
                status="DISMISSED",
                reason=func.concat(Recommendation.reason, " · 已被新一轮规则推荐替换"),
                updated_at=now,
            )
        )
        session.add_all(
            [
                Recommendation(
                    student_id=student_id,
                    recommendation_type=draft.recommendation_type,
                    title=draft.title,
                    description=draft.description,
                    reason=draft.reason,
                    evidence_ids=draft.evidence_ids,
                    related_book_id=draft.related_book_id,
                    status="ACTIVE",
                )
                for draft in drafts
            ]
        )
        await session.commit()
        return await self.list_active(session, student_id)

    async def list_for_user(
        self, session: AsyncSession, user_id: UUID
    ) -> list[Recommendation]:
        student_id = await self._student_id(session, user_id)
        return await self.generate_for_student(session, student_id)

    async def list_active(
        self, session: AsyncSession, student_id: UUID
    ) -> list[Recommendation]:
        return list(
            (
                await session.execute(
                    select(Recommendation)
                    .where(
                        Recommendation.student_id == student_id,
                        Recommendation.status == "ACTIVE",
                    )
                    .order_by(
                        Recommendation.created_at.desc(),
                        Recommendation.recommendation_id.desc(),
                    )
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )

    async def dismiss(
        self, session: AsyncSession, user_id: UUID, recommendation_id: UUID
    ) -> Recommendation:
        student_id = await self._student_id(session, user_id)
        recommendation = (
            await session.execute(
                select(Recommendation).where(
                    Recommendation.recommendation_id == recommendation_id,
                    Recommendation.student_id == student_id,
                )
            )
        ).scalar_one_or_none()
        if recommendation is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "RECOMMENDATION_NOT_FOUND",
                    "message": "recommendation not found",
                },
            )
        recommendation.status = "DISMISSED"
        recommendation.reason = f"{recommendation.reason} · 学生已忽略"
        await session.commit()
        await session.refresh(recommendation)
        return recommendation
