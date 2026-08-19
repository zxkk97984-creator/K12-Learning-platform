from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_student
from app.api.envelope import ok
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_session
from app.modules.memory.schemas import (
    EpisodeImportance,
    InsightStatus,
    InsightType,
    MemoryStatus,
    MemoryType,
    PatchMemoryRequest,
)
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


@router.get("/me/insights")
async def list_insights(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    status: InsightStatus = Query(default="ACTIVE"),
    insight_type: InsightType | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    rows, next_cursor, has_more = await service.list_insights(
        session,
        user.user_id,
        status=status,
        insight_type=insight_type,
        cursor=cursor,
        limit=limit,
    )
    return ok(rows, {"next_cursor": next_cursor, "has_more": has_more})


@router.get("/me/insights/{insight_id}")
async def get_insight(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    insight_id: UUID,
):
    insight, evidence = await service.get_insight(session, user.user_id, insight_id)
    return ok(insight, {"evidence": evidence})


@router.get("/me/episodes")
async def list_episodes(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    importance: EpisodeImportance | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    rows, next_cursor, has_more = await service.list_episodes(
        session,
        user.user_id,
        importance=importance,
        cursor=cursor,
        limit=limit,
    )
    return ok(rows, {"next_cursor": next_cursor, "has_more": has_more})


@router.get("/me/episodes/{episode_id}")
async def get_episode(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    episode_id: UUID,
):
    episode = await service.get_episode(session, user.user_id, episode_id)
    return ok(episode)
