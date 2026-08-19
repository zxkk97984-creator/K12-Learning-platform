from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_student
from app.api.envelope import ok
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_session
from app.modules.content.service import ContentService

router = APIRouter(tags=["content"])
service = ContentService()


@router.get("/books")
async def list_books(
    _user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    grade_min: int | None = Query(default=None, ge=1, le=12),
    grade_max: int | None = Query(default=None, ge=1, le=12),
    tag: str | None = Query(default=None),
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"] = Query(default="PUBLISHED"),
):
    page = await service.list_books(
        session,
        cursor=cursor,
        limit=limit,
        grade_min=grade_min,
        grade_max=grade_max,
        tag=tag,
        status=status,
    )
    return ok(page.items, page.meta.model_dump())


@router.get("/books/{book_id}")
async def get_book(
    _user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    book_id: UUID,
):
    return ok(await service.get_book(session, book_id))


@router.get("/books/{book_id}/chapters")
async def list_chapters(
    _user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    book_id: UUID,
):
    return ok(await service.list_chapters(session, book_id))


@router.get("/chapters/{chapter_id}")
async def get_chapter_detail(
    _user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    chapter_id: UUID,
):
    return ok(await service.get_chapter_detail(session, chapter_id))


@router.get("/knowledge-points/{knowledge_point_id}")
async def get_knowledge_point(
    _user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    knowledge_point_id: UUID,
):
    return ok(await service.get_knowledge_point(session, knowledge_point_id))
