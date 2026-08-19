"""Phase 4 Memory Domain API tests (real PostgreSQL + TestClient)."""

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.database.models import (
    MemoryEvidence,
    StudentMemory,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password


USER_NAME = "test_memory_user"
USER_PASSWORD = "memorypass"
OTHER_USER_NAME = "other_memory_user"
OTHER_USER_PASSWORD = "othermemorypass"


def _ensure_user(username: str, password: str, nickname: str) -> UUID:
    async def run() -> UUID:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.username == username))
            user = result.scalar_one_or_none()
            if user is None:
                user = User(
                    username=username,
                    password_hash=hash_password(password),
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
                    user_id=user.user_id,
                    nickname=nickname,
                    grade=8,
                    language="zh-CN",
                )
                session.add(profile)
                await session.flush()
            await session.commit()
            return profile.student_id

    return asyncio.run(run())


@pytest.fixture(scope="module")
def client() -> TestClient:
    _ensure_user(USER_NAME, USER_PASSWORD, "记忆测试")
    _ensure_user(OTHER_USER_NAME, OTHER_USER_PASSWORD, "其他记忆测试")
    return TestClient(app)


@pytest.fixture(scope="module")
def token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": USER_NAME, "password": USER_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


@pytest.fixture(scope="module")
def other_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": OTHER_USER_NAME, "password": OTHER_USER_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _insert_memory(
    username: str,
    *,
    content: str = "我喜欢通过例子学习",
    memory_type: str = "PREFERENCE",
    status: str = "ACTIVE",
) -> tuple[UUID, UUID]:
    async def run() -> tuple[UUID, UUID]:
        async with async_session() as session:
            user_result = await session.execute(
                select(User).where(User.username == username)
            )
            user = user_result.scalar_one()
            profile_result = await session.execute(
                select(StudentProfile).where(StudentProfile.user_id == user.user_id)
            )
            profile = profile_result.scalar_one()
            now = datetime.now(timezone.utc)
            evidence_id = uuid4()
            memory_id = uuid4()
            session.add(
                MemoryEvidence(
                    evidence_id=evidence_id,
                    student_id=profile.student_id,
                    source_type="CONVERSATION",
                    event_ids=[str(uuid4())],
                    payload={"fact": content},
                    count=1,
                    first_occurred_at=now,
                    last_occurred_at=now,
                    derived_at=now,
                    rule_version="test-v1",
                )
            )
            session.add(
                StudentMemory(
                    memory_id=memory_id,
                    student_id=profile.student_id,
                    memory_type=memory_type,
                    content=content,
                    tags=["例子"],
                    confidence="MEDIUM",
                    status=status,
                    evidence_ids=[str(evidence_id)],
                    user_confirmed=False,
                )
            )
            await session.commit()
            return memory_id, evidence_id

    return asyncio.run(run())


