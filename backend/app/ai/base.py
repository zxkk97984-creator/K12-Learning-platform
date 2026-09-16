from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from typing import Any


class AIProvider(ABC):
    """AI provider contract: streaming chat + structured JSON chat."""

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

    async def chat_json(
        self,
        messages: Sequence[dict[str, str]],
        *,
        operation: str,
    ) -> dict[str, Any]:
        """Return a structured JSON object for a multi-message request.

        与 ``stream_chat`` 是**两种不同能力**：这里要的是严格 JSON 结构化输出
        （temperature=0 + JSON mode + 预算登记），用于 CodeLab 的代码评分。

        ``operation`` 必须已在 ``app.ai.json_utils.OPERATION_MAX_TOKENS`` 登记
        completion 预算；未登记即抛错（fail-closed），避免无界输出与成本失控。

        **刻意不是 abstractmethod**：只支持流式对话的 provider 是合法且完整的
        实现，JSON 模式是可选能力。设为抽象会强制所有既有实现（含仅用于测试
        流式行为的替身）都实现它，把一个新增能力变成对所有调用方的破坏性变更。
        真正需要时未实现会在调用点立刻抛错，不会静默失败。
        """
        raise NotImplementedError(
            f"{type(self).__name__} 不支持结构化 JSON 调用（chat_json）"
        )
