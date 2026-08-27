"""Worker loop and job-type dispatch for PostgreSQL background jobs."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.infrastructure.database.models import BackgroundJob
from app.infrastructure.database.session import async_session
from app.jobs.queue import (
    claim_next,
    mark_failed,
    mark_success,
    recover_stale_running,
)

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
    """Run one already-claimed job and persist success/retry state.

    注意：必须在触碰 session 前先把 job 的标量字段捕获到局部变量。
    handler 失败后的 ``session.rollback()`` 会使 ORM 实例属性过期，此后再访问
    ``job.job_id`` 会触发同步惰性加载并抛出 MissingGreenlet（缺陷 A 根因），
    因此失败/成功收尾一律通过局部 job_id 重新查询实例。
    """
    job_id = job.job_id
    job_type = job.job_type
    payload = dict(job.payload or {})
    try:
        handler = resolve_handler(job_type)
        await handler(session, payload)
    except Exception as exc:
        logger.exception("background job failed", extra={"job_id": str(job_id)})
        await session.rollback()
        current = await session.get(BackgroundJob, job_id)
        if current is not None:
            await mark_failed(session, current, str(exc))
        return False
    finished = await session.get(BackgroundJob, job_id)
    if finished is not None:
        await mark_success(session, finished)
    return True


async def run_worker(
    *,
    stop_event: asyncio.Event | None = None,
    poll_interval: float | None = None,
) -> None:
    """Poll until stopped; each job is claimed by exactly one worker.

    单个任务的任何异常（包括 process_claimed_job 内部的意外错误）都不允许
    终止 Worker：循环体整体兜底，记日志后继续下一轮。崩溃瞬间被认领的任务
    会停留在 running，由 recover_stale_running 在后续轮次按 TTL 回收。
    """
    interval = poll_interval or settings.worker_poll_interval
    while stop_event is None or not stop_event.is_set():
        try:
            async with async_session() as session:
                recovered = await recover_stale_running(session)
                job = await claim_next(session)
                # 即使没有认领到任务也要提交：stale 回收的变更不能被回滚丢弃。
                await session.commit()
            if recovered:
                logger.warning("recovered %d stale running job(s)", recovered)
            if job is not None:
                await process_claimed_job(session, job)
                await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("worker loop iteration failed; continuing")

        if stop_event is None:
            await asyncio.sleep(interval)
        else:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except TimeoutError:
                pass


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("background worker stopped")


if __name__ == "__main__":  # pragma: no cover
    main()
