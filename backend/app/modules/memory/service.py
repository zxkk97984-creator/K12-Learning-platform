from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    MemoryEvidence,
    StudentMemory,
    StudentProfile,
)
from app.modules.memory.schemas import (
    MemoryEvidenceDTO,
    MemoryStatus,
    MemoryType,
    PatchMemoryRequest,
    StudentMemoryDTO,
)

def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _memory_dto(memory: StudentMemory) -> StudentMemoryDTO:
    return StudentMemoryDTO.model_validate(memory)


def _evidence_dto(evidence: MemoryEvidence) -> MemoryEvidenceDTO:
    return MemoryEvidenceDTO.model_validate(evidence)


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
