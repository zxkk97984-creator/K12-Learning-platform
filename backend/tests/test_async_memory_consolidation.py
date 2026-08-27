"""memory_consolidation 异步化回归测试（真实 PostgreSQL）。

覆盖 Phase 1 要求：
1. 学习事件与 Quiz 答题不再在 HTTP 路径内同步执行完整 MemoryPipeline，
   而是 job 行与业务写入同事务落库（原子交接）；
2. 同一学生已有 queued/running 的 consolidation job 时去重，不重复入队；
3. Worker（claim_next + process_claimed_job）能消费该 job 并产出 MemoryEvidence，
   失败语义保持可重试。
"""

import asyncio
from datetime import datetime, timezone
from typing import Callable
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.infrastructure.database.models import (
    BackgroundJob,
    Book,
    Chapter,
    Conversation,
    ConversationSummary,
    KnowledgeChunk,
    LearningEvent,
    MemoryCandidate,
    MemoryEvidence,
    Message,
    ProfileInsight,
    QuizAnswer,
    QuizInteraction,
    QuizQuestion,
    QuizSession,
    StudentEpisode,
    StudentMemory,
    StudentPreference,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.jobs.queue import claim_next
from app.jobs.worker import process_claimed_job
from app.main import app
from app.modules.identity.security import hash_password

QUIZ_BOOK_ID = UUID("b6000000-0000-0000-0000-0000000000a1")
QUIZ_CHAPTER_ID = UUID("c6000000-0000-0000-0000-0000000000a1")


def _ensure_quiz_content() -> None:
    async def run() -> None:
        async with async_session() as session:
            if await session.get(Book, QUIZ_BOOK_ID) is None:
                session.add(
                    Book(
                        book_id=QUIZ_BOOK_ID,
                        title="异步记忆测验书",
                        grade_min=7,
                        grade_max=9,
                        difficulty="MEDIUM",
                        estimated_minutes=60,
                        status="PUBLISHED",
                        published_at=datetime.now(timezone.utc),
                    )
                )
            if await session.get(Chapter, QUIZ_CHAPTER_ID) is None:
                session.add(
                    Chapter(
                        chapter_id=QUIZ_CHAPTER_ID,
                        book_id=QUIZ_BOOK_ID,
                        title="训练数据章",
                        chapter_order=1,
                        estimated_minutes=15,
                        status="PUBLISHED",
                    )
                )
            await session.commit()

    asyncio.run(run())


def _create_student() -> tuple[str, UUID]:
    """每个用例使用独立学生，避免共享状态；结束时清理。"""
    username = f"test_memq_{uuid4().hex[:10]}"

    async def run() -> UUID:
        async with async_session() as session:
            user = User(
                username=username,
                password_hash=hash_password("memqueuepass"),
                user_type="STUDENT",
            )
            session.add(user)
            await session.flush()
            profile = StudentProfile(
                user_id=user.user_id,
                nickname="队列记忆测试",
                grade=8,
                language="zh-CN",
            )
            session.add(profile)
            await session.flush()
            session.add(
                StudentPreference(
                    student_id=profile.student_id,
                    preferred_explanation_style="EXAMPLE_BASED",
                    preferred_difficulty="MEDIUM",
                    preferred_session_length="SHORT",
                )
            )
            await session.commit()
            return profile.student_id

    return username, asyncio.run(run())


def _cleanup_student(username: str, student_id: UUID) -> None:
    async def run() -> None:
        async with async_session() as session:
            await session.execute(
                delete(BackgroundJob).where(
                    BackgroundJob.payload["student_id"].astext == str(student_id)
                )
            )
            conversation_ids = (
                await session.execute(
                    select(Conversation.conversation_id).where(
                        Conversation.student_id == student_id
                    )
                )
            ).scalars().all()
            if conversation_ids:
                await session.execute(
                    delete(Message).where(Message.conversation_id.in_(conversation_ids))
                )
                await session.execute(
                    delete(ConversationSummary).where(
                        ConversationSummary.conversation_id.in_(conversation_ids)
                    )
                )
                quiz_session_ids = (
                    await session.execute(
                        select(QuizSession.quiz_session_id).where(
                            QuizSession.conversation_id.in_(conversation_ids)
                        )
                    )
                ).scalars().all()
                if quiz_session_ids:
                    for model in (
                        QuizInteraction,
                        QuizAnswer,
                        QuizQuestion,
                    ):
                        await session.execute(
                            delete(model).where(
                                model.quiz_session_id.in_(quiz_session_ids)
                            )
                        )
                    await session.execute(
                        delete(QuizSession).where(
                            QuizSession.quiz_session_id.in_(quiz_session_ids)
                        )
                    )
                await session.execute(
                    delete(Conversation).where(
                        Conversation.conversation_id.in_(conversation_ids)
                    )
                )
            for model in (
                ProfileInsight,
                StudentEpisode,
                StudentMemory,
                MemoryCandidate,
                MemoryEvidence,
                LearningEvent,
            ):
                await session.execute(delete(model).where(model.student_id == student_id))
            profile = await session.get(StudentProfile, student_id)
            if profile is not None:
                await session.delete(profile)
            user = (
                await session.execute(select(User).where(User.username == username))
            ).scalar_one_or_none()
            if user is not None:
                await session.delete(user)
            await session.commit()

    asyncio.run(run())


def _queued_memory_jobs(student_id: UUID) -> list[BackgroundJob]:
    async def run() -> list[BackgroundJob]:
        async with async_session() as session:
            rows = (
                await session.execute(
                    select(BackgroundJob).where(
                        BackgroundJob.job_type == "memory_consolidation",
                        BackgroundJob.status.in_(("queued", "running")),
                    )
                )
            ).scalars().all()
            return [
                row
                for row in rows
                if (row.payload or {}).get("student_id") == str(student_id)
            ]

    return asyncio.run(run())


def _evidence_count(student_id: UUID) -> int:
    async def run() -> int:
        async with async_session() as session:
            return (
                await session.execute(
                    select(func.count())
                    .select_from(MemoryEvidence)
                    .where(MemoryEvidence.student_id == student_id)
                )
            ).scalar_one()

    return asyncio.run(run())


def _consume_one_memory_job(student_id: UUID | None = None) -> bool:
    """按 Worker 语义逐个消费 memory_consolidation job。

    指定 ``student_id`` 时跳过（真实处理）其他学生的历史遗留 job，
    只报告目标学生 job 的消费结果；队列耗尽返回 False。
    """
    async def run() -> bool:
        async with async_session() as session:
            while True:
                job = await claim_next(session, "memory_consolidation")
                if job is None:
                    await session.rollback()
                    return False
                await session.commit()
                succeeded = await process_claimed_job(session, job)
                await session.commit()
                if student_id is None or (
                    job.payload or {}
                ).get("student_id") == str(student_id):
                    return succeeded

    return asyncio.run(run())


@pytest.fixture(scope="module")
def client() -> TestClient:
    _ensure_quiz_content()
    return TestClient(app)


def _login(client: TestClient, username: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "memqueuepass"},
    )
    assert response.status_code == 200
    return response.json()["data"]["access_token"]


