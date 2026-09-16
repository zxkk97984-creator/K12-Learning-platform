"""OpenAI-compatible chat provider (non-streaming; outer layer frames deltas)."""

import asyncio
from collections.abc import AsyncIterator, Sequence
import logging
import os
from typing import Any, Literal
from uuid import uuid4

import httpx

from app.ai.base import AIProvider
from app.ai.json_utils import (
    AIServiceError,
    OPERATION_MAX_TOKENS,
    extract_json_object,
    is_non_retryable_status,
    is_retryable_status,
    normalize_chat_endpoint,
    sanitize_ai_error,
)

logger = logging.getLogger("shuangling.ai")


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
        max_retries: int = 3,
        json_timeout_seconds: float = 120.0,
    ) -> None:
        if not base_url or not api_key:
            raise ValueError("ai_base_url and ai_api_key are required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.thinking_mode = thinking_mode
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)
        self.json_timeout_seconds = json_timeout_seconds
        self.last_usage: dict[str, Any] | None = None

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
        # T20 §20b：采集 provider 实际 usage（OpenAI-compatible 通常返回 usage）。
        # 拿不到时置空，由调用方标注 estimated，绝不把字符数冒充为 token。
        self.last_usage = data.get("usage")
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("AI_PROVIDER_ERROR: unexpected chat completions response") from exc
        text = str(content or "")
        for start in range(0, len(text), 16):
            yield text[start : start + 16]

    async def chat_json(
        self,
        messages: Sequence[dict[str, str]],
        *,
        operation: str,
    ) -> dict[str, Any]:
        """结构化 JSON 输出（temperature=0 + JSON mode + 预算登记 + 重试）。

        移植自 dai `app/services/ai_client.py:106-314` 的完整成熟逻辑：
        - 未登记 `operation` → 直接抛错（fail-closed，不允许无界输出）
        - `response_format={"type":"json_object"}`；若模型返回 400 不支持，
          去掉该参数**再试一次且不占用业务重试预算**
        - 401/403 不重试；429/5xx/超时/网络错误/JSON 解析失败可重试
        - 退避 `min(2^(attempt-1), 8)` 秒
        - 错误文本经 `sanitize_ai_error` 脱敏，凭证绝不外泄
        - `finish_reason=length` 时给出「推理 token 可能耗尽预算」的明确提示
        """
        max_tokens = OPERATION_MAX_TOKENS.get(operation)
        if max_tokens is None:
            raise ValueError(
                f"AI 操作 {operation!r} 未登记 completion 预算（OPERATION_MAX_TOKENS）"
            )

        max_attempts = 1 + self.max_retries
        endpoint = normalize_chat_endpoint(self.base_url)
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if self.thinking_mode != "auto":
            payload["thinking"] = {"type": self.thinking_mode}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        proxy_url = _http_proxy_url()
        request_id = uuid4().hex[:12]
        last_error: AIServiceError | None = None
        attempt = 0

        while attempt < max_attempts:
            attempt += 1
            try:
                async with httpx.AsyncClient(
                    timeout=self.json_timeout_seconds,
                    trust_env=False,
                    proxy=proxy_url,
                ) as client:
                    response = await client.post(endpoint, headers=headers, json=payload)

                # 模型不支持 JSON mode：去掉 response_format 再试，不计入业务重试预算
                if response.status_code == 400 and "response_format" in payload:
                    logger.warning(
                        "AI 不支持 response_format，降级重试",
                        extra={"request_id": request_id, "operation": operation},
                    )
                    del payload["response_format"]
                    max_attempts += 1
                    continue

                if is_non_retryable_status(response.status_code):
                    raise AIServiceError(
                        f"http_{response.status_code}",
                        f"AI 认证失败: {sanitize_ai_error(response.text[:500])}",
                        retryable=False,
                    )
                if is_retryable_status(response.status_code):
                    raise AIServiceError(
                        f"http_{response.status_code}",
                        f"AI 服务暂时不可用 ({response.status_code}): "
                        f"{sanitize_ai_error(response.text[:500])}",
                        retryable=True,
                    )
                response.raise_for_status()
                data = response.json()

                self.last_usage = data.get("usage")
                choices = data.get("choices") or []
                logger.info(
                    "ai_chat_json_completed",
                    extra={
                        "request_id": request_id,
                        "operation": operation,
                        "model": self.model,
                        "finish_reason": choices[0].get("finish_reason") if choices else None,
                        "attempts": attempt,
                        "prompt_tokens": (self.last_usage or {}).get("prompt_tokens"),
                        "completion_tokens": (self.last_usage or {}).get("completion_tokens"),
                        "max_tokens": max_tokens,
                    },
                )
                if not choices:
                    raise AIServiceError("empty_choices", "AI 返回空的 choices 列表", retryable=True)

                message = choices[0].get("message") or {}
                content = message.get("content")
                if not isinstance(content, str) or not content.strip():
                    finish_reason = choices[0].get("finish_reason")
                    hint = (
                        "（finish_reason=length，reasoning token 可能耗尽预算）"
                        if finish_reason == "length"
                        else ""
                    )
                    raise AIServiceError(
                        "bad_json", f"AI 返回空 content{hint}", retryable=True
                    )
                return extract_json_object(content)

            except AIServiceError as exc:
                if not exc.retryable:
                    raise
                last_error = exc
                logger.warning(
                    "ai_retryable_error",
                    extra={
                        "request_id": request_id,
                        "operation": operation,
                        "attempt": attempt,
                        "code": exc.code,
                    },
                )
            except httpx.TimeoutException:
                last_error = AIServiceError(
                    "timeout", f"AI 请求超时 (尝试 {attempt}/{max_attempts})", retryable=True
                )
                logger.warning(
                    "ai_timeout",
                    extra={"request_id": request_id, "operation": operation, "attempt": attempt},
                )
            except httpx.NetworkError as exc:
                last_error = AIServiceError("network_error", f"AI 网络错误: {exc}", retryable=True)
                logger.warning(
                    "ai_network_error",
                    extra={"request_id": request_id, "operation": operation, "attempt": attempt},
                )
            except (ValueError, TypeError) as exc:
                # json.JSONDecodeError 是 ValueError 的子类
                last_error = AIServiceError(
                    "bad_json", f"AI 返回非 JSON 内容: {exc}", retryable=True
                )
                logger.warning(
                    "ai_bad_json",
                    extra={"request_id": request_id, "operation": operation, "attempt": attempt},
                )

            if attempt < max_attempts:
                await asyncio.sleep(min(2 ** (attempt - 1), 8))

        logger.error(
            "ai_retries_exhausted",
            extra={"request_id": request_id, "operation": operation, "attempts": max_attempts},
        )
        raise last_error or AIServiceError("unknown", "AI 调用失败", retryable=False)
