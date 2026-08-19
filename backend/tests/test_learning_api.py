"""Phase 3 学习进度 API 测试（真实 DB；单一 ACTIVE 不变量 + 事件 append-only）。"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.infrastructure.database.models import (
    Book,
    BookProgress,
    Chapter,
    StudentPreference,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password

BOOK1_ID = UUID("b1000000-0000-0000-0000-000000000001")
BOOK2_ID = UUID("b2000000-0000-0000-0000-000000000001")
CH1_ID = UUID("c1000000-0000-0000-0000-000000000001")
CH2_ID = UUID("c2000000-0000-0000-0000-000000000001")


def _ensure_content() -> None:
    async def run() -> None:
        async with async_session() as session:
            if (await session.execute(select(Book).where(Book.book_id == BOOK1_ID))).scalar_one_or_none():
                return
            session.add(
                Book(
                    book_id=BOOK1_ID,
                    title="学习测试书一",
                    grade_min=7,
                    grade_max=9,
                    difficulty="MEDIUM",
                    estimated_minutes=60,
                    status="PUBLISHED",
                    published_at=datetime.now(timezone.utc),
                )
            )
            session.add(
                Book(
                    book_id=BOOK2_ID,
                    title="学习测试书二",
                    grade_min=7,
                    grade_max=9,
                    difficulty="MEDIUM",
                    estimated_minutes=60,
                    status="PUBLISHED",
                    published_at=datetime.now(timezone.utc),
                )
            )
            session.add(
                Chapter(
                    chapter_id=CH1_ID,
                    book_id=BOOK1_ID,
                    title="第一章",
                    chapter_order=1,
                    estimated_minutes=10,
                    status="PUBLISHED",
                )
            )
            session.add(
                Chapter(
                    chapter_id=CH2_ID,
                    book_id=BOOK2_ID,
                    title="第二章",
                    chapter_order=1,
                    estimated_minutes=10,
                    status="PUBLISHED",
                )
            )
            await session.commit()

    asyncio.run(run())


def _ensure_user() -> None:
    async def run() -> None:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.username == "test_learning_user"))
            user = result.scalar_one_or_none()
            if user is None:
                user = User(
                    username="test_learning_user",
                    password_hash=hash_password("learningpass"),
                    user_type="STUDENT",
                )
                session.add(user)
                await session.flush()
            profile_result = await session.execute(
                select(StudentProfile).where(StudentProfile.user_id == user.user_id)
            )
            profile = profile_result.scalar_one_or_none()
            if profile is None:
                profile = StudentProfile(
                    user_id=user.user_id, nickname="学习测试", grade=8, language="zh-CN"
                )
                session.add(profile)
                await session.flush()
            pref_result = await session.execute(
                select(StudentPreference).where(
                    StudentPreference.student_id == profile.student_id
                )
            )
            if pref_result.scalar_one_or_none() is None:
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
        "/api/v1/auth/login", json={"username": "test_learning_user", "password": "learningpass"}
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _clear_book_progress() -> None:
    async def run() -> None:
        async with async_session() as session:
            await session.execute(delete(BookProgress).where(BookProgress.book_id == BOOK1_ID))
            await session.commit()

    asyncio.run(run())


class TestLearningAPI:
    def test_requires_auth(self, client: TestClient) -> None:
        assert client.get("/api/v1/me/progress").status_code == 401

    def test_create_session_201(self, client: TestClient, token: str) -> None:
        response = client.post(
            "/api/v1/learning-sessions",
            headers=headers(token),
            json={"book_id": str(BOOK1_ID), "chapter_id": str(CH1_ID), "entry_route": "home"},
        )
        assert response.status_code == 201
        assert response.json()["data"]["status"] == "ACTIVE"

    def _assert_second_session_closes_old_active(self, client: TestClient, token: str) -> str:
        first = client.post(
            "/api/v1/learning-sessions",
            headers=headers(token),
            json={"book_id": str(BOOK1_ID), "chapter_id": str(CH1_ID)},
        ).json()["data"]
        second = client.post(
            "/api/v1/learning-sessions",
            headers=headers(token),
            json={"book_id": str(BOOK2_ID), "chapter_id": str(CH2_ID)},
        )
        assert second.status_code == 201
        assert second.json()["data"]["status"] == "ACTIVE"
        # 旧会话已被自动关闭：再 PATCH 应 409
        patch_old = client.patch(
            f"/api/v1/learning-sessions/{first['session_id']}",
            headers=headers(token),
            json={"status": "ENDED"},
        )
        assert patch_old.status_code == 409
        assert patch_old.json()["error"]["code"] == "LEARNING_SESSION_INVALID_STATUS"
        return second.json()["data"]["session_id"]

    def test_second_session_closes_old_active(self, client: TestClient, token: str) -> None:
        self._assert_second_session_closes_old_active(client, token)

    def test_patch_session_ends_with_duration(self, client: TestClient, token: str) -> None:
        session_id = self._assert_second_session_closes_old_active(client, token)
        response = client.patch(
            f"/api/v1/learning-sessions/{session_id}",
            headers=headers(token),
            json={"status": "ENDED"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "ENDED"
        assert data["duration_seconds"] >= 0
        assert data["ended_at"] is not None

    def test_chapter_must_belong_to_book(self, client: TestClient, token: str) -> None:
        response = client.post(
            "/api/v1/learning-sessions",
            headers=headers(token),
            json={"book_id": str(BOOK1_ID), "chapter_id": str(CH2_ID)},
        )
        assert response.status_code == 422

    def test_create_event_and_append_only(self, client: TestClient, token: str) -> None:
        response = client.post(
            "/api/v1/learning-events",
            headers=headers(token),
            json={
                "event_type": "TEXT_SELECTED",
                "occurred_at": "2026-08-19T08:00:00Z",
                "book_id": str(BOOK1_ID),
                "chapter_id": str(CH1_ID),
                "payload": {"selected_text": "训练数据"},
            },
        )
        assert response.status_code == 201
        assert response.json()["data"]["event_type"] == "TEXT_SELECTED"

    def test_create_event_invalid_type_422(self, client: TestClient, token: str) -> None:
        response = client.post(
            "/api/v1/learning-events",
            headers=headers(token),
            json={
                "event_type": "NOT_A_REAL_EVENT",
                "occurred_at": "2026-08-19T08:00:00Z",
                "payload": {},
            },
        )
        assert response.status_code == 422

    def test_get_progress_empty_list(self, client: TestClient, token: str) -> None:
        response = client.get("/api/v1/me/progress", headers=headers(token))
        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_get_book_progress_null_and_not_found(self, client: TestClient, token: str) -> None:
        existing = client.get(
            f"/api/v1/me/progress/{BOOK1_ID}", headers=headers(token)
        )
        assert existing.status_code == 200
        assert existing.json()["data"] is None
        missing = client.get(
            f"/api/v1/me/progress/{UUID('b9999999-0000-0000-0000-000000000009')}",
            headers=headers(token),
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "BOOK_NOT_FOUND"

    def test_upsert_progress_creates_with_defaults(self, client: TestClient, token: str) -> None:
        _clear_book_progress()
        response = client.put(
            f"/api/v1/me/progress/{BOOK1_ID}",
            headers=headers(token),
            json={"chapter_id": str(CH1_ID), "position_percent": 42},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["book_id"] == str(BOOK1_ID)
        assert data["chapter_id"] == str(CH1_ID)
        assert data["status"] == "READING"
        assert data["position_percent"] == 42
        assert data["last_read_at"] is not None

    def test_upsert_progress_updates_existing_row_partially(
        self, client: TestClient, token: str
    ) -> None:
        _clear_book_progress()
        created = client.put(
            f"/api/v1/me/progress/{BOOK1_ID}",
            headers=headers(token),
            json={"chapter_id": str(CH1_ID), "position_percent": 20},
        )
        assert created.status_code == 200
        progress_id = created.json()["data"]["progress_id"]

        updated = client.put(
            f"/api/v1/me/progress/{BOOK1_ID}",
            headers=headers(token),
            json={"status": "COMPLETED", "position_percent": 100},
        )
        assert updated.status_code == 200
        data = updated.json()["data"]
        assert data["progress_id"] == progress_id
        assert data["chapter_id"] == str(CH1_ID)
        assert data["status"] == "COMPLETED"
        assert data["position_percent"] == 100
        assert data["last_read_at"] is not None

    def test_upsert_progress_rejects_chapter_from_another_book(
        self, client: TestClient, token: str
    ) -> None:
        _clear_book_progress()
        response = client.put(
            f"/api/v1/me/progress/{BOOK1_ID}",
            headers=headers(token),
            json={"chapter_id": str(CH2_ID)},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    @pytest.mark.parametrize("position_percent", [-1, 101])
    def test_upsert_progress_rejects_position_out_of_range(
        self, client: TestClient, token: str, position_percent: int
    ) -> None:
        response = client.put(
            f"/api/v1/me/progress/{BOOK1_ID}",
            headers=headers(token),
            json={"position_percent": position_percent},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_upsert_progress_rejects_invalid_status(self, client: TestClient, token: str) -> None:
        response = client.put(
            f"/api/v1/me/progress/{BOOK1_ID}",
            headers=headers(token),
            json={"status": "PAUSED"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_upsert_progress_rejects_missing_book(self, client: TestClient, token: str) -> None:
        missing_book_id = UUID("b9999999-0000-0000-0000-000000000009")
        response = client.put(
            f"/api/v1/me/progress/{missing_book_id}",
            headers=headers(token),
            json={"position_percent": 10},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "BOOK_NOT_FOUND"

    def test_list_events_with_filter(self, client: TestClient, token: str) -> None:
        response = client.get("/api/v1/me/learning-events", headers=headers(token))
        assert response.status_code == 200
        body = response.json()
        assert any(item["event_type"] == "TEXT_SELECTED" for item in body["data"])
        assert "has_more" in body["meta"]
        filtered = client.get(
            "/api/v1/me/learning-events?event_type=TEXT_SELECTED", headers=headers(token)
        )
        assert all(item["event_type"] == "TEXT_SELECTED" for item in filtered.json()["data"])
