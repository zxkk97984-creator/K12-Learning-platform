"""Deterministic mock embedding (Phase 8; real provider lands in Phase 9)."""

import hashlib
import math
from abc import ABC, abstractmethod
from typing import Sequence

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


def get_embedding_provider() -> EmbeddingProvider:
    provider_name = settings.embedding_provider.strip().lower()
    if provider_name == "mock":
        return MockEmbeddingProvider()
    raise ValueError(f"unsupported embedding provider: {settings.embedding_provider}")


def get_embedding(text: str) -> list[float]:
    return get_embedding_provider().embed(text)
