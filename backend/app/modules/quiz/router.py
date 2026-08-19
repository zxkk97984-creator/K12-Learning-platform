from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_student
from app.api.envelope import ok
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_session
from app.modules.quiz.schemas import (
    CreateQuizSessionRequest,
    QuizKind,
    QuizStatus,
    SubmitQuizAnswerRequest,
)
from app.modules.quiz.service import QuizService

router = APIRouter(tags=["assessment"])
service = QuizService()


@router.post("/quiz-sessions", status_code=201)
async def create_quiz_session(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    body: CreateQuizSessionRequest,
):
    return ok(await service.create_session(session, user.user_id, body))


@router.get("/quiz-sessions")
async def list_quiz_sessions(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    quiz_kind: QuizKind | None = Query(default=None),
    status: QuizStatus | None = Query(default=None),
    book_id: UUID | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
):
    rows, meta = await service.list_sessions(
        session,
        user.user_id,
        cursor=cursor,
        limit=limit,
        quiz_kind=quiz_kind,
        status=status,
        book_id=book_id,
        date_from=date_from,
        date_to=date_to,
    )
    return ok(rows, meta.model_dump())


@router.get("/quiz-sessions/{quiz_session_id}")
async def get_quiz_session(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    quiz_session_id: UUID,
):
    return ok(await service.get_session(session, user.user_id, quiz_session_id))


@router.get("/quiz-sessions/{quiz_session_id}/questions")
async def list_quiz_questions(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    quiz_session_id: UUID,
):
    questions = await service.list_questions(session, user.user_id, quiz_session_id)
    return ok([question.model_dump(exclude_none=True) for question in questions])


@router.post(
    "/quiz-sessions/{quiz_session_id}/questions/{question_id}/answers",
    status_code=201,
)
async def submit_quiz_answer(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
    quiz_session_id: UUID,
    question_id: UUID,
    body: SubmitQuizAnswerRequest,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    answer, replayed = await service.submit_answer(
        session,
        user.user_id,
        quiz_session_id,
        question_id,
        body,
        idempotency_key,
    )
    if replayed:
        response.status_code = 200
        response.headers["Idempotency-Replayed"] = "true"
    return ok(answer)


@router.post(
    "/quiz-sessions/{quiz_session_id}/questions/{question_id}/hints",
    status_code=201,
)
async def request_quiz_hint(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    response: Response,
    quiz_session_id: UUID,
    question_id: UUID,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
):
    hint, replayed = await service.request_hint(
        session,
        user.user_id,
        quiz_session_id,
        question_id,
        idempotency_key,
    )
    if replayed:
        response.status_code = 200
        response.headers["Idempotency-Replayed"] = "true"
    return ok(hint)


@router.get("/quiz-sessions/{quiz_session_id}/answers")
async def list_quiz_answers(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    quiz_session_id: UUID,
):
    return ok(await service.list_answers(session, user.user_id, quiz_session_id))


@router.get("/quiz-sessions/{quiz_session_id}/interactions")
async def list_quiz_interactions(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    quiz_session_id: UUID,
):
    return ok(await service.list_interactions(session, user.user_id, quiz_session_id))
