"""Rule-based conversation summary job handler."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.infrastructure.database.models import ConversationSummary, Message

_KEY_MESSAGE_TYPES = {"QUIZ", "HINT", "RECOMMENDATION", "LEARNING_SUMMARY", "SYSTEM"}
_MAX_LINE_CHARS = 160


def _summary_messages(messages: list[Message]) -> list[Message]:
    selected: list[Message] = []
    if messages:
        selected.append(messages[0])
    selected.extend(
        message
        for message in messages[1:-1]
        if message.type in _KEY_MESSAGE_TYPES
    )
    if messages and messages[-1] not in selected:
        selected.append(messages[-1])
    return selected


def _summary_text(messages: list[Message]) -> str:
    lines = [
        f"{message.role}: {message.content.strip()[:_MAX_LINE_CHARS]}"
        for message in _summary_messages(messages)
        if message.content.strip()
    ]
    return "会话摘要：\n" + "\n".join(lines)


async def handle_conversation_summary(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    raw_conversation_id = payload.get("conversation_id")
    if raw_conversation_id is None:
        raise ValueError("conversation_summary payload requires conversation_id")
    try:
        conversation_id = UUID(str(raw_conversation_id))
    except (TypeError, ValueError) as exc:
        raise ValueError("conversation_summary conversation_id must be a UUID") from exc

    messages = (
        await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.sequence.asc(), Message.message_id.asc())
        )
    ).scalars().all()
    if len(messages) < settings.summary_message_threshold:
        return

    summary_text = _summary_text(messages)
    source_message_ids = [str(message.message_id) for message in _summary_messages(messages)]
    existing = (
        await session.execute(
            select(ConversationSummary)
            .where(ConversationSummary.conversation_id == conversation_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            ConversationSummary(
                conversation_id=conversation_id,
                summary=summary_text,
                token_count=len(summary_text),
                summary_version=1,
                source_message_ids=source_message_ids,
                model_info={"provider": "rule", "model": "conversation-summary-v1"},
            )
        )
    else:
        existing.summary = summary_text
        existing.token_count = len(summary_text)
        existing.summary_version = int(existing.summary_version or 0) + 1
        existing.source_message_ids = source_message_ids
        existing.model_info = {"provider": "rule", "model": "conversation-summary-v1"}
    # 该 handler 会被 Worker 与直接调用（测试/请求内）两种情况触发。
    # 若省略此处 commit，直接调用方（未再提交）将无法读到刚写入的摘要；
    # Worker 路径随后也 commit，二次 commit 为无害幂等。故保留内部 commit。
    await session.commit()
