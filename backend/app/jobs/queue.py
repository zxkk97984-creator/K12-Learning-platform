"""Database-backed job queue primitives.

The public functions intentionally depend only on ``AsyncSession`` and the
job contract.  A Redis implementation can replace ``PostgresJobQueue`` later
without changing callers in the API or Worker.
"""

from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.infrastructure.database.models import BackgroundJob

class JobQueue(Protocol):
    async def enqueue(
        self, session: AsyncSession, job_type: str, payload: dict[str, Any]
    ) -> BackgroundJob: ...

    async def claim_next(
        self, session: AsyncSession, job_type: str | None = None
    ) -> BackgroundJob | None: ...

    async def mark_success(
        self, session: AsyncSession, job: BackgroundJob
    ) -> None: ...

    async def mark_failed(
        self, session: AsyncSession, job: BackgroundJob, error: str
    ) -> None: ...


class PostgresJobQueue:
    """PostgreSQL queue using ``FOR UPDATE SKIP LOCKED`` for worker claims."""

    async def enqueue(
        self, session: AsyncSession, job_type: str, payload: dict[str, Any]
    ) -> BackgroundJob:
        if not job_type or len(job_type) > 64:
            raise ValueError("job_type must be between 1 and 64 characters")
        if not isinstance(payload, dict):
            raise TypeError("job payload must be an object")
        job = BackgroundJob(
            job_id=uuid4(),
            job_type=job_type,
            status="queued",
            attempt=0,
            payload=dict(payload),
        )
        session.add(job)
        await session.flush()
        return job

    async def claim_next(
        self, session: AsyncSession, job_type: str | None = None
    ) -> BackgroundJob | None:
        query = select(BackgroundJob).where(BackgroundJob.status == "queued")
        if job_type is not None:
            query = query.where(BackgroundJob.job_type == job_type)
        query = (
            query.order_by(BackgroundJob.created_at.asc(), BackgroundJob.job_id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(query)
        job = result.scalar_one_or_none()
        if job is None:
            return None
        job.status = "running"
        job.attempt += 1
        job.started_at = datetime.now(timezone.utc)
        job.finished_at = None
        job.error = None
        await session.flush()
        return job

    async def mark_success(
        self, session: AsyncSession, job: BackgroundJob
    ) -> None:
        job.status = "success"
        job.error = None
        job.finished_at = datetime.now(timezone.utc)
        await session.flush()

    async def mark_failed(
        self, session: AsyncSession, job: BackgroundJob, error: str
    ) -> None:
        job.error = str(error)[:4000]
        if job.attempt >= settings.worker_max_attempts:
            job.status = "failed"
            job.finished_at = datetime.now(timezone.utc)
        else:
            job.status = "queued"
            job.finished_at = None
        await session.flush()


_queue: JobQueue = PostgresJobQueue()


async def enqueue(
    session: AsyncSession, job_type: str, payload: dict[str, Any]
) -> BackgroundJob:
    return await _queue.enqueue(session, job_type, payload)


async def claim_next(
    session: AsyncSession, job_type: str | None = None
) -> BackgroundJob | None:
    return await _queue.claim_next(session, job_type)


async def mark_success(session: AsyncSession, job: BackgroundJob) -> None:
    await _queue.mark_success(session, job)


async def mark_failed(
    session: AsyncSession, job: BackgroundJob, error: str
) -> None:
    await _queue.mark_failed(session, job, error)


async def has_pending_job(
    session: AsyncSession,
    job_type: str,
    payload_match: dict[str, Any],
) -> bool:
    """Return whether a queued/running job matches the supplied payload keys."""
    result = await session.execute(
        select(BackgroundJob).where(
            BackgroundJob.job_type == job_type,
            BackgroundJob.status.in_(("queued", "running")),
        )
    )
    return any(
        all(job.payload.get(key) == value for key, value in payload_match.items())
        for job in result.scalars().all()
    )
