from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from typing import Any


class AIProvider(ABC):
    """Minimal streaming contract used by the Conversation Agent."""

    provider: str
    model: str
    # T20 §20b：最近一次调用的真实 usage（若 provider 返回）；拿不到则为 None，
    # 由调用方标注 estimated，不把字符数冒充 token。
    last_usage: dict[str, Any] | None = None

    @property
    def model_info(self) -> dict[str, str]:
        return {"provider": self.provider, "model": self.model}

    @abstractmethod
    async def stream_chat(
        self,
        history: Sequence[dict[str, Any]],
        system_prompt: str,
    ) -> AsyncIterator[str]:
        """Yield assistant text deltas for a validated conversation history."""
        raise NotImplementedError
