"""Knowledge resource parsing and indexing job handler."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.ingestion import ingest_stored_resource


async def handle_knowledge_ingest(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    raw_resource_id = payload.get("resource_id")
    if raw_resource_id is None:
        raise ValueError("knowledge_ingest payload requires resource_id")
    try:
        resource_id = UUID(str(raw_resource_id))
    except (TypeError, ValueError) as exc:
        raise ValueError("knowledge_ingest resource_id must be a UUID") from exc
    await ingest_stored_resource(
        session,
        resource_id,
        force_reprocess=bool(payload.get("force_reprocess", False)),
    )
