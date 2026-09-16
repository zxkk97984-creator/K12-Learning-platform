from typing import Literal

from pydantic import Field, model_validator
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
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_dimension: int = Field(default=64, gt=0)
    worker_poll_interval: float = Field(default=1.0, gt=0, le=60)
    worker_max_attempts: int = Field(default=3, ge=1, le=10)
    # running 状态超过该秒数的任务视为 Worker 崩溃遗留的孤儿，回收重排。
    # 默认 10 分钟：远大于正常任务耗时，又能在进程崩溃后及时恢复消费者语义。
    worker_running_ttl_seconds: int = Field(default=600, ge=1, le=86400)
    # 失败重试的指数退避：attempt=1 失败后等 base*2^(attempt-1) 秒，上限 max。
    worker_backoff_base_seconds: float = Field(default=2.0, ge=0.1, le=60)
    worker_backoff_max_seconds: float = Field(default=300.0, ge=1.0, le=86400)
    summary_message_threshold: int = Field(default=20, ge=1)
    context_window_token_budget: int = Field(default=3000, ge=200)
    knowledge_upload_max_bytes: int = Field(default=20 * 1024 * 1024, ge=1)
    avatar_upload_max_bytes: int = Field(default=2 * 1024 * 1024, ge=1)
    # ---- Phase 5-A：限流（Redis 可用则分布式，否则进程内降级；均强制）----
    rate_limit_enabled: bool = True
    rate_limit_api_per_minute: int = Field(default=600, ge=1)
    rate_limit_login_per_minute: int = Field(default=30, ge=1)

    # ---- 存储抽象（Phase 4）：知识资源与头像共用 ----
    storage_backend: str = "local"  # local | s3
    storage_local_root: str = "storage"
    s3_endpoint: str = ""
    s3_region: str = "us-east-1"
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""

    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True
    redis_lock_ttl_seconds: int = Field(default=120, ge=1, le=3600)
    redis_cache_ttl_seconds: int = Field(default=60, ge=1, le=86400)
    voice_provider: str = "mock"
    tts_model: str = ""
    tts_voice: str = "alicia"
    # none：未配置真实 TTS 时明确不可用（Phase 4）；mock 仅用于本地/测试
    tts_provider: str = "none"
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
        # Embedding 复用阿里云百炼 Key：百炼是 OpenAI 兼容端点，用户通常只配
        # ALIYUN_DASHSCOPE_API_KEY（供语音/LLM 用）。当 embedding 走 openai_compatible
        # 且未单独设 EMBEDDING_API_KEY 时回退到该 Key，避免重复配置同一凭据。
        if (
            self.embedding_provider.strip().lower() == "openai_compatible"
            and not self.embedding_api_key
            and self.aliyun_dashscope_api_key
        ):
            self.embedding_api_key = self.aliyun_dashscope_api_key
        return self


settings = Settings()
