from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.database.engine import engine

async_session = async_sessionmaker(bind=engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 异步依赖（2-C 使用）；1 Request = 1 AsyncSession（架构 §42）。"""
    async with async_session() as session:
        yield session
