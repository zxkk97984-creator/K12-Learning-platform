from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_student
from app.api.envelope import ok
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_session
from app.modules.identity.schemas import (
    LoginRequest,
    StudentPreferencePatch,
    StudentProfilePatch,
)
from app.modules.identity.service import IdentityService

router = APIRouter(tags=["identity"])
service = IdentityService()


@router.post("/auth/login")
async def login(
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    return ok(await service.login(session, body.username, body.password))


@router.post("/auth/logout", status_code=204)
async def logout(user: Annotated[User, Depends(require_student)]):
    # MVP 无服务端会话状态（0-D §1.2）；客户端丢弃令牌即可
    return Response(status_code=204)


@router.get("/me")
async def get_me(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    return ok(await service.get_me(session, user.user_id))


@router.patch("/me")
async def update_me(
    body: StudentProfilePatch,
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    return ok(await service.update_me(session, user.user_id, body))


@router.get("/me/preferences")
async def get_preferences(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    return ok(await service.get_preferences(session, user.user_id))


@router.patch("/me/preferences")
async def update_preferences(
    body: StudentPreferencePatch,
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    return ok(await service.update_preferences(session, user.user_id, body))
