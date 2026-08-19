import base64
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embedding import get_embedding
from app.infrastructure.database.models import KnowledgeChunk, KnowledgeResource
from app.modules.knowledge.schemas import (
    KnowledgeChunkDTO,
    KnowledgeResourceDTO,
    KnowledgeSearchRequest,
    ResourceStatus,
)


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _encode_cursor(timestamp: datetime, entity_id: UUID) -> str:
    payload = json.dumps([timestamp.isoformat(), str(entity_id)])
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = json.loads(
            base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        )
        if not isinstance(raw, list) or len(raw) != 2:
            raise ValueError("invalid cursor")
        timestamp = datetime.fromisoformat(raw[0])
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp, UUID(raw[1])
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise _error(422, "VALIDATION_ERROR", "invalid cursor") from exc


def _resource_dto(row: KnowledgeResource) -> KnowledgeResourceDTO:
    return KnowledgeResourceDTO.model_validate(row)


def _chunk_dto(row: KnowledgeChunk) -> KnowledgeChunkDTO:
    return KnowledgeChunkDTO(
        chunk_id=row.chunk_id,
        resource_id=row.resource_id,
        chunk_index=row.chunk_index,
        content=row.content,
        content_type=row.content_type,
        metadata=row.metadata_ or {},
        knowledge_point_ids=row.knowledge_point_ids or [],
        token_count=row.token_count,
        status=row.status,
        created_at=row.created_at,
    )


class KnowledgeService:
    async def list_resources(
        self,
        session: AsyncSession,
        *,
        status: ResourceStatus,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[KnowledgeResourceDTO], str | None, bool]:
        query = select(KnowledgeResource).where(
            KnowledgeResource.status == status
        )
        if cursor is not None:
            cursor_created_at, cursor_id = _decode_cursor(cursor)
            query = query.where(
                tuple_(KnowledgeResource.created_at, KnowledgeResource.resource_id)
                < (cursor_created_at, cursor_id)
            )
        query = (
            query.order_by(
                KnowledgeResource.created_at.desc(),
                KnowledgeResource.resource_id.desc(),
            )
            .limit(limit + 1)
        )
        rows = (await session.execute(query)).scalars().all()
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = (
            _encode_cursor(page[-1].created_at, page[-1].resource_id)
            if has_more and page
            else None
        )
        return [_resource_dto(row) for row in page], next_cursor, has_more

    async def get_resource(
        self, session: AsyncSession, resource_id: UUID
    ) -> KnowledgeResourceDTO:
        resource = await session.get(KnowledgeResource, resource_id)
        if resource is None:
            raise _error(404, "RESOURCE_NOT_FOUND", "knowledge resource not found")
        return _resource_dto(resource)

    async def list_chunks(
        self, session: AsyncSession, resource_id: UUID
    ) -> list[KnowledgeChunkDTO]:
        resource = await session.get(KnowledgeResource, resource_id)
        if resource is None:
            raise _error(404, "RESOURCE_NOT_FOUND", "knowledge resource not found")
        rows = (
            await session.execute(
                select(KnowledgeChunk)
                .where(
                    KnowledgeChunk.resource_id == resource_id,
                    KnowledgeChunk.status == "READY",
                )
                .order_by(KnowledgeChunk.chunk_index.asc())
            )
        ).scalars().all()
        return [_chunk_dto(row) for row in rows]

    async def search(
        self,
        session: AsyncSession,
        request: KnowledgeSearchRequest,
    ) -> list[KnowledgeChunkDTO]:
        embedding = get_embedding(request.query)
        embedding_value = "[" + ",".join(f"{value:.8f}" for value in embedding) + "]"
        params: dict = {
            "query_embedding": embedding_value,
            "limit": request.limit,
            "kp_ids": request.knowledge_point_ids,
        }
        kp_filter = ""
        if request.knowledge_point_ids:
            kp_filter = (
                "AND EXISTS (SELECT 1 FROM jsonb_array_elements_text("
                "knowledge_chunks.knowledge_point_ids) AS kp "
                "WHERE kp = ANY(:kp_ids))"
            )
        sql = text(
            "SELECT chunk_id, resource_id, chunk_index, content, content_type, "
            "metadata, knowledge_point_ids, token_count, status, created_at, "
            "embedding <=> CAST(:query_embedding AS vector) AS distance "
            "FROM knowledge_chunks "
            "WHERE status = 'READY' "
            + kp_filter
            + " ORDER BY embedding <=> CAST(:query_embedding AS vector) "
            "LIMIT :limit"
        )
        result = await session.execute(sql, params)
        rows = result.mappings().all()
        if not rows:
            return await self._keyword_fallback(session, request)
        rows = sorted(
            rows,
            key=lambda row: (
                0 if request.query in row["content"] else 1,
                row["distance"] if row["distance"] is not None else 0,
            ),
        )
        return [
            KnowledgeChunkDTO(
                chunk_id=row["chunk_id"],
                resource_id=row["resource_id"],
                chunk_index=row["chunk_index"],
                content=row["content"],
                content_type=row["content_type"],
                metadata=row["metadata"] or {},
                knowledge_point_ids=row["knowledge_point_ids"] or [],
                token_count=row["token_count"],
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def _keyword_fallback(
        self,
        session: AsyncSession,
        request: KnowledgeSearchRequest,
    ) -> list[KnowledgeChunkDTO]:
        query = select(KnowledgeChunk).where(
            KnowledgeChunk.status == "READY",
            KnowledgeChunk.content.ilike(f"%{request.query}%"),
        )
        if request.knowledge_point_ids:
            query = query.where(
                KnowledgeChunk.knowledge_point_ids.contains(
                    request.knowledge_point_ids
                )
            )
        rows = (
            await session.execute(
                query.order_by(KnowledgeChunk.chunk_index.asc()).limit(
                    request.limit
                )
            )
        ).scalars().all()
        return [_chunk_dto(row) for row in rows]
