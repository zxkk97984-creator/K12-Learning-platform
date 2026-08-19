"""Phase 7 .agent.md rendering and evidence-citation reply tests."""

import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.database.models import (
    MemoryEvidence,
    ProfileInsight,
    StudentEpisode,
    StudentMemory,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password
from app.modules.memory.agent_md import is_evidence_question


USER_NAME = "test_agent_md_user"
USER_PASSWORD = "agentmdpass"
EMPTY_USER_NAME = "test_agent_md_empty"
EMPTY_USER_PASSWORD = "agentmdempty"


def _ensure_user(username: str, password: str, nickname: str) -> UUID:
    async def run() -> UUID:
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


def _insert_material(student_id: UUID) -> UUID:
    async def run() -> UUID:
        async with async_session() as session:
            now = datetime.now(timezone.utc)
            evidence_id = uuid4()
            session.add(
                MemoryEvidence(
                    evidence_id=evidence_id,
                    student_id=student_id,
                    source_type="CONVERSATION",
                    event_ids=[str(uuid4())],
                    payload={"explain_requested_count": 2, "dimension": "conversation_requests"},
                    count=2,
                    first_occurred_at=now,
                    last_occurred_at=now,
                    derived_at=now,
                    rule_version="memory-rule-v1",
                )
            )
            insight_id = uuid4()
            session.add(
                ProfileInsight(
                    insight_id=insight_id,
                    student_id=student_id,
                    insight_type="INTEREST",
                    dimension="example_learning",
                    level="较稳定",
                    description="多次主动请求解释，喜欢借助具体讲解理解概念。",
                    evidence_ids=[str(evidence_id)],
                    status="ACTIVE",
                    valid_from=now,
                    valid_until=None,
                    rule_version="profile-rule-v1",
                    model_info={"provider": "rule", "model": "profile-rule-v1"},
                )
            )
            session.add(
                StudentMemory(
                    memory_id=uuid4(),
                    student_id=student_id,
                    memory_type="PREFERENCE",
                    content="喜欢通过主动提问和讲解来理解内容",
                    tags=["例子"],
                    confidence="MEDIUM",
                    status="ACTIVE",
                    evidence_ids=[str(evidence_id)],
                    user_confirmed=False,
                )
            )
            session.add(
                StudentEpisode(
                    episode_id=uuid4(),
                    student_id=student_id,
                    title="主动向霜铃提问",
                    summary="多次主动请求解释当前内容。",
                    occurred_at=now,
                    event_ids=[str(uuid4())],
                    importance="MEDIUM",
                    tags=["conversation"],
                )
            )
            await session.commit()
            return evidence_id

    return asyncio.run(run())


@pytest.fixture(scope="module")
def client() -> TestClient:
    _ensure_user(USER_NAME, USER_PASSWORD, "AgentMD 测试")
    _ensure_user(EMPTY_USER_NAME, EMPTY_USER_PASSWORD, "空证据测试")
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
def empty_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": EMPTY_USER_NAME, "password": EMPTY_USER_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def parse_sse(raw: str) -> list[dict]:
    events: list[dict] = []
    for frame in raw.split("\n\n"):
        if not frame.strip() or frame.lstrip().startswith(":"):
            continue
        event_name = None
        data_lines: list[str] = []
        for line in frame.splitlines():
            if line.startswith("event: "):
                event_name = line[7:]
            elif line.startswith("data: "):
                data_lines.append(line[6:])
        if event_name is not None:
            events.append({"event": event_name, "data": json.loads("\n".join(data_lines))})
    return events


def create_conversation(client: TestClient, token: str) -> str:
    response = client.post(
        "/api/v1/conversations",
        headers=headers(token),
        json={"title": "证据引用测试"},
    )
    assert response.status_code == 201
    return response.json()["data"]["conversation_id"]


def test_evidence_question_intent_matcher() -> None:
    assert is_evidence_question("为什么你觉得我比较喜欢通过例子学习？")
    assert is_evidence_question("为什么你认为我擅长数学")
    assert not is_evidence_question("给我出题")
    assert not is_evidence_question("为什么出错")


def test_agent_md_endpoint_renders_view_with_evidence(
    client: TestClient, token: str
) -> None:
    student_id = _ensure_user(USER_NAME, USER_PASSWORD, "AgentMD 测试")
    _insert_material(student_id)

    response = client.get("/api/v1/me/agent.md", headers=headers(token))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "渲染视图，不是数据事实源" in response.text
    assert "## AI 学习画像" in response.text
    assert "较稳定" in response.text
    assert "证据：" in response.text
    assert "## 稳定记忆" in response.text
    assert "## 学习情节" in response.text


def test_evidence_question_returns_cited_reply(
    client: TestClient, token: str
) -> None:
    student_id = _ensure_user(USER_NAME, USER_PASSWORD, "AgentMD 测试")
    evidence_id = _insert_material(student_id)
    conversation_id = create_conversation(client, token)

    response = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers(token),
        json={"content": "为什么你觉得我比较喜欢通过例子学习？"},
    )

    assert response.status_code == 200
    events = parse_sse(response.text)
    done = next(event for event in events if event["event"] == "text.done")
    assert "我观察到" in done["data"]["content"]
    assert "证据：" in done["data"]["content"]
    assert str(evidence_id) in done["data"]["content"]
    assert "喜欢借助具体讲解" in done["data"]["content"]


def test_evidence_question_without_data_falls_back_honestly(
    client: TestClient, empty_token: str
) -> None:
    conversation_id = create_conversation(client, empty_token)
    response = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=headers(empty_token),
        json={"content": "为什么你觉得我比较喜欢通过例子学习？"},
    )

    assert response.status_code == 200
    events = parse_sse(response.text)
    done = next(event for event in events if event["event"] == "text.done")
    assert "我还在观察中" in done["data"]["content"]
