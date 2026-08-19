"""Mock ASR/TTS providers (Phase 9 voice; real providers need keys later)."""

import io
import wave
from abc import ABC, abstractmethod

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
    raise ValueError(f"unsupported ASR provider: {settings.voice_provider}")


def get_tts_provider() -> TTSProvider:
    if settings.voice_provider.strip().lower() == "mock":
        return MockTTS()
    raise ValueError(f"unsupported TTS provider: {settings.voice_provider}")
