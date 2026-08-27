import base64
import json
"""Phase 4 验收测试：存储抽象、SigV4、TTS 明确降级、对话详情富化。"""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.infrastructure.database.models import (
    Conversation,
    Message,
    StudentProfile,
    TeacherRole,
    User,
)
from app.infrastructure.storage import get_storage
from app.infrastructure.storage.base import (
    StoredObject,
    StorageConfigError,
    StorageError,
)
from app.infrastructure.storage.local import LocalObjectStorage
from app.infrastructure.storage.s3 import sign_request
from app.infrastructure.database.session import async_session
from app.main import app


class TestStorageAbstraction:
    def test_local_roundtrip_and_traversal_guard(self, tmp_path):
        storage = LocalObjectStorage(root=tmp_path / "root")
        key = "knowledge/owner-1/a.md"
        asyncio.run(storage.put(key, "hello".encode(), content_type="text/markdown"))
        stored = asyncio.run(storage.get(key))
        assert isinstance(stored, StoredObject)
        assert stored.data == b"hello"
        assert asyncio.run(storage.exists(key)) is True

        for bad in ("../escape.md", "a/../../b", ".hidden"):
            with pytest.raises(StorageError):
                asyncio.run(storage.put(bad, b"x"))
        # 绝对路径前缀被剥离后成为普通相对键（合法）
        asyncio.run(storage.put("/abs/path", b"y"))

        with pytest.raises(StorageError):
            asyncio.run(storage.get("missing/object.txt"))

        # 物理隔离：文件确实落在 root 下
        assert (tmp_path / "root" / "knowledge" / "owner-1" / "a.md").is_file()

    def test_s3_config_error_is_explicit(self, monkeypatch: pytest.MonkeyPatch):
        from app.infrastructure.storage.s3 import S3ObjectStorage

        monkeypatch.setattr(settings, "s3_endpoint", "")
        monkeypatch.setattr(settings, "s3_bucket", "")
        monkeypatch.setattr(settings, "s3_access_key", "")
        monkeypatch.setattr(settings, "s3_secret_key", "")
        with pytest.raises(StorageConfigError) as exc:
            S3ObjectStorage()
        assert "S3_ENDPOINT" in str(exc.value)

    def test_sigv4_signature_is_deterministic(self, monkeypatch: pytest.MonkeyPatch):
        """固定输入 → 固定签名（同一输入两次计算必须一致；且随负载变化）。"""
        monkeypatch.setattr(settings, "__dict__", settings.__dict__)  # no-op guard
        common = dict(
            method="PUT",
            url="https://minio.local:9000/bucket/knowledge/x.md",
            region="us-east-1",
            access_key="AKIDEXAMPLE",
            secret_key="secret",
            payload_hash="payload-hash-1",
            now=datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc),
        )
        h1 = sign_request(**common)
        h2 = sign_request(**common)
        assert h1 == h2
        assert h1["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/")
        assert "x-amz-date" in h1

        changed = sign_request(**{**common, "payload_hash": "payload-hash-2"})
        assert changed["Authorization"] != h1["Authorization"]

    def test_factory_uses_configured_backend(self, monkeypatch: pytest.MonkeyPatch, tmp_path):
        monkeypatch.setattr(settings, "storage_backend", "local")
        monkeypatch.setattr(settings, "storage_local_root", str(tmp_path))
        get_storage.cache_clear()
        try:
            storage = get_storage()
            assert isinstance(storage, LocalObjectStorage)
        finally:
            get_storage.cache_clear()


