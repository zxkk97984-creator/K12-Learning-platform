"""Admin domain service: stats, books, content, knowledge points."""

import base64
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminPrincipal
from app.infrastructure.database.models import (
    Admin,
    Book,
    Chapter,
    ContentBlock,
    IdempotencyKey,
    KnowledgePoint,
    KnowledgeResource,
    StudentProfile,
    User,
)
from app.modules.admin.schemas import (
    AdminBookDTO,
    AdminStatsDTO,
    CreateBookRequest,
    CreateChapterRequest,
    CreateContentBlockRequest,
    CreateKnowledgePointRequest,
    PatchBookRequest,
    PatchChapterRequest,
    PatchContentBlockRequest,
    PatchKnowledgePointRequest,
    PatchKnowledgeResourceRequest,
)
from app.modules.knowledge.ingestion import ingest_text
from app.modules.knowledge.schemas import KnowledgeResourceDTO


STORAGE_ROOT = Path(__file__).resolve().parents[3] / "storage" / "knowledge"


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


def canonical_request_hash(body: Any) -> str:
    raw = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value.lower()).strip("-")
    return slug or "knowledge-point"


class IdempotencyService:
    async def execute(
        self,
        session: AsyncSession,
        *,
        actor_id: UUID,
        actor_type: str,
        key: str,
        request_hash: str,
        handler: Callable[[], Awaitable[dict]],
    ) -> tuple[dict, bool]:
        existing = (
            await session.execute(
                select(IdempotencyKey).where(
                    IdempotencyKey.actor_id == actor_id,
                    IdempotencyKey.actor_type == actor_type,
                    IdempotencyKey.key == key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.request_hash != request_hash:
                raise _error(
                    409,
                    "IDEMPOTENCY_KEY_REUSED",
                    "idempotency key was reused with a different request",
                )
            return existing.response, True

        result = await handler()
        session.add(
            IdempotencyKey(
                idempotency_id=uuid4(),
                actor_id=actor_id,
                actor_type=actor_type,
                key=key,
                request_hash=request_hash,
                response=result,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            )
        )
        await session.commit()
        return result, False


class AdminService:
    def _storage_path(self, storage_key: str) -> Path:
        path = STORAGE_ROOT / storage_key
        if not str(path.resolve()).startswith(str(STORAGE_ROOT.resolve())):
            raise _error(422, "VALIDATION_ERROR", "invalid storage key")
        return path

    async def stats(self, session: AsyncSession) -> AdminStatsDTO:
        async def count(model, *filters) -> int:
            query = select(func.count()).select_from(model)
            if filters:
                query = query.where(*filters)
            return int((await session.execute(query)).scalar_one())

        return AdminStatsDTO(
            books_total=await count(Book),
            books_published=await count(Book, Book.status == "PUBLISHED"),
            chapters_total=await count(Chapter),
            knowledge_points_total=await count(KnowledgePoint),
            resources_total=await count(KnowledgeResource),
            resources_ready=await count(
                KnowledgeResource, KnowledgeResource.status == "READY"
            ),
            resources_failed=await count(
                KnowledgeResource, KnowledgeResource.status == "FAILED"
            ),
            students_total=await count(StudentProfile),
        )

    async def list_books(
        self,
        session: AsyncSession,
        *,
        status: str | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[AdminBookDTO], str | None, bool]:
        query = select(Book)
        if status is not None:
            query = query.where(Book.status == status)
        if cursor is not None:
            cursor_created_at, cursor_id = _decode_cursor(cursor)
            query = query.where(
                tuple_(Book.created_at, Book.book_id) < (cursor_created_at, cursor_id)
            )
        query = query.order_by(Book.created_at.desc(), Book.book_id.desc()).limit(
            limit + 1
        )
        rows = (await session.execute(query)).scalars().all()
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = (
            _encode_cursor(page[-1].created_at, page[-1].book_id)
            if has_more and page
            else None
        )
        return [AdminBookDTO.model_validate(row) for row in page], next_cursor, has_more

    async def get_book(self, session: AsyncSession, book_id: UUID) -> AdminBookDTO:
        book = await session.get(Book, book_id)
        if book is None:
            raise _error(404, "BOOK_NOT_FOUND", "book not found")
        return AdminBookDTO.model_validate(book)

    async def create_book(
        self,
        session: AsyncSession,
        admin: AdminPrincipal,
        request: CreateBookRequest,
    ) -> AdminBookDTO:
        if admin.admin_id is None:
            raise _error(422, "ADMIN_NOT_REGISTERED", "admin profile not registered")
        if request.grade_min > request.grade_max:
            raise _error(422, "VALIDATION_ERROR", "grade_min must not exceed grade_max")
        book = Book(
            book_id=uuid4(),
            title=request.title,
            description=request.description,
            cover_url=request.cover_url,
            grade_min=request.grade_min,
            grade_max=request.grade_max,
            difficulty=request.difficulty,
            estimated_minutes=request.estimated_minutes,
            author=request.author,
            source_ids=request.source_ids,
            license=request.license,
            copyright_status=request.copyright_status,
            tags=request.tags,
            status=request.status,
            created_by=admin.admin_id,
        )
        session.add(book)
        await session.flush()
        return AdminBookDTO.model_validate(book)

    async def patch_book(
        self,
        session: AsyncSession,
        book_id: UUID,
        request: PatchBookRequest,
    ) -> AdminBookDTO:
        book = await session.get(Book, book_id)
        if book is None:
            raise _error(404, "BOOK_NOT_FOUND", "book not found")
        data = request.model_dump(exclude_unset=True)
        new_status = data.get("status")
        if new_status is not None and new_status != book.status:
            if book.status == "ARCHIVED" and new_status != "ARCHIVED":
                raise _error(409, "BOOK_INVALID_STATUS", "archived book cannot reactivate")
            if new_status == "PUBLISHED":
                grade_min = data.get("grade_min", book.grade_min)
                grade_max = data.get("grade_max", book.grade_max)
                if grade_min > grade_max:
                    raise _error(422, "VALIDATION_ERROR", "grade_min must not exceed grade_max")
                chapter_count = (
                    await session.execute(
                        select(func.count(Chapter.chapter_id)).where(
                            Chapter.book_id == book_id
                        )
                    )
                ).scalar_one()
                if int(chapter_count) < 1:
                    raise _error(
                        422,
                        "VALIDATION_ERROR",
                        "published book requires at least one chapter",
                    )
                book.published_at = datetime.now(timezone.utc)
        for key, value in data.items():
            if key == "status":
                continue
            setattr(book, key, value)
        book.status = new_status or book.status
        book.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return AdminBookDTO.model_validate(book)

    async def create_chapter(
        self,
        session: AsyncSession,
        book_id: UUID,
        request: CreateChapterRequest,
    ) -> dict:
        book = await session.get(Book, book_id)
        if book is None:
            raise _error(404, "BOOK_NOT_FOUND", "book not found")
        max_order = (
            await session.execute(
                select(func.max(Chapter.chapter_order)).where(
                    Chapter.book_id == book_id
                )
            )
        ).scalar_one()
        chapter = Chapter(
            chapter_id=uuid4(),
            book_id=book_id,
            title=request.title,
            chapter_order=(max_order or 0) + 1,
            summary=request.summary,
            estimated_minutes=request.estimated_minutes,
            status=request.status,
        )
        session.add(chapter)
        await session.flush()
        return {
            "chapter_id": str(chapter.chapter_id),
            "book_id": str(chapter.book_id),
            "title": chapter.title,
            "chapter_order": chapter.chapter_order,
        }

    async def patch_chapter(
        self,
        session: AsyncSession,
        chapter_id: UUID,
        request: PatchChapterRequest,
    ) -> dict:
        chapter = await session.get(Chapter, chapter_id)
        if chapter is None:
            raise _error(404, "CHAPTER_NOT_FOUND", "chapter not found")
        for key, value in request.model_dump(exclude_unset=True).items():
            setattr(chapter, key, value)
        await session.flush()
        return {
            "chapter_id": str(chapter.chapter_id),
            "title": chapter.title,
            "status": chapter.status,
        }

    async def create_content_block(
        self,
        session: AsyncSession,
        chapter_id: UUID,
        request: CreateContentBlockRequest,
    ) -> dict:
        chapter = await session.get(Chapter, chapter_id)
        if chapter is None:
            raise _error(404, "CHAPTER_NOT_FOUND", "chapter not found")
        max_order = (
            await session.execute(
                select(func.max(ContentBlock.block_order)).where(
                    ContentBlock.chapter_id == chapter_id
                )
            )
        ).scalar_one()
        block = ContentBlock(
            block_id=uuid4(),
            chapter_id=chapter_id,
            block_type=request.block_type,
            content=request.content,
            block_order=(max_order or 0) + 1,
            section_key=request.section_key,
            knowledge_point_ids=request.knowledge_point_ids,
        )
        session.add(block)
        await session.flush()
        return {
            "block_id": str(block.block_id),
            "chapter_id": str(block.chapter_id),
            "block_order": block.block_order,
            "block_type": block.block_type,
        }

    async def patch_content_block(
        self,
        session: AsyncSession,
        block_id: UUID,
        request: PatchContentBlockRequest,
    ) -> dict:
        block = await session.get(ContentBlock, block_id)
        if block is None:
            raise _error(404, "CONTENT_BLOCK_NOT_FOUND", "content block not found")
        for key, value in request.model_dump(exclude_unset=True).items():
            setattr(block, key, value)
        await session.flush()
        return {"block_id": str(block.block_id), "block_type": block.block_type}

    async def create_knowledge_point(
        self,
        session: AsyncSession,
        request: CreateKnowledgePointRequest,
    ) -> dict:
        slug = request.slug or slugify(request.name)
        duplicate = (
            await session.execute(
                select(KnowledgePoint).where(KnowledgePoint.slug == slug)
            )
        ).scalar_one_or_none()
        if duplicate is not None:
            raise _error(409, "KNOWLEDGE_POINT_SLUG_EXISTS", "slug already exists")
        point = KnowledgePoint(
            knowledge_point_id=uuid4(),
            name=request.name,
            slug=slug,
            description=request.description,
            topic=request.topic,
            parent_id=request.parent_id,
            status=request.status,
        )
        session.add(point)
        await session.flush()
        return {
            "knowledge_point_id": str(point.knowledge_point_id),
            "name": point.name,
            "slug": point.slug,
        }

    async def patch_knowledge_point(
        self,
        session: AsyncSession,
        knowledge_point_id: UUID,
        request: PatchKnowledgePointRequest,
    ) -> dict:
        point = await session.get(KnowledgePoint, knowledge_point_id)
        if point is None:
            raise _error(404, "KNOWLEDGE_POINT_NOT_FOUND", "knowledge point not found")
        for key, value in request.model_dump(exclude_unset=True).items():
            setattr(point, key, value)
        await session.flush()
        return {
            "knowledge_point_id": str(point.knowledge_point_id),
            "name": point.name,
            "slug": point.slug,
        }

    async def upload_knowledge_resource(
        self,
        session: AsyncSession,
        admin: AdminPrincipal,
        *,
        file_bytes: bytes,
        filename: str,
        source_name: str,
        source_url: str,
        author: str | None,
        license: str,
        copyright_status: str,
    ) -> KnowledgeResourceDTO:
        if admin.admin_id is None:
            raise _error(422, "ADMIN_NOT_REGISTERED", "admin profile not registered")
        ext = Path(filename).suffix.lower().lstrip(".")
        file_type = {"md": "MARKDOWN", "markdown": "MARKDOWN", "txt": "TXT", "html": "HTML"}.get(
            ext
        )
        if file_type is None:
            raise _error(
                422,
                "UNSUPPORTED_FILE_TYPE",
                "only MARKDOWN/TXT/HTML are supported; PDF parsing lands in Phase 12",
            )
        if not source_name.strip() or not source_url.strip():
            raise _error(422, "VALIDATION_ERROR", "source_name and source_url are required")
        if not license.strip() or not copyright_status.strip():
            raise _error(422, "VALIDATION_ERROR", "license and copyright_status are required")

        storage_key = f"{admin.admin_id}/{uuid4()}.{ext}"
        path = self._storage_path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(file_bytes)
        text = file_bytes.decode("utf-8", errors="replace")
        resource_id, _ = await ingest_text(
            session,
            text=text,
            source_name=source_name,
            source_url=source_url,
            license=license,
            copyright_status=copyright_status,
            author=author,
            storage_key=storage_key,
        )
        resource = await session.get(KnowledgeResource, resource_id)
        if resource is None:
            raise _error(404, "RESOURCE_NOT_FOUND", "resource not found")
        return KnowledgeResourceDTO.model_validate(resource)

    async def patch_knowledge_resource(
        self,
        session: AsyncSession,
        resource_id: UUID,
        request: PatchKnowledgeResourceRequest,
    ) -> KnowledgeResourceDTO:
        resource = await session.get(KnowledgeResource, resource_id)
        if resource is None:
            raise _error(404, "RESOURCE_NOT_FOUND", "resource not found")
        for key, value in request.model_dump(exclude_unset=True).items():
            setattr(resource, key, value)
        resource.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return KnowledgeResourceDTO.model_validate(resource)

    async def reprocess_knowledge_resource(
        self,
        session: AsyncSession,
        resource_id: UUID,
    ) -> KnowledgeResourceDTO:
        resource = await session.get(KnowledgeResource, resource_id)
        if resource is None:
            raise _error(404, "RESOURCE_NOT_FOUND", "resource not found")
        path = self._storage_path(str(resource.storage_key))
        if not path.exists():
            raise _error(422, "SOURCE_FILE_MISSING", "stored source file is missing")
        text = path.read_text(encoding="utf-8", errors="replace")
        await ingest_text(
            session,
            text=text,
            source_name=resource.source_name,
            source_url=resource.source_url,
            license=resource.license,
            copyright_status=resource.copyright_status,
            author=resource.author,
            storage_key=str(resource.storage_key),
            force_reprocess=True,
        )
        resource = await session.get(KnowledgeResource, resource_id)
        await session.refresh(resource)
        return KnowledgeResourceDTO.model_validate(resource)
