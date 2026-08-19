from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

BookDifficulty = Literal["EASY", "MEDIUM", "HARD"]
BookStatus = Literal["DRAFT", "PUBLISHED", "ARCHIVED"]
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


class BookDTO(BaseModel):
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
    published_at: datetime | None
    chapter_count: int  # (derived)


class ChapterDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chapter_id: UUID
    book_id: UUID
    title: str
    chapter_order: int
    summary: str | None
    estimated_minutes: int
    status: BookStatus


class ContentBlockDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    block_id: UUID
    chapter_id: UUID
    block_type: ContentBlockType
    content: dict
    block_order: int
    section_key: str | None
    knowledge_point_ids: list


class KnowledgePointDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    knowledge_point_id: UUID
    name: str
    slug: str
    description: str | None
    topic: str | None
    parent_id: UUID | None
    status: Literal["ACTIVE", "ARCHIVED"]


class ChapterDetailDTO(BaseModel):
    chapter: ChapterDTO
    content_blocks: list[ContentBlockDTO]
    knowledge_points: list[KnowledgePointDTO]


class BookPageMeta(BaseModel):
    next_cursor: str | None
    has_more: bool


class BookPageDTO(BaseModel):
    items: list[BookDTO]
    meta: BookPageMeta
