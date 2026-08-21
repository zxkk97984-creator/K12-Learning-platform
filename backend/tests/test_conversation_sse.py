"""Phase 4-B SSE conversation tests (real PostgreSQL + TestClient)."""

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.base import AIProvider
from app.infrastructure.database.models import ConversationSummary, Message, StudentProfile, User
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password
from app.modules.conversation.schemas import SendMessageRequest


OWNER_NAME = "test_conversation_sse_user"
OWNER_PASSWORD = "conversation-sse-pass"
OTHER_NAME = "other_conversation_sse_user"
OTHER_PASSWORD = "other-conversation-sse-pass"


def _ensure_user(username: str, password: str, nickname: str) -> None:
    async def run() -> None:
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    username=username,
                    password_hash=hash_password(password),
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
                        nickname=nickname,
                        grade=8,
                        language="zh-CN",
                    )
                )
            await session.commit()

    asyncio.run(run())


@pytest.fixture(scope="module")
def client() -> TestClient:
    _ensure_user(OWNER_NAME, OWNER_PASSWORD, "SSE 测试")
    _ensure_user(OTHER_NAME, OTHER_PASSWORD, "其他 SSE 测试")
    return TestClient(app)


@pytest.fixture(scope="module")
def token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": OWNER_NAME, "password": OWNER_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


@pytest.fixture(scope="module")
def other_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": OTHER_NAME, "password": OTHER_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def headers(token: str, **extra: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
        **extra,
    }


def create_conversation(client: TestClient, token: str) -> str:
    response = client.post(
        "/api/v1/conversations",
        headers=headers(token, **{"Idempotency-Key": f"conv-{uuid4()}"}),
        json={"title": "SSE 测试会话"},
    )
    assert response.status_code == 201
    return response.json()["data"]["conversation_id"]


def parse_sse(raw: str) -> list[dict]:
    events: list[dict] = []
    for frame in raw.split("\n\n"):
        if not frame.strip() or frame.lstrip().startswith(":"):
            continue
        event_name = None
        event_id = None
        data_lines: list[str] = []
        for line in frame.splitlines():
            if line.startswith("id: "):
                event_id = line[4:]
            elif line.startswith("event: "):
                event_name = line[7:]
            elif line.startswith("data: "):
                data_lines.append(line[6:])
        if event_name is not None:
            events.append(
                {
                    "id": event_id,
                    "event": event_name,
                    "data": json.loads("\n".join(data_lines)),
                }
            )
    return events


class FailingProvider(AIProvider):
    provider = "failing"
    model = "test-model"

    async def stream_chat(self, history, system_prompt):
        del history, system_prompt
        raise RuntimeError("simulated provider outage")
        if False:
            yield ""


class OneChunkProvider(AIProvider):
    provider = "heartbeat-test"
    model = "heartbeat-test-model"

    async def stream_chat(self, history, system_prompt):
        del history, system_prompt
        yield "心跳后内容"


class CapturingProvider(AIProvider):
    provider = "capturing"
    model = "capturing-model"

    def __init__(self) -> None:
        self.system_prompts: list[str] = []

    async def stream_chat(self, history, system_prompt):
        del history
        self.system_prompts.append(system_prompt)
        yield "上下文已收到"


def _insert_long_summary(conversation_id: UUID, summary: str) -> None:
    async def run() -> None:
        async with async_session() as session:
            session.add_all(
                [
                    Message(
                        conversation_id=conversation_id,
                        role="STUDENT" if index % 2 else "TEACHER",
                        type="TEXT",
                        content=f"长对话消息 {index}",
                        sequence=index,
                    )
                    for index in range(1, 21)
                ]
            )
            session.add(
                ConversationSummary(
                    conversation_id=conversation_id,
                    summary=summary,
                    token_count=len(summary),
                    summary_version=3,
                    source_message_ids=["source-1", "source-20"],
                    model_info={"provider": "rule", "model": "test-summary"},
                )
            )
            await session.commit()

    asyncio.run(run())


