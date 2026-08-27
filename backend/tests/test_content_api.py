"""Phase 3 Content 读取 API 测试（真实 DB；沿用 NullPool 测试机制）。"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.database.models import (
    Book,
    Chapter,
    ContentBlock,
    KnowledgePoint,
    StudentPreference,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password

BOOK_ID = UUID("b0000000-0000-0000-0000-000000000001")
CH1_ID = UUID("c0000000-0000-0000-0000-000000000001")
CH2_ID = UUID("c0000000-0000-0000-0000-000000000002")
BLK1_ID = UUID("a0000000-0000-0000-0000-000000000001")
BLK2_ID = UUID("a0000000-0000-0000-0000-000000000002")
KP1_ID = UUID("10000000-0000-0000-0000-000000000001")
KP2_ID = UUID("10000000-0000-0000-0000-000000000002")


def _ensure_content() -> None:
    """幂等且自愈的固定夹具 seed。

    不做「存在即跳过」的弱检查：固定 UUID 的书/章/块若曾被外部操作污染
    （如批量归档脚本按标题误杀、状态被改、内容缺失），这里一律恢复为
    期望状态（缺陷 B 的自愈要求），测试不依赖手工修库。
    """

    async def run() -> None:
        async with async_session() as session:
            book = await session.get(Book, BOOK_ID)
            if book is None:
                book = Book(book_id=BOOK_ID)
                session.add(book)
            book.title = "AI 不是魔法"
            book.description = "从推荐系统、训练数据到算法公平。"
            book.grade_min = 7
            book.grade_max = 9
            book.difficulty = "MEDIUM"
            book.estimated_minutes = 90
            book.tags = ["AI 基础"]
            book.status = "PUBLISHED"
            if book.published_at is None:
                book.published_at = datetime.now(timezone.utc)

            chapter_specs = [
                (CH1_ID, 1, "从“会回答”开始", 13),
                (CH2_ID, 2, "训练数据", 13),
            ]
            for chapter_id, order, title, minutes in chapter_specs:
                ch = await session.get(Chapter, chapter_id)
                if ch is None:
                    ch = Chapter(chapter_id=chapter_id, book_id=BOOK_ID, chapter_order=order)
                    session.add(ch)
                # 防历史误挂：夹具章节必须归属夹具书并保持可读状态。
                ch.book_id = BOOK_ID
                ch.chapter_order = order
                ch.title = title
                ch.estimated_minutes = minutes
                ch.status = "PUBLISHED"

            existing_kps = {
                row[0]
                for row in (
                    await session.execute(
                        select(KnowledgePoint.knowledge_point_id).where(
                            KnowledgePoint.knowledge_point_id.in_([KP1_ID, KP2_ID])
                        )
                    )
                ).all()
            }
            if KP1_ID not in existing_kps:
                session.add(
                    KnowledgePoint(
                        knowledge_point_id=KP1_ID,
                        name="训练数据",
                        slug="training_data",
                        description="训练数据是一组用来帮助机器发现规律的例子。",
                        topic="AI 基础",
                    )
                )
            if KP2_ID not in existing_kps:
                session.add(
                    KnowledgePoint(
                        knowledge_point_id=KP2_ID,
                        name="标签",
                        slug="label",
                        description="我们希望机器学会的答案。",
                        topic="AI 基础",
                    )
                )

            block_specs = [
                (
                    BLK1_ID,
                    {
                        "block_type": "PARAGRAPH",
                        "content": {"text": "机器学习里的训练数据，就像反复展示的例子。"},
                        "block_order": 1,
                        "section_key": "训练数据 · 定义",
                        "knowledge_point_ids": [str(KP1_ID)],
                    },
                ),
                (
                    BLK2_ID,
                    {
                        "block_type": "KNOWLEDGE_CARD",
                        "content": {"title": "训练数据", "text": "例子越有代表性，机器判断越可靠。"},
                        "block_order": 2,
                        "section_key": "知识卡片 · 训练数据",
                        "knowledge_point_ids": [str(KP1_ID), str(KP2_ID)],
                    },
                ),
            ]
            for block_id, spec in block_specs:
                block = await session.get(ContentBlock, block_id)
                if block is None:
                    block = ContentBlock(block_id=block_id, chapter_id=CH2_ID)
                    session.add(block)
                block.chapter_id = CH2_ID
                block.block_type = spec["block_type"]
                block.content = spec["content"]
                block.block_order = spec["block_order"]
                block.section_key = spec["section_key"]
                block.knowledge_point_ids = spec["knowledge_point_ids"]

            await session.commit()

    asyncio.run(run())


def _ensure_user() -> None:
    async def run() -> None:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.username == "test_content_user"))
            user = result.scalar_one_or_none()
            if user is None:
                user = User(
                    username="test_content_user",
                    password_hash=hash_password("contentpass"),
                    user_type="STUDENT",
                )
                session.add(user)
                await session.flush()
                profile = StudentProfile(
                    user_id=user.user_id, nickname="内容测试", grade=8, language="zh-CN"
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
    _ensure_content()
    _ensure_user()
    return TestClient(app)


@pytest.fixture(scope="module")
def token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"username": "test_content_user", "password": "contentpass"}
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestContentAPI:
    def test_books_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/books")
        assert response.status_code == 401

    def test_list_books_only_published(self, client: TestClient, token: str) -> None:
        response = client.get("/api/v1/books?limit=100", headers=headers(token))
        assert response.status_code == 200
        body = response.json()["data"]
        assert all(book["status"] == "PUBLISHED" for book in body)
        assert any(book["book_id"] == str(BOOK_ID) for book in body)
        assert "meta" in response.json()
        assert "has_more" in response.json()["meta"]

    def test_get_book_with_chapter_count(self, client: TestClient, token: str) -> None:
        response = client.get(f"/api/v1/books/{BOOK_ID}", headers=headers(token))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["title"] == "AI 不是魔法"
        assert data["chapter_count"] == 2

    def test_get_book_not_found(self, client: TestClient, token: str) -> None:
        response = client.get(
            f"/api/v1/books/{UUID('b9999999-0000-0000-0000-000000000009')}",
            headers=headers(token),
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "BOOK_NOT_FOUND"

    def test_list_chapters_ordered(self, client: TestClient, token: str) -> None:
        response = client.get(f"/api/v1/books/{BOOK_ID}/chapters", headers=headers(token))
        assert response.status_code == 200
        chapters = response.json()["data"]
        assert [chapter["chapter_order"] for chapter in chapters] == [1, 2]

    def test_list_chapters_missing_book(self, client: TestClient, token: str) -> None:
        missing_book_id = UUID("b9999999-0000-0000-0000-000000000009")
        response = client.get(
            f"/api/v1/books/{missing_book_id}/chapters", headers=headers(token)
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "BOOK_NOT_FOUND"

    def test_chapter_detail_includes_blocks_and_knowledge_points(
        self, client: TestClient, token: str
    ) -> None:
        response = client.get(f"/api/v1/chapters/{CH2_ID}", headers=headers(token))
        assert response.status_code == 200
        data = response.json()["data"]
        assert [block["block_order"] for block in data["content_blocks"]] == [1, 2]
        names = {point["name"] for point in data["knowledge_points"]}
        assert names == {"训练数据", "标签"}

    def test_chapter_detail_missing_chapter(self, client: TestClient, token: str) -> None:
        missing_chapter_id = UUID("c9999999-0000-0000-0000-000000000009")
        response = client.get(
            f"/api/v1/chapters/{missing_chapter_id}", headers=headers(token)
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CHAPTER_NOT_FOUND"

    def test_knowledge_point_detail(self, client: TestClient, token: str) -> None:
        response = client.get(f"/api/v1/knowledge-points/{KP1_ID}", headers=headers(token))
        assert response.status_code == 200
        assert response.json()["data"]["slug"] == "training_data"

    def test_knowledge_point_missing(self, client: TestClient, token: str) -> None:
        missing_point_id = UUID("19999999-0000-0000-0000-000000000009")
        response = client.get(
            f"/api/v1/knowledge-points/{missing_point_id}", headers=headers(token)
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "KNOWLEDGE_POINT_NOT_FOUND"

    def test_grade_filter(self, client: TestClient, token: str) -> None:
        response = client.get("/api/v1/books?grade_min=10", headers=headers(token))
        assert response.status_code == 200
        assert all(book["grade_min"] >= 10 for book in response.json()["data"])

    def test_list_books_rejects_invalid_cursor(self, client: TestClient, token: str) -> None:
        response = client.get(
            "/api/v1/books?cursor=not-a-valid-cursor", headers=headers(token)
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
