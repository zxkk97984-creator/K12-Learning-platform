from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置（pydantic-settings 读 .env；占位值安全，2-B/2-C 接入）。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "霜铃 K12 API"
    environment: Literal["dev", "test", "prod"] = "dev"
    api_v1_prefix: str = "/api/v1"
    # asyncpg 驱动（架构 §42 AsyncSession）；真实值在 .env
    database_url: str = "postgresql+asyncpg://shuangling:***@localhost:5432/shuangling"
    # 2-C 认证使用（JWT Bearer，0-D §1.2）
    jwt_secret: str = "dev-only-change-me-32bytes-secret"
    jwt_expire_minutes: int = 60 * 24 * 7
    ai_provider: str = "mock"
    ai_model: str = "mock-model"
    ai_max_tokens: int = 512
    embedding_provider: str = "mock"
    embedding_dimension: int = 64
    voice_provider: str = "mock"


settings = Settings()
