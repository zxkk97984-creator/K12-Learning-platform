from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_student
from app.api.envelope import ok
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_session
from app.modules.learning.schemas import (
    CreateLearningEventRequest,
    CreateLearningSessionRequest,
    PatchLearningSessionRequest,
)
from app.modules.learning.service import LearningService

router = APIRouter(tags=["learning"])
service = LearningService()


@router.post("/learning-sessions", status_code=201)
async def create_learning_session(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    body: CreateLearningSessionRequest,
):
    return ok(await service.create_session(session, user.user_id, body))


@router.patch("/learning-sessions/{session_id}")
async def patch_learning_session(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    session_id: UUID,
    body: PatchLearningSessionRequest,
):
    return ok(await service.patch_session(session, user.user_id, session_id, body))


@router.post("/learning-events", status_code=201)
async def create_learning_event(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    body: CreateLearningEventRequest,
):
    return ok(await service.create_event(session, user.user_id, body))


@router.get("/me/progress")
async def get_progress(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    return ok(await service.get_progress(session, user.user_id))


@router.get("/me/progress/{book_id}")
async def get_book_progress(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    book_id: UUID,
):
    return ok(await service.get_book_progress(session, user.user_id, book_id))


@router.get("/me/learning-events")
async def list_learning_events(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    event_type: Literal[
        "CHAPTER_STARTED",
        "CHAPTER_FINISHED",
        "SECTION_READ",
        "KNOWLEDGE_CARD_VIEWED",
        "HELP_REQUESTED",
        "EXPLAIN_REQUESTED",
        "SUMMARY_REQUESTED",
        "QUIZ_CREATED",
        "QUIZ_ANSWERED",
        "ANSWER_CORRECT",
        "ANSWER_WRONG",
        "HINT_REQUESTED",
        "QUESTION_ASKED",
        "BOOK_STARTED",
        "BOOK_FINISHED",
        "VOICE_SESSION_STARTED",
        "ROLE_SWITCHED",
        "TEXT_SELECTED",
    ] = Query(default=None),
):
    page = await service.list_events(
        session,
        user.user_id,
        cursor=cursor,
        limit=limit,
        event_type=event_type,
    )
    return ok(page.items, page.meta.model_dump())
