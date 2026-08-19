"""幂等演示种子：创建小明显示学生（仅本地演示）。

用法：uv run python -m app.scripts.seed
密码默认 demo123，可用环境变量 SEED_PASSWORD 覆盖（仅本地演示）。
teacher_roles 表 Phase 11 才建，本脚本不种角色。
"""

import asyncio
import os

from sqlalchemy import select

from app.infrastructure.database.engine import engine
from app.infrastructure.database.models import (
    StudentMemory,
    StudentPreference,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.modules.identity.security import hash_password

SEED_PASSWORD = os.getenv("SEED_PASSWORD", "demo123")

# E2E 演示记忆（memory-flow.spec 依赖；seed 幂等补全，FORGET 后可重跑恢复）
E2E_MEMORY_CONTENT = "E2E 记忆验证：喜欢通过真实例子学习"


async def seed() -> None:
    try:
        async with async_session() as session:
            result = await session.execute(select(User).where(User.username == "xiaoming"))
            user = result.scalar_one_or_none()
            if user is None:
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
                print("seed: 已创建 xiaoming（密码 {SEED_PASSWORD}，grade 8，昵称 小明）")
            # 幂等补全 E2E 演示记忆（memory-flow.spec 依赖；REMOVED 时恢复 ACTIVE，FORGET 后可重跑恢复）
            profile_result = await session.execute(
                select(StudentProfile).where(StudentProfile.user_id == user.user_id)
            )
            profile = profile_result.scalar_one()
            memory_result = await session.execute(
                select(StudentMemory).where(
                    StudentMemory.student_id == profile.student_id,
                    StudentMemory.content == E2E_MEMORY_CONTENT,
                )
            )
            e2e_memory = memory_result.scalar_one_or_none()
            if e2e_memory is None:
                session.add(
                    StudentMemory(
                        student_id=profile.student_id,
                        memory_type="PREFERENCE",
                        content=E2E_MEMORY_CONTENT,
                        tags=["演示"],
                        confidence="MEDIUM",
                        status="ACTIVE",
                    )
                )
                print("seed: 已补 E2E 演示记忆")
            elif e2e_memory.status != "ACTIVE":
                e2e_memory.status = "ACTIVE"
                print("seed: 已恢复 E2E 演示记忆为 ACTIVE")
            await session.commit()
    finally:
        # 释放连接池，避免跨事件循环复用 asyncpg 连接（asyncio.run / TestClient 场景）
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
