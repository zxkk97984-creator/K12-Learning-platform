"""Phase 7 ProfileInsight / StudentEpisode API tests (real PostgreSQL)."""

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.infrastructure.database.models import (
    MemoryEvidence,
    ProfileInsight,
    StudentEpisode,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.main import app
from app.modules.identity.security import hash_password


USER_NAME = "test_insight_user"
USER_PASSWORD = "insightpass"
OTHER_USER_NAME = "other_insight_user"
OTHER_USER_PASSWORD = "otherinsightpass"


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


def _insert_data(username: str) -> tuple[UUID, UUID, UUID]:
    async def run() -> tuple[UUID, UUID, UUID]:
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one()
            profile = (
                await session.execute(
                    select(StudentProfile).where(StudentProfile.user_id == user.user_id)
                )
            ).scalar_one()
            now = datetime.now(timezone.utc)
            evidence_id = uuid4()
            insight_id = uuid4()
            episode_id = uuid4()
            session.add(
                MemoryEvidence(
                    evidence_id=evidence_id,
                    student_id=profile.student_id,
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
            session.add(
                ProfileInsight(
                    insight_id=insight_id,
                    student_id=profile.student_id,
                    insight_type="INTEREST",
                    dimension="example_learning",
                    level="较稳定",
                    description="多次主动请求解释，喜欢借助讲解理解概念。",
                    evidence_ids=[str(evidence_id)],
                    status="ACTIVE",
                    valid_from=now,
                    valid_until=None,
                    rule_version="profile-rule-v1",
                    model_info={"provider": "rule", "model": "profile-rule-v1"},
                )
            )
            session.add(
                StudentEpisode(
                    episode_id=episode_id,
                    student_id=profile.student_id,
                    title="主动向霜铃提问",
                    summary="多次主动请求解释当前内容。",
                    occurred_at=now,
                    event_ids=[str(uuid4())],
                    importance="MEDIUM",
                    tags=["conversation"],
                )
            )
            await session.commit()
            return insight_id, evidence_id, episode_id

    return asyncio.run(run())


def _insert_insight(
    username: str,
    *,
    dimension: str = "example_learning",
    status: str = "ACTIVE",
    level: str = "较稳定",
) -> UUID:
    async def run() -> UUID:
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one()
            profile = (
                await session.execute(
                    select(StudentProfile).where(StudentProfile.user_id == user.user_id)
                )
            ).scalar_one()
            now = datetime.now(timezone.utc)
            insight_id = uuid4()
            session.add(
                ProfileInsight(
                    insight_id=insight_id,
                    student_id=profile.student_id,
                    insight_type="HABIT",
                    dimension=dimension,
                    level=level,
                    description="测试画像。",
                    evidence_ids=[],
                    status=status,
                    valid_from=now,
                    valid_until=now if status == "SUPERSEDED" else None,
                    rule_version="profile-rule-v1",
                )
            )
            await session.commit()
            return insight_id

    return asyncio.run(run())


@pytest.fixture(scope="module")
def client() -> TestClient:
    _ensure_user(USER_NAME, USER_PASSWORD, "画像测试")
    _ensure_user(OTHER_USER_NAME, OTHER_USER_PASSWORD, "其他画像测试")
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


def _get_student_id(username: str) -> UUID:
    async def run() -> UUID:
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one()
            profile = (
                await session.execute(
                    select(StudentProfile).where(StudentProfile.user_id == user.user_id)
                )
            ).scalar_one()
            return profile.student_id

    return asyncio.run(run())


def _claim_memory_consolidation_job(student_id: UUID) -> UUID | None:
    """查找该学生的 queued memory_consolidation job，返回 job_id。"""
    from app.infrastructure.database.models import BackgroundJob

    async def run() -> UUID | None:
        async with async_session() as session:
            rows = (
                await session.execute(
                    select(BackgroundJob).where(
                        BackgroundJob.job_type == "memory_consolidation",
                        BackgroundJob.status.in_(("queued", "running")),
                    )
                )
            ).scalars().all()
            for row in rows:
                if (row.payload or {}).get("student_id") == str(student_id):
                    return row.job_id
            return None

    return asyncio.run(run())


def _count_evidence(username: str, source_type: str) -> int:
    async def run() -> int:
        async with async_session() as session:
            user = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one()
            profile = (
                await session.execute(
                    select(StudentProfile).where(StudentProfile.user_id == user.user_id)
                )
            ).scalar_one()
            return int(
                (
                    await session.execute(
                        select(func.count(MemoryEvidence.evidence_id)).where(
                            MemoryEvidence.student_id == profile.student_id,
                            MemoryEvidence.source_type == source_type,
                        )
                    )
                ).scalar_one()
            )

    return asyncio.run(run())


class TestInsightsEpisodesAPI:
    def test_requires_authentication(self, client: TestClient) -> None:
        assert client.get("/api/v1/me/insights").status_code == 401
        assert client.get("/api/v1/me/episodes").status_code == 401

    def test_list_insights_filters_type_and_detail_expands_evidence(
        self, client: TestClient, token: str
    ) -> None:
        insight_id, evidence_id, _ = _insert_data(USER_NAME)

        listed = client.get(
            "/api/v1/me/insights?insight_type=INTEREST",
            headers=headers(token),
        )
        assert listed.status_code == 200
        assert any(
            row["insight_id"] == str(insight_id) for row in listed.json()["data"]
        )
        assert listed.json()["data"][0]["level"] in {
            "偏弱",
            "一般",
            "较稳定",
            "较强",
            "仍需观察",
        }

        detail = client.get(
            f"/api/v1/me/insights/{insight_id}",
            headers=headers(token),
        )
        assert detail.status_code == 200
        assert detail.json()["data"]["insight_id"] == str(insight_id)
        evidence = detail.json()["meta"]["evidence"]
        assert len(evidence) == 1
        assert evidence[0]["evidence_id"] == str(evidence_id)

    def test_insight_missing_and_owner_scoped(
        self,
        client: TestClient,
        token: str,
        other_token: str,
    ) -> None:
        insight_id, _, _ = _insert_data(USER_NAME)
        missing = client.get(
            f"/api/v1/me/insights/{uuid4()}", headers=headers(token)
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "INSIGHT_NOT_FOUND"

        forbidden = client.get(
            f"/api/v1/me/insights/{insight_id}",
            headers=headers(other_token),
        )
        assert forbidden.status_code == 403

    def test_list_episodes_filters_importance_and_detail(
        self, client: TestClient, token: str
    ) -> None:
        _, _, episode_id = _insert_data(USER_NAME)

        listed = client.get(
            "/api/v1/me/episodes?importance=MEDIUM",
            headers=headers(token),
        )
        assert listed.status_code == 200
        assert any(
            row["episode_id"] == str(episode_id) for row in listed.json()["data"]
        )

        detail = client.get(
            f"/api/v1/me/episodes/{episode_id}",
            headers=headers(token),
        )
        assert detail.status_code == 200
        assert detail.json()["data"]["episode_id"] == str(episode_id)
        assert detail.json()["data"]["summary"]

    def test_episode_missing_and_owner_scoped(
        self,
        client: TestClient,
        token: str,
        other_token: str,
    ) -> None:
        _, _, episode_id = _insert_data(USER_NAME)
        missing = client.get(
            f"/api/v1/me/episodes/{uuid4()}", headers=headers(token)
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "EPISODE_NOT_FOUND"

        forbidden = client.get(
            f"/api/v1/me/episodes/{episode_id}",
            headers=headers(other_token),
        )
        assert forbidden.status_code == 403

    def test_learning_event_write_triggers_pipeline(
        self, client: TestClient, token: str
    ) -> None:
        """Phase 1 起记忆整合异步化：事件写入只入队 memory_consolidation，
        由 Worker 消费后才产出 MemoryEvidence（不再在请求内同步执行）。"""
        before = _count_evidence(USER_NAME, "CONVERSATION")
        response = client.post(
            "/api/v1/learning-events",
            headers=headers(token),
            json={
                "event_type": "EXPLAIN_REQUESTED",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "payload": {"route": "chapter_reader", "page_type": "chapter_reader"},
            },
        )
        assert response.status_code == 201

        # 事件返回时不产生证据，而是存在待消费的 consolidation job
        assert _count_evidence(USER_NAME, "CONVERSATION") == before
        student_id = _get_student_id(USER_NAME)
        job_id = _claim_memory_consolidation_job(student_id)
        assert job_id is not None

        from app.infrastructure.database.models import BackgroundJob
        from app.jobs.worker import process_claimed_job

        async def consume() -> bool:
            async with async_session() as session:
                job = await session.get(BackgroundJob, job_id)
                assert job is not None and job.status == "queued"
                # 模拟 claim_next 的声明语义后走真实 Worker 派发路径
                job.status = "running"
                job.attempt += 1
                job.started_at = datetime.now(timezone.utc)
                await session.commit()
                succeeded = await process_claimed_job(session, job)
                await session.commit()
                return succeeded

        assert asyncio.run(consume()) is True
        assert _count_evidence(USER_NAME, "CONVERSATION") > before

    def test_invalid_insight_level_is_rejected_by_database_check(
        self, client: TestClient, token: str
    ) -> None:
        async def insert_invalid() -> None:
            async with async_session() as session:
                user = (
                    await session.execute(select(User).where(User.username == USER_NAME))
                ).scalar_one()
                profile = (
                    await session.execute(
                        select(StudentProfile).where(
                            StudentProfile.user_id == user.user_id
                        )
                    )
                ).scalar_one()
                now = datetime.now(timezone.utc)
                session.add(
                    ProfileInsight(
                        insight_id=uuid4(),
                        student_id=profile.student_id,
                        insight_type="HABIT",
                        dimension="invalid_level",
                        level="强",
                        description="非法档位。",
                        evidence_ids=[],
                        status="ACTIVE",
                        valid_from=now,
                        valid_until=None,
                        rule_version="profile-rule-v1",
                    )
                )
                await session.commit()

        with pytest.raises(IntegrityError):
            asyncio.run(insert_invalid())

    def test_invalid_insight_type_and_episode_importance_query_rejected(
        self, client: TestClient, token: str
    ) -> None:
        bad_insight = client.get(
            "/api/v1/me/insights?insight_type=UNKNOWN",
            headers=headers(token),
        )
        assert bad_insight.status_code == 422

        bad_episode = client.get(
            "/api/v1/me/episodes?importance=URGENT",
            headers=headers(token),
        )
        assert bad_episode.status_code == 422

    def test_insight_status_filter_returns_superseded_history(
        self, client: TestClient, token: str
    ) -> None:
        active_id = _insert_insight(USER_NAME, dimension="history_dimension")
        superseded_id = _insert_insight(
            USER_NAME,
            dimension="history_dimension",
            status="SUPERSEDED",
            level="一般",
        )

        active = client.get(
            "/api/v1/me/insights?status=ACTIVE",
            headers=headers(token),
        )
        superseded = client.get(
            "/api/v1/me/insights?status=SUPERSEDED",
            headers=headers(token),
        )
        assert str(active_id) in {row["insight_id"] for row in active.json()["data"]}
        assert str(superseded_id) in {
            row["insight_id"] for row in superseded.json()["data"]
        }

    def test_insights_list_cursor_pagination_has_no_overlap(
        self, client: TestClient, token: str
    ) -> None:
        _insert_insight(USER_NAME, dimension="page_dimension_a")
        _insert_insight(USER_NAME, dimension="page_dimension_b")

        first = client.get(
            "/api/v1/me/insights?limit=1",
            headers=headers(token),
        )
        assert first.status_code == 200
        first_rows = first.json()["data"]
        assert len(first_rows) == 1
        assert first.json()["meta"]["has_more"] is True
        next_cursor = first.json()["meta"]["next_cursor"]
        assert next_cursor

        second = client.get(
            f"/api/v1/me/insights?limit=1&cursor={next_cursor}",
            headers=headers(token),
        )
        assert second.status_code == 200
        second_rows = second.json()["data"]
        assert second_rows
        assert {
            row["insight_id"] for row in first_rows
        }.isdisjoint({row["insight_id"] for row in second_rows})
