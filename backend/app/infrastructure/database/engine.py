from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings

# 测试环境（TestClient 每次请求独立事件循环）用 NullPool，避免 asyncpg 连接跨循环复用；
# 生产/开发环境保持默认 AsyncAdaptedQueuePool（连接绑定 uvicorn 单一事件循环）
_engine_kwargs: dict = {"pool_pre_ping": True}
if settings.environment == "test":
    _engine_kwargs["poolclass"] = NullPool

engine = create_async_engine(settings.database_url, **_engine_kwargs)
