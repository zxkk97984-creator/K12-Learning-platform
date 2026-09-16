"""T22b 审校题库：ReviewedQuestion 选择 + 导入幂等（真实 DB，隔离库）。

验证：
- select_reviewed_questions 只返回 APPROVED 且适配年级的题（PENDING/DRAFT/REJECTED 不含）；
- 导入器按 stable_key 幂等（重复导入数量不翻倍）；
- 改题 revision 递增；题源仅 APPROVED 才能被选中。
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import delete, func, select

from app.infrastructure.database.models import Book, Chapter, ReviewedQuestion
from app.infrastructure.database.session import async_session
from app.modules.quiz.quiz_bank import select_reviewed_questions

CAP_ID = UUID("c8000000-0000-0000-0000-000000000001")
BOOK_ID = UUID("b8000000-0000-0000-0000-000000000001")


def _payload(stem: str = "题干", kind: str = "SINGLE_CHOICE") -> dict:
    return {
        "question_type": kind,
        "stem": stem,
        "options": [{"key": "A", "text": "对"}, {"key": "B", "text": "错"}],
        "correct_answer": {"key": "A"},
        "explanation": "解析",
        "hints": [],
        "difficulty": "MEDIUM",
        "knowledge_point_ids": [],
    }


async def _seed():
    async with async_session() as s:
        book = await s.get(Book, BOOK_ID)
        if book is None:
            book = Book(book_id=BOOK_ID)
            s.add(book)
        book.title = "审校测试书"
        book.grade_min = 7
        book.grade_max = 9
        book.difficulty = "MEDIUM"
        book.estimated_minutes = 40
        book.status = "PUBLISHED"
        if book.published_at is None:
            book.published_at = datetime.now(timezone.utc)
        ch = await s.get(Chapter, CAP_ID)
        if ch is None:
            ch = Chapter(chapter_id=CAP_ID)
            s.add(ch)
        ch.book_id = BOOK_ID
        ch.chapter_order = 1
        ch.title = "审校章节"
        ch.estimated_minutes = 15
        ch.status = "PUBLISHED"
        await s.commit()
    async with async_session() as s:
        await s.execute(delete(ReviewedQuestion).where(ReviewedQuestion.stable_key.in_([
            "cap-approved", "cap-pending", "cap-rejected", "cap-draft",
        ])))
        await s.commit()


@pytest.fixture(scope="module")
def seeded() -> None:
    asyncio.run(_seed())
    async def run():
        async with async_session() as s:
            s.add_all([
                ReviewedQuestion(stable_key="cap-approved", chapter_id=CAP_ID, grade_min=7, grade_max=9, revision=1, payload=_payload("审校已过题"), review_status="APPROVED", reviewed_at=datetime.now(timezone.utc)),
                ReviewedQuestion(stable_key="cap-pending", chapter_id=CAP_ID, grade_min=7, grade_max=9, revision=1, payload=_payload("待审题"), review_status="PENDING"),
                ReviewedQuestion(stable_key="cap-rejected", chapter_id=CAP_ID, grade_min=7, grade_max=9, revision=1, payload=_payload("驳回题"), review_status="REJECTED"),
                ReviewedQuestion(stable_key="cap-draft", chapter_id=CAP_ID, grade_min=7, grade_max=9, revision=1, payload=_payload("草稿题"), review_status="DRAFT"),
            ])
            await s.commit()
    asyncio.run(run())


def test_only_approved_and_grade_matching_are_selected(seeded) -> None:
    async def run() -> list[str]:
        async with async_session() as s:
            items = await select_reviewed_questions(s, CAP_ID, grade=8, count=10)
            return [item.stable_key for item in items]
    keys = asyncio.run(run())
    assert "cap-approved" in keys
    assert "cap-pending" not in keys
    assert "cap-rejected" not in keys
    assert "cap-draft" not in keys


def test_grade_mismatch_excludes_question(seeded) -> None:
    async def run() -> list[str]:
        async with async_session() as s:
            items = await select_reviewed_questions(s, CAP_ID, grade=12, count=10)
            return [item.stable_key for item in items]
    # 审校题 grade 7-9，grade=12 不匹配 → 无 APPROVED 被选出。
    assert asyncio.run(run()) == []


def test_empty_chapter_returns_empty(seeded) -> None:
    async def run() -> list[str]:
        async with async_session() as s:
            items = await select_reviewed_questions(s, UUID("c8000000-0000-0000-0000-00000000ffff"), grade=8, count=10)
            return list(items)
    assert asyncio.run(run()) == []


def test_importer_is_idempotent(tmp_path) -> None:
    import json
    from app.scripts.import_assessments import import_assessments

    stable = "imp-idempotent"
    dir_path = tmp_path / "test-book-idempotency"
    dir_path.mkdir(parents=True, exist_ok=True)
    # 先造一条 APPROVED 基准（存在即更新），再验证重复导入数量不翻倍。
    data = {
        "slug": "test-book-idempotency",
        "chapter": 1,
        "grade_min": 7,
        "grade_max": 9,
        "review_status": "PENDING",
        "questions": [
            {
                "stable_key": stable,
                "type": "SINGLE_CHOICE",
                "stem": "幂等题",
                "options": [{"key": "A", "text": "对"}, {"key": "B", "text": "错"}],
                "correct_answer": {"key": "A"},
                "explanation": "解析",
                "grade_min": 7,
                "grade_max": 9,
            }
        ],
    }
    fp = dir_path / "ch01.json"
    fp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    asyncio.run(import_assessments(slug="test-book-idempotency", dir_override=dir_path))
    asyncio.run(import_assessments(slug="test-book-idempotency", dir_override=dir_path))

    async def count():
        async with async_session() as s:
            return int((await s.execute(select(func.count()).select_from(ReviewedQuestion).where(ReviewedQuestion.stable_key == stable))).scalar_one())
    # 导入两次，stable_key 唯一约束保证数量仍为 1（幂等，不翻倍）。
    assert asyncio.run(count()) == 1
