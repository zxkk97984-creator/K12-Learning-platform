"""T03 RAG 与出题同步遵守内容可见性（真实 DB）。

验证：
- 章节出题核实 book/chapter 归属与发布状态（不可见章节不出题）；
- 篡改 chapter/book 组合被拒绝；
- 资源非 READY（FAILED 等）时 RAG 检索不返回其 chunk；
- 历史答卷按快照仍可读（不因可见性误伤——由既存 snapshot 保证）。
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.database.models import (
    Book,
    Chapter,
    ContentBlock,
    KnowledgeChunk,
    KnowledgeResource,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password
from app.modules.quiz.chapter_source import load_chapter_source
from app.modules.knowledge.schemas import KnowledgeSearchRequest
from app.modules.knowledge.service import KnowledgeService

VISUAL_BOOK = UUID("b3000000-0000-0000-0000-000000000001")
VISUAL_CH = UUID("c3000000-0000-0000-0000-000000000001")
DRAFT_BOOK = UUID("b3000000-0000-0000-0000-000000000002")
INVISIBLE_CH = UUID("c3000000-0000-0000-0000-000000000002")


def _ensure() -> None:
    async def run() -> None:
        async with async_session() as session:
            # 已发布书 + 已发布章（含可出题正文）
            book = await session.get(Book, VISUAL_BOOK)
            if book is None:
                book = Book(book_id=VISUAL_BOOK)
                session.add(book)
            book.title = "AI 可见性测试书"
            book.grade_min = 7
            book.grade_max = 9
            book.difficulty = "MEDIUM"
            book.estimated_minutes = 40
            book.status = "PUBLISHED"
            if book.published_at is None:
                book.published_at = datetime.now(timezone.utc)

            ch = await session.get(Chapter, VISUAL_CH)
            if ch is None:
                ch = Chapter(chapter_id=VISUAL_CH, book_id=VISUAL_BOOK, chapter_order=1)
                session.add(ch)
            ch.book_id = VISUAL_BOOK
            ch.chapter_order = 1
            ch.title = "AI 可见性·训练数据"
            ch.estimated_minutes = 15
            ch.status = "PUBLISHED"

            blk = await session.get(ContentBlock, UUID("a3000000-0000-0000-0000-000000000001"))
            if blk is None:
                blk = ContentBlock(
                    block_id=UUID("a3000000-0000-0000-0000-000000000001"),
                    chapter_id=VISUAL_CH,
                )
                session.add(blk)
            blk.chapter_id = VISUAL_CH
            blk.block_type = "PARAGRAPH"
            blk.content = {"text": "训练数据是一组用来帮助机器发现规律的例子。"}
            blk.block_order = 1

            # 草稿书 + 已发布章（章可 PUBLISHED，但全书不可见）
            d_book = await session.get(Book, DRAFT_BOOK)
            if d_book is None:
                d_book = Book(book_id=DRAFT_BOOK)
                session.add(d_book)
            d_book.title = "草稿书"
            d_book.grade_min = 8
            d_book.grade_max = 10
            d_book.difficulty = "MEDIUM"
            d_book.estimated_minutes = 20
            d_book.status = "DRAFT"

            i_ch = await session.get(Chapter, INVISIBLE_CH)
            if i_ch is None:
                i_ch = Chapter(chapter_id=INVISIBLE_CH, book_id=DRAFT_BOOK, chapter_order=1)
                session.add(i_ch)
            i_ch.book_id = DRAFT_BOOK
            i_ch.chapter_order = 1
            i_ch.title = "草稿书里的章"
            i_ch.estimated_minutes = 15
            i_ch.status = "PUBLISHED"

            await session.commit()

    asyncio.run(run())


def _ensure_user() -> None:
    async def run() -> None:
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.username == "test_ai_vis"))
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    username="test_ai_vis",
                    password_hash=hash_password("aipass"),
                    user_type="STUDENT",
                )
                session.add(user)
                await session.flush()
                profile = StudentProfile(
                    user_id=user.user_id, nickname="AI可见", grade=8, language="zh-CN"
                )
                session.add(profile)
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
        "/api/v1/auth/login", json={"username": "test_ai_vis", "password": "aipass"}
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def headers(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


def _make_conversation(client: TestClient, token: str) -> str:
    resp = client.post(
        "/api/v1/conversations",
        headers=headers(token, **{"Idempotency-Key": f"conv-{uuid4()}"}),
        json={"title": "AI 可见性"},
    )
    assert resp.status_code == 201
    return resp.json()["data"]["conversation_id"]


class TestChapterSourceVisibility:
    def run_loader(self, book_id, chapter_id):
        async def call():
            async with async_session() as session:
                return await load_chapter_source(session, book_id, chapter_id)

        return asyncio.run(call())

    def test_published_chapter_loads_source(self) -> None:
        source = self.run_loader(VISUAL_BOOK, VISUAL_CH)
        assert source is not None
        assert "训练数据是一组用来帮助机器发现规律的例子。" in source.texts

    def test_draft_book_hides_published_chapter(self) -> None:
        source = self.run_loader(DRAFT_BOOK, INVISIBLE_CH)
        assert source is None, "草稿书内的章不应作为出题素材"

    def test_mismatched_book_chapter_rejected(self) -> None:
        source = self.run_loader(VISUAL_BOOK, INVISIBLE_CH)
        assert source is None, "章节与指定书不匹配应被拒绝"

    def test_wrong_book_id_rejected(self) -> None:
        source = self.run_loader(DRAFT_BOOK, VISUAL_CH)
        assert source is None, "用错误书 id 读取可见章应被拒绝"


class TestQuizApiVisibility:
    def test_can_create_published_chapter_quiz(self, client: TestClient, token: str) -> None:
        conv = _make_conversation(client, token)
        resp = client.post(
            "/api/v1/quiz-sessions",
            headers=headers(token),
            json={
                "conversation_id": conv,
                "book_id": str(VISUAL_BOOK),
                "chapter_id": str(VISUAL_CH),
                "question_count": 2,
            },
        )
        assert resp.status_code == 201, resp.text

    def test_cannot_create_quiz_from_draft_book(self, client: TestClient, token: str) -> None:
        conv = _make_conversation(client, token)
        resp = client.post(
            "/api/v1/quiz-sessions",
            headers=headers(token),
            json={
                "conversation_id": conv,
                "book_id": str(DRAFT_BOOK),
                "chapter_id": str(INVISIBLE_CH),
                "question_count": 2,
            },
        )
        assert resp.status_code == 404

    def test_cannot_create_quiz_from_archived_book_via_chapter(
        self, client: TestClient, token: str
    ) -> None:
        # 用不存在的书 + 真实章：应因章节与书不匹配（422）或书不存在（404）被拒。
        conv = _make_conversation(client, token)
        ghost_book = UUID("b3000000-0000-0000-0000-000000000099")
        resp = client.post(
            "/api/v1/quiz-sessions",
            headers=headers(token),
            json={
                "conversation_id": conv,
                "book_id": str(ghost_book),
                "chapter_id": str(VISUAL_CH),
                "question_count": 2,
            },
        )
        assert resp.status_code in (404, 422)


class TestKnowledgeRetrievalAvoidsHiddenResources:
    """非 READY 资源（如已 FAILED/不再可用）的 chunk 不应被 RAG 检索返回。"""

    def test_failed_resource_chunk_not_retrieved(self) -> None:
        resource_id = uuid4()
        chunk_id = uuid4()

        async def insert() -> None:
            async with async_session() as session:
                session.add(
                    KnowledgeResource(
                        resource_id=resource_id,
                        source_name="失效资源",
                        source_url=f"https://test.shuangling.local/zombie-{uuid4()}",
                        license="CC-BY-4.0",
                        copyright_status="测试资源",
                        storage_key=f"knowledge/zombie-{uuid4()}",
                        file_type="MARKDOWN",
                        status="FAILED",
                        error="embedding failed",
                    )
                )
                await session.flush()
                session.add(
                    KnowledgeChunk(
                        chunk_id=chunk_id,
                        resource_id=resource_id,
                        chunk_index=0,
                        content="一个只属于失效资源的独特关键词xyzzy",
                        metadata_={},
                        status="READY",
                    )
                )
                await session.commit()

        asyncio.run(insert())

        async def search() -> list:
            async with async_session() as session:
                results = await KnowledgeService().search(
                    session, KnowledgeSearchRequest(query="xyzzy", limit=5)
                )
                return [r.content for r in results]

        contents = asyncio.run(search())
        assert all("xyzzy" not in c for c in contents), "FAILED 资源的 chunk 不应被检索到"
