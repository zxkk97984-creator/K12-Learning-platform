from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_student
from app.api.envelope import ok
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_session
from app.modules.admin.router import require_idempotency_key
from app.modules.admin.service import IdempotencyService, canonical_request_hash
from app.modules.conversation.schemas import (
    ConversationChannel,
    ConversationStatus,
    CreateConversationRequest,
    PatchConversationRequest,
    SendMessageRequest,
)
from app.modules.conversation.service import ConversationService

router = APIRouter(tags=["conversations"])
service = ConversationService()
idempotency = IdempotencyService()


@router.get("/conversations")
async def list_conversations(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    status: ConversationStatus = Query(default="ACTIVE"),
    channel: ConversationChannel | None = Query(default=None),
):
    items, meta = await service.list_conversations(
        session,
        user.user_id,
        cursor=cursor,
        limit=limit,
        status=status,
        channel=channel,
    )
    return ok(items, meta.model_dump())


@router.post("/conversations", status_code=201)
async def create_conversation(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    body: CreateConversationRequest,
    key: Annotated[str, Depends(require_idempotency_key)],
    response: Response,
):
    result, replayed = await idempotency.execute(
        session,
        actor_id=user.user_id,
        actor_type="STUDENT",
        key=key,
        request_hash=canonical_request_hash(body.model_dump(exclude_unset=True)),
        handler=lambda: _create_conversation(session, user, body),
    )
    if replayed:
        response.status_code = 200
        response.headers["Idempotency-Replayed"] = "true"
    return result


async def _create_conversation(
    session: AsyncSession,
    user: User,
    body: CreateConversationRequest,
) -> dict:
    conversation = await service.create_conversation(session, user.user_id, body)
    return ok(jsonable_encoder(conversation))


@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    conversation_id: UUID,
    body: SendMessageRequest,
):
    stream = await service.send_message(session, user.user_id, conversation_id, body)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    conversation_id: UUID,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    sort: Literal["asc", "desc"] = Query(default="asc"),
):
    messages, meta = await service.list_messages(
        session,
        user.user_id,
        conversation_id,
        cursor=cursor,
        limit=limit,
        sort=sort,
    )
    return ok(messages, meta.model_dump())


@router.get("/conversations/{conversation_id}/summary")
async def get_summary(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    conversation_id: UUID,
):
    summary = await service.get_summary(session, user.user_id, conversation_id)
    return ok(summary)


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    conversation_id: UUID,
):
    conversation = await service.get_conversation(session, user.user_id, conversation_id)
    return ok(conversation)


@router.patch("/conversations/{conversation_id}")
async def patch_conversation(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
    conversation_id: UUID,
    body: PatchConversationRequest,
):
    conversation = await service.patch_conversation(
        session, user.user_id, conversation_id, body
    )
    return ok(conversation)
