from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
import jwt
from fastapi import HTTPException

from app.config import settings


def hash_password(plain: str) -> str:
    """bcrypt 直调（不走 passlib，规避 passlib/bcrypt>=4 兼容问题）。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: UUID, user_type: str) -> tuple[str, datetime]:
    """HS256 JWT，含 sub / user_type / exp（PyJWT）。"""
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": str(subject), "user_type": user_type, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256"), expires_at


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHENTICATED", "message": "invalid or expired token"},
        ) from exc
