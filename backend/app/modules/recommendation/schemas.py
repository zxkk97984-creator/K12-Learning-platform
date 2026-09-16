from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

LearningNextType = Literal[
    "CONTINUE_QUIZ",
    "REVIEW_QUIZ",
    "NEXT_CHAPTER",
    "CONTINUE_READING",
    "START_BOOK",
]


class RecommendationDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recommendation_id: UUID
    student_id: UUID
    recommendation_type: str
    title: str
    description: str
    reason: str
    evidence_ids: list[str]
    related_book_id: UUID | None
    source_ids: list[str]
    license: str | None
    source_url: str | None
    model_info: dict | None
    skill_version: str | None
    expires_at: datetime | None
    status: str
    created_at: datetime
    updated_at: datetime


class LearningNextActionDTO(BaseModel):
    """§6.1 统一下一步行动契约。type/label 用于展示；具体 ID 驱动跳转。"""

    type: LearningNextType
    label: str
    book_id: UUID | None = None
    chapter_id: UUID | None = None
    quiz_session_id: UUID | None = None
    reason: str
    evidence_ids: list[str] = []

