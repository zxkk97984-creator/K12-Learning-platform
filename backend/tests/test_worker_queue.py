"""Background job queue and worker routing tests."""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete

from app.config import settings
from app.infrastructure.database.models import BackgroundJob
from app.infrastructure.database.session import async_session
from app.jobs.queue import (
    enqueue,
    claim_next,
    mark_failed,
    mark_success,
    recover_stale_running,
)
from app.jobs.worker import process_claimed_job, run_worker


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


def test_failed_job_retries_twice_then_becomes_failed_on_third_attempt(
    monkeypatch,
) -> None:
    # 关闭退避：本测试在紧循环里连续认领，需让失败任务立即可再次认领。
    monkeypatch.setattr(settings, "worker_backoff_base_seconds", 0.0)
    monkeypatch.setattr(settings, "worker_backoff_max_seconds", 0.0)

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


def test_failed_job_backoff_defers_next_claim(monkeypatch) -> None:
    """D5：失败重试按指数退避延后，退避期内 claim_next 不认领，期满后恢复。"""
    base = settings.worker_backoff_base_seconds
    assert base >= 0.1  # 确保默认真实退避生效（非 0）
    job_id = None
    job_type = f"backoff_probe_{uuid4()}"

    async def run() -> None:
        nonlocal job_id
        async with async_session() as session:
            job = await enqueue(session, job_type, {"test_id": str(uuid4())})
            job_id = job.job_id
            await session.commit()

        # 第一次认领 → 失败（attempt=1），退避期内不可再次认领。
        async with async_session() as session:
            claimed = await claim_next(session, job_type)
            assert claimed is not None and claimed.job_id == job_id
            await session.commit()
        async with async_session() as session:
            running = await session.get(BackgroundJob, job_id)
            await mark_failed(session, running, "boom")
            await session.commit()

        async with async_session() as session:
            deferred = await session.get(BackgroundJob, job_id)
            assert deferred is not None
            assert deferred.status == "queued"
            assert deferred.next_attempt_at is not None
            assert deferred.next_attempt_at > datetime.now(timezone.utc)

        # 退避期内：claim_next 不应认领该任务。
        async with async_session() as session:
            assert await claim_next(session, job_type) is None
            await session.commit()

        # 摸拟退避期满，下一轮可认领。
        async with async_session() as session:
            row = await session.get(BackgroundJob, job_id)
            row.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            await session.commit()
        async with async_session() as session:
            retried = await claim_next(session, job_type)
            assert retried is not None and retried.job_id == job_id
            assert retried.attempt == 2
            await session.commit()

        async with async_session() as session:
            await session.execute(delete(BackgroundJob).where(BackgroundJob.job_id == job_id))
            await session.commit()

    asyncio.run(run())


def test_failed_job_rollback_does_not_poison_worker_failure_path(monkeypatch) -> None:
    """缺陷 A 回归：handler 失败 → rollback 使实例过期 → 访问标量字段。

    旧实现在此处访问 job.job_id 触发同步懒加载并抛 MissingGreenlet，
    异常逃逸导致整个 Worker 进程退出。修复后必须正常返回 False 并把
    任务置回可重试状态。
    """
    # 关退避：与旧口径一致（失败后立即回到可重试 queued），避免跨测试时序放大。
    monkeypatch.setattr(settings, "worker_backoff_base_seconds", 0.0)
    monkeypatch.setattr(settings, "worker_backoff_max_seconds", 0.0)

    async def run() -> None:
        job_type = f"rollback_poison_{uuid4()}"
        async with async_session() as session:
            job = await enqueue(session, job_type, {"test_id": str(uuid4())})
            job_id = job.job_id
            await session.commit()

        async with async_session() as session:
            claimed = await claim_next(session, job_type)
            assert claimed is not None
            await session.commit()
            processed = await process_claimed_job(session, claimed)
            assert processed is False
            await session.commit()

        async with async_session() as session:
            row = await session.get(BackgroundJob, job_id)
            assert row is not None
            assert row.status == "queued"
            assert row.attempt == 1
            assert "unknown job type" in (row.error or "")
            await session.execute(delete(BackgroundJob).where(BackgroundJob.job_id == job_id))
            await session.commit()

    asyncio.run(run())


