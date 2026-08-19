"""Phase 4 Conversation Domain API tests (real PostgreSQL + TestClient)."""

import asyncio
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.database.models import (
    ConversationSummary,
    Message,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password


USER_NAME = "test_conversation_user"
USER_PASSWORD = "conversationpass"
OTHER_USER_NAME = "other_conversation_user"
OTHER_USER_PASSWORD = "otherconversationpass"


def _ensure_user(username: str, password: str, nickname: str) -> None:
    async def run() -> None:
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
            if profile_result.scalar_one_or_none() is None:
                session.add(
                    StudentProfile(
                        user_id=user.user_id,
                        nickname=nickname,
                        grade=8,
                        language="zh-CN",
                    )
                )
            await session.commit()

    asyncio.run(run())


@pytest.fixture(scope="module")
def client() -> TestClient:
    _ensure_user(USER_NAME, USER_PASSWORD, "会话测试")
    _ensure_user(OTHER_USER_NAME, OTHER_USER_PASSWORD, "其他会话测试")
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


def headers(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


def create_conversation(
    client: TestClient, token: str, payload: dict | None = None
) -> dict:
    response = client.post(
        "/api/v1/conversations",
        headers=headers(token, **{"Idempotency-Key": f"conv-{uuid4()}"}),
        json=payload or {},
    )
    assert response.status_code == 201
    return response.json()["data"]


def _insert_messages_and_summary(conversation_id: UUID) -> None:
    async def run() -> None:
        async with async_session() as session:
            session.add_all(
                [
                    Message(
                        conversation_id=conversation_id,
                        role="STUDENT",
                        type="TEXT",
                        content="第一条消息",
                        metadata_={"source": "test"},
                        sequence=1,
                    ),
                    Message(
                        conversation_id=conversation_id,
                        role="TEACHER",
                        type="SYSTEM",
                        content="第二条消息",
                        sequence=2,
                    ),
                ]
            )
            session.add(
                ConversationSummary(
                    conversation_id=conversation_id,
                    summary="测试摘要",
                    token_count=3,
                    summary_version=1,
                    source_message_ids=[],
                )
            )
            await session.commit()

    asyncio.run(run())


class TestConversationAPI:
    def test_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/conversations")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    def test_create_defaults_and_detail(self, client: TestClient, token: str) -> None:
        conversation = create_conversation(client, token)

        assert conversation["status"] == "ACTIVE"
        assert conversation["channel"] == "TEXT"
        assert conversation["current_page_context"] == {}
        assert conversation["recent_messages"] == []
        assert conversation["conversation_summary"] is None

        detail = client.get(
            f"/api/v1/conversations/{conversation['conversation_id']}",
            headers=headers(token),
        )
        assert detail.status_code == 200
        assert detail.json()["data"]["conversation_id"] == conversation["conversation_id"]

    def test_create_conversation_requires_idempotency_key(
        self, client: TestClient, token: str
    ) -> None:
        response = client.post(
            "/api/v1/conversations",
            headers=headers(token),
            json={"title": "缺幂等键"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_create_conversation_idempotent_replay(
        self, client: TestClient, token: str
    ) -> None:
        idempotency_key = f"conv-{uuid4()}"
        first = client.post(
            "/api/v1/conversations",
            headers=headers(token, **{"Idempotency-Key": idempotency_key}),
            json={"title": "幂等会话"},
        )
        assert first.status_code == 201

        replay = client.post(
            "/api/v1/conversations",
            headers=headers(token, **{"Idempotency-Key": idempotency_key}),
            json={"title": "幂等会话"},
        )
        assert replay.status_code == 200
        assert replay.headers["Idempotency-Replayed"] == "true"
        assert (
            replay.json()["data"]["conversation_id"]
            == first.json()["data"]["conversation_id"]
        )

    def test_create_conversation_idempotency_conflict(
        self, client: TestClient, token: str
    ) -> None:
        idempotency_key = f"conv-{uuid4()}"
        first = client.post(
            "/api/v1/conversations",
            headers=headers(token, **{"Idempotency-Key": idempotency_key}),
            json={"title": "原请求"},
        )
        assert first.status_code == 201

        conflict = client.post(
            "/api/v1/conversations",
            headers=headers(token, **{"Idempotency-Key": idempotency_key}),
            json={"title": "不同请求"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    def test_create_voice_with_explicit_teacher_role(
        self, client: TestClient, token: str
    ) -> None:
        role_id = "00000000-0000-0000-0000-000000000001"
        conversation = create_conversation(
            client,
            token,
            {"teacher_role_id": role_id, "channel": "VOICE", "title": "语音会话"},
        )
        assert conversation["teacher_role_id"] == str(role_id)
        assert conversation["channel"] == "VOICE"
        assert conversation["title"] == "语音会话"

    def test_list_cursor_and_status_filter(
        self, client: TestClient, token: str
    ) -> None:
        first = create_conversation(client, token, {"title": "分页会话一"})
        second = create_conversation(client, token, {"title": "分页会话二"})

        page = client.get(
            "/api/v1/conversations?status=ACTIVE&limit=1",
            headers=headers(token),
        )
        assert page.status_code == 200
        assert len(page.json()["data"]) == 1
        assert page.json()["meta"]["has_more"] is True
        assert page.json()["meta"]["next_cursor"]

        next_page = client.get(
            "/api/v1/conversations",
            params={"status": "ACTIVE", "limit": 1, "cursor": page.json()["meta"]["next_cursor"]},
            headers=headers(token),
        )
        assert next_page.status_code == 200
        assert len(next_page.json()["data"]) == 1
        assert {first["conversation_id"], second["conversation_id"]}.intersection(
            {next_page.json()["data"][0]["conversation_id"]}
        )

        archived = client.patch(
            f"/api/v1/conversations/{first['conversation_id']}",
            headers=headers(token),
            json={"status": "ARCHIVED"},
        )
        assert archived.status_code == 200
        archived_page = client.get(
            "/api/v1/conversations?status=ARCHIVED",
            headers=headers(token),
        )
        assert archived_page.status_code == 200
        assert first["conversation_id"] in {
            row["conversation_id"] for row in archived_page.json()["data"]
        }

    def test_patch_soft_delete_and_reject_reactivation(
        self, client: TestClient, token: str
    ) -> None:
        conversation = create_conversation(client, token, {"title": "状态机"})
        conversation_id = conversation["conversation_id"]

        archived = client.patch(
            f"/api/v1/conversations/{conversation_id}",
            headers=headers(token),
            json={"title": "已归档", "status": "ARCHIVED"},
        )
        assert archived.status_code == 200
        assert archived.json()["data"]["status"] == "ARCHIVED"
        assert archived.json()["data"]["title"] == "已归档"

        deleted = client.patch(
            f"/api/v1/conversations/{conversation_id}",
            headers=headers(token),
            json={"status": "DELETED"},
        )
        assert deleted.status_code == 200
        assert deleted.json()["data"]["status"] == "DELETED"

        reactivated = client.patch(
            f"/api/v1/conversations/{conversation_id}",
            headers=headers(token),
            json={"status": "ACTIVE"},
        )
        assert reactivated.status_code == 409
        assert reactivated.json()["error"]["code"] == "CONVERSATION_INVALID_STATUS"

    def test_messages_and_summary_empty(self, client: TestClient, token: str) -> None:
        conversation = create_conversation(client, token)
        conversation_id = conversation["conversation_id"]

        messages = client.get(
            f"/api/v1/conversations/{conversation_id}/messages?sort=desc",
            headers=headers(token),
        )
        assert messages.status_code == 200
        assert messages.json()["data"] == []
        assert messages.json()["meta"] == {"next_cursor": None, "has_more": False}

        summary = client.get(
            f"/api/v1/conversations/{conversation_id}/summary",
            headers=headers(token),
        )
        assert summary.status_code == 200
        assert summary.json()["data"] is None

    def test_messages_pagination_and_summary_dto(
        self, client: TestClient, token: str
    ) -> None:
        conversation = create_conversation(client, token)
        conversation_id = UUID(conversation["conversation_id"])
        _insert_messages_and_summary(conversation_id)

        first_page = client.get(
            f"/api/v1/conversations/{conversation_id}/messages?limit=1&sort=asc",
            headers=headers(token),
        )
        assert first_page.status_code == 200
        assert first_page.json()["data"][0]["sequence"] == 1
        assert first_page.json()["data"][0]["metadata"] == {"source": "test"}
        assert first_page.json()["meta"]["has_more"] is True

        second_page = client.get(
            f"/api/v1/conversations/{conversation_id}/messages",
            params={
                "limit": 1,
                "sort": "asc",
                "cursor": first_page.json()["meta"]["next_cursor"],
            },
            headers=headers(token),
        )
        assert second_page.status_code == 200
        assert second_page.json()["data"][0]["sequence"] == 2
        assert second_page.json()["meta"]["has_more"] is False

        descending = client.get(
            f"/api/v1/conversations/{conversation_id}/messages?limit=1&sort=desc",
            headers=headers(token),
        )
        assert descending.status_code == 200
        assert descending.json()["data"][0]["sequence"] == 2

        summary = client.get(
            f"/api/v1/conversations/{conversation_id}/summary",
            headers=headers(token),
        )
        assert summary.status_code == 200
        assert summary.json()["data"]["summary"] == "测试摘要"
        assert summary.json()["data"]["token_count"] == 3

        detail = client.get(
            f"/api/v1/conversations/{conversation_id}", headers=headers(token)
        )
        assert detail.status_code == 200
        assert detail.json()["data"]["conversation_summary"] == "测试摘要"

    def test_only_owner_can_read_conversation(
        self, client: TestClient, token: str, other_token: str
    ) -> None:
        conversation = create_conversation(client, token)
        conversation_id = conversation["conversation_id"]

        for path in (
            f"/api/v1/conversations/{conversation_id}",
            f"/api/v1/conversations/{conversation_id}/messages",
            f"/api/v1/conversations/{conversation_id}/summary",
        ):
            response = client.get(path, headers=headers(other_token))
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "FORBIDDEN"

    def test_missing_conversation_returns_not_found(
        self, client: TestClient, token: str
    ) -> None:
        missing_id = UUID("00000000-0000-0000-0000-000000000099")
        response = client.get(
            f"/api/v1/conversations/{missing_id}", headers=headers(token)
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

    def test_patch_is_owner_scoped_and_missing_conversation_is_not_found(
        self,
        client: TestClient,
        token: str,
        other_token: str,
    ) -> None:
        conversation = create_conversation(client, token, {"title": "权限边界"})
        conversation_id = conversation["conversation_id"]

        forbidden = client.patch(
            f"/api/v1/conversations/{conversation_id}",
            headers=headers(other_token),
            json={"title": "越权修改"},
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "FORBIDDEN"

        missing = client.patch(
            f"/api/v1/conversations/{uuid4()}",
            headers=headers(token),
            json={"title": "不存在"},
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

    @pytest.mark.parametrize("suffix", ["/messages", "/summary"])
    def test_missing_nested_conversation_returns_not_found(
        self, client: TestClient, token: str, suffix: str
    ) -> None:
        response = client.get(
            f"/api/v1/conversations/{uuid4()}{suffix}", headers=headers(token)
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

    def test_patch_rejects_unknown_status_before_service_call(
        self, client: TestClient, token: str
    ) -> None:
        conversation = create_conversation(client, token)
        response = client.patch(
            f"/api/v1/conversations/{conversation['conversation_id']}",
            headers=headers(token),
            json={"status": "UNKNOWN"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_list_channel_filter_is_scoped_to_requested_channel(
        self, client: TestClient, token: str
    ) -> None:
        voice = create_conversation(client, token, {"channel": "VOICE"})
        response = client.get(
            "/api/v1/conversations?channel=VOICE", headers=headers(token)
        )
        assert response.status_code == 200
        rows = response.json()["data"]
        assert rows
        assert voice["conversation_id"] in {
            row["conversation_id"] for row in rows
        }
        assert {row["channel"] for row in rows} == {"VOICE"}

    @pytest.mark.parametrize(
        "query",
        [
            {"limit": 0},
            {"status": "UNKNOWN"},
            {"channel": "UNKNOWN"},
        ],
    )
    def test_list_rejects_invalid_query(
        self, client: TestClient, token: str, query: dict
    ) -> None:
        response = client.get(
            "/api/v1/conversations", params=query, headers=headers(token)
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
