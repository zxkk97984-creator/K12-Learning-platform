from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.infrastructure.database.models import Admin, User
from app.infrastructure.database.session import get_session
from app.modules.identity.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHENTICATED", "message": "missing bearer token"},
        )
    payload = decode_access_token(credentials.credentials)
    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHENTICATED", "message": "invalid token subject"},
        ) from exc
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHENTICATED", "message": "user not found"},
        )
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
    if admin is not None:
        return AdminPrincipal(
            admin_id=admin.admin_id,
            user_id=admin.user_id,
            display_name=admin.display_name,
            role_level=admin.role_level,
        )
    # Legacy compatibility: user_type=ADMIN without an admins row still passes,
    # but writes that need an admin_id must ensure the row exists.
    return AdminPrincipal(
        admin_id=None,
        user_id=user.user_id,
        display_name=user.username,
        role_level="SUPERVISOR",
    )