def test_learning_event_enqueues_and_worker_consumes(client: TestClient) -> None:
    username, student_id = _create_student()
    try:
        token = _login(client, username)
        response = client.post(
            "/api/v1/learning-events",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "event_type": "ANSWER_CORRECT",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "payload": {"source": "async-memory-test"},
            },
        )
        assert response.status_code == 201

        jobs = _queued_memory_jobs(student_id)
        assert len(jobs) == 1
        assert jobs[0].payload == {"student_id": str(student_id)}
        # 关键断言：事件返回时记忆尚未生成（不再同步执行 pipeline）
        assert _evidence_count(student_id) == 0

        assert _consume_one_memory_job(student_id) is True
        assert _evidence_count(student_id) >= 1

        async def job_state() -> str | None:
            async with async_session() as session:
                job = await session.get(BackgroundJob, jobs[0].job_id)
                return None if job is None else job.status

        assert asyncio.run(job_state()) == "success"
    finally:
        _cleanup_student(username, student_id)


def test_learning_event_dedupes_pending_memory_consolidation(
    client: TestClient,
) -> None:
    username, student_id = _create_student()
    try:
        token = _login(client, username)
        for _ in range(2):
            response = client.post(
                "/api/v1/learning-events",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "event_type": "EXPLAIN_REQUESTED",
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "payload": {},
                },
            )
            assert response.status_code == 201

        assert len(_queued_memory_jobs(student_id)) == 1
    finally:
        _cleanup_student(username, student_id)


def test_quiz_answer_enqueues_memory_consolidation(client: TestClient) -> None:
    username, student_id = _create_student()
    try:
        token = _login(client, username)
        conversation = client.post(
            "/api/v1/conversations",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"memq-conv-{uuid4()}",
            },
            json={"title": "异步记忆测验会话"},
        )
        assert conversation.status_code == 201
        conversation_id = conversation.json()["data"]["conversation_id"]

        quiz = client.post(
            "/api/v1/quiz-sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "conversation_id": conversation_id,
                "book_id": str(QUIZ_BOOK_ID),
                "chapter_id": str(QUIZ_CHAPTER_ID),
                "quiz_kind": "CHAPTER_QUIZ",
                "question_count": 1,
                "difficulty": "MEDIUM",
            },
        )
        assert quiz.status_code == 201
        session_data = quiz.json()["data"]
        question = session_data["questions_snapshot"][0]

        assert len(_queued_memory_jobs(student_id)) == 0

        answer = client.post(
            f"/api/v1/quiz-sessions/{session_data['quiz_session_id']}"
            f"/questions/{question['question_id']}/answers",
            headers={"Authorization": f"Bearer {token}"},
            json={"answer": question["correct_answer"]},
        )
        assert answer.status_code == 201

        jobs = _queued_memory_jobs(student_id)
        assert len(jobs) == 1
        assert jobs[0].payload == {"student_id": str(student_id)}

        assert _consume_one_memory_job(student_id) is True
        assert _evidence_count(student_id) >= 1
    finally:
        _cleanup_student(username, student_id)


