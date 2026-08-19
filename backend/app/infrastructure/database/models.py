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
