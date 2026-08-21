from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_student
from app.api.envelope import ok
from app.infrastructure.database.models import User
from app.infrastructure.database.session import get_session
from app.modules.recommendation.schemas import RecommendationDTO
from app.modules.recommendation.service import RecommendationService


router = APIRouter(tags=["recommendations"])
service = RecommendationService()


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
