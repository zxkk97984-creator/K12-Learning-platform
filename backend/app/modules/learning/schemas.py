from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

LearningSessionStatus = Literal["ACTIVE", "ENDED", "ABANDONED"]
BookProgressStatus = Literal["NOT_STARTED", "READING", "COMPLETED"]
LearningEventType = Literal[
    "CHAPTER_STARTED",
    "CHAPTER_FINISHED",
    "SECTION_READ",
    "KNOWLEDGE_CARD_VIEWED",
    "HELP_REQUESTED",
    "EXPLAIN_REQUESTED",
    "SUMMARY_REQUESTED",
    "QUIZ_CREATED",
    "QUIZ_ANSWERED",
    "ANSWER_CORRECT",
    "ANSWER_WRONG",
    "HINT_REQUESTED",
    "QUESTION_ASKED",
    "BOOK_STARTED",
    "BOOK_FINISHED",
    "VOICE_SESSION_STARTED",
    "VOICE_SESSION_ENDED",
    "ROLE_SWITCHED",
    "TEXT_SELECTED",
]


class CreateLearningSessionRequest(BaseModel):
    book_id: UUID
    chapter_id: UUID
    entry_route: str | None = Field(default=None, max_length=64)


class PatchLearningSessionRequest(BaseModel):
    status: Literal["ENDED", "ABANDONED"]


class LearningSessionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: UUID
    student_id: UUID
    book_id: UUID
    chapter_id: UUID
    started_at: datetime
    ended_at: datetime | None
    duration_seconds: int
    status: LearningSessionStatus
    entry_route: str | None
    created_at: datetime


class CreateLearningEventRequest(BaseModel):
    session_id: UUID | None = None
    event_type: LearningEventType
    occurred_at: datetime
    book_id: UUID | None = None
    chapter_id: UUID | None = None
    block_id: UUID | None = None
    knowledge_point_ids: list[UUID] = Field(default_factory=list)
    conversation_id: UUID | None = None
    quiz_session_id: UUID | None = None
    payload: dict = Field(default_factory=dict)


class LearningEventDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: UUID
    student_id: UUID
    session_id: UUID | None
    event_type: LearningEventType
    occurred_at: datetime
    book_id: UUID | None
    chapter_id: UUID | None
    block_id: UUID | None
    knowledge_point_ids: list
    conversation_id: UUID | None
    quiz_session_id: UUID | None
    payload: dict
    created_at: datetime


class BookProgressDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    progress_id: UUID
    student_id: UUID
    book_id: UUID
    chapter_id: UUID | None
    block_id: UUID | None
    status: BookProgressStatus
    position_percent: int
    last_read_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    total_seconds: int
    updated_at: datetime


class UpsertBookProgressRequest(BaseModel):
    chapter_id: UUID | None = None
    block_id: UUID | None = None
    status: BookProgressStatus | None = None
    position_percent: int | None = Field(default=None, ge=0, le=100)


class EventPageMeta(BaseModel):
    next_cursor: str | None
    has_more: bool


class EventPageDTO(BaseModel):
    items: list[LearningEventDTO]
    meta: EventPageMeta
