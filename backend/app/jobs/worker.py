"""Worker loop and job-type dispatch for PostgreSQL background jobs."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.infrastructure.database.models import BackgroundJob
from app.infrastructure.database.session import async_session
from app.jobs.queue import claim_next, mark_failed, mark_success

logger = logging.getLogger(__name__)

JobHandler = Callable[[AsyncSession, dict[str, Any]], Awaitable[None]]


class UnknownJobTypeError(RuntimeError):
    """Raised when a queued job has no registered handler."""


def resolve_handler(job_type: str) -> JobHandler:
    if job_type == "knowledge_ingest":
        from app.jobs.handlers.knowledge import handle_knowledge_ingest

        return handle_knowledge_ingest
    if job_type == "conversation_summary":
        from app.jobs.handlers.conversation import handle_conversation_summary

        return handle_conversation_summary
    if job_type == "memory_consolidation":
        from app.jobs.handlers.memory import handle_memory_consolidation

        return handle_memory_consolidation
    raise UnknownJobTypeError(f"unknown job type: {job_type}")


async def process_claimed_job(session: AsyncSession, job: BackgroundJob) -> bool:
    """Run one already-claimed job and persist success/retry state."""
    try:
        handler = resolve_handler(job.job_type)
        await handler(session, dict(job.payload or {}))
    except Exception as exc:
        logger.exception("background job failed", extra={"job_id": str(job.job_id)})
        await session.rollback()
        current = await session.get(BackgroundJob, job.job_id)
        if current is not None:
            await mark_failed(session, current, str(exc))
        return False
    await mark_success(session, job)
    return True


async def run_worker(
    *,
    stop_event: asyncio.Event | None = None,
    poll_interval: float | None = None,
) -> None:
    """Poll until stopped; each job is claimed by exactly one worker."""
    interval = poll_interval or settings.worker_poll_interval
    while stop_event is None or not stop_event.is_set():
        async with async_session() as session:
            job = await claim_next(session)
            if job is None:
                await session.rollback()
            else:
                await session.commit()
                await process_claimed_job(session, job)
                await session.commit()

        if stop_event is None:
            await asyncio.sleep(interval)
        else:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("background worker stopped")


if __name__ == "__main__":  # pragma: no cover
    main()
