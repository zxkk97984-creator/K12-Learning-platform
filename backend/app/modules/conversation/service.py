import asyncio
import base64
import binascii
import json
import logging
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
from app.config import settings
from app.infrastructure.cache.redis import acquire_lock, release_lock
from app.infrastructure.database.models import (
    Conversation,
    ConversationSummary,
    Message,
    StudentProfile,
    TeacherRole,
)
from app.jobs.queue import enqueue, has_pending_job
from app.modules.conversation.context_window import build_input_window
from app.modules.conversation.context_window import estimate_tokens
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
from app.modules.memory.agent_md import (
    build_evidence_context,
    build_evidence_reply,
    is_evidence_question,
)
from app.modules.conversation.teacher_context import (
    build_teacher_context,
    teacher_usage_note,
)
from app.modules.knowledge.retrieval import retrieve
from app.modules.identity.service import IdentityService
from app.modules.quiz.schemas import CreateQuizSessionRequest
from app.modules.quiz.service import QuizService


QUIZ_INTENT_KEYWORDS = ("出题", "题目", "测验", "quiz", "考考我")

logger = logging.getLogger(__name__)

_CONVERSATION_LOCKS: dict[str, asyncio.Lock] = {}


class EmptyAIResponseError(RuntimeError):
    """The provider completed without returning an assistant message."""


def _conversation_lock(conversation_id: UUID) -> asyncio.Lock:
    return _CONVERSATION_LOCKS.setdefault(str(conversation_id), asyncio.Lock())


def _is_quiz_intent(content: str) -> bool:
    normalized = content.casefold()
    return any(keyword.casefold() in normalized for keyword in QUIZ_INTENT_KEYWORDS)


def _uuid_or_none(value: Any) -> UUID | None:
    """把 ScreenContext 里的 id 字段安全解析为 UUID；缺失/非法返回 None。"""
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


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


def _usage_report(
    provider: AIProvider,
    history: list[dict[str, str]],
    output_text: str,
) -> dict[str, Any]:
    """T20 §20b：优先用 provider 实际 usage；拿不到则标注 estimated，不把字符数冒充 token。"""
    usage = getattr(provider, "last_usage", None)
    if isinstance(usage, dict):
        prompt_tokens = usage.get("prompt_tokens")
        completion_tokens = usage.get("completion_tokens")
        if prompt_tokens is not None or completion_tokens is not None:
            return {
                "estimated": False,
                "input_tokens": prompt_tokens,
                "output_tokens": completion_tokens,
            }
    # 无真实 usage：估算（字符数 × 系数），明确标注 estimated 与估算方法。
    return {
        "estimated": True,
        "estimate_method": "chars_to_tokens",
        "chars_per_token_estimate": 0.6,
        "input_estimate": sum(estimate_tokens(str(item.get("content", ""))) for item in history),
        "output_estimate": estimate_tokens(output_text),
    }


def _role_summary(role: TeacherRole | None) -> dict | None:
    if role is None:
        return None
    return {
        "role_id": str(role.role_id),
        "name": role.name,
        "tone": role.tone,
        "teaching_style": role.teaching_style,
    }


def _list_item_dto(
    conversation: Conversation,
    *,
    role: TeacherRole | None = None,
    preview: str | None = None,
) -> ConversationListItemDTO:
    return ConversationListItemDTO(
        conversation_id=conversation.conversation_id,
        title=conversation.title,
        status=conversation.status,
        channel=conversation.channel,
        teacher_role_id=conversation.teacher_role_id,
        teacher_role=_role_summary(role),
        last_message_preview=preview,
        last_message_at=conversation.last_message_at,
        updated_at=conversation.updated_at,
    )


async def _recent_messages_for(
    session: AsyncSession, conversation_ids: list[UUID], per_conversation: int = 5
) -> dict[UUID, list[MessageDTO]]:
    """批量取每个会话最近 N 条消息（sequence 倒序截取后反转）。"""
    if not conversation_ids:
        return {}
    rows = (
        await session.execute(
            select(Message)
            .where(Message.conversation_id.in_(conversation_ids))
            .order_by(Message.conversation_id.asc(), Message.sequence.desc())
        )
    ).scalars().all()
    grouped: dict[UUID, list[MessageDTO]] = {}
    for message in rows:
        bucket = grouped.setdefault(message.conversation_id, [])
        if len(bucket) < per_conversation:
            bucket.append(_message_dto(message))
    for conv_id in grouped:
        grouped[conv_id].reverse()
    return grouped


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


