"""Memory consolidation job handler."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.memory.pipeline import MemoryPipeline


async def handle_memory_consolidation(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    raw_student_id = payload.get("student_id")
    if raw_student_id is None:
        raise ValueError("memory_consolidation payload requires student_id")
    try:
        student_id = UUID(str(raw_student_id))
    except (TypeError, ValueError) as exc:
        raise ValueError("memory_consolidation student_id must be a UUID") from exc
    await MemoryPipeline().process_student(session, student_id)
