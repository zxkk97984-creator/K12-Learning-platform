from app.ai.base import AIProvider
from app.ai.mock import MockAIProvider
from app.ai.openai_compatible import OpenAICompatibleProvider
from app.config import settings


def get_ai_provider() -> AIProvider:
    """Return the configured provider; real LLM providers will be added later."""
    provider_name = settings.ai_provider.strip().lower()
    if provider_name == "mock":
        return MockAIProvider(
            model=settings.ai_model,
            max_tokens=settings.ai_max_tokens,
        )
    if provider_name == "openai_compatible":
        return OpenAICompatibleProvider(
            base_url=settings.ai_base_url,
            api_key=settings.ai_api_key,
            model=settings.ai_model,
            max_tokens=settings.ai_max_tokens,
            thinking_mode=settings.ai_thinking_mode,
        )
    raise ValueError(f"unsupported AI provider: {settings.ai_provider}")
