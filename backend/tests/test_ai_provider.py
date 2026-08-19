import asyncio

from app.ai.factory import get_ai_provider
from app.ai.mock import MockAIProvider
from app.config import settings


def _collect_chunks(provider: MockAIProvider) -> list[str]:
    async def run() -> list[str]:
        return [
            chunk
            async for chunk in provider.stream_chat(
                [{"role": "user", "content": "什么是训练数据"}],
                "你是霜铃老师",
            )
        ]

    return asyncio.run(run())


def test_mock_provider_streams_rule_based_chunks() -> None:
    provider = MockAIProvider(model="test-model")

    chunks = _collect_chunks(provider)

    assert len(chunks) > 1
    assert all(chunks)
    assert "训练数据" in "".join(chunks)
    assert provider.model_info == {"provider": "mock", "model": "test-model"}


def test_provider_factory_uses_mock_from_settings() -> None:
    original_provider = settings.ai_provider
    original_model = settings.ai_model
    try:
        settings.ai_provider = "mock"
        settings.ai_model = "factory-test-model"

        provider = get_ai_provider()

        assert isinstance(provider, MockAIProvider)
        assert provider.model_info == {
            "provider": "mock",
            "model": "factory-test-model",
        }
    finally:
        settings.ai_provider = original_provider
        settings.ai_model = original_model
