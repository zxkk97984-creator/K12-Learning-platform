from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import StudentPreference, StudentProfile, User
from app.modules.identity.schemas import (
    AuthDTO,
    AuthUser,
    StudentPreferenceDTO,
    StudentPreferencePatch,
    StudentProfileDTO,
    StudentProfilePatch,
)
from app.modules.identity.security import create_access_token, verify_password


def derive_stage(grade: int) -> str:
    if 1 <= grade <= 6:
        return "PRIMARY"
    if 7 <= grade <= 9:
        return "JUNIOR"
    return "SENIOR"


def to_profile_dto(profile: StudentProfile) -> StudentProfileDTO:
    return StudentProfileDTO(
        student_id=profile.student_id,
        nickname=profile.nickname,
        avatar_url=profile.avatar_url,
        grade=profile.grade,
        stage=derive_stage(profile.grade),  # type: ignore[arg-type]
        birth_date=profile.birth_date,
        language=profile.language,
        learning_goal=profile.learning_goal,
        current_teacher_role_id=profile.current_teacher_role_id,
        learning_days=profile.learning_days,
        total_learning_minutes=profile.total_learning_minutes,
        completed_books=profile.completed_books,
        completed_chapters=profile.completed_chapters,
        quiz_count=profile.quiz_count,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def to_preference_dto(preference: StudentPreference) -> StudentPreferenceDTO:
    return StudentPreferenceDTO(
        preference_id=preference.preference_id,
        student_id=preference.student_id,
        preferred_explanation_style=preference.preferred_explanation_style,
        preferred_difficulty=preference.preferred_difficulty,
        preferred_session_length=preference.preferred_session_length,
        voice_preference=preference.voice_preference,
        active_questioning_enabled=preference.active_questioning_enabled,
        daily_learning_minutes=preference.daily_learning_minutes,
        evidence_ids=preference.evidence_ids,
        updated_at=preference.updated_at,
    )


class IdentityService:
    """身份/学生档案 Domain Service（Router 只做编排，SQL 在此层）。"""

    async def login(self, session: AsyncSession, username: str, password: str) -> AuthDTO:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=401,
                detail={"code": "INVALID_CREDENTIALS", "message": "invalid username or password"},
            )
        user.last_login_at = datetime.now(timezone.utc)
        await session.commit()
        token, expires_at = create_access_token(user.user_id, user.user_type)
        return AuthDTO(
            access_token=token,
            token_type="Bearer",
            expires_at=expires_at,
            user=AuthUser(user_id=user.user_id, username=user.username, user_type=user.user_type),
        )

    async def get_profile(self, session: AsyncSession, user_id: UUID) -> StudentProfile:
        result = await session.execute(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "STUDENT_PROFILE_NOT_FOUND", "message": "student profile not found"},
            )
        return profile

    async def get_me(self, session: AsyncSession, user_id: UUID) -> StudentProfileDTO:
        return to_profile_dto(await self.get_profile(session, user_id))

    async def update_me(
        self, session: AsyncSession, user_id: UUID, patch: StudentProfilePatch
    ) -> StudentProfileDTO:
        profile = await self.get_profile(session, user_id)
        nullable_fields = {"avatar_url", "birth_date", "learning_goal", "current_teacher_role_id"}
        for key, value in patch.model_dump(exclude_unset=True).items():
            if value is None and key not in nullable_fields:
                continue
            setattr(profile, key, value)
        await session.commit()
        await session.refresh(profile)
        return to_profile_dto(profile)

    async def get_or_create_preference(
        self, session: AsyncSession, profile: StudentProfile
    ) -> StudentPreference:
        result = await session.execute(
            select(StudentPreference).where(StudentPreference.student_id == profile.student_id)
        )
        preference = result.scalar_one_or_none()
        if preference is not None:
            return preference
        preference = StudentPreference(student_id=profile.student_id)
        session.add(preference)
        await session.commit()
        await session.refresh(preference)
        return preference

    async def get_preferences(
        self, session: AsyncSession, user_id: UUID
    ) -> StudentPreferenceDTO:
        profile = await self.get_profile(session, user_id)
        return to_preference_dto(await self.get_or_create_preference(session, profile))

    async def update_preferences(
        self, session: AsyncSession, user_id: UUID, patch: StudentPreferencePatch
    ) -> StudentPreferenceDTO:
        profile = await self.get_profile(session, user_id)
        preference = await self.get_or_create_preference(session, profile)
        for key, value in patch.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(preference, key, value)
        await session.commit()
        await session.refresh(preference)
        return to_preference_dto(preference)
