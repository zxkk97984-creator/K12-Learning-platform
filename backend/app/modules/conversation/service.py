import asyncio
import base64
import binascii
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import AIProvider
from app.ai.factory import get_ai_provider
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
    SendMessageRequest,
)
from app.modules.memory.agent_md import build_evidence_reply, is_evidence_question
from app.modules.quiz.schemas import CreateQuizSessionRequest
from app.modules.quiz.service import QuizService


QUIZ_INTENT_KEYWORDS = ("出题", "题目", "测验", "quiz", "考考我")


def _is_quiz_intent(content: str) -> bool:
    normalized = content.casefold()
    return any(keyword.casefold() in normalized for keyword in QUIZ_INTENT_KEYWORDS)


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


def _sse_frame(
    event: str,
    data: dict[str, Any],
    *,
    event_id: UUID | str | None = None,
) -> str:
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(
        "data: " + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    )
    return "\n".join(lines) + "\n\n"


def _sse_error(
    request_id: str,
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> str:
    return _sse_frame(
        "error",
        {
            "request_id": request_id,
            "code": code,
            "message": message,
            "details": details or {},
            "fatal": True,
        },
    )


def _isoformat_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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

    def __init__(self, quiz_service: QuizService | None = None) -> None:
        self.quiz_service = quiz_service or QuizService()

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

    async def _next_message_sequence(
        self, session: AsyncSession, conversation_id: UUID
    ) -> int:
        result = await session.execute(
            select(func.max(Message.sequence)).where(
                Message.conversation_id == conversation_id
            )
        )
        current_sequence = result.scalar_one()
        return (current_sequence or 0) + 1

    async def send_message(
        self,
        session: AsyncSession,
        user_id: UUID,
        conversation_id: UUID,
        request: SendMessageRequest,
    ) -> AsyncIterator[str]:
        """Persist the student turn, then return its AI-backed SSE generator.

        The preflight work intentionally happens before the StreamingResponse is
        created, so ownership, not-found, deleted, and validation errors retain
        their normal HTTP status and error envelope.
        """
        profile = await self._get_profile(session, user_id)
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None:
            raise _error(404, "CONVERSATION_NOT_FOUND", "conversation not found")
        if conversation.student_id != profile.student_id:
            raise _error(403, "FORBIDDEN", "conversation does not belong to student")
        if conversation.status == "DELETED":
            raise _error(
                409,
                "CONVERSATION_INVALID_STATUS",
                "deleted conversation cannot receive messages",
            )

        current_context = dict(conversation.current_page_context or {})
        if request.screen_context is not None:
            current_context.update(request.screen_context)
        if request.selected_text is not None:
            current_context["selected_text"] = request.selected_text

        student_sequence = await self._next_message_sequence(
            session, conversation_id
        )
        now = datetime.now(timezone.utc)
        student_message = Message(
            conversation_id=conversation_id,
            role="STUDENT",
            type=request.type,
            content=request.content,
            metadata_={},
            sequence=student_sequence,
            created_at=now,
        )
        conversation.current_page_context = current_context
        conversation.last_message_at = now
        session.add(student_message)
        await session.commit()
        await session.refresh(student_message)

        history_rows = (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.sequence.asc())
            )
        ).scalars().all()
        history: list[dict[str, str]] = []
        for message in history_rows:
            role = {
                "STUDENT": "user",
                "TEACHER": "assistant",
                "SYSTEM": "system",
            }.get(message.role, "user")
            history.append({"role": role, "content": message.content})

        teacher_message_id = uuid4()
        teacher_sequence = student_sequence + 1
        teacher_created_at = datetime.now(timezone.utc)
        request_id = str(uuid4())
        quiz_intent = _is_quiz_intent(request.content)
        evidence_reply: str | None = None
        try:
            if is_evidence_question(request.content):
                evidence_reply = await build_evidence_reply(
                    session, profile.student_id, request.content
                )
        except Exception:  # pragma: no cover - evidence citation must not break chat
            evidence_reply = None
        system_prompt = (
            "你是霜铃，一位耐心、清晰的中文 K12 数字教师。"
            "请根据学生的问题循序解释，鼓励学生自己思考。"
            f"当前页面上下文：{json.dumps(current_context, ensure_ascii=False)}"
        )

        async def stream() -> AsyncIterator[str]:
            yield _sse_frame(
                "message.start",
                {
                    "message_id": str(teacher_message_id),
                    "conversation_id": str(conversation_id),
                    "role": "TEACHER",
                    "type": "TEXT",
                    "sequence": teacher_sequence,
                    "created_at": _isoformat_z(teacher_created_at),
                    "request_id": request_id,
                },
                event_id=teacher_message_id,
            )

            if quiz_intent:
                chunks: list[str] = []
                tool_run_id = str(uuid4())
                intro = "好的，我来出一道题，请听题～"
                chunks.append(intro)
                yield _sse_frame(
                    "text.delta",
                    {
                        "message_id": str(teacher_message_id),
                        "delta": intro,
                        "index": 0,
                        "sequence": teacher_sequence,
                    },
                    event_id=teacher_message_id,
                )
                yield _sse_frame(
                    "tool.start",
                    {
                        "tool_run_id": tool_run_id,
                        "tool": "quiz",
                        "state": "running",
                        "message_id": str(teacher_message_id),
                        "payload": {"quiz_session_id": None},
                    },
                    event_id=teacher_message_id,
                )
                try:
                    quiz_session = await self.quiz_service.create_session(
                        session,
                        user_id,
                        CreateQuizSessionRequest(
                            conversation_id=conversation_id,
                            question_count=1,
                            difficulty="MEDIUM",
                        ),
                    )
                except HTTPException as exc:
                    await session.rollback()
                    detail = exc.detail if isinstance(exc.detail, dict) else {}
                    code = str(detail.get("code", "QUIZ_SKILL_ERROR"))
                    message = str(detail.get("message", "quiz skill failed"))
                    yield _sse_frame(
                        "tool.result",
                        {
                            "tool_run_id": tool_run_id,
                            "tool": "quiz",
                            "status": "error",
                            "payload": {"code": code, "message": message},
                        },
                        event_id=teacher_message_id,
                    )
                    yield _sse_error(request_id, code, message)
                    return
                except Exception:
                    await session.rollback()
                    yield _sse_frame(
                        "tool.result",
                        {
                            "tool_run_id": tool_run_id,
                            "tool": "quiz",
                            "status": "error",
                            "payload": {
                                "code": "QUIZ_SKILL_ERROR",
                                "message": "quiz skill unavailable",
                            },
                        },
                        event_id=teacher_message_id,
                    )
                    yield _sse_error(
                        request_id,
                        "QUIZ_SKILL_ERROR",
                        "quiz skill unavailable",
                    )
                    return

                quiz_session_id = str(quiz_session.quiz_session_id)
                yield _sse_frame(
                    "tool.result",
                    {
                        "tool_run_id": tool_run_id,
                        "tool": "quiz",
                        "status": "success",
                        "payload": {
                            "quiz_session_id": quiz_session_id,
                            "skill_version": quiz_session.skill_version,
                        },
                    },
                    event_id=teacher_message_id,
                )
                outro = "题目已生成，请在卡片中作答～"
                chunks.append(outro)
                yield _sse_frame(
                    "text.delta",
                    {
                        "message_id": str(teacher_message_id),
                        "delta": outro,
                        "index": 1,
                        "sequence": teacher_sequence,
                    },
                    event_id=teacher_message_id,
                )
                content = "".join(chunks)
                model_info = dict(self.quiz_service.skill.model_info)
                yield _sse_frame(
                    "text.done",
                    {
                        "message_id": str(teacher_message_id),
                        "content": content,
                        "model_info": model_info,
                        "usage": {
                            "input_tokens": sum(
                                len(item["content"]) for item in history
                            ),
                            "output_tokens": len(content),
                        },
                    },
                    event_id=teacher_message_id,
                )
                teacher_message = Message(
                    message_id=teacher_message_id,
                    conversation_id=conversation_id,
                    role="TEACHER",
                    type="TEXT",
                    content=content,
                    metadata_={"tool": "quiz", "quiz_session_id": quiz_session_id},
                    sequence=teacher_sequence,
                    model_info=model_info,
                    created_at=teacher_created_at,
                )
                session.add(teacher_message)
                conversation.last_message_at = teacher_created_at
                try:
                    await session.commit()
                except Exception:
                    await session.rollback()
                    yield _sse_error(
                        request_id,
                        "MESSAGE_PERSISTENCE_ERROR",
                        "assistant message could not be persisted",
                    )
                    return
                yield _sse_frame(
                    "message.done",
                    {
                        "message_id": str(teacher_message_id),
                        "conversation_id": str(conversation_id),
                        "sequence": teacher_sequence,
                        "created_at": _isoformat_z(teacher_created_at),
                        "metadata": {"tool": "quiz", "quiz_session_id": quiz_session_id},
                    },
                    event_id=teacher_message_id,
                )
                return

            if evidence_reply is not None:
                content = evidence_reply
                model_info = {"provider": "rule", "model": "memory-rule-v1"}
                delta_index = 0
                for index in range(0, len(content), 8):
                    chunk = content[index : index + 8]
                    yield _sse_frame(
                        "text.delta",
                        {
                            "message_id": str(teacher_message_id),
                            "delta": chunk,
                            "index": delta_index,
                            "sequence": teacher_sequence,
                        },
                        event_id=teacher_message_id,
                    )
                    delta_index += 1
                yield _sse_frame(
                    "text.done",
                    {
                        "message_id": str(teacher_message_id),
                        "content": content,
                        "model_info": model_info,
                        "usage": {
                            "input_tokens": sum(
                                len(item["content"]) for item in history
                            ),
                            "output_tokens": len(content),
                        },
                    },
                    event_id=teacher_message_id,
                )
                teacher_message = Message(
                    message_id=teacher_message_id,
                    conversation_id=conversation_id,
                    role="TEACHER",
                    type="TEXT",
                    content=content,
                    metadata_={},
                    sequence=teacher_sequence,
                    model_info=model_info,
                    created_at=teacher_created_at,
                )
                session.add(teacher_message)
                conversation.last_message_at = teacher_created_at
                try:
                    await session.commit()
                except Exception:
                    await session.rollback()
                    yield _sse_error(
                        request_id,
                        "MESSAGE_PERSISTENCE_ERROR",
                        "assistant message could not be persisted",
                    )
                    return
                yield _sse_frame(
                    "message.done",
                    {
                        "message_id": str(teacher_message_id),
                        "conversation_id": str(conversation_id),
                        "sequence": teacher_sequence,
                        "created_at": _isoformat_z(teacher_created_at),
                        "metadata": {},
                    },
                    event_id=teacher_message_id,
                )
                return

            chunks: list[str] = []
            try:
                provider = get_ai_provider()
                delta_index = 0
                async for chunk in self._provider_chunks(
                    provider, history, system_prompt
                ):
                    if chunk is None:
                        yield ": ping\n\n"
                        continue
                    if not chunk:
                        continue
                    chunks.append(chunk)
                    yield _sse_frame(
                        "text.delta",
                        {
                            "message_id": str(teacher_message_id),
                            "delta": chunk,
                            "index": delta_index,
                            "sequence": teacher_sequence,
                        },
                        event_id=teacher_message_id,
                    )
                    delta_index += 1

                content = "".join(chunks)
                model_info = provider.model_info
                yield _sse_frame(
                    "text.done",
                    {
                        "message_id": str(teacher_message_id),
                        "content": content,
                        "model_info": model_info,
                        "usage": {
                            "input_tokens": sum(
                                len(item["content"]) for item in history
                            ),
                            "output_tokens": len(content),
                        },
                    },
                    event_id=teacher_message_id,
                )

                teacher_message = Message(
                    message_id=teacher_message_id,
                    conversation_id=conversation_id,
                    role="TEACHER",
                    type="TEXT",
                    content=content,
                    metadata_={},
                    sequence=teacher_sequence,
                    model_info=model_info,
                    created_at=teacher_created_at,
                )
                session.add(teacher_message)
                conversation.last_message_at = teacher_created_at
                try:
                    await session.commit()
                except Exception:
                    await session.rollback()
                    yield _sse_error(
                        request_id,
                        "MESSAGE_PERSISTENCE_ERROR",
                        "assistant message could not be persisted",
                    )
                    return

                yield _sse_frame(
                    "message.done",
                    {
                        "message_id": str(teacher_message_id),
                        "conversation_id": str(conversation_id),
                        "sequence": teacher_sequence,
                        "created_at": _isoformat_z(teacher_created_at),
                        "metadata": {},
                    },
                    event_id=teacher_message_id,
                )
            except Exception:
                await session.rollback()
                yield _sse_error(
                    request_id,
                    "AI_PROVIDER_ERROR",
                    "AI provider unavailable",
                )

        return stream()

    async def _provider_chunks(
        self,
        provider: AIProvider,
        history: list[dict[str, str]],
        system_prompt: str,
    ) -> AsyncIterator[str | None]:
        """Bridge provider output to a queue so 15s heartbeats remain reliable."""
        queue: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

        async def produce() -> None:
            try:
                async for chunk in provider.stream_chat(history, system_prompt):
                    await queue.put(("chunk", chunk))
                await queue.put(("done", None))
            except Exception as exc:
                await queue.put(("error", exc))

        producer = asyncio.create_task(produce())
        try:
            while True:
                try:
                    kind, value = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield None
                    continue
                if kind == "chunk":
                    yield str(value)
                elif kind == "done":
                    return
                else:
                    if isinstance(value, Exception):
                        raise value
                    raise RuntimeError("AI provider stream failed")
        finally:
            if not producer.done():
                producer.cancel()
            with suppress(asyncio.CancelledError):
                await producer

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
