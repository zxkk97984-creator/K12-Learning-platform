from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ResourceStatus = Literal[
    "UPLOADED", "PARSING", "CHUNKING", "INDEXING", "READY", "FAILED"
]
ResourceFileType = Literal["PDF", "MARKDOWN", "TXT", "HTML"]
ChunkStatus = Literal["PENDING", "READY", "FAILED"]


class KnowledgeResourceDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    resource_id: UUID
    source_name: str
    source_url: str
    author: str | None
    license: str
    copyright_status: str
    storage_key: str
    file_type: ResourceFileType
    status: ResourceStatus
    uploaded_by: UUID | None
    error: str | None
    uploaded_at: datetime
    created_at: datetime
    updated_at: datetime


class KnowledgeChunkDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: UUID
    resource_id: UUID
    chunk_index: int
    content: str
    content_type: str | None
    metadata: dict
    knowledge_point_ids: list
    token_count: int
    status: ChunkStatus
    created_at: datetime


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1, le=20)
