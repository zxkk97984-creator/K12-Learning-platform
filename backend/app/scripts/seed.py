"""幂等演示种子：创建小明显示学生（仅本地演示）。

用法：uv run python -m app.scripts.seed
密码默认 demo123，可用环境变量 SEED_PASSWORD 覆盖（仅本地演示）。
teacher_roles 表 Phase 11 才建，本脚本不种角色。
"""

import asyncio
import os

from sqlalchemy import select

from app.infrastructure.database.engine import engine
from app.infrastructure.database.models import StudentPreference, StudentProfile, User
from app.infrastructure.database.session import async_session
from app.modules.identity.security import hash_password

SEED_PASSWORD = os.getenv("SEED_PASSWORD", "demo123")


async def seed() -> None:
    try:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.username == "xiaoming"))
            if result.scalar_one_or_none() is not None:
                print("seed: xiaoming 已存在，跳过")
                return
            user = User(
                username="xiaoming",
                password_hash=hash_password(SEED_PASSWORD),
                user_type="STUDENT",
            )
            session.add(user)
            await session.flush()
            profile = StudentProfile(
                user_id=user.user_id,
                nickname="小明",
                grade=8,
                language="zh-CN",
            )
            session.add(profile)
            await session.flush()
            session.add(
                StudentPreference(
                    student_id=profile.student_id,
                    preferred_explanation_style="EXAMPLE_BASED",
                    preferred_difficulty="MEDIUM",
                    preferred_session_length="SHORT",
                )
            )
            await session.commit()
            print(f"seed: 已创建 xiaoming（密码 {SEED_PASSWORD}，grade 8，昵称 小明）")
    finally:
        # 释放连接池，避免跨事件循环复用 asyncpg 连接（asyncio.run / TestClient 场景）
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
