"""Background job queue and worker routing tests."""

import asyncio
from uuid import uuid4

from sqlalchemy import delete

from app.infrastructure.database.models import BackgroundJob
from app.infrastructure.database.session import async_session
from app.jobs.queue import (
    enqueue,
    claim_next,
    mark_failed,
    mark_success,
)
from app.jobs.worker import process_claimed_job


def test_enqueue_claim_and_mark_success_follow_job_state_machine() -> None:
    async def run() -> None:
        job_id = None
        job_type = f"test_success_{uuid4()}"
        async with async_session() as session:
            job = await enqueue(
                session,
                job_type,
                {"test_id": str(uuid4())},
            )
            job_id = job.job_id
            await session.commit()

        async with async_session() as session:
            claimed = await claim_next(session, job_type)
            assert claimed is not None
            assert claimed.job_id == job_id
            assert claimed.status == "running"
            assert claimed.attempt == 1
            await session.commit()

        async with async_session() as session:
            running = await session.get(BackgroundJob, job_id)
            assert running is not None
            await mark_success(session, running)
            await session.commit()

        async with async_session() as session:
            finished = await session.get(BackgroundJob, job_id)
            assert finished is not None
            assert finished.status == "success"
            assert finished.finished_at is not None
            await session.execute(delete(BackgroundJob).where(BackgroundJob.job_id == job_id))
            await session.commit()

    asyncio.run(run())


def test_failed_job_retries_twice_then_becomes_failed_on_third_attempt() -> None:
    async def run() -> None:
        job_type = f"test_failure_{uuid4()}"
        async with async_session() as session:
            job = await enqueue(session, job_type, {"test_id": str(uuid4())})
            job_id = job.job_id
            await session.commit()

        for expected_attempt in (1, 2, 3):
            async with async_session() as session:
                claimed = await claim_next(session, job_type)
                assert claimed is not None
                assert claimed.job_id == job_id
                assert claimed.attempt == expected_attempt
                await session.commit()

            async with async_session() as session:
                running = await session.get(BackgroundJob, job_id)
                assert running is not None
                await mark_failed(session, running, "test failure")
                await session.commit()

        async with async_session() as session:
            failed = await session.get(BackgroundJob, job_id)
            assert failed is not None
            assert failed.status == "failed"
            assert failed.attempt == 3
            assert failed.error == "test failure"
            await session.execute(delete(BackgroundJob).where(BackgroundJob.job_id == job_id))
            await session.commit()

    asyncio.run(run())


def test_unknown_job_type_is_captured_as_a_retryable_failure() -> None:
    async def run() -> None:
        job_type = f"unknown_job_type_{uuid4()}"
        async with async_session() as session:
            job = await enqueue(session, job_type, {"test_id": str(uuid4())})
            job_id = job.job_id
            await session.commit()

        async with async_session() as session:
            claimed = await claim_next(session, job_type)
            assert claimed is not None
            assert claimed.job_id == job_id
            await session.commit()

        async with async_session() as session:
            running = await session.get(BackgroundJob, job_id)
            assert running is not None
            processed = await process_claimed_job(session, running)
            assert processed is False
            await session.commit()

        async with async_session() as session:
            retried = await session.get(BackgroundJob, job_id)
            assert retried is not None
            assert retried.status == "queued"
            assert "unknown job type" in (retried.error or "")
            await session.execute(delete(BackgroundJob).where(BackgroundJob.job_id == job_id))
            await session.commit()