class EmptyProvider(AIProvider):
    provider = "empty"
    model = "empty-model"

    async def stream_chat(self, history, system_prompt):
        del history, system_prompt
        yield ""


class TestConversationSSE:
    def test_stream_order_and_message_persistence(
        self, client: TestClient, token: str
    ) -> None:
        conversation_id = create_conversation(client, token)
        response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
            json={
                "content": "什么是训练数据",
                "screen_context": {"route": "/reader", "page_type": "reader"},
                "selected_text": "训练数据",
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(response.text)
        names = [event["event"] for event in events]
        assert names[0] == "message.start"
        assert names[-2:] == ["text.done", "message.done"]
        assert names.count("text.delta") > 1
        assert set(names).issubset({"message.start", "text.delta", "text.done", "message.done"})

        start = events[0]["data"]
        text_done = next(event["data"] for event in events if event["event"] == "text.done")
        done = events[-1]["data"]
        assert start["conversation_id"] == conversation_id
        assert start["role"] == "TEACHER"
        assert start["sequence"] == 2
        assert text_done["model_info"]["provider"] == "mock"
        assert done["message_id"] == start["message_id"]
        assert done["sequence"] == 2

        messages = client.get(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
        )
        assert messages.status_code == 200
        rows = messages.json()["data"]
        assert [row["role"] for row in rows] == ["STUDENT", "TEACHER"]
        assert [row["sequence"] for row in rows] == [1, 2]
        assert rows[0]["content"] == "什么是训练数据"
        assert rows[0]["metadata"] == {}
        assert rows[1]["content"] == text_done["content"]
        assert rows[1]["model_info"]["model"] == "mock-model"

        detail = client.get(
            f"/api/v1/conversations/{conversation_id}", headers=headers(token)
        )
        assert detail.status_code == 200
        context = detail.json()["data"]["current_page_context"]
        assert context["route"] == "/reader"
        assert context["selected_text"] == "训练数据"

    def test_summary_is_injected_into_teacher_context(
        self,
        client: TestClient,
        token: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        conversation_id = create_conversation(client, token)
        summary = "学生已经掌握训练数据的定义，正在追问推荐系统的原因。"
        _insert_long_summary(UUID(conversation_id), summary)
        provider = CapturingProvider()

        async def no_retrieval(*args, **kwargs):
            del args, kwargs
            return []

        monkeypatch.setattr(
            "app.modules.conversation.service.get_ai_provider", lambda: provider
        )
        monkeypatch.setattr("app.modules.conversation.service.retrieve", no_retrieval)

        response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
            json={"content": "我还想继续追问"},
        )

        assert response.status_code == 200
        assert provider.system_prompts
        assert "【本会话长对话摘要（v3）】" in provider.system_prompts[0]
        assert summary in provider.system_prompts[0]

    def test_summary_is_not_injected_before_threshold(
        self,
        client: TestClient,
        token: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        conversation_id = create_conversation(client, token)
        provider = CapturingProvider()

        async def no_retrieval(*args, **kwargs):
            del args, kwargs
            return []

        monkeypatch.setattr(
            "app.modules.conversation.service.get_ai_provider", lambda: provider
        )
        monkeypatch.setattr("app.modules.conversation.service.retrieve", no_retrieval)

        response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
            json={"content": "新会话问题"},
        )

        assert response.status_code == 200
        assert provider.system_prompts
        assert "【本会话长对话摘要" not in provider.system_prompts[0]

    def test_quiz_intent_emits_tool_events_and_persists_quiz_session(
        self, client: TestClient, token: str
    ) -> None:
        conversation_id = create_conversation(client, token)
        response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
            json={"content": "给我出题"},
        )

        assert response.status_code == 200
        events = parse_sse(response.text)
        names = [event["event"] for event in events]
        assert names == [
            "message.start",
            "text.delta",
            "tool.start",
            "tool.result",
            "text.delta",
            "text.done",
            "message.done",
        ]

        start = events[0]["data"]
        tool_start = events[2]["data"]
        tool_result = events[3]["data"]
        text_done = events[5]["data"]
        assert tool_start["tool"] == "quiz"
        assert tool_start["state"] == "running"
        assert tool_start["message_id"] == start["message_id"]
        assert tool_start["payload"] == {"quiz_session_id": None}
        assert tool_result["tool_run_id"] == tool_start["tool_run_id"]
        assert tool_result["tool"] == "quiz"
        assert tool_result["status"] == "success"
        assert tool_result["payload"]["skill_version"] == "quiz-v1"
        quiz_session_id = tool_result["payload"]["quiz_session_id"]
        assert quiz_session_id
        assert "好的，我来出一道题" in text_done["content"]
        assert "题目已生成" in text_done["content"]

        detail = client.get(
            f"/api/v1/quiz-sessions/{quiz_session_id}",
            headers=headers(token),
        )
        assert detail.status_code == 200
        assert detail.json()["data"]["conversation_id"] == conversation_id
        assert detail.json()["data"]["status"] == "ACTIVE"

        messages = client.get(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
        )
        assert messages.status_code == 200
        rows = messages.json()["data"]
        assert [row["role"] for row in rows] == ["STUDENT", "TEACHER"]
        assert rows[1]["content"] == text_done["content"]

    def test_stream_requires_owner_and_active_conversation(
        self, client: TestClient, token: str, other_token: str
    ) -> None:
        conversation_id = create_conversation(client, token)
        forbidden = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(other_token),
            json={"content": "越权提问"},
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "FORBIDDEN"

        missing_id = UUID("00000000-0000-0000-0000-000000000098")
        missing = client.post(
            f"/api/v1/conversations/{missing_id}/messages",
            headers=headers(token),
            json={"content": "不存在的会话"},
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"

        deleted = client.patch(
            f"/api/v1/conversations/{conversation_id}",
            headers=headers(token),
            json={"status": "DELETED"},
        )
        assert deleted.status_code == 200
        invalid_status = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
            json={"content": "已删除会话"},
        )
        assert invalid_status.status_code == 409
        assert invalid_status.json()["error"]["code"] == "CONVERSATION_INVALID_STATUS"

    def test_stream_validation_and_authentication(
        self, client: TestClient, token: str
    ) -> None:
        conversation_id = create_conversation(client, token)

        no_auth = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"content": "没有令牌"},
        )
        assert no_auth.status_code == 401
        assert no_auth.json()["error"]["code"] == "UNAUTHENTICATED"

        invalid_type = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
            json={"content": "错误类型", "type": "QUIZ"},
        )
        assert invalid_type.status_code == 422
        assert invalid_type.json()["error"]["code"] == "VALIDATION_ERROR"

        empty_content = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
            json={"content": ""},
        )
        assert empty_content.status_code == 422
        assert empty_content.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_provider_failure_is_emitted_as_fatal_sse_error(
        self, client: TestClient, token: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conversation_id = create_conversation(client, token)
        monkeypatch.setattr(
            "app.modules.conversation.service.get_ai_provider",
            lambda: FailingProvider(),
        )

        response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
            json={"content": "触发 provider 错误"},
        )

        assert response.status_code == 200
        events = parse_sse(response.text)
        assert [event["event"] for event in events] == ["message.start", "error"]
        assert events[-1]["data"]["code"] == "AI_PROVIDER_ERROR"
        assert events[-1]["data"]["fatal"] is True

    def test_provider_failure_keeps_student_message_but_not_teacher_message(
        self, client: TestClient, token: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conversation_id = create_conversation(client, token)
        monkeypatch.setattr(
            "app.modules.conversation.service.get_ai_provider",
            lambda: FailingProvider(),
        )

        response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
            json={"content": "provider 失败后的落库检查"},
        )

        assert response.status_code == 200
        messages = client.get(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
        )
        assert messages.status_code == 200
        rows = messages.json()["data"]
        assert [(row["role"], row["content"]) for row in rows] == [
            ("STUDENT", "provider 失败后的落库检查")
        ]

    def test_empty_provider_response_is_not_persisted(
        self, client: TestClient, token: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conversation_id = create_conversation(client, token)
        monkeypatch.setattr(
            "app.modules.conversation.service.get_ai_provider",
            lambda: EmptyProvider(),
        )

        response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
            json={"content": "空回复保护"},
        )

        assert response.status_code == 200
        events = parse_sse(response.text)
        assert [event["event"] for event in events] == ["message.start", "error"]
        assert events[-1]["data"]["code"] == "AI_EMPTY_RESPONSE"
        rows = client.get(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(token),
        ).json()["data"]
        assert [(row["role"], row["content"]) for row in rows] == [
            ("STUDENT", "空回复保护")
        ]

    def test_provider_chunks_emits_heartbeat_without_waiting_fifteen_seconds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.modules.conversation import service as conversation_service_module

        real_wait_for = conversation_service_module.asyncio.wait_for
        timed_out = False

        async def wait_for_once(awaitable, timeout):
            nonlocal timed_out
            if timeout == 15 and not timed_out:
                timed_out = True
                awaitable.close()
                raise asyncio.TimeoutError
            return await real_wait_for(awaitable, timeout)

        monkeypatch.setattr(
            conversation_service_module.asyncio, "wait_for", wait_for_once
        )

        async def collect_chunks() -> list[str | None]:
            service = conversation_service_module.ConversationService()
            return [
                chunk
                async for chunk in service._provider_chunks(
                    OneChunkProvider(), [], ""
                )
            ]

        chunks = asyncio.run(collect_chunks())
        assert chunks == [None, "心跳后内容"]

    def test_concurrent_streams_for_one_conversation_are_serialized(self) -> None:
        from app.modules.conversation.service import ConversationService

        service = ConversationService()
        conversation_id = uuid4()
        active_streams = 0
        peak_streams = 0

        async def fake_send_message_locked(*args, **kwargs):
            del args, kwargs

            async def stream():
                nonlocal active_streams, peak_streams
                active_streams += 1
                peak_streams = max(peak_streams, active_streams)
                try:
                    yield "ok"
                    await asyncio.sleep(0.01)
                finally:
                    active_streams -= 1

            return stream()

        service._send_message_locked = fake_send_message_locked  # type: ignore[method-assign]

        async def collect(stream) -> list[str]:
            return [frame async for frame in stream]

        async def run() -> list[list[str]]:
            request = SendMessageRequest(content="并发测试")
            async def send_and_collect() -> list[str]:
                stream = await service.send_message(
                    uuid4(), uuid4(), conversation_id, request
                )
                return await collect(stream)

            return await asyncio.gather(send_and_collect(), send_and_collect())

        assert asyncio.run(run()) == [["ok"], ["ok"]]
        assert peak_streams == 1

    def test_redis_lock_is_released_after_stream_finishes(self, monkeypatch) -> None:
        from app.modules.conversation import service as conversation_module
        from app.modules.conversation.service import ConversationService

        service = ConversationService()
        conversation_id = uuid4()
        released: list[tuple[str, str]] = []

        async def fake_acquire(key: str, ttl: int) -> str:
            assert key == f"lock:conversation:{conversation_id}"
            assert ttl == 120
            return "redis-token"

        async def fake_release(key: str, token: str) -> bool:
            released.append((key, token))
            return True

        async def fake_send_message_locked(*args, **kwargs):
            del args, kwargs

            async def stream():
                yield "ok"

            return stream()

        monkeypatch.setattr(conversation_module, "acquire_lock", fake_acquire)
        monkeypatch.setattr(conversation_module, "release_lock", fake_release)
        service._send_message_locked = fake_send_message_locked  # type: ignore[method-assign]

        async def run() -> list[str]:
            stream = await service.send_message(
                uuid4(), uuid4(), conversation_id, SendMessageRequest(content="锁测试")
            )
            assert released == []
            return [frame async for frame in stream]

        assert asyncio.run(run()) == ["ok"]
        assert released == [(f"lock:conversation:{conversation_id}", "redis-token")]
