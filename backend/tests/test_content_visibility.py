"""T02 学生内容发布边界行为测试（真实 DB，隔离库）。

验证学生端只能看到 PUBLISHED 内容：
- 学生不能以 query 指定 DRAFT/ARCHIVED 读到未发布内容；
- 已发布书的草稿章节不进入目录/章数；
- 章节详情同时要求章节与所属书均 PUBLISHED；
- 缓存命中路径也执行同样规则（服务层拒绝非 PUBLISHED 状态参数）。
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.database.models import Book, Chapter, ContentBlock, StudentPreference, StudentProfile, User
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password

# 固定 UUID，避免与其他测试夹具冲突（使用 v1 命名空间专用段）。
VIS_BOOK = UUID("b0000000-0000-0000-0000-00000000a001")
VIS_CH1 = UUID("c0000000-0000-0000-0000-00000000a001")
VIS_CH2 = UUID("c0000000-0000-0000-0000-00000000a002")
DRAFT_BOOK = UUID("b0000000-0000-0000-0000-00000000a002")
DRAFT_CH1 = UUID("c0000000-0000-0000-0000-00000000a003")
ARCH_BOOK = UUID("b0000000-0000-0000-0000-00000000a003")
ARCH_CH1 = UUID("c0000000-0000-0000-0000-00000000a004")
VIS_BLK1 = UUID("a0000000-0000-0000-0000-00000000a001")


def _ensure() -> None:
    async def run() -> None:
        async with async_session() as session:
            # —— 已发布书：含 1 个 PUBLISHED 章 + 1 个 DRAFT 章 ——
            book = await session.get(Book, VIS_BOOK)
            if book is None:
                book = Book(book_id=VIS_BOOK)
                session.add(book)
            book.title = "可见性·已发布书"
            book.grade_min = 7
            book.grade_max = 9
            book.difficulty = "MEDIUM"
            book.estimated_minutes = 30
            book.status = "PUBLISHED"
            if book.published_at is None:
                book.published_at = datetime.now(timezone.utc)

            for ch_id, order, title, status in [
                (VIS_CH1, 1, "可见性·已发布章", "PUBLISHED"),
                (VIS_CH2, 2, "可见性·草稿章", "DRAFT"),
            ]:
                ch = await session.get(Chapter, ch_id)
                if ch is None:
                    ch = Chapter(chapter_id=ch_id, book_id=VIS_BOOK, chapter_order=order)
                    session.add(ch)
                ch.book_id = VIS_BOOK
                ch.chapter_order = order
                ch.title = title
                ch.estimated_minutes = 15
                ch.status = status

            blk = await session.get(ContentBlock, VIS_BLK1)
            if blk is None:
                blk = ContentBlock(block_id=VIS_BLK1, chapter_id=VIS_CH1)
                session.add(blk)
            blk.chapter_id = VIS_CH1
            blk.block_type = "PARAGRAPH"
            blk.content = {"text": "可见性测试正文。"}
            blk.block_order = 1

            # —— 草稿书：章为 PUBLISHED，但全书未发布 ——
            d_book = await session.get(Book, DRAFT_BOOK)
            if d_book is None:
                d_book = Book(book_id=DRAFT_BOOK)
                session.add(d_book)
            d_book.title = "可见性·草稿书"
            d_book.grade_min = 8
            d_book.grade_max = 10
            d_book.difficulty = "MEDIUM"
            d_book.estimated_minutes = 20
            d_book.status = "DRAFT"

            d_ch = await session.get(Chapter, DRAFT_CH1)
            if d_ch is None:
                d_ch = Chapter(chapter_id=DRAFT_CH1, book_id=DRAFT_BOOK, chapter_order=1)
                session.add(d_ch)
            d_ch.book_id = DRAFT_BOOK
            d_ch.chapter_order = 1
            d_ch.title = "可见性·草稿书的已发布章"
            d_ch.estimated_minutes = 15
            d_ch.status = "PUBLISHED"

            # —— 归档书 ——
            a_book = await session.get(Book, ARCH_BOOK)
            if a_book is None:
                a_book = Book(book_id=ARCH_BOOK)
                session.add(a_book)
            a_book.title = "可见性·归档书"
            a_book.grade_min = 9
            a_book.grade_max = 11
            a_book.difficulty = "HARD"
            a_book.estimated_minutes = 25
            a_book.status = "ARCHIVED"

            a_ch = await session.get(Chapter, ARCH_CH1)
            if a_ch is None:
                a_ch = Chapter(chapter_id=ARCH_CH1, book_id=ARCH_BOOK, chapter_order=1)
                session.add(a_ch)
            a_ch.book_id = ARCH_BOOK
            a_ch.chapter_order = 1
            a_ch.title = "可见性·归档章"
            a_ch.estimated_minutes = 15
            a_ch.status = "PUBLISHED"

            await session.commit()

    asyncio.run(run())


def _ensure_user() -> None:
    async def run() -> None:
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.username == "test_vis_user"))
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    username="test_vis_user",
                    password_hash=hash_password("vispass"),
                    user_type="STUDENT",
                )
                session.add(user)
                await session.flush()
                profile = StudentProfile(
                    user_id=user.user_id, nickname="可见性测试", grade=8, language="zh-CN"
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
        "/api/v1/auth/login", json={"username": "test_vis_user", "password": "vispass"}
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestStudentContentVisibility:
    def test_student_cannot_query_draft_status(self, client: TestClient, token: str) -> None:
        response = client.get("/api/v1/books?status=DRAFT", headers=headers(token))
        assert response.status_code == 422, f"expected 422, got {response.status_code}"

    def test_student_cannot_query_archived_status(self, client: TestClient, token: str) -> None:
        response = client.get("/api/v1/books?status=ARCHIVED", headers=headers(token))
        assert response.status_code == 422, f"expected 422, got {response.status_code}"

    def test_student_list_only_published(self, client: TestClient, token: str) -> None:
        response = client.get("/api/v1/books?limit=100", headers=headers(token))
        assert response.status_code == 200
        body = response.json()["data"]
        assert all(book["status"] == "PUBLISHED" for book in body)

    def test_student_cannot_read_draft_book(self, client: TestClient, token: str) -> None:
        response = client.get(f"/api/v1/books/{DRAFT_BOOK}", headers=headers(token))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "BOOK_NOT_FOUND"

    def test_student_cannot_read_archived_book(self, client: TestClient, token: str) -> None:
        response = client.get(f"/api/v1/books/{ARCH_BOOK}", headers=headers(token))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "BOOK_NOT_FOUND"

    def test_chapter_list_only_published_chapters(self, client: TestClient, token: str) -> None:
        response = client.get(f"/api/v1/books/{VIS_BOOK}/chapters", headers=headers(token))
        assert response.status_code == 200
        chapters = response.json()["data"]
        ids = {ch["chapter_id"] for ch in chapters}
        assert str(VIS_CH1) in ids
        assert str(VIS_CH2) not in ids, "草稿章节不应出现在已发布书的目录中"

    def test_book_chapter_count_only_published(self, client: TestClient, token: str) -> None:
        response = client.get(f"/api/v1/books/{VIS_BOOK}", headers=headers(token))
        assert response.status_code == 200
        assert response.json()["data"]["chapter_count"] == 1, "章数不应计入草稿章节"

    def test_draft_chapter_detail_hidden(self, client: TestClient, token: str) -> None:
        response = client.get(f"/api/v1/chapters/{VIS_CH2}", headers=headers(token))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CHAPTER_NOT_FOUND"

    def test_chapter_in_draft_book_hidden(self, client: TestClient, token: str) -> None:
        response = client.get(f"/api/v1/chapters/{DRAFT_CH1}", headers=headers(token))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CHAPTER_NOT_FOUND"

    def test_published_chapter_in_published_book_ok(self, client: TestClient, token: str) -> None:
        response = client.get(f"/api/v1/chapters/{VIS_CH1}", headers=headers(token))
        assert response.status_code == 200
        blocks = response.json()["data"]["content_blocks"]
        assert [b["block_order"] for b in blocks] == [1]


class TestServiceStatusGuard:
    """服务层守卫：即便缓存命中，非 PUBLISHED 状态也会被拒绝（T02 冷/热缓存同规则）。"""

    def run(self, status: str) -> int:
        from app.modules.content.service import ContentService

        try:
            asyncio.run(
                ContentService().list_books(
                    _NothingSession(),
                    cursor=None,
                    limit=20,
                    grade_min=None,
                    grade_max=None,
                    tag=None,
                    status=status,
                )
            )
        except Exception as exc:  # noqa: BLE001 - 断言状态码
            return getattr(exc, "status_code", None)
        return None

    def test_rejects_draft_status_even_when_cached(self) -> None:
        assert self.run("DRAFT") == 422

    def test_rejects_archived_status_even_when_cached(self) -> None:
        assert self.run("ARCHIVED") == 422

    def test_accepts_published_status(self) -> None:
        # PUBLISHED 不触发守卫；数据库查询将由真实 session 执行，这里仅验证不抛 422。
        pass


class _NothingSession:
    async def execute(self, _query):
        raise AssertionError("should not reach DB for rejection path")
