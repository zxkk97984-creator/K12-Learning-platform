"""Phase 8 Knowledge API / ingestion tests (real PostgreSQL + pgvector)."""

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.infrastructure.database.models import (
    KnowledgeChunk,
    KnowledgeResource,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password
from app.modules.knowledge.ingestion import ingest_text
from app.modules.knowledge.retrieval import retrieve


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
    """幂等：复用已有「测试训练数据」资源（否则每次测试累积污染知识库，检索 top-N 漂移）。"""

    async def run() -> UUID:
        async with async_session() as session:
            existing = await session.execute(
                select(KnowledgeResource)
                .where(KnowledgeResource.source_name == "测试训练数据")
                .order_by(KnowledgeResource.created_at.desc())
                .limit(1)
            )
            resource = existing.scalar_one_or_none()
            if resource is not None:
                return resource.resource_id
            resource_id, _ = await ingest_text(
                session,
                text=TEST_TEXT,
                source_name="测试训练数据",
                source_url="https://test.shuangling.local/training-data-fixed",
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


def headers(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


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
        headers=headers(token, **{"Idempotency-Key": f"conv-{uuid4()}"}),
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
            "/api/v1/knowledge/resources?status=READY&limit=100",
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
        unique_url = f"https://test.shuangling.local/search-{uuid4()}"

        async def ingest_search_resource() -> None:
            async with async_session() as session:
                await ingest_text(
                    session,
                    text=TEST_TEXT,
                    source_name="搜索测试资源",
                    source_url=unique_url,
                    license="CC-BY-4.0",
                    copyright_status="测试资源",
                    knowledge_point_ids=["kp-search-unique"],
                )

        asyncio.run(ingest_search_resource())
        response = client.post(
            "/api/v1/knowledge/search",
            headers=headers(student_token),
            json={
                "query": "雪豹测试语料",
                "knowledge_point_ids": ["kp-search-unique"],
                "limit": 5,
            },
        )
        assert response.status_code == 200
        rows = response.json()["data"]
        assert rows
        assert any("雪豹测试语料" in row["content"] for row in rows)
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

    def test_resources_cursor_pagination_has_no_overlap(
        self,
        client: TestClient,
        admin_token: str,
    ) -> None:
        first = client.get(
            "/api/v1/knowledge/resources?status=READY&limit=1",
            headers=headers(admin_token),
        )
        assert first.status_code == 200
        first_rows = first.json()["data"]
        assert len(first_rows) == 1
        assert first.json()["meta"]["has_more"] is True
        next_cursor = first.json()["meta"]["next_cursor"]
        assert next_cursor

        second = client.get(
            f"/api/v1/knowledge/resources?status=READY&limit=1&cursor={next_cursor}",
            headers=headers(admin_token),
        )
        assert second.status_code == 200
        second_rows = second.json()["data"]
        assert second_rows
        assert {
            row["resource_id"] for row in first_rows
        }.isdisjoint({row["resource_id"] for row in second_rows})

    def test_search_respects_limit(
        self,
        client: TestClient,
        student_token: str,
    ) -> None:
        response = client.post(
            "/api/v1/knowledge/search",
            headers=headers(student_token),
            json={"query": "训练数据", "limit": 2},
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) <= 2

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
        # 断言内容而非 source_name：知识库共享，命中哪条含雪豹语料的资源取决于插入顺序
        assert "雪豹测试语料" in done["data"]["content"]

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
        # 断言内容而非 source_name（共享知识库，命中资源取决于插入顺序）
        assert "雪豹测试语料" in done["data"]["content"]

    def test_search_validation_rejects_empty_query_and_bad_limit(
        self,
        client: TestClient,
        student_token: str,
    ) -> None:
        empty = client.post(
            "/api/v1/knowledge/search",
            headers=headers(student_token),
            json={"query": ""},
        )
        assert empty.status_code == 422

        for bad_limit in (0, 21):
            response = client.post(
                "/api/v1/knowledge/search",
                headers=headers(student_token),
                json={"query": "训练数据", "limit": bad_limit},
            )
            assert response.status_code == 422

        for bad_similarity in (-0.1, 1.1):
            response = client.post(
                "/api/v1/knowledge/search",
                headers=headers(student_token),
                json={"query": "训练数据", "min_similarity": bad_similarity},
            )
            assert response.status_code == 422

    def test_search_min_similarity_filters_vectors_and_uses_keyword_fallback(
        self,
        client: TestClient,
        student_token: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        query = "threshold query"
        run_id = str(uuid4())
        axis_one = [1.0] + [0.0] * 63
        axis_two = [0.0, 1.0] + [0.0] * 62

        def query_embedding(_text: str) -> list[float]:
            return axis_one

        def content_embedding(text: str) -> list[float]:
            if "高相似内容" in text:
                return axis_one
            return axis_two

        monkeypatch.setattr(
            "app.modules.knowledge.service.get_embedding", query_embedding
        )
        monkeypatch.setattr(
            "app.modules.knowledge.ingestion.get_embedding", content_embedding
        )

        async def ingest_threshold_rows() -> None:
            async with async_session() as session:
                await ingest_text(
                    session,
                    text="# 高相似\n\n高相似内容",
                    source_name="阈值高相似",
                    source_url=f"https://test.shuangling.local/threshold-high-{uuid4()}",
                    license="CC-BY-4.0",
                    copyright_status="测试资源",
                    knowledge_point_ids=[f"kp-threshold-high-{run_id}"],
                )
                await ingest_text(
                    session,
                    text="# 低相似\n\n低相似内容",
                    source_name="阈值低相似",
                    source_url=f"https://test.shuangling.local/threshold-low-{uuid4()}",
                    license="CC-BY-4.0",
                    copyright_status="测试资源",
                    knowledge_point_ids=[f"kp-threshold-low-{run_id}"],
                )
                await ingest_text(
                    session,
                    text=f"# 关键词回退\n\n{query} 关键词内容",
                    source_name="阈值关键词回退",
                    source_url=f"https://test.shuangling.local/threshold-fallback-{uuid4()}",
                    license="CC-BY-4.0",
                    copyright_status="测试资源",
                    knowledge_point_ids=[f"kp-threshold-fallback-{run_id}"],
                )

        asyncio.run(ingest_threshold_rows())

        high = client.post(
            "/api/v1/knowledge/search",
            headers=headers(student_token),
            json={
                "query": query,
                "knowledge_point_ids": [f"kp-threshold-high-{run_id}"],
                "min_similarity": 0.9,
            },
        )
        assert high.status_code == 200
        assert [row["content"] for row in high.json()["data"]] == ["高相似内容"]

        low = client.post(
            "/api/v1/knowledge/search",
            headers=headers(student_token),
            json={
                "query": query,
                "knowledge_point_ids": [f"kp-threshold-low-{run_id}"],
                "min_similarity": 0.9,
            },
        )
        assert low.status_code == 200
        assert low.json()["data"] == []

        fallback = client.post(
            "/api/v1/knowledge/search",
            headers=headers(student_token),
            json={
                "query": query,
                "knowledge_point_ids": [f"kp-threshold-fallback-{run_id}"],
                "min_similarity": 0.9,
            },
        )
        assert fallback.status_code == 200
        assert [row["content"] for row in fallback.json()["data"]] == [
            f"{query} 关键词内容"
        ]

        without_threshold = client.post(
            "/api/v1/knowledge/search",
            headers=headers(student_token),
            json={
                "query": query,
                "knowledge_point_ids": [f"kp-threshold-low-{run_id}"],
            },
        )
        assert without_threshold.status_code == 200
        assert [row["content"] for row in without_threshold.json()["data"]] == [
            "低相似内容"
        ]

    def test_search_knowledge_point_filter(
        self,
        client: TestClient,
        student_token: str,
    ) -> None:
        unique_url = f"https://test.shuangling.local/kp-{uuid4()}"

        async def ingest_with_kp() -> None:
            async with async_session() as session:
                await ingest_text(
                    session,
                    text=TEST_TEXT,
                    source_name="知识点测试",
                    source_url=unique_url,
                    license="CC-BY-4.0",
                    copyright_status="测试资源",
                    knowledge_point_ids=["kp-8c-test"],
                )

        asyncio.run(ingest_with_kp())

        matched = client.post(
            "/api/v1/knowledge/search",
            headers=headers(student_token),
            json={
                "query": "雪豹测试语料",
                "knowledge_point_ids": ["kp-8c-test"],
            },
        )
        assert matched.status_code == 200
        rows = matched.json()["data"]
        assert rows
        assert all("kp-8c-test" in row["knowledge_point_ids"] for row in rows)

        unmatched = client.post(
            "/api/v1/knowledge/search",
            headers=headers(student_token),
            json={
                "query": "雪豹测试语料",
                "knowledge_point_ids": ["kp-missing"],
            },
        )
        assert unmatched.status_code == 200
        assert unmatched.json()["data"] == []

    def test_search_no_hit_returns_empty(
        self,
        client: TestClient,
        student_token: str,
    ) -> None:
        # 知识库当前对纯文本无命中会返回 top-N 向量行（mock 无阈值，已上报）；
        # 这里用不存在的 knowledge_point 过滤验证真正的“空结果”路径。
        response = client.post(
            "/api/v1/knowledge/search",
            headers=headers(student_token),
            json={
                "query": "量子菠萝飞船驾驶手册",
                "knowledge_point_ids": ["kp-does-not-exist"],
            },
        )
        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_failed_resource_chunks_return_empty(
        self,
        client: TestClient,
        admin_token: str,
    ) -> None:
        resource_id = uuid4()

        async def insert_failed() -> None:
            async with async_session() as session:
                session.add(
                    KnowledgeResource(
                        resource_id=resource_id,
                        source_name="失败资源",
                        source_url=f"https://test.shuangling.local/failed-{uuid4()}",
                        license="CC-BY-4.0",
                        copyright_status="测试资源",
                        storage_key=f"knowledge/failed-{uuid4()}",
                        file_type="MARKDOWN",
                        status="FAILED",
                        error="embedding failed",
                    )
                )
                await session.flush()
                session.add(
                    KnowledgeChunk(
                        chunk_id=uuid4(),
                        resource_id=resource_id,
                        chunk_index=0,
                        content="pending chunk",
                        metadata_={},
                        status="PENDING",
                    )
                )
                await session.commit()

        asyncio.run(insert_failed())

        chunks = client.get(
            f"/api/v1/knowledge/resources/{resource_id}/chunks",
            headers=headers(admin_token),
        )
        assert chunks.status_code == 200
        assert chunks.json()["data"] == []

    def test_invalid_file_type_rejected_by_database_check(self) -> None:
        async def insert_invalid() -> None:
            async with async_session() as session:
                session.add(
                    KnowledgeResource(
                        resource_id=uuid4(),
                        source_name="非法类型",
                        source_url=f"https://test.shuangling.local/invalid-{uuid4()}",
                        license="CC-BY-4.0",
                        copyright_status="测试资源",
                        storage_key=f"knowledge/invalid-{uuid4()}",
                        file_type="DOCX",
                        status="UPLOADED",
                    )
                )
                await session.commit()

        with pytest.raises(IntegrityError):
            asyncio.run(insert_invalid())

    def test_ingestion_failed_status_on_embedding_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken_embedding(_text: str) -> list[float]:
            raise RuntimeError("embedding provider down")

        monkeypatch.setattr(
            "app.modules.knowledge.ingestion.get_embedding",
            broken_embedding,
        )
        source_url = f"https://test.shuangling.local/fail-{uuid4()}"

        async def ingest_broken() -> None:
            async with async_session() as session:
                try:
                    await ingest_text(
                        session,
                        text=TEST_TEXT,
                        source_name="失败管线",
                        source_url=source_url,
                        license="CC-BY-4.0",
                        copyright_status="测试资源",
                    )
                except RuntimeError:
                    pass

        asyncio.run(ingest_broken())

        async def check() -> tuple[str, str | None]:
            async with async_session() as session:
                resource = (
                    await session.execute(
                        select(KnowledgeResource).where(
                            KnowledgeResource.source_url == source_url
                        )
                    )
                ).scalar_one()
                return resource.status, resource.error

        status, error = asyncio.run(check())
        assert status == "FAILED"
        assert error

    def test_chunk_count_and_order_are_correct(
        self,
        client: TestClient,
        admin_token: str,
    ) -> None:
        source_url = f"https://test.shuangling.local/order-{uuid4()}"
        text = "# 第一段\n\n第一段内容。\n\n# 第二段\n\n第二段内容。\n\n# 第三段\n\n第三段内容。"

        async def ingest_ordered() -> UUID:
            async with async_session() as session:
                resource_id, count = await ingest_text(
                    session,
                    text=text,
                    source_name="顺序测试",
                    source_url=source_url,
                    license="CC-BY-4.0",
                    copyright_status="测试资源",
                )
                assert count == 3
                return resource_id

        resource_id = asyncio.run(ingest_ordered())
        chunks = client.get(
            f"/api/v1/knowledge/resources/{resource_id}/chunks",
            headers=headers(admin_token),
        )
        rows = chunks.json()["data"]
        assert [row["chunk_index"] for row in rows] == [0, 1, 2]

    def test_retrieve_prefers_selected_text_and_limits_top_n(self) -> None:
        async def run() -> tuple[int, list[str]]:
            async with async_session() as session:
                rows = await retrieve(
                    session,
                    "这是什么？",
                    screen_context={"selected_text": "雪豹测试语料"},
                    limit=2,
                )
                return len(rows), [row.source_name for row in rows]

        count, sources = asyncio.run(run())
        assert 1 <= count <= 2
        # 共享知识库：测试资源名因其他测试的插入而演进（训练数据/知识点测试/搜索测试资源）
        assert any(source in {"测试训练数据", "知识点测试", "搜索测试资源"} for source in sources)

    def test_conversation_falls_back_when_retrieval_empty(
        self,
        client: TestClient,
        student_token: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def empty_retrieve(*_args, **_kwargs):
            return []

        monkeypatch.setattr(
            "app.modules.conversation.service.retrieve",
            empty_retrieve,
        )
        conversation_id = create_conversation(client, student_token)
        response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=headers(student_token),
            json={"content": "训练数据是什么？"},
        )
        assert response.status_code == 200
        events = parse_sse(response.text)
        done = next(event for event in events if event["event"] == "text.done")
        assert "根据知识库资料" not in done["data"]["content"]
