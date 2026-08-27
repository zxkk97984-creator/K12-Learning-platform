from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminPrincipal, require_admin, require_student
from app.api.envelope import ok
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_session
from app.config import settings
from app.infrastructure.rate_limit import rate_limiter
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
    request: Request,
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    # Phase 5-A：登录限流（IP+username 维度，防撞库）
    client_ip = request.client.host if request.client else "unknown"
    result = rate_limiter.check(
        f"login:{client_ip}:{body.username}",
        limit=settings.rate_limit_login_per_minute,
        window_seconds=60,
    )
    if not result.allowed:
        raise HTTPException(
            status_code=429,
            headers={"Retry-After": str(result.retry_after)},
            detail={"code": "RATE_LIMITED", "message": "too many attempts, retry later"},
        )
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


@router.get("/me/admin", response_model=None)
async def get_admin_me(
    admin: Annotated[AdminPrincipal, Depends(require_admin)],
):
    """Phase 5-A：受 require_admin 保护的稳定后台身份 DTO。

    前端登录/刷新时调用此接口做真实后台鉴权验证（不再只信 JWT decode）。
    """
    return ok(
        {
            "admin_id": str(admin.admin_id) if admin.admin_id else None,
            "user_id": str(admin.user_id),
            "display_name": admin.display_name,
            "role_level": admin.role_level,
        }
    )


@router.post("/me/avatar")
async def upload_avatar(
    file: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    data = await file.read()
    return ok(
        await service.upload_avatar(session, user.user_id, file.content_type or "", data)
    )


@router.get("/files/avatars/{filename}")
async def get_avatar_file(filename: str):
    data, media_type = await service.get_avatar_file(filename)
    return Response(content=data, media_type=media_type)


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


@router.get("/teacher-roles")
async def list_teacher_roles(
    _user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    enabled: bool = True,
):
    return ok(await service.list_teacher_roles(session, enabled_only=enabled))