class TestMemoryAPI:
    def test_requires_auth_and_lists_active_with_type_filter(
        self, client: TestClient, token: str
    ) -> None:
        unauthenticated = client.get("/api/v1/me/memories")
        assert unauthenticated.status_code == 401
        assert unauthenticated.json()["error"]["code"] == "UNAUTHENTICATED"

        memory_id, _ = _insert_memory(USER_NAME, memory_type="LEARNING")
        response = client.get(
            "/api/v1/me/memories?memory_type=LEARNING", headers=headers(token)
        )
        assert response.status_code == 200
        rows = response.json()["data"]
        assert str(memory_id) in {row["memory_id"] for row in rows}
        assert all(row["memory_type"] == "LEARNING" for row in rows)

    def test_confirm_dispute_confirm_forget_and_reject_removed_transition(
        self, client: TestClient, token: str
    ) -> None:
        memory_id, _ = _insert_memory(USER_NAME)
        endpoint = f"/api/v1/me/memories/{memory_id}"

        confirmed = client.patch(
            endpoint, headers=headers(token), json={"action": "CONFIRM"}
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["data"]["status"] == "ACTIVE"
        assert confirmed.json()["data"]["user_confirmed"] is True
        assert confirmed.json()["data"]["confirmed_at"] is not None

        disputed = client.patch(
            endpoint, headers=headers(token), json={"action": "DISPUTE"}
        )
        assert disputed.status_code == 200
        assert disputed.json()["data"]["status"] == "DISPUTED"

        reconfirmed = client.patch(
            endpoint, headers=headers(token), json={"action": "CONFIRM"}
        )
        assert reconfirmed.status_code == 200
        assert reconfirmed.json()["data"]["status"] == "ACTIVE"

        forgotten = client.patch(
            endpoint, headers=headers(token), json={"action": "FORGET"}
        )
        assert forgotten.status_code == 200
        assert forgotten.json()["data"]["status"] == "REMOVED"

        invalid = client.patch(
            endpoint, headers=headers(token), json={"action": "CONFIRM"}
        )
        assert invalid.status_code == 409
        assert invalid.json()["error"]["code"] == "MEMORY_INVALID_TRANSITION"

    def test_edit_supersedes_old_memory_and_requires_content(
        self, client: TestClient, token: str
    ) -> None:
        memory_id, _ = _insert_memory(USER_NAME, content="旧的学习偏好")
        endpoint = f"/api/v1/me/memories/{memory_id}"

        missing_content = client.patch(
            endpoint, headers=headers(token), json={"action": "EDIT"}
        )
        assert missing_content.status_code == 422
        assert missing_content.json()["error"]["code"] == "VALIDATION_ERROR"

        edited = client.patch(
            endpoint,
            headers=headers(token),
            json={"action": "EDIT", "content": "更新后的学习偏好"},
        )
        assert edited.status_code == 200
        new_memory = edited.json()["data"]
        assert UUID(new_memory["memory_id"]) != memory_id
        assert new_memory["content"] == "更新后的学习偏好"
        assert new_memory["status"] == "ACTIVE"
        assert new_memory["user_confirmed"] is True

        old_rows = client.get(
            "/api/v1/me/memories?status=SUPERSEDED", headers=headers(token)
        )
        assert old_rows.status_code == 200
        old = next(row for row in old_rows.json()["data"] if row["memory_id"] == str(memory_id))
        assert old["status"] == "SUPERSEDED"

    def test_memory_and_evidence_are_owner_scoped(
        self,
        client: TestClient,
        token: str,
        other_token: str,
    ) -> None:
        memory_id, evidence_id = _insert_memory(USER_NAME)
        memory_endpoint = f"/api/v1/me/memories/{memory_id}"
        evidence_endpoint = f"/api/v1/me/evidence/{evidence_id}"

        forbidden_memory = client.patch(
            memory_endpoint,
            headers=headers(other_token),
            json={"action": "CONFIRM"},
        )
        assert forbidden_memory.status_code == 403
        assert forbidden_memory.json()["error"]["code"] == "FORBIDDEN"

        forbidden_evidence = client.get(evidence_endpoint, headers=headers(other_token))
        assert forbidden_evidence.status_code == 403
        assert forbidden_evidence.json()["error"]["code"] == "FORBIDDEN"

        evidence = client.get(evidence_endpoint, headers=headers(token))
        assert evidence.status_code == 200
        assert evidence.json()["data"]["evidence_id"] == str(evidence_id)
        assert evidence.json()["data"]["source_type"] == "CONVERSATION"
        assert evidence.json()["data"]["payload"]["fact"] == "我喜欢通过例子学习"

        missing = client.get(
            f"/api/v1/me/evidence/{uuid4()}", headers=headers(token)
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "EVIDENCE_NOT_FOUND"

    def test_invalid_action_and_memory_type_are_validation_errors(
        self, client: TestClient, token: str
    ) -> None:
        memory_id, _ = _insert_memory(USER_NAME)
        invalid_action = client.patch(
            f"/api/v1/me/memories/{memory_id}",
            headers=headers(token),
            json={"action": "MERGE"},
        )
        assert invalid_action.status_code == 422
        assert invalid_action.json()["error"]["code"] == "VALIDATION_ERROR"

        invalid_filter = client.get(
            "/api/v1/me/memories?memory_type=UNKNOWN", headers=headers(token)
        )
        assert invalid_filter.status_code == 422
        assert invalid_filter.json()["error"]["code"] == "VALIDATION_ERROR"
