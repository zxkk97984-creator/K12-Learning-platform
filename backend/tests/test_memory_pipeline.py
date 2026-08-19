"""Phase 7 rule-based Memory Pipeline tests (real PostgreSQL)."""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select

from app.infrastructure.database.models import (
    LearningEvent,
    MemoryCandidate,
    MemoryEvidence,
    ProfileInsight,
    StudentEpisode,
    StudentMemory,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.modules.identity.security import hash_password
from app.modules.memory.pipeline import MemoryPipeline


PIPELINE_USER = "test_pipeline_user"
PIPELINE_PASSWORD = "pipelinepass"
SINGLE_USER = "test_pipeline_single_user"
SINGLE_PASSWORD = "singlesingle"


def _ensure_user(username: str, password: str, nickname: str) -> UUID:
    async def run() -> UUID:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.username == username)
            )
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


def _insert_events(student_id: UUID, event_types: list[str]) -> None:
    async def run() -> None:
        async with async_session() as session:
            now = datetime.now(timezone.utc)
            for index, event_type in enumerate(event_types):
                session.add(
                    LearningEvent(
                        event_id=uuid4(),
                        student_id=student_id,
                        event_type=event_type,
                        occurred_at=now - timedelta(minutes=len(event_types) - index),
                        payload={},
                    )
                )
            await session.commit()

    asyncio.run(run())


def _run_pipeline(student_id: UUID, *, force_insights: bool = False) -> dict:
    async def run() -> dict:
        async with async_session() as session:
            return await MemoryPipeline().process_student(
                session, student_id, force_insights=force_insights
            )

    return asyncio.run(run())


def _reset_student(student_id: UUID) -> None:
    async def run() -> None:
        async with async_session() as session:
            for model in (
                ProfileInsight,
                StudentEpisode,
                StudentMemory,
                MemoryCandidate,
                MemoryEvidence,
                LearningEvent,
            ):
                await session.execute(
                    delete(model).where(model.student_id == student_id)
                )
            await session.commit()

    asyncio.run(run())


def _count(model: type, student_id: UUID) -> int:
    async def run() -> int:
        async with async_session() as session:
            return (
                await session.execute(
                    select(func.count()).select_from(model).where(
                        model.__table__.c.student_id == student_id
                    )
                )
            ).scalar_one()

    return asyncio.run(run())


@pytest.fixture(scope="module")
def student_id() -> UUID:
    return _ensure_user(PIPELINE_USER, PIPELINE_PASSWORD, "管线测试")


@pytest.fixture(autouse=True)
def clean_pipeline_data(student_id: UUID) -> None:
    _reset_student(student_id)
    single_id = _ensure_user(SINGLE_USER, SINGLE_PASSWORD, "单事件测试")
    _reset_student(single_id)
    yield


def test_pipeline_aggregates_evidence_candidate_memory_episode_insight(
    student_id: UUID,
) -> None:
    _insert_events(
        student_id,
        [
            "ANSWER_CORRECT",
            "ANSWER_CORRECT",
            "EXPLAIN_REQUESTED",
            "EXPLAIN_REQUESTED",
        ],
    )

    result = _run_pipeline(student_id)

    assert result["processed_events"] == 4
    assert result["groups"] == 2

    evidence_count = _count(MemoryEvidence, student_id)
    candidate_count = _count(MemoryCandidate, student_id)
    memory_count = _count(StudentMemory, student_id)
    episode_count = _count(StudentEpisode, student_id)
    insight_count = _count(ProfileInsight, student_id)
    assert evidence_count == 2
    assert candidate_count == 2
    assert memory_count == 2
    assert episode_count == 2
    assert insight_count == 2


