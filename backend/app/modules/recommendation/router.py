from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_student
from app.api.envelope import ok
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_session
from app.modules.recommendation.schemas import (
    LearningNextActionDTO,
    RecommendationDTO,
)
from app.modules.recommendation.service import RecommendationService


router = APIRouter(tags=["recommendations"])
service = RecommendationService()


@router.get("/me/learning-next")
async def get_learning_next(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """§6.1 统一下一步行动（首页行动卡 / 后续推荐共用一套规则）。"""
    return ok(await service.learning_next(session, user.user_id))


@router.get("/me/recommendations")
async def list_recommendations(
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    rows = await service.list_for_user(session, user.user_id)
    return ok([RecommendationDTO.model_validate(row) for row in rows])


@router.post("/me/recommendations/{recommendation_id}/dismiss")
async def dismiss_recommendation(
    recommendation_id: UUID,
    user: Annotated[User, Depends(require_student)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    row = await service.dismiss(session, user.user_id, recommendation_id)
    return ok(RecommendationDTO.model_validate(row))