def test_memory_job_failure_stays_retryable(client: TestClient) -> None:
    """坏 payload 的 job 必须以可重试失败记录，而不是被吞掉或伪造成功。"""
    async def enqueue_bad() -> UUID:
        async with async_session() as session:
            from app.jobs.queue import enqueue

            job = await enqueue(session, "memory_consolidation", {"student_id": "not-a-uuid"})
            await session.commit()
            return job.job_id

    job_id = asyncio.run(enqueue_bad())
    try:
        consumed = _consume_one_memory_job_by_id(job_id)
        assert consumed is False

        async def read_job() -> BackgroundJob:
            async with async_session() as session:
                return await session.get(BackgroundJob, job_id)

        job = asyncio.run(read_job())
        assert job.status == "queued"
        assert "student_id must be a UUID" in (job.error or "")
    finally:
        _delete_job(job_id)


def _consume_one_memory_job_by_id(job_id: UUID) -> bool:
    async def run() -> bool:
        from app.infrastructure.database.models import BackgroundJob as Job

        async with async_session() as session:
            job = await session.get(Job, job_id)
            if job is None or job.status != "queued":
                return False
            claimed = await claim_next(session, "memory_consolidation")
            if claimed is None or claimed.job_id != job_id:
                await session.rollback()
                return False
            await session.commit()
            succeeded = await process_claimed_job(session, claimed)
            await session.commit()
            return succeeded

    return asyncio.run(run())


def _delete_job(job_id: UUID) -> None:
    async def run() -> None:
        async with async_session() as session:
            job = await session.get(BackgroundJob, job_id)
            if job is not None:
                await session.delete(job)
                await session.commit()

    asyncio.run(run())


def test_worker_dispatch_consumes_knowledge_ingest_and_conversation_summary(
    client: TestClient,
) -> None:
    """三类 handler 都能经真实 Worker 派发路径（resolve_handler）消费成功。"""
    admin_name = f"test_memq_admin_{uuid4().hex[:8]}"

    async def ensure_admin() -> UUID:
        async with async_session() as session:
            user = User(
                username=admin_name,
                password_hash=hash_password("memqadminpass"),
                user_type="ADMIN",
            )
            session.add(user)
            await session.flush()
            from app.infrastructure.database.models import Admin

            session.add(Admin(user_id=user.user_id, display_name="队列管理员", role_level="SUPERVISOR", enabled=True))
            await session.commit()
            return user.user_id

    asyncio.run(ensure_admin())
    try:
        token = client.post(
            "/api/v1/auth/login",
            json={"username": admin_name, "password": "memqadminpass"},
        ).json()["data"]["access_token"]

        uploaded = client.post(
            "/api/v1/admin/knowledge/resources",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": f"memq-upload-{uuid4()}",
            },
            files={"file": ("memq.md", "# 队列消费\n\n这是一段用于验证 Worker 派发的知识内容。".encode(), "text/markdown")},
            data={
                "source_name": "Worker 派发测试",
                "source_url": f"https://test.shuangling.local/memq-{uuid4()}",
                "license": "CC-BY-4.0",
                "copyright_status": "测试",
            },
        )
        assert uploaded.status_code == 202
        resource_id = uploaded.json()["data"]["resource_id"]

        async def queued_job_for(payload_key: str, value: str) -> BackgroundJob:
            async with async_session() as session:
                rows = (
                    await session.execute(
                        select(BackgroundJob).where(
                            BackgroundJob.job_type == "knowledge_ingest",
                            BackgroundJob.status == "queued",
                        )
                    )
                ).scalars().all()
                matches = [
                    row
                    for row in rows
                    if (row.payload or {}).get(payload_key) == value
                ]
                assert len(matches) == 1
                return matches[0]

        ingest_job = asyncio.run(queued_job_for("resource_id", resource_id))

        consumed = _process_job_by_id(ingest_job.job_id)
        assert consumed is True

        async def resource_status() -> str:
            async with async_session() as session:
                from app.infrastructure.database.models import KnowledgeResource

                resource = await session.get(KnowledgeResource, UUID(resource_id))
                assert resource is not None
                return str(resource.status)

        assert asyncio.run(resource_status()) == "READY"

        # conversation_summary：入队后由同一 Worker 路径消费成功
        summary_job_id, summary_cleanup = _enqueue_summary_for_new_conversation()
        assert summary_job_id is not None
        assert _process_job_by_id(summary_job_id) is True

        async def summary_state() -> str:
            async with async_session() as session:
                job = await session.get(BackgroundJob, summary_job_id)
                return str(job.status)

        assert asyncio.run(summary_state()) == "success"
    finally:
        _delete_uploaded_resource(resource_id)
        summary_cleanup()
        asyncio.run(_delete_admin(admin_name))


