from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ExplanationStyle = Literal[
    "EXAMPLE_BASED", "VISUAL", "STORY", "DIRECT_DEFINITION", "STEP_BY_STEP", "CODE", "INTERACTIVE"
]
PreferredDifficulty = Literal["EASY", "MEDIUM", "HARD"]
PreferredSessionLength = Literal["SHORT", "MEDIUM", "LONG"]
Stage = Literal["PRIMARY", "JUNIOR", "SENIOR"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1)


class AuthUser(BaseModel):
    user_id: UUID
    username: str
    user_type: str


class AuthDTO(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_at: datetime
    user: AuthUser


class StudentProfileDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_id: UUID
    nickname: str
    avatar_url: str | None
    grade: int
    stage: Stage
    birth_date: date | None
    language: str
    learning_goal: str | None
    current_teacher_role_id: UUID | None
    learning_days: int
    total_learning_minutes: int
    completed_books: int
    completed_chapters: int
    quiz_count: int
    created_at: datetime
    updated_at: datetime


class StudentProfilePatch(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=32)
    avatar_url: str | None = Field(default=None, max_length=512)
    grade: int | None = Field(default=None, ge=1, le=12)
    birth_date: date | None = None
    language: str | None = Field(default=None, min_length=1, max_length=16)
    learning_goal: str | None = Field(default=None, max_length=2000)
    current_teacher_role_id: UUID | None = None


class VoicePreference(BaseModel):
    input_enabled: bool = True
    tts_enabled: bool = True
    volume: float = Field(default=0.8, ge=0, le=1)
    speed: float = Field(default=1.0, ge=0.1, le=3)


class StudentPreferenceDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    preference_id: UUID
    student_id: UUID
    preferred_explanation_style: ExplanationStyle
    preferred_difficulty: PreferredDifficulty
    preferred_session_length: PreferredSessionLength
    voice_preference: VoicePreference
    active_questioning_enabled: bool
    daily_learning_minutes: int
    evidence_ids: list
    updated_at: datetime


class StudentPreferencePatch(BaseModel):
    preferred_explanation_style: ExplanationStyle | None = None
    preferred_difficulty: PreferredDifficulty | None = None
    preferred_session_length: PreferredSessionLength | None = None
    voice_preference: VoicePreference | None = None
    active_questioning_enabled: bool | None = None
    daily_learning_minutes: int | None = Field(default=None, ge=0)
