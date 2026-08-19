"""RAG retrieval: Question + ScreenContext -> RelevantKnowledge (Phase 8)."""

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import KnowledgeResource
from app.modules.knowledge.schemas import KnowledgeChunkDTO, KnowledgeSearchRequest
from app.modules.knowledge.service import KnowledgeService


@dataclass
class RetrievedChunk:
    chunk: KnowledgeChunkDTO
    source_name: str


def _screen_context_terms(screen_context: dict[str, Any] | None) -> list[str]:
    if not screen_context:
        return []
    terms: list[str] = []
    selected_text = screen_context.get("selected_text")
    if isinstance(selected_text, str) and selected_text.strip():
        terms.append(selected_text.strip())
    chapter_title = screen_context.get("chapter_title")
    if isinstance(chapter_title, str) and chapter_title.strip():
        terms.append(chapter_title.strip())
    return terms


def _split_terms(query: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"[，。？?！!、\s]+", query)
        if len(part.strip()) >= 2
    ]


def _content_overlaps(query: str, content: str) -> bool:
    cleaned = re.sub(r"[，。？?！!、\s]+", "", query)
    return any(
        cleaned[index : index + 5] in content
        for index in range(max(0, len(cleaned) - 4))
    )


def _query_ngrams(query: str) -> list[str]:
    cleaned = re.sub(r"[，。？?！!、\s]+", "", query)
    return [
        cleaned[index : index + 5]
        for index in range(max(0, len(cleaned) - 4))
    ]


async def retrieve(
    session: AsyncSession,
    query: str,
    *,
    screen_context: dict[str, Any] | None = None,
    limit: int = 3,
) -> list[RetrievedChunk]:
    """Combine user question with screen context, then run the 8-A search."""
    service = KnowledgeService()
    terms = [query, *_screen_context_terms(screen_context)]
    filter_terms = [
        *_split_terms(query),
        *_screen_context_terms(screen_context),
    ]
    enhanced_query = " ".join(term for term in terms if term).strip()
    results = await service.search(
        session,
        KnowledgeSearchRequest(
            query=enhanced_query or query,
            limit=limit,
        ),
    )
    if not results:
        fallback_terms = _screen_context_terms(screen_context)
        if fallback_terms:
            results = await service.search(
                session,
                KnowledgeSearchRequest(
                    query=" ".join(fallback_terms),
                    limit=limit,
                ),
            )
    def keep_relevant(rows: list[KnowledgeChunkDTO]) -> list[KnowledgeChunkDTO]:
        relevant_terms = [term for term in filter_terms if len(term) >= 2]
        screen_terms = _screen_context_terms(screen_context)
        return [
            row
            for row in rows
            if any(term in row.content for term in relevant_terms)
            or _content_overlaps(query, row.content)
            or any(_content_overlaps(term, row.content) for term in screen_terms)
        ]

    results = keep_relevant(results)
    if not results:
        for term in [*_query_ngrams(query), *_screen_context_terms(screen_context)]:
            candidates = await service.search(
                session,
                KnowledgeSearchRequest(query=term, limit=limit),
            )
            results = keep_relevant(candidates)
            if results:
                break

    resource_ids = [str(row.resource_id) for row in results]
    source_names: dict[str, str] = {}
    if resource_ids:
        resources = (
            await session.execute(
                select(KnowledgeResource).where(
                    KnowledgeResource.resource_id.in_(resource_ids)
                )
            )
        ).scalars().all()
        source_names = {str(row.resource_id): row.source_name for row in resources}
    return [
        RetrievedChunk(
            chunk=row,
            source_name=source_names.get(str(row.resource_id), "知识库"),
        )
        for row in results
    ]
