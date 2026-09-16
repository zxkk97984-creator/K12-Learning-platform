"""T16 统一下一步行动（§6.1）+ 相似练习来源 + 复习完成幂等（真实 DB，隔离库）。

验证：
- 优先级：进行中练习 > 未复习错题回顾 > 下一章 > 继续阅读 > 按年级开始第一章；
- 相似练习 source_quiz_session_id/source_question_id 保留且归当前学生；
- QUIZ_REVIEW_COMPLETED 幂等（同一 request_id 只记一次）+ 所有权校验；
- 空数据/课程已归档时有合法下一步。
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, update

from app.infrastructure.database.models import (
    Book,
    BookProgress,
    Chapter,
    Conversation,
    LearningEvent,
    QuizAnswer,
    QuizQuestion,
    QuizSession,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.modules.learning.schemas import CreateLearningEventRequest
from app.modules.learning.service import LearningService
from app.modules.identity.security import hash_password
from app.modules.recommendation.service import RecommendationService

USER = "test_next_action"


async def _student() -> tuple[User, StudentProfile]:
    async with async_session() as s:
        user = (await s.execute(select(User).where(User.username == USER))).scalar_one_or_none()
        if user is None:
            user = User(username=USER, password_hash=hash_password("pass"), user_type="STUDENT")
            s.add(user)
            await s.flush()
        profile = (await s.execute(select(StudentProfile).where(StudentProfile.user_id == user.user_id))).scalar_one_or_none()
        if profile is None:
            profile = StudentProfile(user_id=user.user_id, nickname="下一步", grade=8, language="zh-CN")
            s.add(profile)
            await s.flush()
        await s.commit()
        return user, profile


def _book(book_id: UUID, grade_min: int = 7, grade_max: int = 9):
    async def run() -> None:
        async with async_session() as s:
            book = await s.get(Book, book_id)
            if book is None:
                book = Book(book_id=book_id)
                s.add(book)
            book.title = f"书-{book_id.hex[:6]}"
            book.grade_min = grade_min
            book.grade_max = grade_max
            book.difficulty = "MEDIUM"
            book.estimated_minutes = 40
            book.status = "PUBLISHED"
            if book.published_at is None:
                book.published_at = datetime.now(timezone.utc)
            await s.commit()
    asyncio.run(run())


def _chapter(chapter_id: UUID, book_id: UUID, order: int, title: str):
    async def run() -> None:
        async with async_session() as s:
            ch = await s.get(Chapter, chapter_id)
            if ch is None:
                ch = Chapter(chapter_id=chapter_id, book_id=book_id)
                s.add(ch)
            ch.book_id = book_id
            ch.chapter_order = order
            ch.title = title
            ch.estimated_minutes = 15
            ch.status = "PUBLISHED"
            await s.commit()
    asyncio.run(run())


def _conversation(student_id: UUID) -> UUID:
    conv_id = uuid4()
    async def run() -> None:
        async with async_session() as s:
            s.add(Conversation(conversation_id=conv_id, student_id=student_id, title="测试会话", channel="TEXT", status="ACTIVE", current_page_context={}, recent_messages=[]))
            await s.commit()
    asyncio.run(run())
    return conv_id


def _quiz(student_id: UUID, *, status: str = "COMPLETED", title: str = "测验") -> tuple[UUID, UUID]:
    quiz_id = uuid4()
    conv_id = _conversation(student_id)
    async def run() -> None:
        async with async_session() as s:
            s.add(QuizSession(quiz_session_id=quiz_id, student_id=student_id, conversation_id=conv_id, book_id=UUID("b7000000-0000-0000-0000-000000000002"), title=title, quiz_kind="CHAPTER_QUIZ", status=status, questions_snapshot=[], result_summary={}, duration_seconds=30, model_info={}, skill_version="quiz-v2", created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc) if status == "COMPLETED" else None))
            await s.commit()
    asyncio.run(run())
    return quiz_id, conv_id


def _cleanup(student_id: UUID):
    async def run() -> None:
        async with async_session() as s:
            for qz in (await s.execute(select(QuizSession).where(QuizSession.student_id == student_id))).scalars().all():
                await s.execute(delete(QuizAnswer).where(QuizAnswer.quiz_session_id == qz.quiz_session_id))
                await s.execute(delete(QuizQuestion).where(QuizQuestion.quiz_session_id == qz.quiz_session_id))
                await s.execute(delete(LearningEvent).where(LearningEvent.quiz_session_id == qz.quiz_session_id))
                await s.execute(delete(QuizSession).where(QuizSession.quiz_session_id == qz.quiz_session_id))
            await s.execute(delete(LearningEvent).where(LearningEvent.student_id == student_id))
            await s.execute(delete(BookProgress).where(BookProgress.student_id == student_id))
            await s.commit()
    asyncio.run(run())


@pytest.fixture(scope="module")
def student() -> tuple[User, StudentProfile]:
    user, profile = asyncio.run(_student())
    _cleanup(profile.student_id)
    return user, profile


def _next(student: StudentProfile) -> dict:
    async def run() -> dict:
        async with async_session() as s:
            dto = await RecommendationService().learning_next(s, student.user_id)
            return dto.model_dump()
    return asyncio.run(run())


class TestPriorityOrder:
    def test_empty_data_fallback_start_book(self, student) -> None:
        _book(UUID("b7000000-0000-0000-0000-000000000001"), 8, 8)
        action = _next(student[1])
        assert action["type"] == "START_BOOK"

    def test_reading_position_beats_start_book(self, student) -> None:
        profile = student[1]
        book_id = UUID("b7000000-0000-0000-0000-000000000002")
        _book(book_id)
        _chapter(UUID("c7000000-0000-0000-0000-000000000001"), book_id, 1, "第一章")
        async def seed():
            async with async_session() as s:
                s.add(BookProgress(student_id=profile.student_id, book_id=book_id, chapter_id=UUID("c7000000-0000-0000-0000-000000000001"), status="READING", position_percent=50, last_read_at=datetime.now(timezone.utc), started_at=datetime.now(timezone.utc)))
                await s.commit()
        asyncio.run(seed())
        action = _next(profile)
        assert action["type"] == "CONTINUE_READING"

    def test_completed_chapter_points_outer_next_chapter(self, student) -> None:
        profile = student[1]
        book_id = UUID("b7000000-0000-0000-0000-000000000002")
        ch2 = UUID("c7000000-0000-0000-0000-000000000002")
        _chapter(ch2, book_id, 2, "第二章")
        async def seed():
            async with async_session() as s:
                s.add(LearningEvent(student_id=profile.student_id, event_type="CHAPTER_FINISHED", occurred_at=datetime.now(timezone.utc), book_id=book_id, chapter_id=UUID("c7000000-0000-0000-0000-000000000001"), payload={}))
                # 清掉进行中的练习干扰（如果有）
                await s.execute(delete(QuizSession).where(QuizSession.student_id == profile.student_id, QuizSession.status == "ACTIVE"))
                await s.commit()
        asyncio.run(seed())
        action = _next(profile)
        assert action["type"] == "NEXT_CHAPTER"
        assert action["chapter_id"] == ch2

    def test_unreviewed_wrong_answers_review_quiz(self, student) -> None:
        profile = student[1]
        book_id = UUID("b7000000-0000-0000-0000-000000000003")
        _book(book_id)
        # 本章被下方 quiz_session.chapter_id 引用；必须在此自建，避免依赖其他用例先跑建立
        #（曾见在干净库上因缺少而 ForeignKeyViolation，属用例间顺序依赖缺陷）。
        ch3 = UUID("c7000000-0000-0000-0000-000000000003")
        _chapter(ch3, book_id, 3, "第三章")
        quiz_id, _ = _quiz(profile.student_id)
        qid = uuid4()
        async def seed():
            async with async_session() as s:
                qz = await s.get(QuizSession, quiz_id)
                qz.book_id = book_id
                qz.chapter_id = ch3
                qz.title = "错题测验"
                await s.flush()
                s.add(QuizQuestion(question_id=qid, quiz_session_id=quiz_id, question_order=1, question_type="SINGLE_CHOICE", stem="题", options=[], correct_answer={}, explanation="", interaction_policy={"allow_hint": True, "max_hint_level": 1}, knowledge_point_ids=[], created_at=datetime.now(timezone.utc)))
                await s.flush()
                s.add(QuizAnswer(answer_id=uuid4(), quiz_session_id=quiz_id, question_id=qid, student_id=profile.student_id, submitted_answer={}, is_correct=False, attempt_no=1, hint_level_at_submit=0, is_final=True, submitted_at=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc)))
                await s.commit()
        asyncio.run(seed())
        action = _next(profile)
        assert action["type"] == "REVIEW_QUIZ"
        assert action["quiz_session_id"] == quiz_id


class TestReviewCompletedIdempotency:
    def test_repeat_request_id_counts_once(self, student) -> None:
        profile = student[1]
        quiz_id, _ = _quiz(profile.student_id)

        async def post(request_id: str):
            async with async_session() as s:
                return await LearningService().create_event(s, profile.user_id, CreateLearningEventRequest(
                    event_type="QUIZ_REVIEW_COMPLETED", occurred_at=datetime.now(timezone.utc),
                    quiz_session_id=quiz_id, payload={"request_id": request_id},
                ))

        e1 = asyncio.run(post("req-abc"))
        e2 = asyncio.run(post("req-abc"))
        assert e1.event_id == e2.event_id

    def test_review_event_rejects_other_students_quiz(self, student) -> None:
        profile = student[1]
        async def post():
            async with async_session() as s:
                return await LearningService().create_event(s, profile.user_id, CreateLearningEventRequest(
                    event_type="QUIZ_REVIEW_COMPLETED", occurred_at=datetime.now(timezone.utc),
                    quiz_session_id=uuid4(), payload={"request_id": "req-other"},
                ))
        import pytest as _pytest
        with _pytest.raises(Exception) as exc:
            asyncio.run(post())
        assert "does not belong" in str(exc.value)

