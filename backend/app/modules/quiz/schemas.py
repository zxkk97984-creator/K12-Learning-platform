from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

QuizKind = Literal["CHAPTER_QUIZ", "AI_QUIZ"]
QuizStatus = Literal["GENERATING", "ACTIVE", "COMPLETED", "ABANDONED"]
QuizDifficulty = Literal["EASY", "MEDIUM", "HARD"]
QuizQuestionType = Literal[
    "SINGLE_CHOICE", "MULTIPLE_CHOICE", "TRUE_FALSE", "FILL_BLANK"
]
QuizInteractionType = Literal[
    "HINT_REQUEST",
    "HINT_RESPONSE",
    "QUESTION_ASK",
    "TEACHER_REPLY",
    "ANSWER_SUBMIT",
    "ANSWER_RESULT",
]


class CreateQuizSessionRequest(BaseModel):
    conversation_id: UUID
    book_id: UUID | None = None
    chapter_id: UUID | None = None
    quiz_kind: QuizKind = "CHAPTER_QUIZ"
    question_count: int = Field(default=3, ge=1, le=10)
    difficulty: QuizDifficulty = "MEDIUM"


class QuizSessionListItemDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quiz_session_id: UUID
    title: str
    quiz_kind: QuizKind
    status: QuizStatus
    book_id: UUID | None
    chapter_id: UUID | None
    result_summary: dict[str, Any] | None
    ai_feedback: str | None
    skill_version: str
    created_at: datetime
    completed_at: datetime | None


class QuizSessionDTO(QuizSessionListItemDTO):
    student_id: UUID
    conversation_id: UUID
    teacher_role_id: UUID | None
    questions_snapshot: list[dict[str, Any]]
    duration_seconds: int
    model_info: dict[str, Any]
    updated_at: datetime


class QuizOptionDTO(BaseModel):
    key: str
    text: str


class QuizQuestionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_id: UUID
    quiz_session_id: UUID
    question_order: int
    question_type: QuizQuestionType
    stem: str
    options: list[QuizOptionDTO]
    correct_answer: dict[str, Any] | None = None
    explanation: str | None = None
    source_context: dict[str, Any] | None
    interaction_policy: dict[str, Any]
    knowledge_point_ids: list


class SubmitQuizAnswerRequest(BaseModel):
    answer: dict[str, Any]
    hint_level_at_submit: int = Field(default=0, ge=0)


class QuizAnswerDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    answer_id: UUID
    quiz_session_id: UUID
    question_id: UUID
    student_id: UUID
    submitted_answer: dict[str, Any]
    is_correct: bool
    attempt_no: int
    hint_level_at_submit: int
    is_final: bool
    submitted_at: datetime
    created_at: datetime


class QuizInteractionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    interaction_id: UUID
    quiz_session_id: UUID
    question_id: UUID | None
    interaction_type: QuizInteractionType
    payload: dict[str, Any]
    message_id: UUID | None
    answer_id: UUID | None
    sequence: int
    created_at: datetime


class QuizHintDTO(BaseModel):
    hint_level: int
    hint_text: str
    max_hint_level: int
    interaction_id: UUID


class QuizPageMeta(BaseModel):
    next_cursor: str | None
    has_more: bool