class TestConversationDetailEnrichment:
    @pytest.fixture(scope="class")
    def env(self):
        username = f"p4_conv_{uuid4().hex[:6]}"
        password = "p4-pass"

        async def seed():
            async with async_session() as session:
                user = User(
                    username=username,
                    password_hash=__import__(
                        "app.modules.identity.security", fromlist=["hash_password"]
                    ).hash_password(password),
                    user_type="STUDENT",
                )
                session.add(user)
                await session.flush()
                profile = StudentProfile(
                    user_id=user.user_id, nickname="P4 会话", grade=8
                )
                session.add(profile)
                await session.flush()
                role_id = uuid4()
                await session.flush()
                session.add(
                    TeacherRole(
                        role_id=role_id,
                        name=f"风格-{username}",
                        tone="温和",
                        teaching_style="启发式",
                        persona={"base_persona": "测试"},
                        sprite_manifest={},
                        grade_rules={},
                        enabled=True,
                        version=1,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.flush()  # 先落 teacher_role，避免无 relationship 时插入顺序歧义
                conv = Conversation(
                    student_id=profile.student_id,
                    teacher_role_id=role_id,
                    title="P4 详情测试",
                    channel="TEXT",
                    status="ACTIVE",
                    current_page_context={},
                    recent_messages=[],
                )
                session.add(conv)
                await session.flush()
                for seq, text in enumerate(["第一条", "第二条"], start=1):
                    session.add(
                        Message(
                            conversation_id=conv.conversation_id,
                            role="TEACHER" if seq % 2 == 0 else "STUDENT",
                            type="TEXT",
                            content=text,
                            metadata_={},
                            sequence=seq,
                            created_at=datetime.now(timezone.utc),
                        )
                    )
                await session.commit()
                return str(conv.conversation_id)

        conversation_id = asyncio.run(seed())
        client = TestClient(app)
        token = client.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        ).json()["data"]["access_token"]
        return client, token, conversation_id

    def test_detail_contains_real_role_and_recent_messages(self, env):
        client, token, conversation_id = env
        resp = client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["teacher_role"] is not None
        assert data["teacher_role"]["name"].startswith("风格-")
        assert len(data["recent_messages"]) >= 2
        contents = [m["content"] for m in data["recent_messages"]]
        assert "第一条" in contents and "第二条" in contents

    def test_list_contains_role_summary_and_preview(self, env):
        client, token, conversation_id = env
        resp = client.get(
            "/api/v1/conversations",
            params={"status": "ACTIVE"},
            headers={"Authorization": f"Bearer {token}"},
        )
        items = resp.json()["data"]
        match = next(item for item in items if item["conversation_id"] == conversation_id)
        assert match["teacher_role"] and match["teacher_role"]["tone"] == "温和"
        assert match["last_message_preview"] in ("第二条", "第一条")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


class TestTTSUnavailablePath:
    def test_missing_tts_returns_error_frame_but_keeps_text_reply(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """TTS 未配置：明确 TTS_UNAVAILABLE 错误帧 + 文字回复仍可达。"""
        from app.ai.voice import MockASR

        username = f"p4_tts_{uuid4().hex[:6]}"

        async def seed():
            async with async_session() as session:
                user = User(
                    username=username,
                    password_hash=__import__(
                        "app.modules.identity.security", fromlist=["hash_password"]
                    ).hash_password("p4-tts"),
                    user_type="STUDENT",
                )
                session.add(user)
                await session.flush()
                profile = StudentProfile(user_id=user.user_id, nickname="TTS", grade=7)
                session.add(profile)
                await session.flush()
                conv = Conversation(
                    student_id=profile.student_id,
                    title="tts",
                    channel="VOICE",
                    status="ACTIVE",
                    current_page_context={},
                    recent_messages=[],
                )
                session.add(conv)
                await session.commit()
                return str(conv.conversation_id)

        conversation_id = asyncio.run(seed())

        def fake_transcribe(self, _audio):  # noqa: ANN001
            return "你好"

        monkeypatch.setattr(MockASR, "transcribe", fake_transcribe)
        monkeypatch.setattr(settings, "voice_provider", "mock")

        # 关键：TTS 指向 none（未配置真实供应商）
        monkeypatch.setattr(settings, "tts_provider", "none")

        token = client.post(
            "/api/v1/auth/login", json={"username": username, "password": "p4-tts"}
        ).json()["data"]["access_token"]

        audio = base64_audio()
        with client.websocket_connect(
            f"/api/v1/voice/ws?conversation_id={conversation_id}&token={token}"
        ) as websocket:
            json.loads(websocket.receive_text())  # initial state
            websocket.send_text(json.dumps({"type": "audio_chunk", "data": audio}))
            json.loads(websocket.receive_text())  # LISTENING
            websocket.send_text(json.dumps({"type": "audio_end"}))
            # THINKING / partial / final / reply / error(TTS_UNAVAILABLE) / IDLE
            frames = [json.loads(websocket.receive_text()) for _ in range(6)]
            types = [f.get("type") for f in frames]
            assert "reply" in types, "文字回复必须先送达"
            errors = [f for f in frames if f.get("type") == "error"]
            assert errors and errors[0]["code"] == "TTS_UNAVAILABLE"
            assert "audio" not in types, "不得再返回静音假音频"


def base64_audio() -> str:
    import base64

    return base64.b64encode(b"\x00\x00" * 160).decode("ascii")
