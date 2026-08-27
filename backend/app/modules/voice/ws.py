"""Voice WebSocket endpoint: frames, state machine, mock ASR/TTS, barge-in."""

import asyncio
import base64
import json
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.ai.voice import ASRProvider, TTSUnavailableError, get_asr_provider, get_tts_provider
from app.infrastructure.database.models import (
    Conversation,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.modules.conversation.schemas import SendMessageRequest
from app.modules.conversation.service import ConversationService
from app.modules.identity.security import decode_access_token

router = APIRouter(tags=["voice"])

conversation_service = ConversationService()


@dataclass
class VoiceSession:
    """按学生复用的语音状态机（barge-in / 分块缓冲）。

    注意：页面 ScreenContext 不放在这里——它必须随连接生命周期隔离，
    否则上一条连接的 book/chapter 会跨会话残留。见 voice_ws 内的
    ``screen_context_box``。
    """

    state: str = "IDLE"
    chunks: list[str] = field(default_factory=list)
    task: asyncio.Task | None = None


SESSIONS: dict[str, VoiceSession] = {}


async def _send(websocket: WebSocket, payload: dict) -> None:
    await websocket.send_text(json.dumps(payload, ensure_ascii=False))


async def _set_state(
    websocket: WebSocket,
    session_state: VoiceSession,
    state: str,
) -> None:
    session_state.state = state
    await _send(websocket, {"type": "state", "state": state})


def _parse_sse_text_done(raw: str) -> str | None:
    for frame in raw.split("\n\n"):
        if not frame.strip():
            continue
        event_name = None
        data_lines: list[str] = []
        for line in frame.splitlines():
            if line.startswith("event: "):
                event_name = line[7:]
            elif line.startswith("data: "):
                data_lines.append(line[6:])
        if event_name == "text.done" and data_lines:
            payload = json.loads("\n".join(data_lines))
            return str(payload.get("content", ""))
    return None


async def _collect_reply(stream) -> str:
    reply: str | None = None
    async for frame in stream:
        content = _parse_sse_text_done(frame)
        if content is not None:
            reply = content
    return reply or "好的，我明白了。"


async def _handle_utterance(
    websocket: WebSocket,
    session,
    *,
    user_id: UUID,
    conversation_id: UUID,
    voice_session: VoiceSession,
    asr_provider: ASRProvider,
    screen_context_box: dict,
) -> None:
    transcript_id = str(uuid4())
    try:
        audio_data = b"".join(
            base64.b64decode(chunk) for chunk in voice_session.chunks if chunk
        )
        transcribe_async = getattr(asr_provider, "transcribe_async", None)
        if transcribe_async is not None:
            text = await transcribe_async(audio_data)
        else:
            text = asr_provider.transcribe(audio_data)
        await _send(
            websocket,
            {"type": "partial", "text": text, "transcript_id": transcript_id},
        )
        await _send(
            websocket,
            {
                "type": "final",
                "text": text,
                "conversation_id": str(conversation_id),
            },
        )
        if not text:
            reply = "我没有听清，请再说一遍。"
        else:
            stream = await conversation_service.send_message(
                session,
                user_id,
                conversation_id,
                SendMessageRequest(
                    content=text,
                    type="TEXT",
                    screen_context=screen_context_box["value"],
                ),
            )
            reply = await _collect_reply(stream)

        # 文字回复和 TTS 是两条独立能力：即使 TTS 被关闭、返回静音音频或播放失败，
        # 前端也应该先收到可展示的文字回复。
        await _send(
            websocket,
            {
                "type": "reply",
                "text": reply,
                "conversation_id": str(conversation_id),
            },
        )

        try:
            audio = get_tts_provider().synthesize(reply)
        except TTSUnavailableError as exc:
            # Phase 4：TTS 未配置/失败时明确告知，不再静音假音频；
            # 文字回复已在上方送达，会话回到 IDLE 可继续下一轮。
            await _send(
                websocket,
                {
                    "type": "error",
                    "code": "TTS_UNAVAILABLE",
                    "message": str(exc),
                },
            )
            await _set_state(websocket, voice_session, "IDLE")
        else:
            if voice_session.state == "THINKING":
                await _set_state(websocket, voice_session, "SPEAKING")
                await _send(
                    websocket,
                    {
                        "type": "audio",
                        "data": base64.b64encode(audio).decode("ascii"),
                    },
                )
                await _set_state(websocket, voice_session, "IDLE")
    except Exception as exc:
        await _send(
            websocket,
            {
                "type": "error",
                "code": "VOICE_PROCESSING_ERROR",
                "message": str(exc),
            },
        )
        await _set_state(websocket, voice_session, "ERROR")
        await _set_state(websocket, voice_session, "IDLE")
    finally:
        voice_session.chunks = []
        voice_session.task = None


@router.websocket("/api/v1/voice/ws")
async def voice_ws(websocket: WebSocket):
    await websocket.accept()
    token = websocket.query_params.get("token")
    conversation_id_raw = websocket.query_params.get("conversation_id")

    async def reject(code: int, error_code: str, message: str) -> None:
        await _send(
            websocket,
            {"type": "error", "code": error_code, "message": message},
        )
        await websocket.close(code=code)

    if not token or not conversation_id_raw:
        await reject(4401, "UNAUTHENTICATED", "token and conversation_id are required")
        return
    try:
        conversation_id = UUID(conversation_id_raw)
        payload = decode_access_token(token)
        user_id = UUID(payload["sub"])
    except (ValueError, KeyError) as exc:
        await reject(4401, "UNAUTHENTICATED", "invalid token or conversation id")
        return

    async with async_session() as session:
        user = await session.get(User, user_id)
        if user is None or user.user_type != "STUDENT":
            await reject(4403, "FORBIDDEN", "student access required")
            return
        # Phase 5-A：禁用账号的 WebSocket 一并拒绝
        if getattr(user, "status", "ACTIVE") == "DISABLED":
            await reject(4401, "ACCOUNT_DISABLED", "account is disabled")
            return
        profile = (
            await session.execute(
                select(StudentProfile).where(StudentProfile.user_id == user.user_id)
            )
        ).scalar_one_or_none()
        if profile is None:
            await reject(4403, "FORBIDDEN", "student profile not found")
            return
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None:
            await reject(4404, "CONVERSATION_NOT_FOUND", "conversation not found")
            return
        if conversation.student_id != profile.student_id:
            await reject(4403, "FORBIDDEN", "conversation does not belong to student")
            return

        voice_session = SESSIONS.setdefault(
            str(profile.student_id), VoiceSession()
        )
        # 连接级页面上下文：新连接从空开始，断开即丢弃（Phase 2 缺口 1）。
        screen_context_box: dict = {"value": None}
        asr_provider = get_asr_provider()
        await _send(websocket, {"type": "state", "state": voice_session.state})
        try:
            while True:
                raw = await websocket.receive_text()
                message = json.loads(raw)
                frame_type = message.get("type")
                if frame_type == "ping":
                    await _send(websocket, {"type": "pong"})
                elif frame_type == "context":
                    # Phase 2-A4 + 缺口 1：客户端可在连接建立后或任意时刻
                    # 上报/更新结构化页面上下文（例如语音中切换 Reader 页面）；
                    # 仅接受 JSON 对象，下一轮 utterance 使用最新值。
                    context = message.get("screen_context")
                    if isinstance(context, dict):
                        screen_context_box["value"] = context
                        await _send(websocket, {"type": "state", "state": voice_session.state})
                    else:
                        await _send(
                            websocket,
                            {
                                "type": "error",
                                "code": "INVALID_FRAME",
                                "message": "context frame requires screen_context object",
                            },
                        )
                elif frame_type == "cancel":
                    if voice_session.task is not None:
                        voice_session.task.cancel()
                        voice_session.task = None
                    voice_session.chunks = []
                    await _set_state(websocket, voice_session, "IDLE")
                elif frame_type == "audio_chunk":
                    if voice_session.state in {"SPEAKING", "THINKING"}:
                        if voice_session.task is not None:
                            voice_session.task.cancel()
                            voice_session.task = None
                        voice_session.chunks = []
                        await _set_state(websocket, voice_session, "LISTENING")
                    elif voice_session.state == "IDLE":
                        await _set_state(websocket, voice_session, "LISTENING")
                    data = message.get("data", "")
                    if isinstance(data, str):
                        voice_session.chunks.append(data)
                elif frame_type == "audio_end":
                    if voice_session.state == "IDLE":
                        await _set_state(websocket, voice_session, "LISTENING")
                    await _set_state(websocket, voice_session, "THINKING")
                    voice_session.task = asyncio.create_task(
                        _handle_utterance(
                            websocket,
                            session,
                            user_id=user.user_id,
                            conversation_id=conversation_id,
                            voice_session=voice_session,
                            asr_provider=asr_provider,
                            screen_context_box=screen_context_box,
                        )
                    )
                else:
                    await _send(
                        websocket,
                        {
                            "type": "error",
                            "code": "INVALID_FRAME",
                            "message": f"unknown frame type: {frame_type}",
                        },
                    )
        except WebSocketDisconnect:
            if voice_session.task is not None:
                voice_session.task.cancel()
                voice_session.task = None
            voice_session.chunks = []
            screen_context_box["value"] = None  # 断开即清，杜绝跨连接残留
