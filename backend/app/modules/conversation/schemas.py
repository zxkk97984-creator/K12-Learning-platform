from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ConversationStatus = Literal["ACTIVE", "ARCHIVED", "DELETED"]
ConversationChannel = Literal["TEXT", "VOICE"]
MessageRole = Literal["STUDENT", "TEACHER", "SYSTEM"]
MessageType = Literal[
    "TEXT",
    "QUIZ",
    "TOOL_STATUS",
    "HINT",
    "RECOMMENDATION",
    "SYSTEM",
    "LEARNING_SUMMARY",
]


class CreateConversationRequest(BaseModel):
    teacher_role_id: UUID | None = None
    channel: ConversationChannel = "TEXT"
    title: str | None = Field(default=None, max_length=255)


class PatchConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    # ACTIVE is accepted here so the service can return the required 409 for
    # the invalid DELETED -> ACTIVE transition instead of a schema 422.
    status: ConversationStatus | None = None


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1)
    type: Literal["TEXT"] = "TEXT"
    screen_context: dict[str, Any] | None = None
    selected_text: str | None = None


class QuizReviewContext(BaseModel):
    """§4.3 错题讲解的屏幕上下文契约。

    后端只信这里的 ID 并从自己的快照查题干/作答/解析，绝不凭客户端传来的
    正确答案或归属结论。ID 可空：有 quiz_session_id 而无 question_id 时，
    服务端明确「还不知道要讲哪一题」。
    """

    quiz_session_id: UUID | None = None
    question_id: UUID | None = None

    @classmethod
    def from_screen_context(cls, screen_context: dict[str, Any] | None) -> "QuizReviewContext":
        if not screen_context:
            return cls()
        raw = screen_context
        # 兼容前端 camelCase 与既有 snake_case 两种来源；ID 畸形按缺失处理，不炸对话。
        quiz = raw.get("quizSessionId") or raw.get("quiz_session_id")
        question = raw.get("questionId") or raw.get("question_id")
        quiz_uuid = None
        question_uuid = None
        try:
            quiz_uuid = UUID(str(quiz)) if quiz is not None else None
        except (ValueError, TypeError, AttributeError):
            quiz_uuid = None
        try:
            question_uuid = UUID(str(question)) if question is not None else None
        except (ValueError, TypeError, AttributeError):
            question_uuid = None
        return cls(quiz_session_id=quiz_uuid, question_id=question_uuid)


class ConversationListItemDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversation_id: UUID
    title: str | None
    status: ConversationStatus
    channel: ConversationChannel
    teacher_role_id: UUID | None
    # Phase 4：真实教师风格摘要（名称/语气），不再恒为 null
    teacher_role: dict | None = None
    # 列表页最近一条消息预览（内容截断），详情见 recent_messages
    last_message_preview: str | None = None
    last_message_at: datetime | None
    updated_at: datetime


class ConversationDTO(ConversationListItemDTO):
    student_id: UUID
    current_page_context: dict
    recent_messages: list
    conversation_summary: str | None


class MessageDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: UUID
    conversation_id: UUID
    role: MessageRole
    type: MessageType
    content: str
    metadata: dict
    sequence: int
    model_info: dict | None
    created_at: datetime


class ConversationSummaryDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary_id: UUID
    conversation_id: UUID
    summary: str
    token_count: int
    summary_version: int
    source_message_ids: list
    model_info: dict | None
    created_at: datetime
    updated_at: datetime


class PageMeta(BaseModel):
    next_cursor: str | None
    has_more: bool
