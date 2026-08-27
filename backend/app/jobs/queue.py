"""Database-backed job queue primitives.

The public functions intentionally depend only on ``AsyncSession`` and the
job contract.  A Redis implementation can replace ``PostgresJobQueue`` later
without changing callers in the API or Worker.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.infrastructure.database.models import BackgroundJob


def _backoff_for(attempt: int) -> timedelta:
    """Exponential backoff delay after ``attempt`` failures (capped)."""
    base = settings.worker_backoff_base_seconds
    cap = settings.worker_backoff_max_seconds
    seconds = min(base * (2 ** max(attempt - 1, 0)), cap)
    return timedelta(seconds=seconds)

class JobQueue(Protocol):
    async def enqueue(
        self, session: AsyncSession, job_type: str, payload: dict[str, Any]
    ) -> BackgroundJob: ...

    async def claim_next(
        self, session: AsyncSession, job_type: str | None = None
    ) -> BackgroundJob | None: ...

    async def recover_stale_running(
        self, session: AsyncSession, max_age_seconds: float
    ) -> int: ...

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
        now = datetime.now(timezone.utc)
        query = select(BackgroundJob).where(
            BackgroundJob.status == "queued",
            # 退避期内的任务不可认领（next_attempt_at 为 NULL 表示立即可认领）。
            (BackgroundJob.next_attempt_at.is_(None))
            | (BackgroundJob.next_attempt_at <= now),
        )
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
        job.started_at = now
        job.finished_at = None
        job.next_attempt_at = None
        job.error = None
        await session.flush()
        return job

    async def recover_stale_running(
        self, session: AsyncSession, max_age_seconds: float
    ) -> int:
        """把超过 max_age_seconds 仍处于 running 的任务重置为 queued。

        场景：Worker 进程在处理中崩溃/被 kill，任务永远停留在 running，
        而 claim_next 只认领 queued——没有回收机制这些任务就永久滞留。
        attempt 不回退：若某任务反复令 Worker 崩溃，attempt 会随每次重新
        认领递增，最终仍走 mark_failed 的上限语义而不会无限循环。
        """
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        result = await session.execute(
            select(BackgroundJob).where(
                BackgroundJob.status == "running",
                BackgroundJob.started_at.is_not(None),
                BackgroundJob.started_at < cutoff,
            )
        )
        stale = list(result.scalars().all())
        for job in stale:
            job.status = "queued"
            job.error = f"requeued by stale-running recovery after {max_age_seconds:.0f}s"
            job.finished_at = None
        if stale:
            await session.flush()
        return len(stale)

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
            job.next_attempt_at = None
        else:
            job.status = "queued"
            job.finished_at = None
            # 指数退避：attempt 次失败后等 base*2^(attempt-1) 秒再重试（封顶 max），
            # 避免毒消息在低轮询间隔下形成紧密重试风暴。
            job.next_attempt_at = datetime.now(timezone.utc) + _backoff_for(job.attempt)
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


async def recover_stale_running(
    session: AsyncSession,
    max_age_seconds: float | None = None,
) -> int:
    """回收超时的 running 任务；缺省使用 worker_running_ttl_seconds 配置。"""
    ttl = settings.worker_running_ttl_seconds if max_age_seconds is None else max_age_seconds
    return await _queue.recover_stale_running(session, ttl)


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


async def enqueue_memory_consolidation(
    session: AsyncSession, student_id: UUID
) -> BackgroundJob | None:
    """Queue memory consolidation for a student unless one is already pending.

    Callers must invoke this inside the same database transaction that persists
    the triggering learning event / quiz answer: the job row then commits
    atomically with the data it consolidates (no lost-handoff window), and a
    failed insert fails the whole request instead of silently dropping memory
    work.  Consolidation itself reads every unprocessed event at run time, so
    skipping duplicates while one is queued/running loses nothing.
    """
    payload = {"student_id": str(student_id)}
    if await has_pending_job(session, "memory_consolidation", payload):
        return None
    return await enqueue(session, "memory_consolidation", payload)
