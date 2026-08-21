"""Mock ASR/TTS providers (Phase 9 voice; real providers need keys later)."""

import asyncio
import io
import json
import wave
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from uuid import uuid4

import websockets

from app.config import settings


class ASRProvider(ABC):
    provider: str

    @abstractmethod
    def transcribe(self, audio_data: bytes) -> str:
        raise NotImplementedError


class TTSProvider(ABC):
    provider: str

    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        raise NotImplementedError


class MockASR(ASRProvider):
    """Deterministic mock: any non-empty audio maps to the acceptance phrase."""

    provider = "mock"

    def transcribe(self, audio_data: bytes) -> str:
        if not audio_data:
            return ""
        return "这里是什么意思"

    async def transcribe_async(self, audio_data: bytes) -> str:
        return self.transcribe(audio_data)


FREE_TIER_EXHAUSTED_CODE = "AllocationQuota.FreeTierOnly"


class ASRStartError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class AliyunASRSession:
    """百炼 Fun-ASR 双向 WebSocket 的一次识别会话。"""

    def __init__(self, websocket, task_id: str, model_name: str):
        self._websocket = websocket
        self._task_id = task_id
        self.model_name = model_name
        self._events: asyncio.Queue[dict | None] = asyncio.Queue()
        self._closed = False
        self._started: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._reader = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            async for raw in self._websocket:
                if isinstance(raw, bytes):
                    continue
                try:
                    message = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                header = message.get("header") or {}
                event = header.get("event")
                sentence = ((message.get("payload") or {}).get("output") or {}).get("sentence") or {}
                text = str(sentence.get("text") or "")
                if event == "task-started":
                    if not self._started.done():
                        self._started.set_result(None)
                elif event in {"result-generated", "transcription-result-changed"}:
                    if sentence.get("sentence_end"):
                        self._events.put_nowait({"type": "final", "text": text})
                    elif text:
                        self._events.put_nowait({"type": "partial", "text": text})
                elif event == "task-failed":
                    code = str(header.get("error_code") or "ASR_TASK_FAILED")
                    message_text = str(header.get("error_message") or "识别任务失败")
                    if not self._started.done():
                        self._started.set_exception(ASRStartError(code, message_text))
                    else:
                        self._events.put_nowait(
                            {"type": "error", "code": code, "message": message_text}
                        )
        except Exception:
            if not self._closed:
                error = ASRStartError("ASR_CONNECTION_ERROR", "识别服务连接失败")
                if not self._started.done():
                    self._started.set_exception(error)
                else:
                    self._events.put_nowait(
                        {"type": "error", "code": error.code, "message": str(error)}
                    )

    async def wait_started(self, timeout: float = 10.0) -> None:
        await asyncio.wait_for(asyncio.shield(self._started), timeout=timeout)

    async def send_audio(self, frame: bytes) -> None:
        if not self._closed:
            await self._websocket.send(frame)

    async def finish(self) -> None:
        if self._closed:
            return
        await self._websocket.send(
            json.dumps(
                {
                    "header": {
                        "action": "finish-task",
                        "task_id": self._task_id,
                        "streaming": "duplex",
                    },
                    "payload": {"input": {}},
                }
            )
        )
        try:
            await asyncio.wait_for(self._websocket.wait_closed(), timeout=5.0)
        except TimeoutError:
            pass
        await asyncio.sleep(0)
        self._closed = True
        self._events.put_nowait(None)

    async def abort(self) -> None:
        if self._closed:
            await self._websocket.close()
            return
        self._closed = True
        self._reader.cancel()
        await self._websocket.close()
        self._events.put_nowait(None)

    async def events(self) -> AsyncIterator[dict]:
        while True:
            event = await self._events.get()
            if event is None:
                break
            yield event


class AliyunASRProvider:
    """复用旧 K12 项目的实时 ASR 协议和同能力模型额度切换策略。"""

    def __init__(self, *, api_key: str | None = None, models: list[str] | None = None, connect=None):
        self._api_key = api_key if api_key is not None else settings.aliyun_dashscope_api_key
        self._models = tuple(dict.fromkeys(model.strip() for model in (models or settings.aliyun_asr_models) if model.strip()))
        if not self._models:
            raise ValueError("aliyun_asr_models 不能为空")
        self._exhausted_models: set[str] = set()
        self._connect = connect or websockets.connect

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    @property
    def exhausted_models(self) -> tuple[str, ...]:
        return tuple(model for model in self._models if model in self._exhausted_models)

    async def start_session(self) -> AliyunASRSession:
        if not self._api_key:
            raise ASRStartError("ASR_NOT_CONFIGURED", "未配置阿里云百炼 API Key")
        for model in self._models:
            if model in self._exhausted_models:
                continue
            task_id = str(uuid4())
            websocket = await self._connect(
                settings.aliyun_asr_ws_url,
                additional_headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "X-DashScope-DataInspection": "disable",
                },
                max_size=settings.asr_max_frame_bytes * 4,
            )
            session = AliyunASRSession(websocket, task_id, model)
            await websocket.send(
                json.dumps(
                    {
                        "header": {"action": "run-task", "task_id": task_id, "streaming": "duplex"},
                        "payload": {
                            "task_group": "audio",
                            "task": "asr",
                            "function": "recognition",
                            "model": model,
                            "parameters": {
                                "format": "pcm",
                                "sample_rate": settings.speech_sample_rate,
                                "language_hints": ["zh"],
                            },
                            "input": {},
                        },
                    }
                )
            )
            try:
                await session.wait_started()
                return session
            except ASRStartError as exc:
                await session.abort()
                if exc.code == FREE_TIER_EXHAUSTED_CODE:
                    self._exhausted_models.add(model)
                    continue
                raise
        raise ASRStartError(FREE_TIER_EXHAUSTED_CODE, "实时语音识别免费模型额度均已耗尽")

    async def transcribe_async(self, audio_data: bytes) -> str:
        if not audio_data:
            return ""
        session = await self.start_session()
        try:
            frame_size = settings.asr_max_frame_bytes
            for offset in range(0, len(audio_data), frame_size):
                await session.send_audio(audio_data[offset : offset + frame_size])
            await session.finish()
            final_text = ""
            async for event in session.events():
                if event.get("type") == "final":
                    final_text = str(event.get("text") or "")
            return final_text
        finally:
            await session.abort()


class MockTTS(TTSProvider):
    """Return a 1-second silent 8kHz mono 16-bit WAV for deterministic playback."""

    provider = "mock"
    sample_rate = 8000
    channels = 1
    sample_width = 2
    duration_seconds = 1

    def synthesize(self, text: str) -> bytes:
        del text
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(self.channels)
            wav.setsampwidth(self.sample_width)
            wav.setframerate(self.sample_rate)
            frames = b"\x00\x00" * (self.sample_rate * self.duration_seconds)
            wav.writeframes(frames)
        return buffer.getvalue()


def get_asr_provider() -> ASRProvider:
    if settings.voice_provider.strip().lower() == "mock":
        return MockASR()
    if settings.voice_provider.strip().lower() == "aliyun":
        return AliyunASRProvider()
    raise ValueError(f"unsupported ASR provider: {settings.voice_provider}")


def get_tts_provider() -> TTSProvider:
    if settings.tts_provider.strip().lower() == "mock":
        return MockTTS()
    raise ValueError(f"unsupported TTS provider: {settings.tts_provider}")
