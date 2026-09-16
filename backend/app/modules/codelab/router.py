"""CodeLab 路由。

Phase 1 的 API 面刻意很小 —— 一个完整可用的工作台只需要 5 个端点：

    GET  /codelab/tasks                 任务列表
    GET  /codelab/tasks/{task_id}       任务详情（不含隐藏测试/标准答案）
    POST /codelab/runs                  运行代码（同步，移出事件循环）
    POST /codelab/reviews               请求 AI 评审（同步，不依赖 Worker）
    GET  /codelab/reviews/{review_id}   读取评审结果

刻意**未**提供：运行历史列表、任务 CRUD、教师评分覆盖、学习事件联动。
这些等 CodeLab 本身稳定后再按需增加。
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_student
from app.api.envelope import ok
from app.config import settings
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_session
from app.infrastructure.rate_limit import rate_limiter
from app.modules.codelab.schemas import CreateCodeReviewRequest, CreateCodeRunRequest
from app.modules.codelab.service import service

router = APIRouter(tags=["codelab"])


def _require_enabled() -> None:
    """未启用时明确拒绝，而不是让请求悄悄走到 Docker 调用上。"""
    if not settings.codelab_enabled:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CODELAB_DISABLED",
                "message": "CodeLab 未启用（CODELAB_ENABLED=false）",
            },
        )


def _check_rate_limit(user: User) -> None:
    """每学生每分钟的运行/评审次数限制。

    复用霜铃既有的限流器（Redis 可用则分布式，否则进程内降级，两种模式都强制）。
    """
    verdict = rate_limiter.check(
        f"codelab:{user.user_id}",
        limit=settings.codelab_rate_limit_per_minute,
        window_seconds=60,
    )
    if not verdict.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "CODELAB_RATE_LIMITED",
                "message": "操作过于频繁，请稍后再试",
            },
            headers={"Retry-After": str(verdict.retry_after)},
        )


@router.get("/codelab/tasks")
async def list_tasks(
    _user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    _require_enabled()
    return ok(await service.list_tasks(session))


@router.get("/codelab/tasks/{task_id}")
async def get_task(
    task_id: UUID,
    _user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    _require_enabled()
    return ok(await service.get_task(session, task_id))


@router.post("/codelab/runs", status_code=201)
async def create_run(
    body: CreateCodeRunRequest,
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    _require_enabled()
    _check_rate_limit(user)
    student_id = await _student_id(session, user)
    return ok(await service.create_run(session, student_id, body.task_id, body.code))


@router.post("/codelab/reviews", status_code=201)
async def create_review(
    body: CreateCodeReviewRequest,
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    _require_enabled()
    _check_rate_limit(user)
    student_id = await _student_id(session, user)
    return ok(await service.create_review(session, student_id, body.run_id))


@router.get("/codelab/reviews/{review_id}")
async def get_review(
    review_id: UUID,
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    _require_enabled()
    student_id = await _student_id(session, user)
    return ok(await service.get_review(session, student_id, review_id))


async def _student_id(session: AsyncSession, user: User) -> UUID:
    """把 users.user_id 解析为 student_profiles.student_id。

    与 content/learning 等模块同一约定（require_student 只保证角色，
    具体档案行仍要查一次）。
    """
    from sqlalchemy import select

    from app.infrastructure.database.models import StudentProfile

    profile = (
        await session.execute(
            select(StudentProfile.student_id).where(StudentProfile.user_id == user.user_id)
        )
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=403,
            detail={"code": "STUDENT_PROFILE_REQUIRED", "message": "学生档案不存在"},
        )
    return profile
