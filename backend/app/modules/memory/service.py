import base64
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    MemoryEvidence,
    ProfileInsight,
    StudentEpisode,
    StudentMemory,
    StudentProfile,
)
from app.modules.memory.schemas import (
    EpisodeImportance,
    InsightStatus,
    InsightType,
    MemoryEvidenceDTO,
    MemoryStatus,
    MemoryType,
    PatchMemoryRequest,
    ProfileInsightDTO,
    StudentMemoryDTO,
    StudentEpisodeDTO,
)


def _encode_cursor(occurred_at: datetime, entity_id: UUID) -> str:
    payload = json.dumps([occurred_at.isoformat(), str(entity_id)])
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = json.loads(
            base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        )
        if not isinstance(raw, list) or len(raw) != 2:
            raise ValueError("invalid cursor")
        occurred_at = datetime.fromisoformat(raw[0])
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)
        return occurred_at, UUID(raw[1])
    except (
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ) as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "VALIDATION_ERROR", "message": "invalid cursor"},
        ) from exc


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _memory_dto(memory: StudentMemory) -> StudentMemoryDTO:
    return StudentMemoryDTO.model_validate(memory)


def _evidence_dto(evidence: MemoryEvidence) -> MemoryEvidenceDTO:
    return MemoryEvidenceDTO.model_validate(evidence)


def _insight_dto(insight: ProfileInsight) -> ProfileInsightDTO:
    return ProfileInsightDTO.model_validate(insight)


def _episode_dto(episode: StudentEpisode) -> StudentEpisodeDTO:
    return StudentEpisodeDTO.model_validate(episode)


