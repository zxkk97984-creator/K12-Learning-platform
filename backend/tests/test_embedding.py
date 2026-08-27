"""Embedding provider tests."""

import math

import pytest

from app.ai.embedding import (
    MockEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    get_embedding,
    get_embedding_provider,
)
from app.config import settings


def test_mock_embedding_is_deterministic_and_normalized() -> None:
    provider = MockEmbeddingProvider()
    vector = provider.embed("训练数据")
    again = provider.embed("训练数据")

    assert vector == again
    # mock 维度跟随配置（默认可为 64/1024）；关键是确定性 + L2 归一化。
    assert len(vector) == provider.dimension
    norm = math.sqrt(sum(value * value for value in vector))
    assert abs(norm - 1.0) < 1e-9


def test_different_text_produces_different_vector() -> None:
    assert get_embedding("训练数据") != get_embedding("算法偏见")


def test_openai_compatible_embedding_requests_normalizes_and_parses_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"data": [{"embedding": [3, 4]}]}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            captured["client_kwargs"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def post(self, *args, **kwargs):
            captured["url"] = args[0]
            captured["request_kwargs"] = kwargs
            return FakeResponse()

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    monkeypatch.setenv("ALL_PROXY", "socks5://unsupported.example:1080")
    monkeypatch.setattr("app.ai.embedding.httpx.Client", FakeClient)

    provider = OpenAICompatibleEmbeddingProvider(
        base_url="https://embedding.example.com/v1/",
        api_key="embedding-key",
        model="embedding-model",
        dimension=2,
    )

    vector = provider.embed("训练数据")

    assert captured["url"] == "https://embedding.example.com/v1/embeddings"
    request_kwargs = captured["request_kwargs"]
    assert request_kwargs == {
        "headers": {
            "Authorization": "Bearer embedding-key",
            "Content-Type": "application/json",
        },
        "json": {"model": "embedding-model", "input": "训练数据"},
    }
    assert captured["client_kwargs"] == {
        "timeout": 30.0,
        "trust_env": False,
        "proxy": "http://proxy.example:8080",
    }
    assert vector == pytest.approx([0.6, 0.8])


def test_openai_compatible_embedding_rejects_dimension_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"data": [{"embedding": [1, 0, 0]}]}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.ai.embedding.httpx.Client", FakeClient)
    provider = OpenAICompatibleEmbeddingProvider(
        base_url="https://embedding.example.com",
        api_key="embedding-key",
        model="embedding-model",
        dimension=2,
    )

    with pytest.raises(ValueError, match="dimension"):
        provider.embed("训练数据")


def test_embedding_factory_requires_real_provider_configuration() -> None:
    original = (
        settings.embedding_provider,
        settings.embedding_base_url,
        settings.embedding_api_key,
        settings.embedding_model,
        settings.embedding_dimension,
    )
    try:
        settings.embedding_provider = "openai_compatible"
        settings.embedding_base_url = ""
        settings.embedding_api_key = ""
        settings.embedding_model = ""
        settings.embedding_dimension = 1024

        with pytest.raises(ValueError, match="required"):
            get_embedding_provider()
    finally:
        (
            settings.embedding_provider,
            settings.embedding_base_url,
            settings.embedding_api_key,
            settings.embedding_model,
            settings.embedding_dimension,
        ) = original
