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
    status: str
    created_at: datetime
    updated_at: datetime