def test_pipeline_is_idempotent_for_same_events(student_id: UUID) -> None:
    before = (
        _count(MemoryEvidence, student_id),
        _count(StudentEpisode, student_id),
        _count(ProfileInsight, student_id),
    )

    result = _run_pipeline(student_id)

    assert result["processed_events"] == 0
    after = (
        _count(MemoryEvidence, student_id),
        _count(StudentEpisode, student_id),
        _count(ProfileInsight, student_id),
    )
    assert after == before


def test_single_event_stays_pending_candidate_without_stable_memory(
    student_id: UUID,
) -> None:
    single_id = _ensure_user(SINGLE_USER, SINGLE_PASSWORD, "单事件测试")
    _reset_student(single_id)
    _insert_events(single_id, ["ANSWER_WRONG"])

    _run_pipeline(single_id)

    async def check() -> tuple[bool, bool]:
        async with async_session() as session:
            candidates = (
                await session.execute(
                    select(MemoryCandidate).where(
                        MemoryCandidate.student_id == single_id,
                        MemoryCandidate.status == "PENDING",
                    )
                )
            ).scalars().all()
            memories = (
                await session.execute(
                    select(StudentMemory).where(
                        StudentMemory.student_id == single_id,
                        StudentMemory.status == "ACTIVE",
                    )
                )
            ).scalars().all()
            return bool(candidates), len(memories) == 0

    has_pending, memory_count_unchanged = asyncio.run(check())
    assert has_pending
    assert memory_count_unchanged


def test_new_evidence_supersedes_old_insight(student_id: UUID) -> None:
    _insert_events(student_id, ["ANSWER_CORRECT", "ANSWER_CORRECT"])
    _run_pipeline(student_id)
    _insert_events(student_id, ["ANSWER_WRONG", "ANSWER_WRONG"])
    _run_pipeline(student_id)

    async def run() -> tuple[int, int]:
        async with async_session() as session:
            active = (
                await session.execute(
                    select(func.count(ProfileInsight.insight_id)).where(
                        ProfileInsight.student_id == student_id,
                        ProfileInsight.status == "ACTIVE",
                    )
                )
            ).scalar_one()
            superseded = (
                await session.execute(
                    select(func.count(ProfileInsight.insight_id)).where(
                        ProfileInsight.student_id == student_id,
                        ProfileInsight.status == "SUPERSEDED",
                    )
                )
            ).scalar_one()
            return int(active), int(superseded)

    active_count, superseded_count = asyncio.run(run())
    assert active_count >= 1
    assert superseded_count >= 1


def test_force_rebuild_does_not_reprocess_events_but_versions_insights(
    student_id: UUID,
) -> None:
    _insert_events(student_id, ["ANSWER_CORRECT", "ANSWER_CORRECT"])
    _run_pipeline(student_id)
    evidence_before = _count(MemoryEvidence, student_id)
    insight_before = _count(ProfileInsight, student_id)

    result = _run_pipeline(student_id, force_insights=True)

    assert result["processed_events"] == 0
    assert result["groups"] == 0
    assert _count(MemoryEvidence, student_id) == evidence_before
    assert _count(ProfileInsight, student_id) > insight_before


def test_incremental_rebuild_creates_one_evidence_and_keeps_event_ids_unique(
    student_id: UUID,
) -> None:
    _insert_events(student_id, ["ANSWER_CORRECT", "ANSWER_CORRECT"])
    _run_pipeline(student_id)
    evidence_before = _count(MemoryEvidence, student_id)

    _insert_events(student_id, ["ANSWER_WRONG"])
    result = _run_pipeline(student_id)

    assert result["processed_events"] == 1
    assert _count(MemoryEvidence, student_id) == evidence_before + 1

    async def check_unique() -> bool:
        async with async_session() as session:
            rows = (
                await session.execute(
                    select(MemoryEvidence).where(
                        MemoryEvidence.student_id == student_id
                    )
                )
            ).scalars().all()
            event_ids = [
                str(item) for row in rows for item in (row.event_ids or [])
            ]
            return len(event_ids) == len(set(event_ids))

    assert asyncio.run(check_unique())