def _latest_summary_query(conversation_id: UUID):
    return (
        select(ConversationSummary)
        .where(ConversationSummary.conversation_id == conversation_id)
        .order_by(ConversationSummary.summary_version.desc())
        .limit(1)
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

        # Phase 4：真实 teacher_role 摘要 + 最近一条消息预览
        role_ids = {row.teacher_role_id for row in page if row.teacher_role_id}
        roles: dict[UUID, TeacherRole] = {}
        if role_ids:
            role_rows = (
                await session.execute(
                    select(TeacherRole).where(TeacherRole.role_id.in_(role_ids))
                )
            ).scalars().all()
            roles = {role.role_id: role for role in role_rows}
        recents = await _recent_messages_for(
            session, [row.conversation_id for row in page], per_conversation=1
        )

        items = []
        for row in page:
            preview_messages = recents.get(row.conversation_id, [])
            preview = preview_messages[0].content[:80] if preview_messages else None
            items.append(
                _list_item_dto(row, role=roles.get(row.teacher_role_id), preview=preview)
            )
        return items, PageMeta(next_cursor=next_cursor, has_more=has_more)

    async def create_conversation(
        self,
        session: AsyncSession,
        user_id: UUID,
        request: CreateConversationRequest,
    ) -> ConversationDTO:
        profile = await self._get_profile(session, user_id)
        role_id = (
            request.teacher_role_id
            or profile.current_teacher_role_id
            or await IdentityService().resolve_default_role_id(session, profile)
        )
        conversation = Conversation(
            student_id=profile.student_id,
            # teacher_roles is a Phase 11 table, so this reference is stored
            # without a FK and falls back to the student's current role.
            teacher_role_id=role_id,
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

    async def _enqueue_summary_if_needed(
        self, session: AsyncSession, conversation_id: UUID
    ) -> None:
        """Queue summary work after persistence without affecting SSE output."""
        try:
            count = int(
                (
                    await session.execute(
                        select(func.count(Message.message_id)).where(
                            Message.conversation_id == conversation_id
                        )
                    )
                ).scalar_one()
            )
            if count < settings.summary_message_threshold:
                return
            payload = {"conversation_id": str(conversation_id)}
            if await has_pending_job(session, "conversation_summary", payload):
                return
            await enqueue(session, "conversation_summary", payload)
            await session.commit()
        except Exception:  # pragma: no cover - summary must not break chat
            await session.rollback()
            logger.warning("conversation summary enqueue failed", exc_info=True)

    async def send_message(
        self,
        session: AsyncSession,
        user_id: UUID,
        conversation_id: UUID,
        request: SendMessageRequest,
        *,
        idempotency_key: str | None = None,
        replay_flag: dict | None = None,
    ) -> AsyncIterator[str]:
        """Serialize turns in one conversation until its SSE stream finishes.

        Phase 5-A：携带 idempotency_key 且命中同一会话内的历史学生消息时，
        返回可消费的 replay SSE（恢复原教师正文），不新增任何消息。
        """
        lock_key = f"lock:conversation:{conversation_id}"
        redis_token = await acquire_lock(
            lock_key, settings.redis_lock_ttl_seconds
        )
        local_lock: asyncio.Lock | None = None
        if redis_token is None:
            local_lock = _conversation_lock(conversation_id)
            await local_lock.acquire()
        try:
            stream = await self._send_message_locked(
                session,
                user_id,
                conversation_id,
                request,
                idempotency_key=idempotency_key,
                replay_flag=replay_flag,
            )
        except BaseException:
            if redis_token is not None:
                await release_lock(lock_key, redis_token)
            elif local_lock is not None:
                local_lock.release()
            raise

        async def guarded_stream() -> AsyncIterator[str]:
            try:
                async for frame in stream:
                    yield frame
            finally:
                if redis_token is not None:
                    await release_lock(lock_key, redis_token)
                elif local_lock is not None:
                    local_lock.release()

        return guarded_stream()

    async def _send_message_locked(
        self,
        session: AsyncSession,
        user_id: UUID,
        conversation_id: UUID,
        request: SendMessageRequest,
        *,
        idempotency_key: str | None = None,
        replay_flag: dict | None = None,
    ) -> AsyncIterator[str]:
        """Persist the student turn, then return its AI-backed SSE generator.

        The preflight work intentionally happens before the StreamingResponse is
        created, so ownership, not-found, deleted, and validation errors retain
        their normal HTTP status and error envelope.
        """
        profile = await self._get_profile(session, user_id)
        # Phase 5-A：对会话行 FOR UPDATE——max+1 序号分配在行锁内串行化
        conversation = await session.get(Conversation, conversation_id, with_for_update=True)
        if conversation is None:
            raise _error(404, "CONVERSATION_NOT_FOUND", "conversation not found")

        # 幂等重放：同会话+同 key 的历史学生消息存在则回放其教师回复
        if idempotency_key:
            prior_student = (
                await session.execute(
                    select(Message)
                    .where(
                        Message.conversation_id == conversation_id,
                        Message.role == "STUDENT",
                        Message.metadata_["idempotency_key"].as_string() == idempotency_key,
                    )
                    .order_by(Message.sequence.asc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if prior_student is not None:
                if replay_flag is not None:
                    replay_flag["replayed"] = True
                return await self._replay_stream(
                    session, conversation_id, prior_student, request_id=str(uuid4())
                )
        if conversation.student_id != profile.student_id:
            raise _error(403, "FORBIDDEN", "conversation does not belong to student")
        if conversation.status == "DELETED":
            raise _error(
                409,
                "CONVERSATION_INVALID_STATUS",
                "deleted conversation cannot receive messages",
            )

        # Phase 2-A：screen_context 是客户端权威快照——提供时整体替换旧值，
        # 保证「离开 Reader 后发送干净上下文」能真正清掉旧 book/chapter；
        # 未提供时沿用会话已有上下文。选中文本作为瞬时叠加项。
        if request.screen_context is not None:
            current_context = dict(request.screen_context)
        else:
            current_context = dict(conversation.current_page_context or {})
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
            metadata_=({"idempotency_key": idempotency_key} if idempotency_key else {}),
            sequence=student_sequence,
            created_at=now,
        )
        conversation.current_page_context = current_context
        conversation.last_message_at = now
        session.add(student_message)
        await session.commit()
        await session.refresh(student_message)
        if replay_flag is not None:
            replay_flag["replayed"] = False

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

        summary_content = ""
        summary_message_count = 0
        summary_version: int | None = None
        summary = (
            await session.execute(_latest_summary_query(conversation_id))
        ).scalar_one_or_none()
        if summary is not None and summary.summary.strip():
            summary_content = summary.summary.strip()
            summary_message_count = int(summary.message_covered_count or 0)
            summary_version = summary.summary_version
        summary_context = (
            f"【本会话长对话摘要（v{summary_version}）】\n{summary_content}"
            if summary_content
            else ""
        )
        # T20 §20a：输入 = 摘要（并入 system prompt）+ 边界后最近消息，按预算截取；
        # 摘要与最近消息不重叠，且始终保留学生的当前问题。
        windowed = build_input_window(
            summary=summary_content,
            summary_message_count=summary_message_count,
            summary_version=summary_version,
            history=history,
            token_budget=settings.context_window_token_budget,
        )
        history = windowed.messages
        if windowed.early_context_unavailable and not summary_context:
            summary_context = "【提示】对话较长，较早的上下文可能不可用，若学生问到较早已答过的问题请如实说明。"

        teacher_message_id = uuid4()
        teacher_sequence = student_sequence + 1
        teacher_created_at = datetime.now(timezone.utc)
        request_id = str(uuid4())
        quiz_intent = _is_quiz_intent(request.content)
        evidence_reply: str | None = None
        evidence_context: str | None = None
        evidence_model_info = {"provider": "rule", "model": "memory-rule-v1"}
        try:
            if is_evidence_question(request.content):
                evidence_reply = await build_evidence_reply(
                    session, profile.student_id, request.content
                )
                evidence_context = await build_evidence_context(
                    session, profile.student_id, request.content
                )
        except Exception:  # pragma: no cover - evidence citation must not break chat
            evidence_reply = None
        real_provider = settings.ai_provider.strip().lower() == "openai_compatible"
        if real_provider and evidence_context:
            try:
                evidence_prompt = (
                    "你是霜铃，一位严谨、可解释的中文 K12 数字教师。\n"
                    f"【证据上下文】\n{evidence_context}\n"
                    "请基于以上真实证据回答学生为什么这样判断，只引用证据中出现的事实。"
                )
                provider = get_ai_provider()
                llm_chunks = []
                async for chunk in provider.stream_chat([], evidence_prompt):
                    llm_chunks.append(chunk)
                if "".join(llm_chunks).strip():
                    evidence_reply = "".join(llm_chunks)
                    evidence_model_info = provider.model_info
            except Exception:
                evidence_reply = evidence_reply or None
        retrieved_chunks = []
        try:
            if not quiz_intent and evidence_reply is None:
                retrieved_chunks = await retrieve(
                    session,
                    request.content,
                    screen_context=current_context,
                    limit=3,
                )
        except Exception:  # pragma: no cover - retrieval must not break chat
            retrieved_chunks = []
        reference_block = ""
        if retrieved_chunks:
            lines = ["【知识库参考】"]
            for item in retrieved_chunks:
                url = item.chunk.metadata.get("source_url", "")
                lines.append(f"- 内容：{item.chunk.content}")
                lines.append(f"- 来源：{item.source_name}")
                lines.append(f"- 链接：{url}")
            reference_block = "\n".join(lines)
        persona_block = ""
        role_id = conversation.teacher_role_id or profile.current_teacher_role_id
        if role_id is not None:
            role = await session.get(TeacherRole, role_id)
            if role is not None:
                persona = role.persona or {}
                persona_block = (
                    "【教师人格】\n"
                    f"base_persona：{persona.get('base_persona', '')}\n"
                    f"tone：{role.tone}\n"
                    f"teaching_style：{role.teaching_style}"
                )
        # Phase 2-C：从 DB 聚合完整 TeacherContext（档案/偏好/记忆/画像/
        # 最近学习与测验/当前阅读位置），失败不阻塞对话。
        try:
            teacher_context_block = await build_teacher_context(
                session,
                student_id=profile.student_id,
                grade=profile.grade,
                language=profile.language,
                learning_goal=profile.learning_goal,
                current_context=current_context,
            )
            teacher_context_block += "\n\n" + teacher_usage_note()
        except Exception:  # pragma: no cover - context must not break chat
            logger.warning("teacher context build failed", exc_info=True)
            teacher_context_block = ""
        instruction_block = (
            "你是霜铃，一位耐心、清晰、不编造事实的中文 K12 数字教师。"
            "请根据学生的问题循序解释，鼓励学生自己思考；引用知识库或证据时必须注明来源。"
            f"当前页面上下文：{json.dumps(current_context, ensure_ascii=False)}"
        )
        system_prompt = "\n\n".join(
            part
            for part in [
                persona_block,
                summary_context,
                teacher_context_block,
                reference_block,
                f"【证据上下文】\n{evidence_context}" if evidence_context else "",
                instruction_block,
            ]
            if part
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
                    # Phase 2-B：从当前页面上下文取 book/chapter，使测验与
                    # 阅读位置真实关联；上下文缺省时退化为无章节 AI 小测。
                    ctx_book_id = _uuid_or_none(
                        current_context.get("bookId") or current_context.get("book_id")
                    )
                    ctx_chapter_id = _uuid_or_none(
                        current_context.get("chapterId")
                        or current_context.get("chapter_id")
                    )
                    quiz_session = await self.quiz_service.create_session(
                        session,
                        user_id,
                        CreateQuizSessionRequest(
                            conversation_id=conversation_id,
                            book_id=ctx_book_id,
                            chapter_id=ctx_chapter_id,
                            quiz_kind="CHAPTER_QUIZ" if ctx_chapter_id else "AI_QUIZ",
                            question_count=3,
                            difficulty="MEDIUM",
                            allow_bank_fallback=False,
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
                model_info = dict(quiz_session.model_info or {})
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
                await self._enqueue_summary_if_needed(session, conversation_id)
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
                model_info = evidence_model_info
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
                await self._enqueue_summary_if_needed(session, conversation_id)
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
                if not content.strip():
                    raise EmptyAIResponseError(
                        "AI provider returned an empty response"
                    )
                model_info = provider.model_info
                usage = _usage_report(provider, history, content)
                yield _sse_frame(
                    "text.done",
                    {
                        "message_id": str(teacher_message_id),
                        "content": content,
                        "model_info": model_info,
                        "usage": usage,
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

                await self._enqueue_summary_if_needed(session, conversation_id)
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
            except EmptyAIResponseError:
                logger.warning("AI provider returned an empty response")
                await session.rollback()
                yield _sse_error(
                    request_id,
                    "AI_EMPTY_RESPONSE",
                    "AI 没有返回有效内容，请重试",
                )
            except Exception:
                logger.exception("AI provider stream failed")
                await session.rollback()
                yield _sse_error(
                    request_id,
                    "AI_PROVIDER_ERROR",
                    "AI provider unavailable",
                )

        return stream()

    async def _replay_stream(
        self,
        session: AsyncSession,
        conversation_id: UUID,
        prior_student: Message,
        *,
        request_id: str,
    ):
        """构造幂等重放 SSE：恢复原教师正文（及 quiz 工具帧），不再调用模型。"""
        teacher_message = (
            await session.execute(
                select(Message)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.role == "TEACHER",
                    Message.sequence > prior_student.sequence,
                )
                .order_by(Message.sequence.asc())
                .limit(1)
            )
        ).scalar_one_or_none()

        async def stream() -> AsyncIterator[str]:
            if teacher_message is None:
                # 历史异常（学生消息后无教师回复）：以空回复收尾，仍可消费
                yield _sse_frame(
                    "message.start",
                    {
                        "message_id": str(prior_student.message_id),
                        "conversation_id": str(conversation_id),
                        "role": "TEACHER",
                        "type": "TEXT",
                        "sequence": prior_student.sequence + 1,
                    },
                    event_id=prior_student.message_id,
                )
                yield _sse_frame(
                    "message.done",
                    {"message_id": str(prior_student.message_id), "conversation_id": str(conversation_id)},
                    event_id=prior_student.message_id,
                )
                return

            teacher_id = teacher_message.message_id
            metadata = teacher_message.metadata_ or {}
            is_quiz = metadata.get("tool") == "quiz"
            yield _sse_frame(
                "message.start",
                {
                    "message_id": str(teacher_id),
                    "conversation_id": str(conversation_id),
                    "role": "TEACHER",
                    "type": "TEXT",
                    "sequence": teacher_message.sequence,
                    "created_at": _isoformat_z(teacher_message.created_at),
                    "request_id": request_id,
                    "replay": True,
                },
                event_id=teacher_id,
            )
            if is_quiz:
                tool_run_id = f"replay-{teacher_id}"
                yield _sse_frame(
                    "tool.start",
                    {
                        "tool_run_id": tool_run_id,
                        "tool": "quiz",
                        "state": "running",
                        "message_id": str(teacher_id),
                        "payload": {"quiz_session_id": None},
                    },
                    event_id=teacher_id,
                )
                yield _sse_frame(
                    "tool.result",
                    {
                        "tool_run_id": tool_run_id,
                        "tool": "quiz",
                        "status": "success",
                        "payload": {
                            "quiz_session_id": metadata.get("quiz_session_id"),
                            "skill_version": None,
                        },
                    },
                    event_id=teacher_id,
                )
            content = teacher_message.content
            for index in range(0, len(content), 16):
                yield _sse_frame(
                    "text.delta",
                    {
                        "message_id": str(teacher_id),
                        "delta": content[index : index + 16],
                        "index": index,
                        "sequence": teacher_message.sequence,
                    },
                    event_id=teacher_id,
                )
            yield _sse_frame(
                "text.done",
                {
                    "message_id": str(teacher_id),
                    "content": content,
                    "model_info": teacher_message.model_info or {},
                    "usage": {"input_tokens": 0, "output_tokens": len(content)},
                },
                event_id=teacher_id,
            )
            yield _sse_frame(
                "message.done",
                {
                    "message_id": str(teacher_id),
                    "conversation_id": str(conversation_id),
                    "sequence": teacher_message.sequence,
                    "metadata": metadata,
                },
                event_id=teacher_id,
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
            await session.execute(_latest_summary_query(conversation_id))
        ).scalar_one_or_none()

        # Phase 4：真实 teacher_role 摘要 + 最近 5 条消息
        role = (
            await session.get(TeacherRole, conversation.teacher_role_id)
            if conversation.teacher_role_id
            else None
        )
        item = _list_item_dto(conversation, role=role)
        recent_map = await _recent_messages_for(session, [conversation_id], per_conversation=5)
        return ConversationDTO(
            **item.model_dump(),
            student_id=conversation.student_id,
            current_page_context=conversation.current_page_context or {},
            recent_messages=[m.model_dump() for m in recent_map.get(conversation_id, [])],
            conversation_summary=summary.summary if summary is not None else None,
        )

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
            await session.execute(_latest_summary_query(conversation_id))
        ).scalar_one_or_none()
        return ConversationSummaryDTO.model_validate(summary) if summary else None


def _encode_cursor_value(sequence: int, entity_id: UUID) -> str:
    payload = json.dumps([sequence, str(entity_id)])
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")
