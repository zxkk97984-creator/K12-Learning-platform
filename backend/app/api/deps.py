from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import User
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
