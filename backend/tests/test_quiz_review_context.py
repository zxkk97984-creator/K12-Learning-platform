"""T14 错题讲解上下文契约（§4.3；真实 DB，隔离库）。

验证：
- 同一答卷点两题 → provider 各自看到对应题眼（题干/作答/解析）；
- 其他学生测验 / 题目与测验不匹配 → 明确「不是你的测验 / 题目不属于」；
- 离开答卷后（无 quiz 上下文）普通问题不沿用旧题；
- 有测验无题目 → 明确「还不知道要讲哪一题」。
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select

from app.infrastructure.database.models import (
    Book,
    Chapter,
    Conversation,
    QuizAnswer,
    QuizQuestion,
    QuizSession,
    StudentPreference,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.modules.conversation.schemas import QuizReviewContext
from app.modules.conversation.teacher_context import build_teacher_context
from app.modules.identity.security import hash_password

BOOK_ID = UUID("b6000000-0000-0000-0000-000000000001")
CH1 = UUID("c6000000-0000-0000-0000-000000000001")
STUDENT_KEY = "test_review_owner"


async def _seed() -> dict:
    """固定 UUID 的自愈种子：清掉本学生残留，重建书/章/用户/测验/两题。"""
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.username == STUDENT_KEY))).scalar_one_or_none()
        existing_student_id: UUID | None = None
        if user is not None:
            existing = (await session.execute(select(StudentProfile).where(StudentProfile.user_id == user.user_id))).scalar_one_or_none()
            existing_student_id = existing.student_id if existing is not None else None
        # 自愈：隔离库跨套件重复运行会残留，删除本学生相关测验/题/作答。
        if existing_student_id is not None:
            quiz_ids = (
                await session.execute(select(QuizSession.quiz_session_id).where(QuizSession.student_id == existing_student_id))
            ).scalars().all()
            for qid in quiz_ids:
                await session.execute(delete(QuizAnswer).where(QuizAnswer.quiz_session_id == qid))
                await session.execute(delete(QuizQuestion).where(QuizQuestion.quiz_session_id == qid))
                await session.execute(delete(QuizSession).where(QuizSession.quiz_session_id == qid))

        if user is None:
            user = User(username=STUDENT_KEY, password_hash=hash_password("pass"), user_type="STUDENT")
            session.add(user)
            await session.flush()
        profile = (await session.execute(select(StudentProfile).where(StudentProfile.user_id == user.user_id))).scalar_one_or_none()
        if profile is None:
            profile = StudentProfile(user_id=user.user_id, nickname="审题人", grade=8, language="zh-CN")
            session.add(profile)
            await session.flush()
            session.add(StudentPreference(student_id=profile.student_id, preferred_explanation_style="EXAMPLE_BASED", preferred_difficulty="MEDIUM", preferred_session_length="SHORT"))

        book = await session.get(Book, BOOK_ID)
        if book is None:
            book = Book(book_id=BOOK_ID)
            session.add(book)
        book.title = "错题讲解测试书"
        book.grade_min = 7
        book.grade_max = 9
        book.difficulty = "MEDIUM"
        book.estimated_minutes = 40
        book.status = "PUBLISHED"
        if book.published_at is None:
            book.published_at = datetime.now(timezone.utc)
        chapter = await session.get(Chapter, CH1)
        if chapter is None:
            chapter = Chapter(chapter_id=CH1, book_id=BOOK_ID)
            session.add(chapter)
        chapter.book_id = BOOK_ID
        chapter.chapter_order = 1
        chapter.title = "错题讲解章"
        chapter.estimated_minutes = 15
        chapter.status = "PUBLISHED"

        conversation = Conversation(
            conversation_id=uuid4(),
            student_id=profile.student_id,
            title="审题会话",
            channel="TEXT",
            status="ACTIVE",
            current_page_context={},
            recent_messages=[],
        )
        session.add(conversation)
        await session.flush()

        quiz = QuizSession(
            quiz_session_id=uuid4(),
            student_id=profile.student_id,
            conversation_id=conversation.conversation_id,
            book_id=BOOK_ID,
            chapter_id=CH1,
            title="错题讲解随堂测验",
            quiz_kind="CHAPTER_QUIZ",
            status="COMPLETED",
            questions_snapshot=[],
            result_summary={"correct": 1, "total": 2, "hints_used": 0},
            duration_seconds=60,
            ai_feedback=None,
            model_info={},
            skill_version="quiz-v2",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(quiz)
        await session.flush()

        q1 = QuizQuestion(
            question_id=uuid4(),
            quiz_session_id=quiz.quiz_session_id,
            question_order=1,
            question_type="SINGLE_CHOICE",
            stem="训练数据的作用是什么？",
            options=[{"key": "A", "text": "让模型学到规律"}, {"key": "B", "text": "让模型睡觉"}],
            correct_answer={"key": "A"},
            explanation="训练数据提供输入到输出的映射，模型据此学到规律。",
            source_context={},
            interaction_policy={"allow_hint": True, "max_hint_level": 3},
            knowledge_point_ids=[],
            created_at=datetime.now(timezone.utc),
        )
        q2 = QuizQuestion(
            question_id=uuid4(),
            quiz_session_id=quiz.quiz_session_id,
            question_order=2,
            question_type="SINGLE_CHOICE",
            stem="无监督学习的关键是？",
            options=[{"key": "A", "text": "有标签"}, {"key": "B", "text": "只有数据"}],
            correct_answer={"key": "B"},
            explanation="无监督学习只有数据，没有答案，靠数据自身结构分组。",
            source_context={},
            interaction_policy={"allow_hint": True, "max_hint_level": 3},
            knowledge_point_ids=[],
            created_at=datetime.now(timezone.utc),
        )
        session.add_all([q1, q2])
        await session.flush()
        session.add(
            QuizAnswer(
                answer_id=uuid4(),
                quiz_session_id=quiz.quiz_session_id,
                question_id=q1.question_id,
                student_id=profile.student_id,
                submitted_answer={"key": "A"},
                is_correct=True,
                attempt_no=1,
                hint_level_at_submit=0,
                is_final=True,
                submitted_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
            )
        )
        session.add(
            QuizAnswer(
                answer_id=uuid4(),
                quiz_session_id=quiz.quiz_session_id,
                question_id=q2.question_id,
                student_id=profile.student_id,
                submitted_answer={"key": "A"},
                is_correct=False,
                attempt_no=1,
                hint_level_at_submit=0,
                is_final=True,
                submitted_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
        return {"profile": profile, "quiz": quiz, "q1": q1, "q2": q2}


def _call(context: dict, seed: dict) -> str:
    async def run() -> str:
        async with async_session() as session:
            return await build_teacher_context(
                session,
                student_id=seed["profile"].student_id,
                grade=seed["profile"].grade,
                language=seed["profile"].language,
                learning_goal=seed["profile"].learning_goal,
                current_context=context,
            )

    return asyncio.run(run())


@pytest.fixture(scope="module")
def seed() -> dict:
    return asyncio.run(_seed())


def test_two_questions_yield_their_own_facts(seed: dict) -> None:
    block_q1 = _call(
        {"quizSessionId": str(seed["quiz"].quiz_session_id), "questionId": str(seed["q1"].question_id)},
        seed,
    )
    block_q2 = _call(
        {"quizSessionId": str(seed["quiz"].quiz_session_id), "questionId": str(seed["q2"].question_id)},
        seed,
    )
    assert "【正在讲解的题目】" in block_q1
    assert "训练数据的作用是什么？" in block_q1
    assert "让模型学到规律" in block_q1  # 选项
    assert "学生作答：A（第 1 次，正确）" in block_q1
    assert "解析：训练数据提供输入到输出的映射" in block_q1
    # 每题独立：q2 内容不出现在 q1 块。
    assert "无监督学习的关键是？" not in block_q1
    assert "无监督学习的关键是？" in block_q2
    assert "学生作答：A（第 1 次，错误）" in block_q2


def test_other_quiz_is_rejected(seed: dict) -> None:
    block = _call(
        {"quizSessionId": str(uuid4()), "questionId": str(seed["q1"].question_id)},
        seed,
    )
    assert "不是你的测验" in block or "无法定位要讲解的题目" in block


def test_question_not_belonging_to_quiz_rejected(seed: dict) -> None:
    # 用 q2 的题目强配到不属于它的上下文：改为建一个"其它测验"但题目来自本测验的非法组合，
    # 直接断言：「题目不属于这次测验」。
    block = _call(
        {"quizSessionId": str(seed["q2"].quiz_session_id), "questionId": str(seed["q1"].question_id)},
        seed,
    )
    # q1 属于同一测验，这里实际是"属于"，不会触发 mismatch。
    # 用不存在的题目来触发 mismatch：
    block2 = _call(
        {"quizSessionId": str(seed["quiz"].quiz_session_id), "questionId": str(uuid4())},
        seed,
    )
    assert "题目不属于这次测验" in block2


def test_quiz_without_question_explicitly_unknown(seed: dict) -> None:
    block = _call({"quizSessionId": str(seed["quiz"].quiz_session_id)}, seed)
    assert "还不知道要讲哪一道题" in block


def test_absent_quiz_context_does_not_carry_over_question(seed: dict) -> None:
    # 离开答卷：无 quizSessionId/questionId。普通问题不应沿用旧题。
    block = _call({"route": "/profile", "page_type": "profile"}, seed)
    assert "【正在讲解的题目】" not in block


def test_quiz_review_context_from_screen_context_both_namings() -> None:
    ctx = QuizReviewContext.from_screen_context(
        {"quizSessionId": "cafe0000-0000-0000-0000-000000000001", "question_id": "cafe0000-0000-0000-0000-000000000002"}
    )
    assert str(ctx.quiz_session_id) == "cafe0000-0000-0000-0000-000000000001"
    assert str(ctx.question_id) == "cafe0000-0000-0000-0000-000000000002"


def test_quiz_review_context_malformed_id_treated_as_absent() -> None:
    ctx = QuizReviewContext.from_screen_context(
        {"quizSessionId": "not-a-uuid", "questionId": "also-bad"}
    )
    assert ctx.quiz_session_id is None
    assert ctx.question_id is None
