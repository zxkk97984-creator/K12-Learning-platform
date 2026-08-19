import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any

from app.ai.base import AIProvider


class MockAIProvider(AIProvider):
    """Deterministic Chinese teaching provider for local development and tests."""

    provider = "mock"

    def __init__(
        self,
        model: str = "mock-model",
        *,
        chunk_size: int = 8,
        delay_seconds: float = 0.03,
        max_tokens: int = 512,
    ) -> None:
        self.model = model
        self.chunk_size = max(1, chunk_size)
        self.delay_seconds = max(0.0, delay_seconds)
        self.max_tokens = max(1, max_tokens)

    @staticmethod
    def _reply_for(content: str) -> str:
        if "训练数据" in content:
            return (
                "训练数据就是用来教会模型的一组例子。它可以包含文字、图片或数字，"
                "模型会从这些例子中发现规律，再把规律用于新的问题。"
            )
        if any(keyword in content for keyword in ("为什么出错", "报错", "错误", "出错")):
            return (
                "遇到错误时，可以先复现问题，再检查输入、步骤和错误提示。"
                "把大问题拆成小步骤，通常更容易找到真正的原因。"
            )
        if any(keyword in content for keyword in ("出题", "题目", "练习")):
            return (
                "当然可以。先确定练习的知识点和难度，再用一个问题检验理解，"
                "最后配上简短提示，而不是直接公布答案。"
            )
        if any(keyword in content for keyword in ("解释", "讲给我听", "怎么理解")):
            return (
                "我们先抓住核心概念，再用一个生活中的例子说明，最后用自己的话复述一遍。"
            )
        return (
            "这是个很好的问题。我们可以先明确已知条件，再一步一步推理，"
            "最后用一个小例子检查结论。"
        )

    async def stream_chat(
        self,
        history: Sequence[dict[str, Any]],
        system_prompt: str,
    ) -> AsyncIterator[str]:
        del system_prompt  # The deterministic mock only needs the latest user turn.
        content = ""
        for message in reversed(history):
            if message.get("role") in {"user", "student", "STUDENT"}:
                content = str(message.get("content", ""))
                break
        reply = self._reply_for(content)[: self.max_tokens]
        for start in range(0, len(reply), self.chunk_size):
            await asyncio.sleep(self.delay_seconds)
            yield reply[start : start + self.chunk_size]
