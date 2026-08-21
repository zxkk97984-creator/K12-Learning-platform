import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.database.models import Book, BookProgress, StudentProfile, User
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password


RUN_ID = uuid4().hex[:10]
STUDENT_NAME = f"recommendation_student_{RUN_ID}"
EMPTY_STUDENT_NAME = f"recommendation_empty_{RUN_ID}"
ADMIN_NAME = f"recommendation_admin_{RUN_ID}"
PASSWORD = "recommendationpass"


async def _create_user(username: str, user_type: str, nickname: str) -> tuple[UUID, UUID | None]:
    async with async_session() as session:
        user = User(
            username=username,
            password_hash=hash_password(PASSWORD),
            user_type=user_type,
        )
        session.add(user)
        await session.flush()
        student_id: UUID | None = None
        if user_type == "STUDENT":
            profile = StudentProfile(
                user_id=user.user_id,
                nickname=nickname,
                grade=8,
                language="zh-CN",
            )
            session.add(profile)
            await session.flush()
            student_id = profile.student_id
        await session.commit()
        return user.user_id, student_id


async def _create_reading_progress(student_id: UUID) -> UUID:
    async with async_session() as session:
        book = Book(
            title=f"推荐测试书 {RUN_ID}",
            description="用于验证规则推荐。",
            grade_min=7,
            grade_max=9,
            difficulty="MEDIUM",
            estimated_minutes=45,
            tags=["推荐测试"],
            status="PUBLISHED",
            published_at=datetime.now(timezone.utc),
        )
        session.add(book)
        await session.flush()
        session.add(
            BookProgress(
                student_id=student_id,
                book_id=book.book_id,
                status="READING",
                position_percent=35,
                last_read_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
        return book.book_id


@pytest.fixture(scope="module")
def client() -> TestClient:
    asyncio.run(_create_user(STUDENT_NAME, "STUDENT", "推荐学生"))
    asyncio.run(_create_user(EMPTY_STUDENT_NAME, "STUDENT", "空推荐学生"))
    asyncio.run(_create_user(ADMIN_NAME, "ADMIN", "推荐管理员"))
    return TestClient(app)


def _login(client: TestClient, username: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


@pytest.fixture(scope="module")
def student_token(client: TestClient) -> str:
    return _login(client, STUDENT_NAME)


@pytest.fixture(scope="module")
def empty_student_token(client: TestClient) -> str:
    return _login(client, EMPTY_STUDENT_NAME)


@pytest.fixture(scope="module")
def admin_token(client: TestClient) -> str:
    return _login(client, ADMIN_NAME)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_recommendations_return_rule_output_and_evidence(
    client: TestClient, student_token: str
) -> None:
    async def add_progress() -> None:
        async with async_session() as session:
            profile = (
                await session.execute(
                    select(StudentProfile).join(User).where(User.username == STUDENT_NAME)
                )
            ).scalar_one()
        await _create_reading_progress(profile.student_id)

    asyncio.run(add_progress())
    response = client.get("/api/v1/me/recommendations", headers=_headers(student_token))

    assert response.status_code == 200
    rows = response.json()["data"]
    continue_rows = [row for row in rows if row["recommendation_type"] == "CONTINUE_READING"]
    assert continue_rows
    assert continue_rows[0]["reason"]
    assert continue_rows[0]["evidence_ids"]
    assert continue_rows[0]["related_book_id"]


def test_recommendations_return_empty_array_when_no_rule_matches(
    client: TestClient, empty_student_token: str
) -> None:
    response = client.get(
        "/api/v1/me/recommendations", headers=_headers(empty_student_token)
    )

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_recommendations_require_student_role(client: TestClient, admin_token: str) -> None:
    response = client.get("/api/v1/me/recommendations", headers=_headers(admin_token))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_dismissed_recommendation_is_not_returned_again(
    client: TestClient, student_token: str
) -> None:
    listed = client.get("/api/v1/me/recommendations", headers=_headers(student_token))
    recommendation_id = listed.json()["data"][0]["recommendation_id"]

    dismissed = client.post(
        f"/api/v1/me/recommendations/{recommendation_id}/dismiss",
        headers=_headers(student_token),
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["data"]["status"] == "DISMISSED"

    refreshed = client.get("/api/v1/me/recommendations", headers=_headers(student_token))
    assert refreshed.json()["data"] == []
