from typing import Literal

from pydantic import model_validator
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
    # 无默认值：生产/测试/本地都必须通过 .env 或环境变量显式提供，禁止静默使用 dev 占位。
    jwt_secret: str
    jwt_expire_minutes: int = 60 * 24 * 7
    ai_provider: str = "mock"
    ai_model: str = "mock-model"
    ai_max_tokens: int = 512
    ai_thinking_mode: Literal["auto", "enabled", "disabled"] = "auto"
    ai_base_url: str = ""
    ai_api_key: str = ""
    embedding_provider: str = "mock"
    embedding_dimension: int = 64
    voice_provider: str = "mock"
    tts_provider: str = "mock"
    aliyun_dashscope_api_key: str = ""
    aliyun_asr_models: list[str] = [
        "fun-asr-realtime",
        "fun-asr-realtime-2026-02-28",
        "fun-asr-realtime-2025-11-07",
        "fun-asr-realtime-2025-09-15",
    ]
    aliyun_asr_ws_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
    speech_sample_rate: int = 16000
    asr_max_frame_bytes: int = 6400

    @model_validator(mode="after")
    def _reject_placeholder_secret_in_prod(self) -> "Settings":
        if self.environment == "prod" and (
            not self.jwt_secret
            or self.jwt_secret.startswith("dev-")
            or self.jwt_secret == "change-me"
        ):
            raise ValueError(
                "JWT_SECRET must be set to a strong non-placeholder value in prod"
            )
        return self


settings = Settings()
