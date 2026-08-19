"""Phase 8 mock embedding tests."""

import math

from app.ai.embedding import MockEmbeddingProvider, get_embedding


def test_mock_embedding_is_deterministic_and_normalized() -> None:
    provider = MockEmbeddingProvider()
    vector = provider.embed("训练数据")
    again = provider.embed("训练数据")

    assert vector == again
    assert len(vector) == 64
    norm = math.sqrt(sum(value * value for value in vector))
    assert abs(norm - 1.0) < 1e-9


def test_different_text_produces_different_vector() -> None:
    assert get_embedding("训练数据") != get_embedding("算法偏见")
