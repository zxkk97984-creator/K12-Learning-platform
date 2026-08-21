import base64
import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.infrastructure.cache.redis import cache_get, cache_set
from app.infrastructure.database.models import Book, Chapter, ContentBlock, KnowledgePoint
from app.modules.content.schemas import (
    BookDTO,
    BookPageDTO,
    BookPageMeta,
    ChapterDTO,
    ChapterDetailDTO,
    ContentBlockDTO,
    KnowledgePointDTO,
)


def _encode_cursor(created_at: datetime, book_id: UUID) -> str:
    payload = json.dumps([created_at.isoformat(), str(book_id)])
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = json.loads(base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8"))
        created_at = datetime.fromisoformat(raw[0])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return created_at, UUID(raw[1])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "VALIDATION_ERROR", "message": "invalid cursor"},
        ) from exc


def _books_cache_key(
    *,
    cursor: str | None,
    limit: int,
    grade_min: int | None,
    grade_max: int | None,
    tag: str | None,
    status: str,
) -> str:
    """Namespace every filter so one cached page cannot satisfy another query."""
    fingerprint = json.dumps(
        {
            "cursor": cursor,
            "grade_max": grade_max,
            "grade_min": grade_min,
            "status": status,
            "tag": tag,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
    return f"cache:books:list:{limit}:{digest}"


class ContentService:
    """Content 只读 Domain Service（Router 只做编排，SQL 在此层）。"""

    async def list_books(
        self,
        session: AsyncSession,
        *,
        cursor: str | None,
        limit: int,
        grade_min: int | None,
        grade_max: int | None,
        tag: str | None,
        status: str,
    ) -> BookPageDTO:
        cache_key = _books_cache_key(
            cursor=cursor,
            limit=limit,
            grade_min=grade_min,
            grade_max=grade_max,
            tag=tag,
            status=status,
        )
        cached = await cache_get(cache_key)
        if cached is not None:
            try:
                return BookPageDTO.model_validate(cached)
            except (TypeError, ValueError):
                # A malformed/old cache entry is treated as a miss.
                pass

        query = select(Book).where(Book.status == status)
        if grade_min is not None:
            query = query.where(Book.grade_min >= grade_min)
        if grade_max is not None:
            query = query.where(Book.grade_max <= grade_max)
        if tag:
            query = query.where(Book.tags.contains([tag]))
        if cursor is not None:
            cursor_created_at, cursor_book_id = _decode_cursor(cursor)
            query = query.where(
                tuple_(Book.created_at, Book.book_id) < (cursor_created_at, cursor_book_id)
            )
        query = query.order_by(Book.created_at.desc(), Book.book_id.desc()).limit(limit + 1)
        rows = (await session.execute(query)).scalars().all()
        has_more = len(rows) > limit
        books = rows[:limit]

        counts: dict[UUID, int] = {}
        if books:
            count_rows = await session.execute(
                select(Chapter.book_id, func.count(Chapter.chapter_id))
                .where(Chapter.book_id.in_([book.book_id for book in books]))
                .group_by(Chapter.book_id)
            )
            counts = dict(count_rows.all())

        items = [
            BookDTO(
                book_id=book.book_id,
                title=book.title,
                cover_url=book.cover_url,
                description=book.description,
                grade_min=book.grade_min,
                grade_max=book.grade_max,
                difficulty=book.difficulty,
                estimated_minutes=book.estimated_minutes,
                author=book.author,
                source_ids=book.source_ids,
                license=book.license,
                copyright_status=book.copyright_status,
                tags=book.tags,
                status=book.status,
                published_at=book.published_at,
                chapter_count=counts.get(book.book_id, 0),
            )
            for book in books
        ]
        next_cursor = (
            _encode_cursor(books[-1].created_at, books[-1].book_id) if has_more and books else None
        )
        page = BookPageDTO(
            items=items,
            meta=BookPageMeta(next_cursor=next_cursor, has_more=has_more),
        )
        await cache_set(
            cache_key,
            page.model_dump(mode="json"),
            settings.redis_cache_ttl_seconds,
        )
        return page

    async def get_book(self, session: AsyncSession, book_id: UUID) -> BookDTO:
        book = await session.get(Book, book_id)
        if book is None or book.status != "PUBLISHED":
            raise HTTPException(
                status_code=404,
                detail={"code": "BOOK_NOT_FOUND", "message": "book not found"},
            )
        count = (
            await session.execute(
                select(func.count(Chapter.chapter_id)).where(Chapter.book_id == book_id)
            )
        ).scalar_one()
        return BookDTO(
            book_id=book.book_id,
            title=book.title,
            cover_url=book.cover_url,
            description=book.description,
            grade_min=book.grade_min,
            grade_max=book.grade_max,
            difficulty=book.difficulty,
            estimated_minutes=book.estimated_minutes,
            author=book.author,
            source_ids=book.source_ids,
            license=book.license,
            copyright_status=book.copyright_status,
            tags=book.tags,
            status=book.status,
            published_at=book.published_at,
            chapter_count=count,
        )

    async def list_chapters(self, session: AsyncSession, book_id: UUID) -> list[ChapterDTO]:
        book = await session.get(Book, book_id)
        if book is None or book.status != "PUBLISHED":
            raise HTTPException(
                status_code=404,
                detail={"code": "BOOK_NOT_FOUND", "message": "book not found"},
            )
        rows = (
            await session.execute(
                select(Chapter)
                .where(Chapter.book_id == book_id)
                .order_by(Chapter.chapter_order.asc())
            )
        ).scalars().all()
        return [ChapterDTO.model_validate(chapter) for chapter in rows]

    async def get_chapter_detail(
        self, session: AsyncSession, chapter_id: UUID
    ) -> ChapterDetailDTO:
        chapter = await session.get(Chapter, chapter_id)
        if chapter is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "CHAPTER_NOT_FOUND", "message": "chapter not found"},
            )
        blocks = (
            (
                await session.execute(
                    select(ContentBlock)
                    .where(ContentBlock.chapter_id == chapter_id)
                    .order_by(ContentBlock.block_order.asc())
                )
            )
            .scalars()
            .all()
        )
        knowledge_point_ids: list[UUID] = []
        seen: set[str] = set()
        for block in blocks:
            for kp_id in block.knowledge_point_ids:
                try:
                    kp_uuid = kp_id if isinstance(kp_id, UUID) else UUID(str(kp_id))
                except ValueError:
                    continue
                key = str(kp_uuid)
                if key not in seen:
                    seen.add(key)
                    knowledge_point_ids.append(kp_uuid)
        knowledge_points: list[KnowledgePointDTO] = []
        if knowledge_point_ids:
            rows = (
                await session.execute(
                    select(KnowledgePoint).where(
                        KnowledgePoint.knowledge_point_id.in_(knowledge_point_ids)
                    )
                )
            ).scalars().all()
            knowledge_points = [KnowledgePointDTO.model_validate(kp) for kp in rows]
        return ChapterDetailDTO(
            chapter=ChapterDTO.model_validate(chapter),
            content_blocks=[ContentBlockDTO.model_validate(block) for block in blocks],
            knowledge_points=knowledge_points,
        )

    async def get_knowledge_point(
        self, session: AsyncSession, knowledge_point_id: UUID
    ) -> KnowledgePointDTO:
        point = await session.get(KnowledgePoint, knowledge_point_id)
        if point is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "KNOWLEDGE_POINT_NOT_FOUND",
                    "message": "knowledge point not found",
                },
            )
        return KnowledgePointDTO.model_validate(point)