def test_stale_running_jobs_are_requeued_after_ttl() -> None:
    """缺陷 A 回归：崩溃 Worker 遗留的 running 任务必须能被回收重排。"""

    async def run() -> None:
        stale_id = uuid4()
        fresh_id = uuid4()
        now = datetime.now(timezone.utc)
        async with async_session() as session:
            session.add(
                BackgroundJob(
                    job_id=stale_id,
                    job_type=f"stale_probe_{uuid4()}",
                    status="running",
                    attempt=2,
                    payload={"probe": "stale"},
                    started_at=now - timedelta(seconds=9999),
                )
            )
            session.add(
                BackgroundJob(
                    job_id=fresh_id,
                    job_type=f"fresh_probe_{uuid4()}",
                    status="running",
                    attempt=1,
                    payload={"probe": "fresh"},
                    started_at=now,
                )
            )
            await session.commit()

        try:
            async with async_session() as session:
                recovered = await recover_stale_running(session)
                await session.commit()
            assert recovered >= 1

            async with async_session() as session:
                stale = await session.get(BackgroundJob, stale_id)
                assert stale is not None
                assert stale.status == "queued"
                assert stale.attempt == 2  # attempt 不回退，重试上限语义保持
                assert "stale-running recovery" in (stale.error or "")
                fresh = await session.get(BackgroundJob, fresh_id)
                assert fresh is not None
                assert fresh.status == "running"
                assert "stale-running recovery" not in (fresh.error or "")
        finally:
            async with async_session() as session:
                await session.execute(
                    delete(BackgroundJob).where(
                        BackgroundJob.job_id.in_([stale_id, fresh_id])
                    )
                )
                await session.commit()

    asyncio.run(run())


def test_worker_loop_survives_bad_job_and_processes_next(monkeypatch) -> None:
    """端到端：坏任务重试耗尽后，Worker 必须继续消费后续任务且不退出。"""

    # 关闭退避：让坏任务在测试窗口内快速耗尽 max_attempts 次重试收敛为 failed。
    monkeypatch.setattr(settings, "worker_backoff_base_seconds", 0.0)
    monkeypatch.setattr(settings, "worker_backoff_max_seconds", 0.0)

    async def run() -> None:
        import app.jobs.worker as worker_mod

        real_claim_next = worker_mod.claim_next
        processed: list[str] = []
        stop_event = asyncio.Event()

        bad_type = f"boom_{uuid4()}"
        good_type = f"good_{uuid4()}"

        async def boom_handler(_session, _payload):
            raise RuntimeError("poison payload")

        async def ok_handler(_session, payload):
            processed.append(payload["marker"])

        def fake_resolve(job_type: str):
            return boom_handler if job_type.startswith("boom_") else ok_handler

        async def filtered_claim_next(session, job_type=None):
            # 只认领本测试的两个任务类型，绝不触碰开发库中的真实队列。
            for target in (bad_type, good_type):
                job = await real_claim_next(session, target)
                if job is not None:
                    return job
            return None

        monkeypatch.setattr(worker_mod, "resolve_handler", fake_resolve)
        monkeypatch.setattr(worker_mod, "claim_next", filtered_claim_next)

        job_ids: dict[str, object] = {}
        async with async_session() as session:
            bad = await enqueue(session, bad_type, {"marker": "bad"})
            good = await enqueue(session, good_type, {"marker": "good"})
            job_ids = {"bad": bad.job_id, "good": good.job_id}
            await session.commit()

        task = asyncio.create_task(
            run_worker(stop_event=stop_event, poll_interval=0.05)
        )
        try:
            for _ in range(200):  # 最多等待 ~10s
                await asyncio.sleep(0.05)
                if processed:
                    break
            assert processed == ["good"], (
                f"Worker 未在坏任务失败后继续消费后续任务：{processed}"
            )

            # 坏任务按 max_attempts 重试后必须收敛为 failed，而非永久 running。
            max_attempts = settings.worker_max_attempts
            for _ in range(200):
                async with async_session() as session:
                    row = await session.get(BackgroundJob, job_ids["bad"])
                    if row is not None and row.status == "failed":
                        break
                await asyncio.sleep(0.05)
            assert row is not None and row.status == "failed"
            assert row.attempt == max_attempts
            assert "poison payload" in (row.error or "")

            async with async_session() as session:
                good_row = await session.get(BackgroundJob, job_ids["good"])
                assert good_row is not None
                assert good_row.status == "success"
        finally:
            stop_event.set()
            await asyncio.wait_for(task, timeout=15)
        assert task.exception() is None

        async with async_session() as session:
            await session.execute(
                delete(BackgroundJob).where(
                    BackgroundJob.job_id.in_([job_ids["bad"], job_ids["good"]])
                )
            )
            await session.commit()

    asyncio.run(run())
