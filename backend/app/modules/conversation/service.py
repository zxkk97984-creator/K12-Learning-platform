import base64
import binascii
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    Conversation,
    ConversationSummary,
    Message,
    StudentProfile,
)
from app.modules.conversation.schemas import (
    ConversationDTO,
    ConversationListItemDTO,
    ConversationSummaryDTO,
    CreateConversationRequest,
    MessageDTO,
    PageMeta,
    PatchConversationRequest,
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
            raise ValueError("cursor must contain timestamp and UUID")
        timestamp = datetime.fromisoformat(raw[0])
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        return timestamp, UUID(raw[1])
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise _error(422, "VALIDATION_ERROR", "invalid cursor") from exc


def _decode_message_cursor(cursor: str) -> tuple[int, UUID]:
    try:
        raw = json.loads(
            base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        )
        if not isinstance(raw, list) or len(raw) != 2:
            raise ValueError("cursor must contain sequence and UUID")
        return int(raw[0]), UUID(raw[1])
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise _error(422, "VALIDATION_ERROR", "invalid cursor") from exc


def _list_item_dto(conversation: Conversation) -> ConversationListItemDTO:
    return ConversationListItemDTO(
        conversation_id=conversation.conversation_id,
        title=conversation.title,
        status=conversation.status,
        channel=conversation.channel,
        teacher_role_id=conversation.teacher_role_id,
        teacher_role=None,
        last_message_at=conversation.last_message_at,
        updated_at=conversation.updated_at,
    )


def _conversation_dto(
    conversation: Conversation,
    summary: ConversationSummary | None,
) -> ConversationDTO:
    item = _list_item_dto(conversation)
    return ConversationDTO(
        **item.model_dump(),
        student_id=conversation.student_id,
        current_page_context=conversation.current_page_context or {},
        recent_messages=conversation.recent_messages or [],
        conversation_summary=summary.summary if summary is not None else None,
    )


def _message_dto(message: Message) -> MessageDTO:
    return MessageDTO(
        message_id=message.message_id,
        conversation_id=message.conversation_id,
        role=message.role,
        type=message.type,
        content=message.content,
        metadata=message.metadata_,
        sequence=message.sequence,
        model_info=message.model_info,
        created_at=message.created_at,
    )


class ConversationService:
    """Conversation Domain application service."""

    async def _get_profile(
        self, session: AsyncSession, user_id: UUID
    ) -> StudentProfile:
        result = await session.execute(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            raise _error(404, "STUDENT_PROFILE_NOT_FOUND", "student profile not found")
        return profile

    async def _get_owned_conversation(
        self,
        session: AsyncSession,
        user_id: UUID,
        conversation_id: UUID,
    ) -> Conversation:
        profile = await self._get_profile(session, user_id)
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None:
            raise _error(404, "CONVERSATION_NOT_FOUND", "conversation not found")
        if conversation.student_id != profile.student_id:
            raise _error(403, "FORBIDDEN", "conversation does not belong to student")
        return conversation

    async def list_conversations(
        self,
        session: AsyncSession,
        user_id: UUID,
        *,
        cursor: str | None,
        limit: int,
        status: str,
        channel: str | None,
    ) -> tuple[list[ConversationListItemDTO], PageMeta]:
        profile = await self._get_profile(session, user_id)
        query = select(Conversation).where(
            Conversation.student_id == profile.student_id,
            Conversation.status == status,
        )
        if channel is not None:
            query = query.where(Conversation.channel == channel)
        if cursor is not None:
            cursor_updated_at, cursor_id = _decode_cursor(cursor)
            query = query.where(
                tuple_(Conversation.updated_at, Conversation.conversation_id)
                < (cursor_updated_at, cursor_id)
            )
        query = query.order_by(
            Conversation.updated_at.desc(), Conversation.conversation_id.desc()
        ).limit(limit + 1)
        rows = (await session.execute(query)).scalars().all()
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = (
            _encode_cursor(page[-1].updated_at, page[-1].conversation_id)
            if has_more and page
            else None
        )
        return [_list_item_dto(row) for row in page], PageMeta(
            next_cursor=next_cursor, has_more=has_more
        )

    async def create_conversation(
        self,
        session: AsyncSession,
        user_id: UUID,
        request: CreateConversationRequest,
    ) -> ConversationDTO:
        profile = await self._get_profile(session, user_id)
        conversation = Conversation(
            student_id=profile.student_id,
            # teacher_roles is a Phase 11 table, so this reference is stored
            # without a FK and falls back to the student's current role.
            teacher_role_id=request.teacher_role_id or profile.current_teacher_role_id,
            title=request.title,
            channel=request.channel,
            current_page_context={},
            recent_messages=[],
        )
        session.add(conversation)
        await session.commit()
        await session.refresh(conversation)
        return _conversation_dto(conversation, None)

    async def get_conversation(
        self, session: AsyncSession, user_id: UUID, conversation_id: UUID
    ) -> ConversationDTO:
        conversation = await self._get_owned_conversation(session, user_id, conversation_id)
        summary = (
            await session.execute(
                select(ConversationSummary).where(
                    ConversationSummary.conversation_id == conversation_id
                )
            )
        ).scalar_one_or_none()
        return _conversation_dto(conversation, summary)

    async def patch_conversation(
        self,
        session: AsyncSession,
        user_id: UUID,
        conversation_id: UUID,
        request: PatchConversationRequest,
    ) -> ConversationDTO:
        conversation = await self._get_owned_conversation(session, user_id, conversation_id)
        if "title" in request.model_fields_set:
            conversation.title = request.title
        if request.status is not None:
            if conversation.status == "DELETED" and request.status != "DELETED":
                raise _error(
                    409,
                    "CONVERSATION_INVALID_STATUS",
                    "deleted conversation cannot be reactivated",
                )
            conversation.status = request.status
        await session.commit()
        await session.refresh(conversation)
        return await self.get_conversation(session, user_id, conversation_id)

    async def list_messages(
        self,
        session: AsyncSession,
        user_id: UUID,
        conversation_id: UUID,
        *,
        cursor: str | None,
        limit: int,
        sort: str,
    ) -> tuple[list[MessageDTO], PageMeta]:
        await self._get_owned_conversation(session, user_id, conversation_id)
        query = select(Message).where(Message.conversation_id == conversation_id)
        if cursor is not None:
            cursor_sequence, cursor_id = _decode_message_cursor(cursor)
            if sort == "asc":
                query = query.where(
                    tuple_(Message.sequence, Message.message_id)
                    > (cursor_sequence, cursor_id)
                )
            else:
                query = query.where(
                    tuple_(Message.sequence, Message.message_id)
                    < (cursor_sequence, cursor_id)
                )
        if sort == "asc":
            query = query.order_by(Message.sequence.asc(), Message.message_id.asc())
        else:
            query = query.order_by(Message.sequence.desc(), Message.message_id.desc())
        query = query.limit(limit + 1)
        rows = (await session.execute(query)).scalars().all()
        has_more = len(rows) > limit
        page = rows[:limit]
        # Message cursors use sequence + message_id because message ordering is
        # independent from created_at and supports both directions.
        next_cursor = (
            _encode_cursor_value(page[-1].sequence, page[-1].message_id)
            if has_more and page
            else None
        )
        return [_message_dto(row) for row in page], PageMeta(
            next_cursor=next_cursor, has_more=has_more
        )

    async def get_summary(
        self, session: AsyncSession, user_id: UUID, conversation_id: UUID
    ) -> ConversationSummaryDTO | None:
        await self._get_owned_conversation(session, user_id, conversation_id)
        summary = (
            await session.execute(
                select(ConversationSummary).where(
                    ConversationSummary.conversation_id == conversation_id
                )
            )
        ).scalar_one_or_none()
        return ConversationSummaryDTO.model_validate(summary) if summary else None


def _encode_cursor_value(sequence: int, entity_id: UUID) -> str:
    payload = json.dumps([sequence, str(entity_id)])
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")
