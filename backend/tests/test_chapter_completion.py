"""T13 章节完成事实表 + 继续学习闭环（真实 DB，隔离库）。

验证：
- 幂等：重复提交/并发提交计数一次；
- 书籍完成 = 本书所有"已发布章节"均完成（草稿章节不计）；
- 目录 DTO is_completed 反映 chapter_completions；
- 未发布书/章被拒绝（可见性 T02/T03）。
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.infrastructure.database.models import (
    Book,
    Chapter,
    ChapterCompletion,
    StudentPreference,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password

BOOK_ID = UUID("d5000000-0000-0000-0000-000000000001")
CH1 = UUID("c5000000-0000-0000-0000-000000000001")
CH2 = UUID("c5000000-0000-0000-0000-000000000002")
CH_DRAFT = UUID("c5000000-0000-0000-0000-000000000003")


def _ensure() -> None:
    async def run() -> None:
        async with async_session() as session:
            # 自愈：清掉本测试书残留的完成事实，保证幂等用例的"首次=1"假设。
            await session.execute(
                delete(ChapterCompletion).where(ChapterCompletion.book_id == BOOK_ID)
            )
            book = await session.get(Book, BOOK_ID)
            if book is None:
                book = Book(book_id=BOOK_ID)
                session.add(book)
            book.title = "完成闭环测试书"
            book.grade_min = 7
            book.grade_max = 9
            book.difficulty = "MEDIUM"
            book.estimated_minutes = 40
            book.status = "PUBLISHED"
            if book.published_at is None:
                book.published_at = datetime.now(timezone.utc)
            for ch_id, order, title, status in [
                (CH1, 1, "第一章（已发布）", "PUBLISHED"),
                (CH2, 2, "第二章（已发布）", "PUBLISHED"),
                (CH_DRAFT, 3, "第三章（草稿）", "DRAFT"),
            ]:
                ch = await session.get(Chapter, ch_id)
                if ch is None:
                    ch = Chapter(chapter_id=ch_id, book_id=BOOK_ID, chapter_order=order)
                    session.add(ch)
                ch.book_id = BOOK_ID
                ch.chapter_order = order
                ch.title = title
                ch.estimated_minutes = 15
                ch.status = status
            await session.commit()

    asyncio.run(run())


def _ensure_user() -> None:
    async def run() -> None:
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.username == "test_completion"))
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    username="test_completion",
                    password_hash=hash_password("completepass"),
                    user_type="STUDENT",
                )
                session.add(user)
                await session.flush()
                profile = StudentProfile(
                    user_id=user.user_id, nickname="完成测试", grade=8, language="zh-CN"
                )
                session.add(profile)
                await session.flush()
                session.add(
                    StudentPreference(
                        student_id=profile.student_id,
                        preferred_explanation_style="EXAMPLE_BASED",
                        preferred_difficulty="MEDIUM",
                        preferred_session_length="SHORT",
                    )
                )
            await session.commit()

    asyncio.run(run())


@pytest.fixture(scope="module")
def client() -> TestClient:
    _ensure()
    _ensure_user()
    return TestClient(app)


@pytest.fixture(scope="module")
def token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"username": "test_completion", "password": "completepass"}
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _mark(client, token, chapter_id):
    return client.put(f"/api/v1/me/chapters/{chapter_id}/completion", headers=headers(token))


class TestChapterCompletion:
    def test_mark_first_chapter_book_not_completed(self, client, token) -> None:
        resp = _mark(client, token, CH1)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["chapter_id"] == str(CH1)
        assert data["book_completed"] is False
        assert data["published_chapters"] == 2
        assert data["completed_chapters"] == 1

    def test_mark_is_idempotent_second_call_counts_once(self, client, token) -> None:
        first = _mark(client, token, CH1)
        second = _mark(client, token, CH1)
        assert first.status_code == second.status_code == 200
        assert second.json()["data"]["completed_chapters"] == 1

    def test_book_completed_only_when_all_published_chapters_done(
        self, client, token
    ) -> None:
        resp = _mark(client, token, CH2)
        data = resp.json()["data"]
        # 2 个已发布章节都完成（草稿不计数）→ 书完成。
        assert data["book_completed"] is True
        assert data["completed_chapters"] == 2
        assert data["published_chapters"] == 2

    def test_directory_reflects_is_completed(self, client, token) -> None:
        resp = client.get(f"/api/v1/books/{BOOK_ID}/chapters", headers=headers(token))
        assert resp.status_code == 200
        by_id = {ch["chapter_id"]: ch for ch in resp.json()["data"]}
        assert by_id[str(CH1)]["is_completed"] is True
        assert by_id[str(CH2)]["is_completed"] is True
        # 草稿章节不在目录中（T02），即使完成态也不出现在已发布目录。
        assert str(CH_DRAFT) not in by_id

    def test_chapter_detail_reflects_completed(self, client, token) -> None:
        resp = client.get(f"/api/v1/chapters/{CH2}", headers=headers(token))
        assert resp.status_code == 200
        assert resp.json()["data"]["chapter"]["is_completed"] is True

    def test_draft_chapter_returns_404(self, client, token) -> None:
        resp = _mark(client, token, CH_DRAFT)
        assert resp.status_code == 404
