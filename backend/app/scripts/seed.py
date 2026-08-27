"""幂等演示种子：演示账号 + 默认教师风格 + E2E 演示记忆（仅本地演示）。

用法：uv run python -m app.scripts.seed
密码默认 demo123，可用环境变量 SEED_PASSWORD 覆盖（仅本地演示）。
本脚本只负责：admin/xiaoming 演示账号、两个默认教师风格、xiaoming 的 E2E
演示记忆。正式书库与知识库内容一律走 validate_library → import_library，
禁止把旧占位内容种子作为初始化路径。
"""

import asyncio
import os
import sys
from uuid import UUID

from sqlalchemy import select

from app.infrastructure.database.engine import engine
from app.infrastructure.database.models import (
    Admin,
    MemoryEvidence,
    StudentMemory,
    StudentPreference,
    StudentProfile,
    TeacherRole,
    User,
)
from app.infrastructure.database.session import async_session
from app.modules.identity.security import hash_password

SEED_PASSWORD = os.getenv("SEED_PASSWORD", "demo123")

# E2E 演示记忆（memory-flow.spec 依赖；seed 幂等补全，FORGET 后可重跑恢复）
E2E_MEMORY_CONTENT = "E2E 记忆验证：喜欢通过真实例子学习"


def _print_demo_warning() -> None:
    message = (
        "⚠️ 演示账号 xiaoming/demo123 + admin/admin123，仅本地开发使用；"
        "生产环境必须修改默认密码并配置强 JWT_SECRET。"
    )
    if sys.stdout.isatty():
        print(f"\033[33m{message}\033[0m")
    else:
        print(message)


async def seed() -> None:
    _print_demo_warning()
    try:
        async with async_session() as session:
            admin_user = (
                await session.execute(select(User).where(User.username == "admin"))
            ).scalar_one_or_none()
            if admin_user is None:
                admin_user = User(
                    username="admin",
                    password_hash=hash_password("admin123"),
                    user_type="ADMIN",
                )
                session.add(admin_user)
                await session.flush()
            admin_row = (
                await session.execute(
                    select(Admin).where(Admin.user_id == admin_user.user_id)
                )
            ).scalar_one_or_none()
            if admin_row is None:
                session.add(
                    Admin(
                        user_id=admin_user.user_id,
                        display_name="系统管理员",
                        role_level="SUPERVISOR",
                        enabled=True,
                    )
                )
                print("seed: 已创建 admin 管理账号（admin / admin123）")

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
            default_role = (
                await session.execute(
                    select(TeacherRole).where(
                        TeacherRole.role_id == UUID("00000000-0000-0000-0000-000000000001")
                    )
                )
            ).scalar_one_or_none()
            if default_role is None:
                default_role = TeacherRole(
                    role_id=UUID("00000000-0000-0000-0000-000000000001"),
                    name="温暖鼓励",
                    description="以鼓励和引导为主的教学风格",
                    persona={
                        "base_persona": "温暖耐心的 K12 数字教师",
                        "character_persona": "霜铃",
                    },
                    tone="温暖、鼓励",
                    teaching_style="从生活例子出发，逐步引导",
                    sprite_manifest={
                        "sheet_url": "",
                        "grid_cols": 7,
                        "grid_rows": 9,
                        "states": {},
                    },
                    grade_rules={
                        "primary": "多用比喻",
                        "junior": "强调理解",
                        "senior": "引导迁移",
                    },
                    prompt_profile={"version": 1},
                    interaction_style="interactive",
                    enabled=True,
                )
                session.add(default_role)
            strict_mentor = (
                await session.execute(
                    select(TeacherRole).where(
                        TeacherRole.role_id == UUID("00000000-0000-0000-0000-000000000002")
                    )
                )
            ).scalar_one_or_none()
            if strict_mentor is None:
                strict_mentor = TeacherRole(
                    role_id=UUID("00000000-0000-0000-0000-000000000002"),
                    name="严谨清晰",
                    description="以逻辑和证据为主的教学风格",
                    persona={
                        "base_persona": "严谨理性的 K12 导师",
                        "character_persona": "严谨导师",
                    },
                    tone="严谨、清晰",
                    teaching_style="强调逻辑与证据",
                    sprite_manifest={
                        "sheet_url": "",
                        "grid_cols": 7,
                        "grid_rows": 9,
                        "states": {},
                    },
                    grade_rules={
                        "primary": "建立规则",
                        "junior": "强调推理",
                        "senior": "批判思考",
                    },
                    prompt_profile={"version": 1},
                    interaction_style="structured",
                    enabled=True,
                )
                session.add(strict_mentor)
            if profile.current_teacher_role_id is None:
                profile.current_teacher_role_id = default_role.role_id
            memory_result = await session.execute(
                select(StudentMemory).where(
                    StudentMemory.student_id == profile.student_id,
                    StudentMemory.content == E2E_MEMORY_CONTENT,
                )
            )
            e2e_memory = memory_result.scalar_one_or_none()
            if e2e_memory is None:
                e2e_memory = StudentMemory(
                    student_id=profile.student_id,
                    memory_type="PREFERENCE",
                    content=E2E_MEMORY_CONTENT,
                    tags=["演示"],
                    confidence="MEDIUM",
                    status="ACTIVE",
                )
                session.add(e2e_memory)
                await session.flush()
                print("seed: 已补 E2E 演示记忆")
            elif e2e_memory.status != "ACTIVE":
                e2e_memory.status = "ACTIVE"
                print("seed: 已恢复 E2E 演示记忆为 ACTIVE")
            # 记忆页「为什么？」按钮仅在 evidence_ids 非空时显示。E2E 记忆须
            # 关联一条 evidence（否则 memory-flow.spec 点击「为什么？」超时）。
            # 全新空库下没有历史事件可聚合，故此处显式补一条 evidence。
            if not e2e_memory.evidence_ids:
                from datetime import datetime, timezone

                evidence = MemoryEvidence(
                    student_id=profile.student_id,
                    source_type="CONVERSATION",
                    event_ids=[],
                    payload={"summary": "演示记忆：学生喜欢通过真实例子理解概念"},
                    count=1,
                    first_occurred_at=datetime.now(timezone.utc),
                    last_occurred_at=datetime.now(timezone.utc),
                    derived_at=datetime.now(timezone.utc),
                    rule_version="seed-v1",
                )
                session.add(evidence)
                await session.flush()
                e2e_memory.evidence_ids = [str(evidence.evidence_id)]
                print("seed: 已为 E2E 演示记忆补 evidence")
            await session.commit()
    finally:
        # 释放连接池，避免跨事件循环复用 asyncpg 连接（asyncio.run / TestClient 场景）
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
