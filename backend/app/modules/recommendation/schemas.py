from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
