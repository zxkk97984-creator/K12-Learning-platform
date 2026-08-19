"""Phase 8 Knowledge API / ingestion tests (real PostgreSQL + pgvector)."""

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.infrastructure.database.models import StudentProfile, User
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password
from app.modules.knowledge.ingestion import ingest_text


ADMIN_NAME = "test_knowledge_admin"
ADMIN_PASSWORD = "knowledgeadmin"
STUDENT_NAME = "test_knowledge_student"
STUDENT_PASSWORD = "knowledgestudent"

TEST_TEXT = """# 训练数据

训练数据是一组用来帮助机器发现规律的例子。例子越能代表真实世界，机器越可能做出合适的判断。

# 特征与标签

训练数据包含“机器看到的内容”和“我们希望它学会的答案”，也就是特征和标签。

# 雪豹测试语料

雪豹测试语料是一种用于验证检索注入的独特标记。
"""


def _ensure_user(username: str, password: str, user_type: str) -> None:
    async def run() -> None:
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one_or_none()
            if user is None:
                session.add(
                    User(
                        username=username,
                        password_hash=hash_password(password),
                        user_type=user_type,
                    )
                )
                await session.flush()
            if user_type == "STUDENT":
                profile = (
                    await session.execute(
                        select(StudentProfile).where(
                            StudentProfile.user_id == user.user_id
                        )
                    )
                ).scalar_one_or_none()
                if profile is None:
                    session.add(
                        StudentProfile(
                            user_id=user.user_id,
                            nickname="知识学生",
                            grade=8,
                            language="zh-CN",
                        )
                    )
            await session.commit()

    asyncio.run(run())


def _ingest_test_resource() -> UUID:
    async def run() -> UUID:
        async with async_session() as session:
            resource_id, _ = await ingest_text(
                session,
                text=TEST_TEXT,
                source_name="测试训练数据",
                source_url=f"https://test.shuangling.local/training-data-{uuid4()}",
                license="CC-BY-4.0",
                copyright_status="测试资源",
            )
            return resource_id

    return asyncio.run(run())


@pytest.fixture(scope="module")
def client() -> TestClient:
    _ensure_user(ADMIN_NAME, ADMIN_PASSWORD, "ADMIN")
    _ensure_user(STUDENT_NAME, STUDENT_PASSWORD, "STUDENT")
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


@pytest.fixture(scope="module")
def resource_id() -> UUID:
    return _ingest_test_resource()


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
            events.append(
                {"event": event_name, "data": json.loads("\n".join(data_lines))}
            )
    return events


def create_conversation(client: TestClient, token: str) -> str:
    response = client.post(
        "/api/v1/conversations",
        headers=headers(token),
        json={"title": "RAG 注入测试"},
    )
    assert response.status_code == 201
    return response.json()["data"]["conversation_id"]


class TestKnowledgeAPI:
    def test_admin_list_detail_chunks(
        self,
        client: TestClient,
        admin_token: str,
        resource_id: UUID,
    ) -> None:
        listed = client.get(
            "/api/v1/knowledge/resources?status=READY",
            headers=headers(admin_token),
        )
        assert listed.status_code == 200
        assert str(resource_id) in {
            row["resource_id"] for row in listed.json()["data"]
        }

        detail = client.get(
            f"/api/v1/knowledge/resources/{resource_id}",
            headers=headers(admin_token),
        )
        assert detail.status_code == 200
        assert detail.json()["data"]["status"] == "READY"
        assert detail.json()["data"]["license"] == "CC-BY-4.0"

        chunks = client.get(
            f"/api/v1/knowledge/resources/{resource_id}/chunks",
            headers=headers(admin_token),
        )
        assert chunks.status_code == 200
        rows = chunks.json()["data"]
        assert len(rows) >= 1
        assert all(row["status"] == "READY" for row in rows)
        assert all(row["metadata"]["source_url"] for row in rows)
        assert all(row["metadata"]["license"] for row in rows)

    def test_student_search_returns_traceable_chunks(
        self,
        client: TestClient,
        student_token: str,
    ) -> None:
        response = client.post(
            "/api/v1/knowledge/search",
            headers=headers(student_token),
            json={"query": "训练数据", "limit": 5},
        )
        assert response.status_code == 200
        rows = response.json()["data"]
        assert rows
        assert any("训练数据" in row["content"] for row in rows)
        assert all(row["metadata"].get("source_url") for row in rows)
        assert all(row["metadata"].get("license") for row in rows)

    def test_admin_only_and_authentication(
        self,
        client: TestClient,
        student_token: str,
    ) -> None:
        forbidden = client.get(
            "/api/v1/knowledge/resources",
            headers=headers(student_token),
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "ADMIN_ONLY"

        unauthenticated = client.get("/api/v1/knowledge/resources")
        assert unauthenticated.status_code == 401

    def test_missing_resource_returns_not_found(
        self,
        client: TestClient,
        admin_token: str,
    ) -> None:
        missing = client.get(
            f"/api/v1/knowledge/resources/{UUID(int=0x9999)}",
            headers=headers(admin_token),
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

    def test_ingestion_is_idempotent(self) -> None:
        unique_url = f"https://test.shuangling.local/training-data-{uuid4()}"

        async def run() -> tuple[int, int]:
            async with async_session() as session:
                _, first_count = await ingest_text(
                    session,
                    text=TEST_TEXT,
                    source_name="测试训练数据",
                    source_url=unique_url,
                    license="CC-BY-4.0",
                    copyright_status="测试资源",
                )
                _, second_count = await ingest_text(
                    session,
                    text=TEST_TEXT,
                    source_name="测试训练数据",
                    source_url=unique_url,
                    license="CC-BY-4.0",
                    copyright_status="测试资源",
                )
                return first_count, second_count

        first_count, second_count = asyncio.run(run())
        assert first_count >= 1
        assert second_count == 0

    def test_conversation_injects_retrieved_knowledge(
        self,
        client: TestClient,
        student_token: str,
    ) -> None:
        conversation_id = create_conversation(client, student_token)
        response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(student_token),
            json={"content": "雪豹测试语料是什么？"},
        )
        assert response.status_code == 200
        events = parse_sse(response.text)
        done = next(event for event in events if event["event"] == "text.done")
        assert "根据知识库资料" in done["data"]["content"]
        assert "测试训练数据" in done["data"]["content"]

    def test_conversation_skips_retrieval_for_unrelated_question(
        self,
        client: TestClient,
        student_token: str,
    ) -> None:
        conversation_id = create_conversation(client, student_token)
        response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(student_token),
            json={"content": "今天天气怎么样？"},
        )
        assert response.status_code == 200
        events = parse_sse(response.text)
        done = next(event for event in events if event["event"] == "text.done")
        assert "根据知识库资料" not in done["data"]["content"]

    def test_screen_context_selected_text_boosts_retrieval(
        self,
        client: TestClient,
        student_token: str,
    ) -> None:
        conversation_id = create_conversation(client, student_token)
        response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(student_token),
            json={
                "content": "这是什么？",
                "screen_context": {
                    "route": "/learn/ch3",
                    "page_type": "chapter_reader",
                    "selected_text": "雪豹测试语料",
                },
            },
        )
        assert response.status_code == 200
        events = parse_sse(response.text)
        done = next(event for event in events if event["event"] == "text.done")
        assert "根据知识库资料" in done["data"]["content"]
        assert "测试训练数据" in done["data"]["content"]
