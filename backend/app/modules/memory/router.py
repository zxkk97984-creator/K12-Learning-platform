from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_student
from app.api.envelope import ok
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_session
from app.modules.memory.schemas import MemoryStatus, MemoryType, PatchMemoryRequest
from app.modules.memory.service import MemoryService

router = APIRouter(tags=["memory"])
service = MemoryService()


@router.get("/me/memories")
async def list_memories(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    status: MemoryStatus = Query(default="ACTIVE"),
    memory_type: MemoryType | None = Query(default=None),
):
    memories = await service.list_memories(
        session,
        user.user_id,
        status=status,
        memory_type=memory_type,
    )
    return ok(memories)


@router.patch("/me/memories/{memory_id}")
async def patch_memory(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    memory_id: UUID,
    body: PatchMemoryRequest,
):
    memory = await service.patch_memory(session, user.user_id, memory_id, body)
    return ok(memory)


@router.get("/me/evidence/{evidence_id}")
async def get_evidence(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    evidence_id: UUID,
):
    evidence = await service.get_evidence(session, user.user_id, evidence_id)
    return ok(evidence)