class MemoryService:
    """Student-facing memory management service.

    Candidate generation and evidence aggregation are intentionally outside this
    service. This task only exposes the read and user-controlled state-machine
    operations defined by the Memory API contract.
    """

    async def _get_profile(
        self, session: AsyncSession, user_id: UUID
    ) -> StudentProfile:
        result = await session.execute(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            raise _error(404, "STUDENT_PROFILE_NOT_FOUND", "student profile not found")
        return profile

    async def _get_owned_memory(
        self, session: AsyncSession, user_id: UUID, memory_id: UUID
    ) -> StudentMemory:
        profile = await self._get_profile(session, user_id)
        memory = await session.get(StudentMemory, memory_id)
        if memory is None:
            raise _error(404, "MEMORY_NOT_FOUND", "memory not found")
        if memory.student_id != profile.student_id:
            raise _error(403, "FORBIDDEN", "memory does not belong to student")
        return memory

    async def _get_owned_evidence(
        self, session: AsyncSession, user_id: UUID, evidence_id: UUID
    ) -> MemoryEvidence:
        profile = await self._get_profile(session, user_id)
        evidence = await session.get(MemoryEvidence, evidence_id)
        if evidence is None:
            raise _error(404, "EVIDENCE_NOT_FOUND", "evidence not found")
        if evidence.student_id != profile.student_id:
            raise _error(403, "FORBIDDEN", "evidence does not belong to student")
        return evidence

    async def list_memories(
        self,
        session: AsyncSession,
        user_id: UUID,
        *,
        status: MemoryStatus,
        memory_type: MemoryType | None,
    ) -> list[StudentMemoryDTO]:
        profile = await self._get_profile(session, user_id)
        query = select(StudentMemory).where(
            StudentMemory.student_id == profile.student_id,
            StudentMemory.status == status,
        )
        if memory_type is not None:
            query = query.where(StudentMemory.memory_type == memory_type)
        query = query.order_by(
            StudentMemory.updated_at.desc(), StudentMemory.memory_id.desc()
        )
        memories = (await session.execute(query)).scalars().all()
        return [_memory_dto(memory) for memory in memories]

    async def patch_memory(
        self,
        session: AsyncSession,
        user_id: UUID,
        memory_id: UUID,
        request: PatchMemoryRequest,
    ) -> StudentMemoryDTO:
        memory = await self._get_owned_memory(session, user_id, memory_id)
        action = request.action
        current_status = memory.status

        if action == "EDIT":
            if current_status == "REMOVED":
                raise _error(
                    409,
                    "MEMORY_INVALID_TRANSITION",
                    "removed memory cannot be edited",
                )
            if request.content is None or not request.content.strip():
                raise _error(
                    422,
                    "VALIDATION_ERROR",
                    "content is required for EDIT",
                )
            now = datetime.now(timezone.utc)
            memory.status = "SUPERSEDED"
            replacement = StudentMemory(
                memory_id=uuid4(),
                student_id=memory.student_id,
                memory_type=memory.memory_type,
                content=request.content,
                tags=list(memory.tags or []),
                confidence=memory.confidence,
                status="ACTIVE",
                evidence_ids=list(memory.evidence_ids or []),
                origin_candidate_id=memory.origin_candidate_id,
                user_confirmed=True,
                confirmed_at=now,
            )
            session.add(replacement)
            await session.commit()
            await session.refresh(replacement)
            return _memory_dto(replacement)

        if current_status == "REMOVED":
            raise _error(
                409,
                "MEMORY_INVALID_TRANSITION",
                "removed memory cannot change state",
            )

        if action == "CONFIRM":
            if current_status not in {"ACTIVE", "DISPUTED"}:
                raise _error(
                    409,
                    "MEMORY_INVALID_TRANSITION",
                    "memory cannot be confirmed from its current state",
                )
            memory.status = "ACTIVE"
            memory.user_confirmed = True
            memory.confirmed_at = datetime.now(timezone.utc)
        elif action == "DISPUTE":
            if current_status != "ACTIVE":
                raise _error(
                    409,
                    "MEMORY_INVALID_TRANSITION",
                    "only active memory can be disputed",
                )
            memory.status = "DISPUTED"
        elif action == "FORGET":
            memory.status = "REMOVED"
        else:  # pragma: no cover - guarded by the Literal request schema
            raise _error(422, "VALIDATION_ERROR", "unsupported memory action")

        await session.commit()
        await session.refresh(memory)
        return _memory_dto(memory)

    async def get_evidence(
        self,
        session: AsyncSession,
        user_id: UUID,
        evidence_id: UUID,
    ) -> MemoryEvidenceDTO:
        evidence = await self._get_owned_evidence(session, user_id, evidence_id)
        return _evidence_dto(evidence)

    async def _get_owned_insight(
        self, session: AsyncSession, user_id: UUID, insight_id: UUID
    ) -> ProfileInsight:
        profile = await self._get_profile(session, user_id)
        insight = await session.get(ProfileInsight, insight_id)
        if insight is None:
            raise _error(404, "INSIGHT_NOT_FOUND", "insight not found")
        if insight.student_id != profile.student_id:
            raise _error(403, "FORBIDDEN", "insight does not belong to student")
        return insight

    async def _get_owned_episode(
        self, session: AsyncSession, user_id: UUID, episode_id: UUID
    ) -> StudentEpisode:
        profile = await self._get_profile(session, user_id)
        episode = await session.get(StudentEpisode, episode_id)
        if episode is None:
            raise _error(404, "EPISODE_NOT_FOUND", "episode not found")
        if episode.student_id != profile.student_id:
            raise _error(403, "FORBIDDEN", "episode does not belong to student")
        return episode

    async def list_insights(
        self,
        session: AsyncSession,
        user_id: UUID,
        *,
        status: InsightStatus,
        insight_type: InsightType | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[ProfileInsightDTO], str | None, bool]:
        profile = await self._get_profile(session, user_id)
        query = select(ProfileInsight).where(
            ProfileInsight.student_id == profile.student_id,
            ProfileInsight.status == status,
        )
        if insight_type is not None:
            query = query.where(ProfileInsight.insight_type == insight_type)
        if cursor is not None:
            cursor_valid_from, cursor_id = _decode_cursor(cursor)
            query = query.where(
                tuple_(ProfileInsight.valid_from, ProfileInsight.insight_id)
                < (cursor_valid_from, cursor_id)
            )
        query = (
            query.order_by(
                ProfileInsight.valid_from.desc(),
                ProfileInsight.insight_id.desc(),
            )
            .limit(limit + 1)
        )
        rows = (await session.execute(query)).scalars().all()
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = (
            _encode_cursor(page[-1].valid_from, page[-1].insight_id)
            if has_more and page
            else None
        )
        return [_insight_dto(row) for row in page], next_cursor, has_more

    async def get_insight(
        self,
        session: AsyncSession,
        user_id: UUID,
        insight_id: UUID,
    ) -> tuple[ProfileInsightDTO, list[MemoryEvidenceDTO]]:
        insight = await self._get_owned_insight(session, user_id, insight_id)
        evidence_ids = [UUID(item) for item in (insight.evidence_ids or []) if item]
        evidence: list[MemoryEvidenceDTO] = []
        if evidence_ids:
            rows = (
                await session.execute(
                    select(MemoryEvidence).where(
                        MemoryEvidence.student_id == insight.student_id,
                        MemoryEvidence.evidence_id.in_(evidence_ids),
                    )
                )
            ).scalars().all()
            evidence = [_evidence_dto(row) for row in rows]
        return _insight_dto(insight), evidence

    async def list_episodes(
        self,
        session: AsyncSession,
        user_id: UUID,
        *,
        importance: EpisodeImportance | None,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[StudentEpisodeDTO], str | None, bool]:
        profile = await self._get_profile(session, user_id)
        query = select(StudentEpisode).where(
            StudentEpisode.student_id == profile.student_id
        )
        if importance is not None:
            query = query.where(StudentEpisode.importance == importance)
        if cursor is not None:
            cursor_occurred_at, cursor_id = _decode_cursor(cursor)
            query = query.where(
                tuple_(StudentEpisode.occurred_at, StudentEpisode.episode_id)
                < (cursor_occurred_at, cursor_id)
            )
        query = (
            query.order_by(
                StudentEpisode.occurred_at.desc(),
                StudentEpisode.episode_id.desc(),
            )
            .limit(limit + 1)
        )
        rows = (await session.execute(query)).scalars().all()
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = (
            _encode_cursor(page[-1].occurred_at, page[-1].episode_id)
            if has_more and page
            else None
        )
        return [_episode_dto(row) for row in page], next_cursor, has_more

    async def get_episode(
        self,
        session: AsyncSession,
        user_id: UUID,
        episode_id: UUID,
    ) -> StudentEpisodeDTO:
        episode = await self._get_owned_episode(session, user_id, episode_id)
        return _episode_dto(episode)
