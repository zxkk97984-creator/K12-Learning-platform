"""OpenAI-compatible chat provider (non-streaming; outer layer frames deltas)."""

from collections.abc import AsyncIterator, Sequence
import os
from typing import Any, Literal

import httpx

from app.ai.base import AIProvider


def _http_proxy_url() -> str | None:
    """Return the first HTTP(S) proxy from env, ignoring unsupported socks URLs."""
    for key in (
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        url = os.environ.get(key)
        if url and url.split("://", 1)[0].lower() in {"http", "https"}:
            return url
    return None


class OpenAICompatibleProvider(AIProvider):
    provider = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        max_tokens: int = 512,
        thinking_mode: Literal["auto", "enabled", "disabled"] = "auto",
        timeout_seconds: float = 30.0,
    ) -> None:
        if not base_url or not api_key:
            raise ValueError("ai_base_url and ai_api_key are required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.thinking_mode = thinking_mode
        self.timeout_seconds = timeout_seconds

    async def stream_chat(
        self,
        history: Sequence[dict[str, Any]],
        system_prompt: str,
    ) -> AsyncIterator[str]:
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(
            {
                "role": "assistant" if message.get("role") == "assistant" else "user",
                "content": str(message.get("content", "")),
            }
            for message in history
        )
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        if self.thinking_mode != "auto":
            payload["thinking"] = {"type": self.thinking_mode}
        # Prefer HTTP(S) proxies over ALL_PROXY: httpx does not parse socks://
        # schemes, and a stray all_proxy would otherwise break every request.
        proxy_url = _http_proxy_url()
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            trust_env=False,
            proxy=proxy_url,
        ) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code >= 400:
                detail = (response.text or "")[:500]
                raise RuntimeError(
                    f"AI_PROVIDER_ERROR: HTTP {response.status_code}: {detail}"
                )
            response.raise_for_status()
            data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("AI_PROVIDER_ERROR: unexpected chat completions response") from exc
        text = str(content or "")
        for start in range(0, len(text), 16):
            yield text[start : start + 16]
