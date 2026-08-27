import asyncio

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.scripts.seed import seed


def _ensure_seed_profile_grade8() -> None:
    async def run() -> None:
        from sqlalchemy import select

        from app.infrastructure.database.models import StudentProfile, User
        from app.infrastructure.database.session import async_session

        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.username == "xiaoming"))
            ).scalar_one_or_none()
            if user is None:
                return
            profile = (
                await session.execute(
                    select(StudentProfile).where(StudentProfile.user_id == user.user_id)
                )
            ).scalar_one_or_none()
            if profile is not None:
                profile.grade = 8
                await session.commit()

    asyncio.run(run())


@pytest.fixture(scope="module")
def client() -> TestClient:
    asyncio.run(seed())
    _ensure_seed_profile_grade8()
    return TestClient(app)


def login(client: TestClient, username: str = "xiaoming", password: str = "demo123"):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_login_returns_auth_dto(client: TestClient) -> None:
    response = login(client)
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["token_type"] == "Bearer"
    assert body["user"]["username"] == "xiaoming"
    assert body["user"]["user_type"] == "STUDENT"


def test_login_wrong_password_401(client: TestClient) -> None:
    response = login(client, password="wrong")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_requires_token(client: TestClient) -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_me_returns_stage_junior(client: TestClient) -> None:
    token = login(client).json()["data"]["access_token"]
    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["nickname"] == "小明"
    assert data["grade"] == 8
    assert data["stage"] == "JUNIOR"


def test_patch_me_grade_out_of_range_422(client: TestClient) -> None:
    token = login(client).json()["data"]["access_token"]
    response = client.patch(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"grade": 13},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
