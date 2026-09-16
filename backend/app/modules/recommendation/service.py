from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    Book,
    BookProgress,
    Chapter,
    LearningEvent,
    QuizAnswer,
    QuizSession,
    Recommendation,
    StudentMemory,
    StudentProfile,
)
from app.modules.recommendation.schemas import LearningNextActionDTO


RecommendationType = Literal[
    "CONTINUE_READING",
    "REVIEW_WEAK",
    "READ_NEXT",
    "INTEREST_MATCH",
]

# 规则式推荐默认过期天数：过期的推荐不再出现在列表（状态保持 ACTIVE，不写 EXPIRED）。
RECOMMENDATION_TTL_DAYS = 7


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
class InterestSignal:
    """来自学生长期记忆（PROFILE/PREFERENCE）的兴趣标签证据。"""

    tag: str
    memory_id: UUID
    memory_content: str


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
    interest_signals: list[InterestSignal] | None = None,
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

    # R4: 长期记忆中的兴趣偏好 ↔ 未读书籍主题匹配（Phase 3 记忆驱动推荐）。
    # 证据为命中的记忆行 id，「为什么推荐」可回查到真实记忆内容。
    if interest_signals:
        started_ids = {progress.book_id for progress in progress_signals}
        matches: dict[str, list[InterestSignal]] = {}
        title_to_candidate: dict[str, BookCandidate] = {}
        for candidate in book_candidates:
            if candidate.is_started or candidate.book_id in started_ids:
                continue
            title_to_candidate[candidate.title] = candidate
            for signal in interest_signals:
                tag = signal.tag.strip()
                if len(tag) < 2:
                    continue
                hit_tags = any(tag in t for t in candidate.tags)
                hit_desc = tag in (candidate.description or "")
                if hit_tags or hit_desc:
                    matches.setdefault(candidate.title, []).append(signal)
        if matches:
            best_title = sorted(matches.keys())[0]
            signals_for_best = matches[best_title]
            candidate = title_to_candidate[best_title]
            memory_ids = [str(signal.memory_id) for signal in signals_for_best]
            interest_names = sorted({signal.tag for signal in signals_for_best})
            drafts.append(
                RecommendationDraft(
                    recommendation_type="INTEREST_MATCH",
                    title=f"试试《{candidate.title}》",
                    description=(
                        f"你的学习档案里提到对{'、'.join(interest_names)}的兴趣，"
                        "这本书正好围绕这些主题展开。"
                    ),
                    reason=(
                        f"你的长期记忆记录了对{'、'.join(interest_names)}的兴趣"
                        f"（依据 {len(memory_ids)} 条记忆），"
                        f"《{candidate.title}》的主题与之匹配且尚未开始阅读。"
                    ),
                    evidence_ids=memory_ids,
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
        memory_rows = (
            await session.execute(
                select(StudentMemory).where(
                    StudentMemory.student_id == student_id,
                    StudentMemory.status == "ACTIVE",
                    StudentMemory.memory_type.in_(("PROFILE", "PREFERENCE")),
                )
            )
        ).scalars().all()
        candidate_tags = {
            tag
            for candidate in book_candidates
            for tag in candidate.tags
        }
        interest_signals: list[InterestSignal] = []
        seen_pairs: set[tuple[UUID, str]] = set()
        for memory in memory_rows:
            for tag in sorted(candidate_tags):
                if len(tag) >= 2 and tag in memory.content:
                    key = (memory.memory_id, tag)
                    if key not in seen_pairs:
                        seen_pairs.add(key)
                        interest_signals.append(
                            InterestSignal(
                                tag=tag,
                                memory_id=memory.memory_id,
                                memory_content=memory.content,
                            )
                        )

        return (
            progress_signals,
            quiz_answer_signals,
            completed_progress_signals,
            book_candidates,
            interest_signals,
        )

    async def learning_next(self, session: AsyncSession, user_id: UUID) -> LearningNextActionDTO:
        """§6.1 统一下一步行动：按顺序取第一条有效行动。"""
        student_id = await self._student_id(session, user_id)
        profile = (
            await session.execute(
                select(StudentProfile).where(StudentProfile.student_id == student_id)
            )
        ).scalar_one()

        # 1) 进行中的练习 → 继续
        active_quiz = (
            await session.execute(
                select(QuizSession)
                .where(
                    QuizSession.student_id == student_id,
                    QuizSession.status == "ACTIVE",
                )
                .order_by(QuizSession.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if active_quiz is not None:
            return LearningNextActionDTO(
                type="CONTINUE_QUIZ",
                label=f"继续《{active_quiz.title}》",
                book_id=active_quiz.book_id,
                chapter_id=active_quiz.chapter_id,
                quiz_session_id=active_quiz.quiz_session_id,
                reason="上次有一场练习还没做完，接着把它完成最顺畅。",
                evidence_ids=[str(active_quiz.quiz_session_id)],
            )

        # 2) 最近完成测验含错题且未复习 → 回顾错题
        recent_quizzes = (
            await session.execute(
                select(QuizSession)
                .where(
                    QuizSession.student_id == student_id,
                    QuizSession.status == "COMPLETED",
                )
                .order_by(QuizSession.created_at.desc())
                .limit(10)
            )
        ).scalars().all()
        reviewed_quiz_ids = set(
            (
                await session.execute(
                    select(LearningEvent.quiz_session_id).where(
                        LearningEvent.student_id == student_id,
                        LearningEvent.event_type == "QUIZ_REVIEW_COMPLETED",
                        LearningEvent.quiz_session_id.is_not(None),
                    )
                )
            ).scalars().all()
        )
        for quiz in recent_quizzes:
            if quiz.quiz_session_id in reviewed_quiz_ids:
                continue
            wrong_count = (
                await session.execute(
                    select(func.count(QuizAnswer.answer_id)).where(
                        QuizAnswer.quiz_session_id == quiz.quiz_session_id,
                        QuizAnswer.is_final.is_(True),
                        QuizAnswer.is_correct.is_(False),
                    )
                )
            ).scalar_one()
            if wrong_count > 0:
                return LearningNextActionDTO(
                    type="REVIEW_QUIZ",
                    label=f"回顾《{quiz.title}》的错题",
                    book_id=quiz.book_id,
                    chapter_id=quiz.chapter_id,
                    quiz_session_id=quiz.quiz_session_id,
                    reason=f"这次测验有 {wrong_count} 道做错，复习一下会记得更牢。",
                    evidence_ids=[str(quiz.quiz_session_id)],
                )

        # 3) 最近已完成章节且还有下一章 → 下一章
        last_completion = (
            await session.execute(
                select(Chapter.chapter_id, Chapter.book_id, Chapter.chapter_order)
                .join(LearningEvent, LearningEvent.chapter_id == Chapter.chapter_id)
                .where(
                    Chapter.status == "PUBLISHED",
                    LearningEvent.student_id == student_id,
                    LearningEvent.event_type.in_(("CHAPTER_FINISHED",)),
                )
                .order_by(LearningEvent.occurred_at.desc())
                .limit(1)
            )
        ).first()
        if last_completion is not None:
            book = await session.get(Book, last_completion.book_id)
            if book is not None and book.status == "PUBLISHED":
                next_chapter = (
                    await session.execute(
                        select(Chapter)
                        .where(
                            Chapter.book_id == last_completion.book_id,
                            Chapter.status == "PUBLISHED",
                            Chapter.chapter_order > last_completion.chapter_order,
                        )
                        .order_by(Chapter.chapter_order.asc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if next_chapter is not None:
                    return LearningNextActionDTO(
                        type="NEXT_CHAPTER",
                        label=f"学下一章：{next_chapter.title}",
                        book_id=next_chapter.book_id,
                        chapter_id=next_chapter.chapter_id,
                        reason=f"你已经读完上一章，接着学《{next_chapter.title}》衔接自然。",
                        evidence_ids=[str(next_chapter.chapter_id)],
                    )

        # 4) 有阅读位置 → 继续阅读
        progress_book = (
            await session.execute(
                select(BookProgress, Book)
                .join(Book, Book.book_id == BookProgress.book_id)
                .where(
                    BookProgress.student_id == student_id,
                    BookProgress.status == "READING",
                    Book.status == "PUBLISHED",
                )
                .order_by(BookProgress.last_read_at.desc())
                .limit(1)
            )
        ).first()
        if progress_book is not None:
            progress, book = progress_book
            return LearningNextActionDTO(
                type="CONTINUE_READING",
                label=f"继续读《{book.title}》",
                book_id=book.book_id,
                chapter_id=progress.chapter_id,
                reason=f"上次读到这本书的 {progress.position_percent}%，继续往下读。",
                evidence_ids=[str(progress.progress_id)],
            )

        # 5) 按年级匹配已发布课程 → 开始第一章
        if profile.grade is not None:
            matches = (
                await session.execute(
                    select(Book)
                    .where(
                        Book.status == "PUBLISHED",
                        Book.grade_min <= profile.grade,
                        Book.grade_max >= profile.grade,
                    )
                    .order_by(Book.created_at.asc())
                )
            ).scalars().all()
            for book in matches:
                first_chapter = (
                    await session.execute(
                        select(Chapter)
                        .where(
                            Chapter.book_id == book.book_id,
                            Chapter.status == "PUBLISHED",
                        )
                        .order_by(Chapter.chapter_order.asc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if first_chapter is not None:
                    return LearningNextActionDTO(
                        type="START_BOOK",
                        label=f"从《{book.title}》开始",
                        book_id=book.book_id,
                        chapter_id=first_chapter.chapter_id,
                        reason=f"这本书匹配你当前年级，从第一章开始最合适。",
                        evidence_ids=[str(first_chapter.chapter_id)],
                    )

        # 兜底：任何合法下一步（课程已归档/空数据时也算合法行动）。
        any_book = (
            await session.execute(
                select(Book).where(Book.status == "PUBLISHED").order_by(Book.created_at.asc())
            )
        ).scalars().first()
        if any_book is not None:
            return LearningNextActionDTO(
                type="START_BOOK",
                label=f"开始读《{any_book.title}》",
                book_id=any_book.book_id,
                reason="先挑一本适合的书开始学习。",
                evidence_ids=[],
            )
        return LearningNextActionDTO(
            type="START_BOOK",
            label="逛逛书库挑一本",
            reason="还没有适合的课程，先去书库看看。",
            evidence_ids=[],
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
            interest_signals=signals[4] if len(signals) > 4 else None,
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
        # 规则式推荐：无 LLM 参与，model_info 置空，skill_version 记录规则版本；
        # expires_at 给一条默认 TTL，到期后由 list_active 自动排除（status 保持 ACTIVE，不落 EXPIRED 写路径）。
        default_ttl = timedelta(days=RECOMMENDATION_TTL_DAYS)
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
                    # D9：规则推荐不引用外部知识来源，source_ids 保持空、license/source_url 置空；
                    # 未来引入基于知识资源的推荐时可在此填充。
                    source_ids=[],
                    license=None,
                    source_url=None,
                    model_info=None,
                    skill_version="rules-v1",
                    expires_at=now + default_ttl,
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
        now = datetime.now(timezone.utc)
        return list(
            (
                await session.execute(
                    select(Recommendation)
                    .where(
                        Recommendation.student_id == student_id,
                        Recommendation.status == "ACTIVE",
                        # 过期推荐自动排除（status 仍为 ACTIVE，但不再对用户可见）。
                        (Recommendation.expires_at.is_(None))
                        | (Recommendation.expires_at > now),
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
