"""Manual Memory Pipeline recompute (Phase 7 rule version).

Usage:
    uv run python -m app.scripts.rebuild_memory [--student xiaoming]

For xiaoming with no learning events yet, a small deterministic demo event
set is seeded so the 16.7 evidence-traceability acceptance path can be shown.
"""

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select

from app.infrastructure.database.engine import engine
from app.infrastructure.database.models import LearningEvent, StudentProfile, User
from app.infrastructure.database.session import async_session
from app.modules.memory.pipeline import MemoryPipeline


async def _ensure_demo_events(student_id: UUID) -> None:
    async with async_session() as session:
        count = (
            await session.execute(
                select(func.count(LearningEvent.event_id)).where(
                    LearningEvent.student_id == student_id
                )
            )
        ).scalar_one()
        if count and count > 0:
            return
        now = datetime.now(timezone.utc)
        demo_events = [
            (
                "ANSWER_CORRECT",
                now - timedelta(minutes=12),
                {"question_id": "demo-question-1", "attempt_no": 1},
            ),
            (
                "ANSWER_CORRECT",
                now - timedelta(minutes=8),
                {"question_id": "demo-question-2", "attempt_no": 1},
            ),
            (
                "EXPLAIN_REQUESTED",
                now - timedelta(minutes=5),
                {"route": "chapter_reader", "page_type": "chapter_reader"},
            ),
            (
                "EXPLAIN_REQUESTED",
                now - timedelta(minutes=2),
                {"route": "chapter_reader", "page_type": "chapter_reader"},
            ),
        ]
        for event_type, occurred_at, payload in demo_events:
            session.add(
                LearningEvent(
                    student_id=student_id,
                    event_type=event_type,
                    occurred_at=occurred_at,
                    payload=payload,
                )
            )
        await session.commit()


async def rebuild(username: str | None) -> None:
    async with async_session() as session:
        query = select(StudentProfile)
        if username is not None:
            user = (
                await session.execute(
                    select(User).where(User.username == username)
                )
            ).scalar_one_or_none()
            if user is None:
                raise SystemExit(f"unknown student: {username}")
            query = query.where(StudentProfile.user_id == user.user_id)
        profiles = (await session.execute(query)).scalars().all()
    for profile in profiles:
        if username == "xiaoming":
            await _ensure_demo_events(profile.student_id)
        async with async_session() as session:
            result = await MemoryPipeline().process_student(
                session, profile.student_id, force_insights=True
            )
            print(
                f"rebuild_memory: student={profile.student_id} "
                f"processed={result['processed_events']} groups={result['groups']}"
            )
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild memory pipeline")
    parser.add_argument("--student", default=None, help="username filter")
    args = parser.parse_args()
    asyncio.run(rebuild(args.student))


if __name__ == "__main__":
    main()
