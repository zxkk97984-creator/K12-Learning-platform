"""Embedding provider gateway with a deterministic mock and HTTP adapter."""

import hashlib
import math
from abc import ABC, abstractmethod
from typing import Sequence

import httpx

from app.ai.openai_compatible import _http_proxy_url
from app.config import settings


class EmbeddingProvider(ABC):
    """Contract for text -> normalized vector."""

    provider: str
    dimension: int

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


def _normalize(values: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        return [0.0] * len(values)
    return [value / norm for value in values]


class MockEmbeddingProvider(EmbeddingProvider):
    """64-dim deterministic hashed embedding; L2-normalized for cosine ops."""

    provider = "mock"

    def __init__(self, dimension: int | None = None) -> None:
        self.dimension = dimension or settings.embedding_dimension

    def embed(self, text: str) -> list[float]:
        raw = [0.0] * self.dimension
        for index in range(self.dimension):
            digest = hashlib.sha256(
                f"{text}::segment::{index}".encode("utf-8")
            ).digest()
            raw[index] = int.from_bytes(digest[:8], "big") / 2**64 - 0.5
        return _normalize(raw)


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    """OpenAI-compatible ``/embeddings`` adapter for real providers."""

    provider = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimension: int | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if not base_url or not api_key or not model:
            raise ValueError(
                "embedding_base_url, embedding_api_key, and embedding_model are required"
            )
        configured_dimension = (
            dimension if dimension is not None else settings.embedding_dimension
        )
        if configured_dimension <= 0:
            raise ValueError("embedding_dimension must be greater than zero")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dimension = configured_dimension
        self.timeout_seconds = timeout_seconds

    def embed(self, text: str) -> list[float]:
        proxy_url = _http_proxy_url()
        with httpx.Client(
            timeout=self.timeout_seconds,
            trust_env=False,
            proxy=proxy_url,
        ) as client:
            response = client.post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self.model, "input": text},
            )
            if response.status_code >= 400:
                detail = (response.text or "")[:500]
                raise RuntimeError(
                    f"EMBEDDING_PROVIDER_ERROR: HTTP {response.status_code}: {detail}"
                )
            response.raise_for_status()
            try:
                payload = response.json()
            except (TypeError, ValueError) as exc:
                raise RuntimeError(
                    "EMBEDDING_PROVIDER_ERROR: invalid JSON response"
                ) from exc

        try:
            raw_embedding = payload["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                "EMBEDDING_PROVIDER_ERROR: unexpected embeddings response"
            ) from exc
        if not isinstance(raw_embedding, list) or not all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value))
            for value in raw_embedding
        ):
            raise RuntimeError(
                "EMBEDDING_PROVIDER_ERROR: embedding must be a finite numeric list"
            )
        if len(raw_embedding) != self.dimension:
            raise ValueError(
                "embedding dimension mismatch: "
                f"expected {self.dimension}, got {len(raw_embedding)}"
            )
        return _normalize([float(value) for value in raw_embedding])


def get_embedding_provider() -> EmbeddingProvider:
    provider_name = settings.embedding_provider.strip().lower()
    if provider_name == "mock":
        return MockEmbeddingProvider()
    if provider_name == "openai_compatible":
        return OpenAICompatibleEmbeddingProvider(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
            dimension=settings.embedding_dimension,
        )
    raise ValueError(f"unsupported embedding provider: {settings.embedding_provider}")


def get_embedding(text: str) -> list[float]:
    return get_embedding_provider().embed(text)
