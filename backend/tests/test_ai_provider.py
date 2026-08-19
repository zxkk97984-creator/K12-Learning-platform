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


def _collect_with_system(provider: MockAIProvider, system_prompt: str) -> list[str]:
    async def run() -> list[str]:
        return [
            chunk
            async for chunk in provider.stream_chat(
                [{"role": "user", "content": "训练数据是什么"}],
                system_prompt,
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


def test_mock_provider_cites_knowledge_reference() -> None:
    provider = MockAIProvider()
    system_prompt = (
        "你是霜铃。\n"
        "【知识库参考】\n"
        "- 内容：训练数据是一组用来帮助机器发现规律的例子。\n"
        "- 来源：AI 不是魔法\n"
        "- 链接：https://demo/training\n"
    )

    chunks = _collect_with_system(provider, system_prompt)
    reply = "".join(chunks)

    assert "根据知识库资料" in reply
    assert "AI 不是魔法" in reply


def test_mock_provider_truncates_long_reference_content() -> None:
    provider = MockAIProvider()
    long_content = "雪豹测试语料" * 40
    system_prompt = (
        "你是霜铃。\n"
        "【知识库参考】\n"
        f"- 内容：{long_content}\n"
        "- 来源：长文档\n"
        "- 链接：https://demo/long\n"
    )

    chunks = _collect_with_system(provider, system_prompt)
    reply = "".join(chunks)

    assert "根据知识库资料" in reply
    assert "长文档" in reply
    snippet = reply.removeprefix("根据知识库资料：").split("（参考：")[0]
    assert len(snippet) <= 140
