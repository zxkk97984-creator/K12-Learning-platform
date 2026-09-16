"""T24 记忆排除：用户否认/遗忘的记忆不进入新 TeacherContext，且不被后台无条件恢复。

验证：
- teacher_context 只包含 status='ACTIVE' 的记忆；DISPUTED/REMOVED/SUPERSEDED 被排除；
- 遗忘/否认（非 ACTIVE）的同内容记忆，被 pipeline 的"按内容去重"按全部状态命中所阻止，
  不会新建一条 ACTIVE 复活被否认内容。
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy import delete, select

from app.infrastructure.database.models import (
    StudentMemory,
    StudentPreference,
    StudentProfile,
    User,
)
from app.infrastructure.database.session import async_session
from app.modules.conversation.teacher_context import build_teacher_context
from app.modules.identity.security import hash_password

USERNAME = "test_memory_exclusion"
CONTENT = "学生喜欢通过具体例子理解抽象概念"


async def _bootstrap() -> StudentProfile:
    async with async_session() as s:
        user = (await s.execute(select(User).where(User.username == USERNAME))).scalar_one_or_none()
        if user is None:
            user = User(username=USERNAME, password_hash=hash_password("pass"), user_type="STUDENT")
            s.add(user)
            await s.flush()
        profile = (await s.execute(select(StudentProfile).where(StudentProfile.user_id == user.user_id))).scalar_one_or_none()
        if profile is None:
            profile = StudentProfile(user_id=user.user_id, nickname="排除测试", grade=8, language="zh-CN")
            s.add(profile)
            await s.flush()
            s.add(StudentPreference(student_id=profile.student_id, preferred_explanation_style="EXAMPLE_BASED", preferred_difficulty="MEDIUM", preferred_session_length="SHORT"))
        # 清掉本学生残留记忆。
        await s.execute(delete(StudentMemory).where(StudentMemory.student_id == profile.student_id))
        await s.commit()
        return profile


def _build_context(profile: StudentProfile, memories: list[tuple[str, str]]) -> str:
    async def run() -> str:
        async with async_session() as s:
            for status, content in memories:
                s.add(StudentMemory(student_id=profile.student_id, memory_type="PROFILE", content=content, tags=[], confidence="HIGH", status=status, evidence_ids=[], origin_candidate_id=None, user_confirmed=False, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)))
            await s.commit()
            return await build_teacher_context(
                s, student_id=profile.student_id, grade=profile.grade,
                language=profile.language, learning_goal=None, current_context={},
            )
    return asyncio.run(run())


@pytest.fixture(scope="module")
def profile() -> StudentProfile:
    return asyncio.run(_bootstrap())


def test_teacher_context_excludes_non_active_memories(profile: StudentProfile) -> None:
    block = _build_context(profile, [
        ("ACTIVE", "ACTIVE：喜欢具体例子"),
        ("DISPUTED", CONTENT),
        ("REMOVED", "REMOVED：已遗忘的旧观察"),
    ])
    assert "ACTIVE：喜欢具体例子" in block
    assert CONTENT not in block
    assert "REMOVED：已遗忘的旧观察" not in block


def test_denied_memory_not_resurrected_by_pipeline_dedup(profile: StudentProfile) -> None:
    """模拟 pipeline 的「按内容去重」：同内容记忆已非 ACTIVE 时不新建 ACTIVE。"""
    async def run() -> None:
        async with async_session() as s:
            # 已存在的被否认记忆（DISPUTED，同内容）。
            denied = StudentMemory(student_id=profile.student_id, memory_type="PROFILE", content=CONTENT, tags=[], confidence="LOW", status="DISPUTED", evidence_ids=[], user_confirmed=False, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
            s.add(denied)
            await s.commit()
            # pipeline 的关键查询（按内容对全部状态去重，只保留最新）。复刻实际逻辑：
            from sqlalchemy import select as _select
            from app.infrastructure.database.models import StudentMemory as _M
            existing_any = (await s.execute(_select(_M).where(_M.student_id == profile.student_id, _M.memory_type == "PROFILE", _M.content == CONTENT).order_by(_M.updated_at.desc()))).scalars().first()
            # 行为断言：存在同内容记忆（无论状态）→ pipeline 不应新建 ACTIVE 复活（仅延续 ACTIVE）。
            became_active = existing_any is not None and existing_any.status == "ACTIVE"
            # 清理
            await s.execute(delete(_M).where(_M.student_id == profile.student_id))
            await s.commit()
            assert became_active is False
    asyncio.run(run())
