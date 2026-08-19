from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class User(Base):
    """users（0-E §3.1）。"""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("user_type IN ('STUDENT','ADMIN')", name="ck_users_user_type"),
        CheckConstraint("status IN ('ACTIVE','DISABLED')", name="ck_users_status"),
        Index(
            "uq_users_email",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
        Index(
            "uq_users_phone",
            "phone",
            unique=True,
            postgresql_where=text("phone IS NOT NULL"),
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    username: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(255))
    user_type: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'ACTIVE'"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StudentProfile(Base):
    """student_profiles（0-E §3.2）。"""

    __tablename__ = "student_profiles"
    __table_args__ = (
        CheckConstraint("grade BETWEEN 1 AND 12", name="ck_student_profiles_grade"),
        CheckConstraint("learning_days >= 0", name="ck_student_profiles_learning_days"),
        CheckConstraint(
            "total_learning_minutes >= 0", name="ck_student_profiles_total_minutes"
        ),
        CheckConstraint("completed_books >= 0", name="ck_student_profiles_completed_books"),
        CheckConstraint(
            "completed_chapters >= 0", name="ck_student_profiles_completed_chapters"
        ),
        CheckConstraint("quiz_count >= 0", name="ck_student_profiles_quiz_count"),
    )

    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        unique=True,
    )
    nickname: Mapped[str] = mapped_column(String(32))
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    grade: Mapped[int] = mapped_column(Integer)
    birth_date: Mapped[date | None] = mapped_column(Date)
    language: Mapped[str] = mapped_column(String(16), server_default=text("'zh-CN'"))
    learning_goal: Mapped[str | None] = mapped_column(Text)
    # FK→teacher_roles 延迟到 Phase 11 补（0-E 已裁定；本任务不建 teacher_roles 表）
    current_teacher_role_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    learning_days: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    total_learning_minutes: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    completed_books: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    completed_chapters: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    quiz_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StudentPreference(Base):
    """student_preferences（0-E §3.3）。"""

    __tablename__ = "student_preferences"
    __table_args__ = (
        CheckConstraint(
            "preferred_explanation_style IN ('EXAMPLE_BASED','VISUAL','STORY',"
            "'DIRECT_DEFINITION','STEP_BY_STEP','CODE','INTERACTIVE')",
            name="ck_student_preferences_explanation_style",
        ),
        CheckConstraint(
            "preferred_difficulty IN ('EASY','MEDIUM','HARD')",
            name="ck_student_preferences_difficulty",
        ),
        CheckConstraint(
            "preferred_session_length IN ('SHORT','MEDIUM','LONG')",
            name="ck_student_preferences_session_length",
        ),
        CheckConstraint(
            "daily_learning_minutes >= 0", name="ck_student_preferences_daily_minutes"
        ),
    )

    preference_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("student_profiles.student_id", ondelete="CASCADE"),
        unique=True,
    )
    preferred_explanation_style: Mapped[str] = mapped_column(String(32))
    preferred_difficulty: Mapped[str] = mapped_column(String(16))
    preferred_session_length: Mapped[str] = mapped_column(String(16))
    voice_preference: Mapped[dict] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    active_questioning_enabled: Mapped[bool] = mapped_column(
        Boolean, server_default=text("true")
    )
    daily_learning_minutes: Mapped[int] = mapped_column(
        Integer, server_default=text("30")
    )
    evidence_ids: Mapped[list] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Book(Base):
    """books（0-E §3.5）。"""

    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint("grade_min BETWEEN 1 AND 12", name="ck_books_grade_min"),
        CheckConstraint("grade_max BETWEEN 1 AND 12", name="ck_books_grade_max"),
        CheckConstraint("grade_min <= grade_max", name="ck_books_grade_range"),
        CheckConstraint("estimated_minutes > 0", name="ck_books_estimated_minutes"),
        CheckConstraint(
            "difficulty IN ('EASY','MEDIUM','HARD')", name="ck_books_difficulty"
        ),
        CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','ARCHIVED')", name="ck_books_status"
        ),
        Index("ix_books_grade_min_max", "grade_min", "grade_max"),
    )

    book_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    title: Mapped[str] = mapped_column(String(255))
    cover_url: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    grade_min: Mapped[int] = mapped_column(Integer)
    grade_max: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[str] = mapped_column(String(16))
    estimated_minutes: Mapped[int] = mapped_column(Integer)
    author: Mapped[str | None] = mapped_column(String(255))
    source_ids: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    license: Mapped[str | None] = mapped_column(String(128))
    copyright_status: Mapped[str | None] = mapped_column(String(128))
    tags: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'DRAFT'"))
    # FK→admins 延迟到 Phase 10 补（0-E 已裁定；本任务不建 admins 表）
    created_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Chapter(Base):
    """chapters（0-E §3.6）。"""

    __tablename__ = "chapters"
    __table_args__ = (
        CheckConstraint("estimated_minutes > 0", name="ck_chapters_estimated_minutes"),
        CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','ARCHIVED')", name="ck_chapters_status"
        ),
        UniqueConstraint("book_id", "chapter_order", name="uq_chapters_book_order"),
    )

    chapter_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    book_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("books.book_id", ondelete="CASCADE"),
    )
    title: Mapped[str] = mapped_column(String(255))
    chapter_order: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    estimated_minutes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), server_default=text("'DRAFT'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ContentBlock(Base):
    """content_blocks（0-E §3.7）。"""

    __tablename__ = "content_blocks"
    __table_args__ = (
        CheckConstraint(
            "block_type IN ('TITLE','PARAGRAPH','IMAGE','FIGURE','KNOWLEDGE_CARD',"
            "'EXAMPLE','CALLOUT','HIGHLIGHT')",
            name="ck_content_blocks_type",
        ),
        UniqueConstraint("chapter_id", "block_order", name="uq_content_blocks_chapter_order"),
    )

    block_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    chapter_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chapters.chapter_id", ondelete="CASCADE"),
    )
    block_type: Mapped[str] = mapped_column(String(32))
    content: Mapped[dict] = mapped_column(JSONB)
    block_order: Mapped[int] = mapped_column(Integer)
    section_key: Mapped[str | None] = mapped_column(String(128))
    knowledge_point_ids: Mapped[list] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgePoint(Base):
    """knowledge_points（0-E §3.8；禁止 mastery/score/percent 数字列）。"""

    __tablename__ = "knowledge_points"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE','ARCHIVED')", name="ck_knowledge_points_status"
        ),
    )

    knowledge_point_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(128))
    slug: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(String(64))
    parent_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("knowledge_points.knowledge_point_id", ondelete="SET NULL"),
    )
    status: Mapped[str] = mapped_column(String(16), server_default=text("'ACTIVE'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LearningSession(Base):
    """learning_sessions（0-E §3.9）。"""

    __tablename__ = "learning_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE','ENDED','ABANDONED')", name="ck_learning_sessions_status"
        ),
        CheckConstraint(
            "duration_seconds >= 0", name="ck_learning_sessions_duration"
        ),
        CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name="ck_learning_sessions_ended_after_started",
        ),
        Index(
            "uq_learning_sessions_one_active",
            "student_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index(
            "ix_learning_sessions_student_started",
            "student_id",
            text("started_at DESC"),
        ),
    )

    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("student_profiles.student_id", ondelete="RESTRICT"),
    )
    book_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("books.book_id", ondelete="RESTRICT")
    )
    chapter_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("chapters.chapter_id", ondelete="RESTRICT")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'ACTIVE'"))
    entry_route: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LearningEvent(Base):
    """learning_events（0-E §3.10；append-only，应用层只 INSERT）。"""

    __tablename__ = "learning_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('CHAPTER_STARTED','CHAPTER_FINISHED','SECTION_READ',"
            "'KNOWLEDGE_CARD_VIEWED','HELP_REQUESTED','EXPLAIN_REQUESTED',"
            "'SUMMARY_REQUESTED','QUIZ_CREATED','QUIZ_ANSWERED','ANSWER_CORRECT',"
            "'ANSWER_WRONG','HINT_REQUESTED','QUESTION_ASKED','BOOK_STARTED',"
            "'BOOK_FINISHED','VOICE_SESSION_STARTED','ROLE_SWITCHED','TEXT_SELECTED')",
            name="ck_learning_events_type",
        ),
        Index(
            "ix_learning_events_student_occurred",
            "student_id",
            text("occurred_at DESC"),
        ),
        Index("ix_learning_events_student_type", "student_id", "event_type"),
        Index("ix_learning_events_quiz_session", "quiz_session_id"),
        Index("ix_learning_events_conversation", "conversation_id"),
        Index("ix_learning_events_session", "session_id"),
    )

    event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("student_profiles.student_id", ondelete="RESTRICT"),
    )
    session_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("learning_sessions.session_id", ondelete="RESTRICT"),
    )
    event_type: Mapped[str] = mapped_column(String(48))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    book_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("books.book_id", ondelete="RESTRICT")
    )
    chapter_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("chapters.chapter_id", ondelete="RESTRICT")
    )
    block_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("content_blocks.block_id", ondelete="RESTRICT")
    )
    knowledge_point_ids: Mapped[list] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    # FK→conversations 延迟到 Phase 4 补（0-E 已裁定）
    conversation_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    # FK→quiz_sessions 延迟到 Phase 6 补（0-E 已裁定）
    quiz_session_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BookProgress(Base):
    """book_progress（0-E §3.11）。"""

    __tablename__ = "book_progress"
    __table_args__ = (
        CheckConstraint(
            "status IN ('NOT_STARTED','READING','COMPLETED')",
            name="ck_book_progress_status",
        ),
        CheckConstraint(
            "position_percent BETWEEN 0 AND 100", name="ck_book_progress_position"
        ),
        CheckConstraint("total_seconds >= 0", name="ck_book_progress_total_seconds"),
        UniqueConstraint("student_id", "book_id", name="uq_book_progress_student_book"),
    )

    progress_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("student_profiles.student_id", ondelete="RESTRICT"),
    )
    book_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("books.book_id", ondelete="RESTRICT")
    )
    chapter_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("chapters.chapter_id", ondelete="RESTRICT")
    )
    block_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("content_blocks.block_id", ondelete="SET NULL"),
    )
    status: Mapped[str] = mapped_column(String(16), server_default=text("'NOT_STARTED'"))
    position_percent: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_seconds: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Conversation(Base):
    """conversations（0-E §3.12；学生对话上下文）。"""

    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE','ARCHIVED','DELETED')",
            name="ck_conversations_status",
        ),
        CheckConstraint(
            "channel IN ('TEXT','VOICE')",
            name="ck_conversations_channel",
        ),
        Index(
            "ix_conversations_student_updated",
            "student_id",
            text("updated_at DESC"),
        ),
        Index("ix_conversations_teacher_role", "teacher_role_id"),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("student_profiles.student_id", ondelete="RESTRICT"),
    )
    # FK→teacher_roles 延迟到 Phase 11；0-E 定义为非空，本任务因角色表尚未落地放宽为可空。
    teacher_role_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    title: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'ACTIVE'"))
    channel: Mapped[str] = mapped_column(String(16), server_default=text("'TEXT'"))
    current_page_context: Mapped[dict] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb")
    )
    recent_messages: Mapped[list] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    """messages（0-E §3.13；只追加，由应用层保证）。"""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('STUDENT','TEACHER','SYSTEM')",
            name="ck_messages_role",
        ),
        CheckConstraint(
            "type IN ('TEXT','QUIZ','TOOL_STATUS','HINT','RECOMMENDATION',"
            "'SYSTEM','LEARNING_SUMMARY')",
            name="ck_messages_type",
        ),
        UniqueConstraint(
            "conversation_id", "sequence", name="uq_messages_conversation_sequence"
        ),
    )

    message_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.conversation_id", ondelete="RESTRICT"),
    )
    role: Mapped[str] = mapped_column(String(16))
    type: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )
    sequence: Mapped[int] = mapped_column(Integer)
    model_info: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ConversationSummary(Base):
    """conversation_summaries（0-E §3.14；每个会话最多一条）。"""

    __tablename__ = "conversation_summaries"
    __table_args__ = (
        CheckConstraint(
            "token_count >= 0", name="ck_conversation_summaries_token_count"
        ),
        UniqueConstraint(
            "conversation_id", name="uq_conversation_summaries_conversation"
        ),
    )

    summary_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
    )
    summary: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    summary_version: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    source_message_ids: Mapped[list] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    model_info: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StudentMemory(Base):
    """student_memories（0-E §3.19；稳定记忆，软删除保留审计）。"""

    __tablename__ = "student_memories"
    __table_args__ = (
        CheckConstraint(
            "memory_type IN ('PROFILE','PREFERENCE','LEARNING','EPISODIC')",
            name="ck_student_memories_type",
        ),
        CheckConstraint(
            "confidence IN ('LOW','MEDIUM','HIGH')",
            name="ck_student_memories_confidence",
        ),
        CheckConstraint(
            "status IN ('ACTIVE','DISPUTED','SUPERSEDED','REMOVED')",
            name="ck_student_memories_status",
        ),
        Index("ix_student_memories_student_status", "student_id", "status"),
        Index(
            "ix_student_memories_student_updated",
            "student_id",
            text("updated_at DESC"),
        ),
    )

    memory_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("student_profiles.student_id", ondelete="RESTRICT"),
    )
    memory_type: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    confidence: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'ACTIVE'"))
    evidence_ids: Mapped[list] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    origin_candidate_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("memory_candidates.candidate_id", ondelete="SET NULL"),
    )
    user_confirmed: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MemoryCandidate(Base):
    """memory_candidates（0-E §3.20；Memory Skill 的内部候选存储）。"""

    __tablename__ = "memory_candidates"
    __table_args__ = (
        CheckConstraint(
            "candidate_type IN ('PROFILE','PREFERENCE','LEARNING','EPISODIC')",
            name="ck_memory_candidates_type",
        ),
        CheckConstraint(
            "confidence IN ('LOW','MEDIUM','HIGH')",
            name="ck_memory_candidates_confidence",
        ),
        CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','MERGED')",
            name="ck_memory_candidates_status",
        ),
        Index("ix_memory_candidates_student_status", "student_id", "status"),
        Index(
            "ix_memory_candidates_status_created", "status", "created_at"
        ),
    )

    candidate_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("student_profiles.student_id", ondelete="RESTRICT"),
    )
    candidate_type: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    proposed_memory: Mapped[dict] = mapped_column(JSONB)
    evidence_ids: Mapped[list] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    confidence: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), server_default=text("'PENDING'"))
    rule_version: Mapped[str] = mapped_column(String(64))
    model_info: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MemoryEvidence(Base):
    """memory_evidence（0-E §3.21；不可变事实聚合，事件以 JSONB 引用）。"""

    __tablename__ = "memory_evidence"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('QUIZ','LEARNING_SESSION','CONVERSATION','BOOK_PROGRESS')",
            name="ck_memory_evidence_source_type",
        ),
        CheckConstraint("count >= 1", name="ck_memory_evidence_count"),
        Index(
            "ix_memory_evidence_student_derived",
            "student_id",
            text("derived_at DESC"),
        ),
    )

    evidence_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("student_profiles.student_id", ondelete="RESTRICT"),
    )
    source_type: Mapped[str] = mapped_column(String(24))
    event_ids: Mapped[list] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    payload: Mapped[dict] = mapped_column(JSONB)
    count: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    first_occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    derived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    rule_version: Mapped[str] = mapped_column(String(64))


