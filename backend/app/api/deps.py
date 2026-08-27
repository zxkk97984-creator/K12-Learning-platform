from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.infrastructure.database.models import Admin, User
from app.infrastructure.database.session import get_session
from app.modules.identity.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def _unauthenticated(message: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"code": "UNAUTHENTICATED", "message": message},
    )


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if credentials is None:
        raise _unauthenticated("missing bearer token")
    payload = decode_access_token(credentials.credentials)
    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise _unauthenticated("invalid token subject") from exc
    user = await session.get(User, user_id)
    if user is None:
        raise _unauthenticated("user not found")
    # Phase 5-A：禁用账号立即失效（所有使用本依赖的 API 一致生效）
    if getattr(user, "status", "ACTIVE") == "DISABLED":
        raise HTTPException(
            status_code=401,
            detail={"code": "ACCOUNT_DISABLED", "message": "account is disabled"},
        )
    # 可观测性：把已认证用户挂到 request.state，访问日志可安全引用
    request.state.user_id = str(user.user_id)
    return user


async def require_student(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.user_type != "STUDENT":
        raise HTTPException(
            status_code=403,
            detail={"code": "FORBIDDEN", "message": "student access required"},
        )
    return user


@dataclass
class AdminPrincipal:
    admin_id: UUID | None
    user_id: UUID
    display_name: str
    role_level: str


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AdminPrincipal:
    """Phase 5-A：严格后台鉴权——必须 ADMIN 用户且存在 enabled 的 admins 行。

    移除旧「Legacy compatibility」放行路径：无 admins 行返回
    403 ADMIN_PROFILE_REQUIRED。
    """
    if user.user_type != "ADMIN":
        raise HTTPException(
            status_code=403,
            detail={"code": "ADMIN_ONLY", "message": "admin access required"},
        )
    admin = (
        await session.execute(
            select(Admin).where(
                Admin.user_id == user.user_id,
                Admin.enabled.is_(True),
            )
        )
    ).scalar_one_or_none()
    if admin is None:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "ADMIN_PROFILE_REQUIRED",
                "message": "admin profile row missing or disabled",
            },
        )
    return AdminPrincipal(
        admin_id=admin.admin_id,
        user_id=admin.user_id,
        display_name=admin.display_name,
        role_level=admin.role_level,
    )
