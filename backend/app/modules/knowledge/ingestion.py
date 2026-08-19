"""Rule-based ingestion: Parser -> Chunker -> Mock Embedding -> DB (Phase 8)."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embedding import get_embedding
from app.infrastructure.database.models import (
    KnowledgeChunk,
    KnowledgeResource,
)

MAX_CHUNK_CHARS = 500


def parse_markdown(text: str) -> list[dict[str, str]]:
    """Split Markdown/TXT into heading-scoped blocks."""
    blocks: list[dict[str, str]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        content = "\n".join(current_lines).strip()
        if content:
            blocks.append(
                {
                    "content_type": current_heading or "plain",
                    "content": content,
                }
            )

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            flush()
            current_lines = []
            current_heading = stripped.lstrip("#").strip()
        else:
            current_lines.append(line)
    flush()
    return blocks


def chunk_blocks(
    blocks: list[dict[str, str]],
    *,
    max_chars: int = MAX_CHUNK_CHARS,
) -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    for block in blocks:
        content = block["content"]
        if len(content) <= max_chars:
            chunks.append(block)
            continue
        for index in range(0, len(content), max_chars):
            chunks.append(
                {
                    "content_type": block["content_type"],
                    "content": content[index : index + max_chars],
                }
            )
    return chunks


def _embedding_value(text: str) -> str:
    vector = get_embedding(text)
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def storage_key_for(source_url: str, source_name: str) -> str:
    digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:16]
    name = Path(source_name).stem.replace(" ", "-")
    return f"knowledge/{digest}/{name}.md"


async def ingest_text(
    session: AsyncSession,
    *,
    text: str,
    source_name: str,
    source_url: str,
    license: str,
    copyright_status: str,
    author: str | None = None,
    storage_key: str | None = None,
    knowledge_point_ids: list[str] | None = None,
    force_reprocess: bool = False,
) -> tuple[UUID, int]:
    storage_key = storage_key or storage_key_for(source_url, source_name)
    existing = (
        await session.execute(
            select(KnowledgeResource).where(
                KnowledgeResource.source_url == source_url,
                KnowledgeResource.storage_key == storage_key,
            )
        )
    ).scalar_one_or_none()
    if (
        existing is not None
        and existing.status == "READY"
        and not force_reprocess
    ):
        return existing.resource_id, 0

    now = datetime.now(timezone.utc)
    if existing is None:
        resource = KnowledgeResource(
            resource_id=uuid4(),
            source_name=source_name,
            source_url=source_url,
            author=author,
            license=license,
            copyright_status=copyright_status,
            storage_key=storage_key,
            file_type="MARKDOWN",
            status="UPLOADED",
            uploaded_at=now,
        )
        session.add(resource)
    else:
        resource = existing
        resource.status = "UPLOADED"
        resource.error = None
        resource.updated_at = now
        await session.execute(
            KnowledgeChunk.__table__.delete().where(
                KnowledgeChunk.resource_id == existing.resource_id
            )
        )
    await session.flush()

    try:
        resource.status = "PARSING"
        blocks = parse_markdown(text)
        resource.status = "CHUNKING"
        chunks = chunk_blocks(blocks)
        resource.status = "INDEXING"
        kp_ids = knowledge_point_ids or []
        for index, chunk in enumerate(chunks):
            embedding = _embedding_value(chunk["content"])
            session.add(
                KnowledgeChunk(
                    chunk_id=uuid4(),
                    resource_id=resource.resource_id,
                    chunk_index=index,
                    content=chunk["content"],
                    content_type=chunk["content_type"],
                    metadata_={
                        "source_url": source_url,
                        "license": license,
                        "copyright_status": copyright_status,
                        "source_ids": [str(resource.resource_id)],
                        "heading": chunk["content_type"],
                    },
                    knowledge_point_ids=kp_ids,
                    embedding=embedding,
                    token_count=len(chunk["content"]),
                    status="READY",
                )
            )
        resource.status = "READY"
        resource.error = None
        resource.updated_at = now
        await session.commit()
        return resource.resource_id, len(chunks)
    except Exception as exc:
        resource.status = "FAILED"
        resource.error = str(exc)
        resource.updated_at = datetime.now(timezone.utc)
        await session.commit()
        raise
