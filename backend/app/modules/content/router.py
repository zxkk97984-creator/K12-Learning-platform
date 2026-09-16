from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_student
from app.api.envelope import ok
from app.infrastructure.database.models import StudentProfile, User
from app.infrastructure.database.session import get_session
from app.modules.content.service import ContentService

router = APIRouter(tags=["content"])
service = ContentService()


async def _resolve_student_id(session: AsyncSession, user_id: UUID) -> UUID | None:
    row = (
        await session.execute(select(StudentProfile.student_id).where(StudentProfile.user_id == user_id))
    ).scalar_one_or_none()
    return row


@router.get("/books")
async def list_books(
    _user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    grade_min: int | None = Query(default=None, ge=1, le=12),
    grade_max: int | None = Query(default=None, ge=1, le=12),
    tag: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    with_total: bool = Query(default=False),
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"] = Query(default="PUBLISHED"),
):
    if status != "PUBLISHED":
        # T02：学生 list 只能是 PUBLISHED；传 DRAFT/ARCHIVED 明确拒绝（422）。
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_CONTENT_STATUS",
                "message": "student content list only exposes PUBLISHED items",
            },
        )
    page = await service.list_books(
        session,
        cursor=cursor,
        limit=limit,
        grade_min=grade_min,
        grade_max=grade_max,
        tag=tag,
        status=status,
        search=search.strip() if search else None,
        with_total=with_total,
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
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    book_id: UUID,
):
    # T13：填充当前学生章节完成态。student_id 解析失败按无完成态处理。
    student_id = await _resolve_student_id(session, user.user_id)
    return ok(await service.list_chapters(session, book_id, student_id))


@router.get("/chapters/{chapter_id}")
async def get_chapter_detail(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    chapter_id: UUID,
):
    student_id = await _resolve_student_id(session, user.user_id)
    return ok(await service.get_chapter_detail(session, chapter_id, student_id))


@router.get("/knowledge-points/{knowledge_point_id}")
async def get_knowledge_point(
    _user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    knowledge_point_id: UUID,
):
    return ok(await service.get_knowledge_point(session, knowledge_point_id))