def _delete_uploaded_resource(resource_id: str) -> None:
    async def run() -> None:
        from app.infrastructure.database.models import KnowledgeResource

        async with async_session() as session:
            rid = UUID(resource_id)
            await session.execute(
                delete(KnowledgeChunk).where(KnowledgeChunk.resource_id == rid)
            )
            resource = await session.get(KnowledgeResource, rid)
            if resource is not None:
                await session.delete(resource)
            await session.commit()

    asyncio.run(run())


def _process_job_by_id(job_id: UUID) -> bool:
    """按 claim_next 的声明语义认领指定 job，再走真实 Worker 派发路径。"""

    async def run() -> bool:
        async with async_session() as session:
            job = await session.get(BackgroundJob, job_id)
            if job is None or job.status != "queued":
                return False
            job.status = "running"
            job.attempt += 1
            job.started_at = datetime.now(timezone.utc)
            await session.commit()
            succeeded = await process_claimed_job(session, job)
            await session.commit()
            return succeeded

    return asyncio.run(run())


def _enqueue_summary_for_new_conversation() -> tuple[UUID, Callable[[], None]]:
    """构造达到阈值的会话并入队 summary；返回 (job_id, cleanup)。"""
    username = f"test_memq_sum_{uuid4().hex[:8]}"

    async def run() -> UUID:
        from app.jobs.queue import enqueue

        async with async_session() as session:
            user = User(
                username=username,
                password_hash=hash_password("sumqueuepass"),
                user_type="STUDENT",
            )
            session.add(user)
            await session.flush()
            profile = StudentProfile(
                user_id=user.user_id, nickname="摘要队列测试", grade=8, language="zh-CN"
            )
            session.add(profile)
            await session.flush()
            conversation = Conversation(
                student_id=profile.student_id,
                title="Worker 摘要派发",
                status="ACTIVE",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(conversation)
            await session.flush()
            from app.infrastructure.database.models import Message

            base = datetime.now(timezone.utc)
            for index in range(24):
                session.add(
                    Message(
                        conversation_id=conversation.conversation_id,
                        role="STUDENT" if index % 2 == 0 else "TEACHER",
                        type="TEXT" if index % 2 == 0 else "QUIZ",
                        content=f"消息 {index}",
                        sequence=index + 1,
                        created_at=base,
                    )
                )
            job = await enqueue(
                session,
                "conversation_summary",
                {"conversation_id": str(conversation.conversation_id)},
            )
            await session.commit()
            return job.job_id

    job_id = asyncio.run(run())

    def cleanup() -> None:
        async def clean() -> None:
            from app.infrastructure.database.models import (
                ConversationSummary as Summary,
                Message as Msg,
            )

            async with async_session() as session:
                user = (
                    await session.execute(select(User).where(User.username == username))
                ).scalar_one_or_none()
                if user is None:
                    return
                profile = (
                    await session.execute(
                        select(StudentProfile).where(StudentProfile.user_id == user.user_id)
                    )
                ).scalar_one_or_none()
                conversations = (
                    await session.execute(
                        select(Conversation.conversation_id).where(
                            Conversation.student_id == profile.student_id
                        )
                    )
                ).scalars().all() if profile else []
                if conversations:
                    await session.execute(delete(Msg).where(Msg.conversation_id.in_(conversations)))
                    await session.execute(
                        delete(Summary).where(Summary.conversation_id.in_(conversations))
                    )
                    await session.execute(
                        delete(Conversation).where(Conversation.conversation_id.in_(conversations))
                    )
                if profile is not None:
                    await session.delete(profile)
                await session.delete(user)
                await session.commit()

        asyncio.run(clean())

    return job_id, cleanup


async def _delete_admin(username: str) -> None:
    from app.infrastructure.database.models import Admin

    async with async_session() as session:
        user = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if user is not None:
            admin = (
                await session.execute(select(Admin).where(Admin.user_id == user.user_id))
            ).scalar_one_or_none()
            if admin is not None:
                await session.delete(admin)
            await session.delete(user)
        await session.commit()
