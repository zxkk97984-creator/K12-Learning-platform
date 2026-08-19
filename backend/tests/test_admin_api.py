"""Phase 10 Admin API tests (admins + idempotency + books/content)."""

import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, select

from app.infrastructure.database.models import (
    Admin,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password


ADMIN_NAME = "test_admin_user"
ADMIN_PASSWORD = "adminpass"
STUDENT_NAME = "test_admin_student"
STUDENT_PASSWORD = "studentpass"


def _ensure_admin() -> UUID:
    async def run() -> UUID:
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.username == ADMIN_NAME))
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    username=ADMIN_NAME,
                    password_hash=hash_password(ADMIN_PASSWORD),
                    user_type="ADMIN",
                )
                session.add(user)
                await session.flush()
            admin = (
                await session.execute(
                    select(Admin).where(Admin.user_id == user.user_id)
                )
            ).scalar_one_or_none()
            if admin is None:
                admin = Admin(
                    user_id=user.user_id,
                    display_name="测试管理员",
                    role_level="SUPERVISOR",
                    enabled=True,
                )
                session.add(admin)
                await session.flush()
            await session.commit()
            return admin.admin_id

    return asyncio.run(run())


def _ensure_student() -> None:
    async def run() -> None:
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.username == STUDENT_NAME))
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    username=STUDENT_NAME,
                    password_hash=hash_password(STUDENT_PASSWORD),
                    user_type="STUDENT",
                )
                session.add(user)
                await session.flush()
            profile = (
                await session.execute(
                    select(StudentProfile).where(StudentProfile.user_id == user.user_id)
                )
            ).scalar_one_or_none()
            if profile is None:
                session.add(
                    StudentProfile(
                        user_id=user.user_id,
                        nickname="管理员测试学生",
                        grade=8,
                        language="zh-CN",
                    )
                )
            await session.commit()

    asyncio.run(run())


@pytest.fixture(scope="module")
def client() -> TestClient:
    _ensure_admin()
    _ensure_student()
    return TestClient(app)


@pytest.fixture(scope="module")
def admin_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": ADMIN_NAME, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


@pytest.fixture(scope="module")
def student_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": STUDENT_NAME, "password": STUDENT_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def headers(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


BOOK_BODY = {
    "title": f"管理端测试书-{uuid4()}",
    "grade_min": 7,
    "grade_max": 9,
    "difficulty": "MEDIUM",
    "estimated_minutes": 30,
    "tags": ["测试"],
}


class TestAdminAPI:
    def test_stats_returns_reasonable_counts(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.get("/api/v1/admin/stats", headers=headers(admin_token))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["books_total"] >= 0
        assert data["students_total"] >= 1

    def test_create_book_requires_idempotency_and_replays(
        self, client: TestClient, admin_token: str
    ) -> None:
        body = dict(BOOK_BODY, title=f"幂等测试书-{uuid4()}")
        missing = client.post(
            "/api/v1/admin/books",
            headers=headers(admin_token),
            json=body,
        )
        assert missing.status_code == 422

        key = f"book-{uuid4()}"
        created = client.post(
            "/api/v1/admin/books",
            headers=headers(admin_token, **{"Idempotency-Key": key}),
            json=body,
        )
        assert created.status_code == 201
        book_id = created.json()["data"]["book_id"]
        assert created.json()["data"]["created_by"]

        replay = client.post(
            "/api/v1/admin/books",
            headers=headers(admin_token, **{"Idempotency-Key": key}),
            json=body,
        )
        assert replay.status_code == 200
        assert replay.json()["data"]["book_id"] == book_id

        conflict = client.post(
            "/api/v1/admin/books",
            headers=headers(admin_token, **{"Idempotency-Key": key}),
            json=dict(body, title="不同标题"),
        )
        assert conflict.status_code == 409

    def test_publish_requires_chapter_and_content_crud(
        self, client: TestClient, admin_token: str
    ) -> None:
        created = client.post(
            "/api/v1/admin/books",
            headers=headers(admin_token, **{"Idempotency-Key": f"crud-{uuid4()}"}),
            json=dict(BOOK_BODY, title=f"发布测试书-{uuid4()}"),
        )
        assert created.status_code == 201
        book_id = created.json()["data"]["book_id"]

        invalid_publish = client.patch(
            f"/api/v1/admin/books/{book_id}",
            headers=headers(admin_token, **{"Idempotency-Key": f"pub-{uuid4()}"}),
            json={"status": "PUBLISHED"},
        )
        assert invalid_publish.status_code == 422

        chapter = client.post(
            f"/api/v1/admin/books/{book_id}/chapters",
            headers=headers(admin_token, **{"Idempotency-Key": f"ch-{uuid4()}"}),
            json={"title": "第一章"},
        )
        assert chapter.status_code == 201
        chapter_id = chapter.json()["data"]["chapter_id"]

        block = client.post(
            f"/api/v1/admin/chapters/{chapter_id}/content-blocks",
            headers=headers(admin_token, **{"Idempotency-Key": f"blk-{uuid4()}"}),
            json={
                "block_type": "PARAGRAPH",
                "content": {"text": "正文"},
            },
        )
        assert block.status_code == 201
        block_id = block.json()["data"]["block_id"]

        patched_block = client.patch(
            f"/api/v1/admin/content-blocks/{block_id}",
            headers=headers(admin_token, **{"Idempotency-Key": f"pblk-{uuid4()}"}),
            json={"content": {"text": "更新正文"}},
        )
        assert patched_block.status_code == 200

        published = client.patch(
            f"/api/v1/admin/books/{book_id}",
            headers=headers(admin_token, **{"Idempotency-Key": f"pub2-{uuid4()}"}),
            json={"status": "PUBLISHED"},
        )
        assert published.status_code == 200
        assert published.json()["data"]["status"] == "PUBLISHED"

        listed = client.get(
            "/api/v1/admin/books?status=PUBLISHED",
            headers=headers(admin_token),
        )
        assert any(row["book_id"] == book_id for row in listed.json()["data"])

    def test_knowledge_point_crud(
        self, client: TestClient, admin_token: str
    ) -> None:
        point = client.post(
            "/api/v1/admin/knowledge-points",
            headers=headers(admin_token, **{"Idempotency-Key": f"kp-{uuid4()}"}),
            json={"name": f"管理端知识点-{uuid4()}"},
        )
        assert point.status_code == 201
        point_id = point.json()["data"]["knowledge_point_id"]

        updated = client.patch(
            f"/api/v1/admin/knowledge-points/{point_id}",
            headers=headers(admin_token, **{"Idempotency-Key": f"pkp-{uuid4()}"}),
            json={"topic": "测试"},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["slug"]

    def test_admin_only_and_authentication(
        self,
        client: TestClient,
        student_token: str,
    ) -> None:
        forbidden = client.get(
            "/api/v1/admin/stats",
            headers=headers(student_token),
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "ADMIN_ONLY"

        assert client.get("/api/v1/admin/stats").status_code == 401

    def test_deferred_fks_are_present(self) -> None:
        async def run() -> set[str]:
            async with async_session() as session:
                rows = (
                    await session.execute(
                        text(
                            "SELECT conname FROM pg_constraint "
                            "WHERE conname IN "
                            "('fk_books_created_by_admin','fk_knowledge_resources_uploaded_by_admin')"
                        )
                    )
                ).scalars().all()
                return set(rows)

        constraints = asyncio.run(run())
        assert "fk_books_created_by_admin" in constraints
        assert "fk_knowledge_resources_uploaded_by_admin" in constraints
