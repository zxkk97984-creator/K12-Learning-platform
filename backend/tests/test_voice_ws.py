"""Phase 9 voice WebSocket tests (mock ASR/TTS + real conversation)."""

import asyncio
import base64
import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai.voice import MockASR, MockTTS
from app.infrastructure.database.models import StudentProfile, User
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password
from app.modules.voice import ws as voice_ws_module


OWNER_NAME = "test_voice_owner"
OWNER_PASSWORD = "voiceowner"
OTHER_NAME = "test_voice_other"
OTHER_PASSWORD = "voiceother"


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
    _ensure_user(OWNER_NAME, OWNER_PASSWORD, "语音测试")
    _ensure_user(OTHER_NAME, OTHER_PASSWORD, "其他语音测试")
    return TestClient(app)


@pytest.fixture(scope="module")
def owner_token(client: TestClient) -> str:
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
    return {"Authorization": f"Bearer {token}", **extra}


def create_conversation(client: TestClient, token: str) -> str:
    response = client.post(
        "/api/v1/conversations",
        headers=headers(token, **{"Idempotency-Key": f"conv-{uuid4()}"}),
        json={"title": "语音测试会话"},
    )
    assert response.status_code == 201
    return response.json()["data"]["conversation_id"]


def test_mock_asr_tts_are_deterministic() -> None:
    audio = b"\x00\x01\x02" * 10
    assert MockASR().transcribe(audio) == "这里是什么意思"
    wav = MockTTS().synthesize("你好")
    assert wav.startswith(b"RIFF")
    assert wav.endswith(b"WAVE") or len(wav) > 1000
    assert MockTTS().synthesize("你好") == wav


def test_voice_ws_full_flow(
    client: TestClient,
    owner_token: str,
) -> None:
    conversation_id = create_conversation(client, owner_token)
    audio = base64.b64encode(b"\x00\x01" * 400).decode("ascii")

    with client.websocket_connect(
        f"/api/v1/voice/ws?conversation_id={conversation_id}&token={owner_token}"
    ) as websocket:
        initial = json.loads(websocket.receive_text())
        assert initial == {"type": "state", "state": "IDLE"}

        websocket.send_text(json.dumps({"type": "audio_chunk", "data": audio}))
        listening = json.loads(websocket.receive_text())
        assert listening == {"type": "state", "state": "LISTENING"}

        websocket.send_text(json.dumps({"type": "audio_end"}))
        frames = [json.loads(websocket.receive_text()) for _ in range(7)]
        states = [frame["state"] for frame in frames if frame["type"] == "state"]
        assert states[:2] == ["THINKING", "SPEAKING"]
        assert states[-1] == "IDLE"
        assert any(
            frame["type"] == "partial" and frame["text"] == "这里是什么意思"
            for frame in frames
        )
        final = next(frame for frame in frames if frame["type"] == "final")
        assert final["text"] == "这里是什么意思"
        assert final["conversation_id"] == conversation_id
        reply = next(frame for frame in frames if frame["type"] == "reply")
        assert reply["text"]
        assert reply["conversation_id"] == conversation_id
        audio_frame = next(frame for frame in frames if frame["type"] == "audio")
        assert base64.b64decode(audio_frame["data"]).startswith(b"RIFF")

        websocket.send_text(json.dumps({"type": "ping"}))
        assert json.loads(websocket.receive_text()) == {"type": "pong"}

    messages = client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers(owner_token),
    )
    rows = messages.json()["data"]
    assert rows[0]["role"] == "STUDENT"
    assert rows[0]["content"] == "这里是什么意思"
    assert rows[-1]["role"] == "TEACHER"
    assert rows[-1]["content"]


def test_voice_ws_requires_token(
    client: TestClient,
    owner_token: str,
) -> None:
    conversation_id = create_conversation(client, owner_token)
    with client.websocket_connect(
        f"/api/v1/voice/ws?conversation_id={conversation_id}"
    ) as websocket:
        frame = json.loads(websocket.receive_text())
        assert frame["type"] == "error"
        assert frame["code"] == "UNAUTHENTICATED"


def test_voice_ws_rejects_foreign_conversation(
    client: TestClient,
    owner_token: str,
    other_token: str,
) -> None:
    conversation_id = create_conversation(client, owner_token)
    with client.websocket_connect(
        f"/api/v1/voice/ws?conversation_id={conversation_id}&token={other_token}"
    ) as websocket:
        frame = json.loads(websocket.receive_text())
        assert frame["type"] == "error"
        assert frame["code"] == "FORBIDDEN"


def test_voice_ws_barge_in_returns_to_listening(
    client: TestClient,
    owner_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def slow_send_message(*_args, **_kwargs):
        async def stream():
            yield "event: text.done\ndata: {\"content\":\"好的，我明白了。\"}\n\n"
            await asyncio.sleep(0.3)

        return stream()

    monkeypatch.setattr(
        voice_ws_module.conversation_service,
        "send_message",
        slow_send_message,
    )
    conversation_id = create_conversation(client, owner_token)
    audio = base64.b64encode(b"\x00\x01" * 100).decode("ascii")

    with client.websocket_connect(
        f"/api/v1/voice/ws?conversation_id={conversation_id}&token={owner_token}"
    ) as websocket:
        assert json.loads(websocket.receive_text()) == {
            "type": "state",
            "state": "IDLE",
        }
        websocket.send_text(json.dumps({"type": "audio_chunk", "data": audio}))
        assert json.loads(websocket.receive_text()) == {
            "type": "state",
            "state": "LISTENING",
        }
        websocket.send_text(json.dumps({"type": "audio_end"}))
        assert json.loads(websocket.receive_text()) == {
            "type": "state",
            "state": "THINKING",
        }

        websocket.send_text(json.dumps({"type": "audio_chunk", "data": audio}))
        while True:
            frame = json.loads(websocket.receive_text())
            if frame["type"] == "state" and frame["state"] == "LISTENING":
                break
            assert frame["type"] in {"partial", "final"}
