from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

BookStatus = Literal["DRAFT", "PUBLISHED", "ARCHIVED"]
BookDifficulty = Literal["EASY", "MEDIUM", "HARD"]
ContentBlockType = Literal[
    "TITLE",
    "PARAGRAPH",
    "IMAGE",
    "FIGURE",
    "KNOWLEDGE_CARD",
    "EXAMPLE",
    "CALLOUT",
    "HIGHLIGHT",
]
KnowledgePointStatus = Literal["ACTIVE", "ARCHIVED"]


class CreateBookRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    cover_url: str | None = Field(default=None, max_length=512)
    grade_min: int = Field(default=1, ge=1, le=12)
    grade_max: int = Field(default=12, ge=1, le=12)
    difficulty: BookDifficulty = "MEDIUM"
    estimated_minutes: int = Field(default=30, ge=1)
    author: str | None = Field(default=None, max_length=255)
    source_ids: list[str] = Field(default_factory=list)
    license: str | None = Field(default=None, max_length=128)
    copyright_status: str | None = Field(default=None, max_length=128)
    tags: list[str] = Field(default_factory=list)
    status: BookStatus = "DRAFT"


class PatchBookRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    cover_url: str | None = Field(default=None, max_length=512)
    grade_min: int | None = Field(default=None, ge=1, le=12)
    grade_max: int | None = Field(default=None, ge=1, le=12)
    difficulty: BookDifficulty | None = None
    estimated_minutes: int | None = Field(default=None, ge=1)
    author: str | None = Field(default=None, max_length=255)
    source_ids: list[str] | None = None
    license: str | None = Field(default=None, max_length=128)
    copyright_status: str | None = Field(default=None, max_length=128)
    tags: list[str] | None = None
    status: BookStatus | None = None


class AdminBookDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    book_id: UUID
    title: str
    cover_url: str | None
    description: str | None
    grade_min: int
    grade_max: int
    difficulty: BookDifficulty
    estimated_minutes: int
    author: str | None
    source_ids: list
    license: str | None
    copyright_status: str | None
    tags: list
    status: BookStatus
    created_by: UUID | None
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AdminStatsDTO(BaseModel):
    books_total: int
    books_published: int
    chapters_total: int
    knowledge_points_total: int
    resources_total: int
    resources_ready: int
    resources_failed: int
    students_total: int


class CreateChapterRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    summary: str | None = None
    estimated_minutes: int = Field(default=15, ge=1)
    status: BookStatus = "DRAFT"


class PatchChapterRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = None
    estimated_minutes: int | None = Field(default=None, ge=1)
    status: BookStatus | None = None


class CreateContentBlockRequest(BaseModel):
    block_type: ContentBlockType
    content: dict
    section_key: str | None = Field(default=None, max_length=128)
    knowledge_point_ids: list[str] = Field(default_factory=list)


class PatchContentBlockRequest(BaseModel):
    block_type: ContentBlockType | None = None
    content: dict | None = None
    section_key: str | None = None
    knowledge_point_ids: list[str] | None = None


class CreateKnowledgePointRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    slug: str | None = Field(default=None, max_length=128)
    description: str | None = None
    topic: str | None = Field(default=None, max_length=64)
    parent_id: UUID | None = None
    status: KnowledgePointStatus = "ACTIVE"


class PatchKnowledgePointRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    slug: str | None = Field(default=None, max_length=128)
    description: str | None = None
    topic: str | None = Field(default=None, max_length=64)
    parent_id: UUID | None = None
    status: KnowledgePointStatus | None = None


class PatchKnowledgeResourceRequest(BaseModel):
    source_name: str | None = Field(default=None, min_length=1, max_length=255)
    source_url: str | None = Field(default=None, min_length=1, max_length=512)
    author: str | None = Field(default=None, max_length=255)
    license: str | None = Field(default=None, min_length=1, max_length=128)
    copyright_status: str | None = Field(default=None, min_length=1, max_length=128)


class CreateTeacherRoleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = None
    persona: dict = Field(default_factory=lambda: {"base_persona": "", "character_persona": ""})
    tone: str = Field(min_length=1, max_length=128)
    teaching_style: str = Field(min_length=1, max_length=128)
    avatar: str | None = Field(default=None, max_length=512)
    sprite_manifest: dict = Field(default_factory=dict)
    voice_id: str | None = Field(default=None, max_length=128)
    grade_rules: dict = Field(
        default_factory=lambda: {"primary": {}, "junior": {}, "senior": {}}
    )
    prompt_profile: dict | None = None
    interaction_style: str | None = Field(default=None, max_length=128)
    enabled: bool = True


class PatchTeacherRoleRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = None
    persona: dict | None = None
    tone: str | None = Field(default=None, min_length=1, max_length=128)
    teaching_style: str | None = Field(default=None, min_length=1, max_length=128)
    avatar: str | None = Field(default=None, max_length=512)
    sprite_manifest: dict | None = None
    voice_id: str | None = Field(default=None, max_length=128)
    grade_rules: dict | None = None
    prompt_profile: dict | None = None
    interaction_style: str | None = Field(default=None, max_length=128)
    enabled: bool | None = None
