from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

MemoryType = Literal["PROFILE", "PREFERENCE", "LEARNING", "EPISODIC"]
MemoryConfidence = Literal["LOW", "MEDIUM", "HIGH"]
MemoryStatus = Literal["ACTIVE", "DISPUTED", "SUPERSEDED", "REMOVED"]
MemoryAction = Literal["CONFIRM", "DISPUTE", "FORGET", "EDIT"]
CandidateStatus = Literal["PENDING", "APPROVED", "REJECTED", "MERGED"]
EvidenceSourceType = Literal[
    "QUIZ", "LEARNING_SESSION", "CONVERSATION", "BOOK_PROGRESS"
]
InsightType = Literal[
    "STRENGTH", "WEAKNESS", "UNDERSTANDING", "HABIT", "CHANGE", "INTEREST"
]
InsightLevel = Literal["偏弱", "一般", "较稳定", "较强", "仍需观察"]
InsightStatus = Literal["ACTIVE", "SUPERSEDED"]
EpisodeImportance = Literal["LOW", "MEDIUM", "HIGH"]


class StudentMemoryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    memory_id: UUID
    memory_type: MemoryType
    content: str
    tags: list
    confidence: MemoryConfidence
    status: MemoryStatus
    evidence_ids: list
    origin_candidate_id: UUID | None
    user_confirmed: bool
    created_at: datetime
    updated_at: datetime
    confirmed_at: datetime | None


class MemoryCandidateDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    candidate_id: UUID
    student_id: UUID
    candidate_type: MemoryType
    content: str
    proposed_memory: dict
    evidence_ids: list
    confidence: MemoryConfidence
    status: CandidateStatus
    rule_version: str
    model_info: dict
    created_at: datetime
    resolved_at: datetime | None


class MemoryEvidenceDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: UUID
    source_type: EvidenceSourceType
    event_ids: list
    payload: dict
    count: int
    first_occurred_at: datetime | None
    last_occurred_at: datetime | None
    derived_at: datetime
    rule_version: str


class ProfileInsightDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    insight_id: UUID
    student_id: UUID
    insight_type: InsightType
    dimension: str
    level: InsightLevel
    description: str
    evidence_ids: list
    status: InsightStatus
    valid_from: datetime
    valid_until: datetime | None
    rule_version: str
    model_info: dict | None
    created_at: datetime
    updated_at: datetime


class StudentEpisodeDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    episode_id: UUID
    student_id: UUID
    title: str
    summary: str
    occurred_at: datetime
    event_ids: list
    book_id: UUID | None
    chapter_id: UUID | None
    knowledge_point_ids: list
    importance: EpisodeImportance
    tags: list
    created_at: datetime


class PatchMemoryRequest(BaseModel):
    action: MemoryAction
    content: str | None = Field(default=None)