class QuizSession(Base):
    """quiz_sessions（0-E §3.15；题目快照创建后不可变）。"""

    __tablename__ = "quiz_sessions"
    __table_args__ = (
        CheckConstraint(
            "quiz_kind IN ('CHAPTER_QUIZ','AI_QUIZ')",
            name="ck_quiz_sessions_kind",
        ),
        CheckConstraint(
            "status IN ('GENERATING','ACTIVE','COMPLETED','ABANDONED')",
            name="ck_quiz_sessions_status",
        ),
        CheckConstraint(
            "duration_seconds >= 0", name="ck_quiz_sessions_duration"
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= created_at",
            name="ck_quiz_sessions_completed_after_created",
        ),
        Index(
            "ix_quiz_sessions_student_created",
            "student_id",
            text("created_at DESC"),
        ),
        Index("ix_quiz_sessions_conversation", "conversation_id"),
        Index("ix_quiz_sessions_book_chapter", "book_id", "chapter_id"),
    )

    quiz_session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("student_profiles.student_id", ondelete="RESTRICT"),
    )
    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.conversation_id", ondelete="RESTRICT"),
    )
    # FK→teacher_roles 延迟到 Phase 11；角色表尚未落地，本列可空且不建 FK。
    teacher_role_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    book_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("books.book_id", ondelete="RESTRICT")
    )
    chapter_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("chapters.chapter_id", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(255))
    quiz_kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(
        String(16), server_default=text("'GENERATING'")
    )
    questions_snapshot: Mapped[list] = mapped_column(JSONB)
    result_summary: Mapped[dict | None] = mapped_column(JSONB)
    duration_seconds: Mapped[int] = mapped_column(
        Integer, server_default=text("0")
    )
    ai_feedback: Mapped[str | None] = mapped_column(Text)
    model_info: Mapped[dict] = mapped_column(JSONB)
    skill_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuizQuestion(Base):
    """quiz_questions（0-E §3.16；服务端 correct_answer 权威）。"""

    __tablename__ = "quiz_questions"
    __table_args__ = (
        CheckConstraint(
            "question_type IN ('SINGLE_CHOICE','MULTIPLE_CHOICE','TRUE_FALSE','FILL_BLANK')",
            name="ck_quiz_questions_type",
        ),
        UniqueConstraint(
            "quiz_session_id", "question_order", name="uq_quiz_questions_session_order"
        ),
    )

    question_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    quiz_session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("quiz_sessions.quiz_session_id", ondelete="RESTRICT"),
    )
    question_order: Mapped[int] = mapped_column(Integer)
    question_type: Mapped[str] = mapped_column(String(24))
    stem: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSONB)
    correct_answer: Mapped[dict] = mapped_column(JSONB)
    explanation: Mapped[str] = mapped_column(Text)
    source_context: Mapped[dict | None] = mapped_column(JSONB)
    interaction_policy: Mapped[dict] = mapped_column(
        JSONB,
        server_default=text(
            "'{\"allow_hint\": true, \"max_hint_level\": 3}'::jsonb"
        ),
    )
    knowledge_point_ids: Mapped[list] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class QuizAnswer(Base):
    """quiz_answers（0-E §3.17；attempt 唯一约束提供幂等兜底）。"""

    __tablename__ = "quiz_answers"
    __table_args__ = (
        UniqueConstraint(
            "quiz_session_id",
            "question_id",
            "attempt_no",
            name="uq_quiz_answers_attempt",
        ),
        CheckConstraint("attempt_no >= 1", name="ck_quiz_answers_attempt_no"),
        CheckConstraint(
            "hint_level_at_submit >= 0", name="ck_quiz_answers_hint_level"
        ),
        Index(
            "ix_quiz_answers_session_question_created",
            "quiz_session_id",
            "question_id",
            "created_at",
        ),
    )

    answer_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    quiz_session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("quiz_sessions.quiz_session_id", ondelete="RESTRICT"),
    )
    question_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("quiz_questions.question_id", ondelete="RESTRICT"),
    )
    student_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("student_profiles.student_id", ondelete="RESTRICT"),
    )
    submitted_answer: Mapped[dict] = mapped_column(JSONB)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    attempt_no: Mapped[int] = mapped_column(Integer)
    hint_level_at_submit: Mapped[int] = mapped_column(
        Integer, server_default=text("0")
    )
    is_final: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false")
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class QuizInteraction(Base):
    """quiz_interactions（0-E §3.18；只追加审计日志）。"""

    __tablename__ = "quiz_interactions"
    __table_args__ = (
        UniqueConstraint(
            "quiz_session_id", "sequence", name="uq_quiz_interactions_session_sequence"
        ),
        CheckConstraint(
            "interaction_type IN ('HINT_REQUEST','HINT_RESPONSE','QUESTION_ASK',"
            "'TEACHER_REPLY','ANSWER_SUBMIT','ANSWER_RESULT')",
            name="ck_quiz_interactions_type",
        ),
        Index(
            "ix_quiz_interactions_session_question_created",
            "quiz_session_id",
            "question_id",
            "created_at",
        ),
        Index("ix_quiz_interactions_message", "message_id"),
        Index("ix_quiz_interactions_answer", "answer_id"),
    )

    interaction_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    quiz_session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("quiz_sessions.quiz_session_id", ondelete="RESTRICT"),
    )
    question_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("quiz_questions.question_id", ondelete="RESTRICT"),
    )
    interaction_type: Mapped[str] = mapped_column(String(24))
    payload: Mapped[dict] = mapped_column(JSONB)
    message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.message_id", ondelete="RESTRICT"),
    )
    answer_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("quiz_answers.answer_id", ondelete="RESTRICT"),
    )
    sequence: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
