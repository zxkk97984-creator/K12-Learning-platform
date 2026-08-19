from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_student
from app.api.envelope import ok
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_session
from app.modules.knowledge.schemas import (
    KnowledgeSearchRequest,
    ResourceStatus,
)
from app.modules.knowledge.service import KnowledgeService

router = APIRouter(tags=["knowledge"])
service = KnowledgeService()


async def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.user_type != "ADMIN":
        raise HTTPException(
            status_code=403,
            detail={"code": "ADMIN_ONLY", "message": "admin access required"},
        )
    return user


@router.get("/knowledge/resources")
async def list_resources(
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    status: ResourceStatus = Query(default="READY"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    rows, next_cursor, has_more = await service.list_resources(
        session,
        status=status,
        cursor=cursor,
        limit=limit,
    )
    return ok(rows, {"next_cursor": next_cursor, "has_more": has_more})


@router.get("/knowledge/resources/{resource_id}")
async def get_resource(
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    resource_id: UUID,
):
    return ok(await service.get_resource(session, resource_id))


@router.get("/knowledge/resources/{resource_id}/chunks")
async def list_chunks(
    _admin: Annotated[User, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    resource_id: UUID,
):
    return ok(await service.list_chunks(session, resource_id))


@router.post("/knowledge/search")
async def search_knowledge(
    _student: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    body: KnowledgeSearchRequest,
):
    return ok(await service.search(session, body))
