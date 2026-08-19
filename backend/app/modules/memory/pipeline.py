"""Rule-based Memory Pipeline (Phase 7; LLM generation lands in Phase 9).

Flow: LearningEvent -> MemoryEvidence aggregation -> MemoryCandidate ->
Stable Memory / StudentEpisode -> ProfileInsight (5 qualitative levels only).
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.factory import get_ai_provider
from app.config import settings
from app.infrastructure.database.models import (
    LearningEvent,
    MemoryCandidate,
    MemoryEvidence,
    ProfileInsight,
    StudentEpisode,
    StudentMemory,
)

logger = logging.getLogger(__name__)

RULE_VERSION = "memory-rule-v1"
INSIGHT_RULE_VERSION = "profile-rule-v1"
MODEL_INFO = {"provider": "rule", "model": RULE_VERSION}
MAX_SAMPLE_TEXTS = 3

QUIZ_EVENT_TYPES = {
    "ANSWER_CORRECT",
    "ANSWER_WRONG",
    "QUIZ_CREATED",
    "QUIZ_ANSWERED",
    "HINT_REQUESTED",
}
CONVERSATION_EVENT_TYPES = {
    "EXPLAIN_REQUESTED",
    "SUMMARY_REQUESTED",
    "QUESTION_ASKED",
    "TEXT_SELECTED",
    "HELP_REQUESTED",
    "ROLE_SWITCHED",
    "VOICE_SESSION_STARTED",
}
LEARNING_EVENT_TYPES = {
    "CHAPTER_STARTED",
    "CHAPTER_FINISHED",
    "SECTION_READ",
    "KNOWLEDGE_CARD_VIEWED",
}
BOOK_EVENT_TYPES = {"BOOK_STARTED", "BOOK_FINISHED"}


def classify_event(event: LearningEvent) -> tuple[str, str] | None:
    if event.event_type in QUIZ_EVENT_TYPES:
        return "QUIZ", "quiz_performance"
    if event.event_type in CONVERSATION_EVENT_TYPES:
        return "CONVERSATION", "conversation_requests"
    if event.event_type in LEARNING_EVENT_TYPES:
        return "LEARNING_SESSION", "learning_session"
    if event.event_type in BOOK_EVENT_TYPES:
        return "BOOK_PROGRESS", "book_progress"
    return None


def _apply_event_facts(facts: dict[str, Any], event: LearningEvent) -> None:
    event_type = event.event_type
    counters = {
        "ANSWER_CORRECT": "correct_count",
        "ANSWER_WRONG": "wrong_count",
        "QUIZ_CREATED": "quiz_created_count",
        "HINT_REQUESTED": "hint_requested_count",
        "EXPLAIN_REQUESTED": "explain_requested_count",
        "SUMMARY_REQUESTED": "summary_requested_count",
        "QUESTION_ASKED": "question_asked_count",
        "TEXT_SELECTED": "selected_text_count",
        "HELP_REQUESTED": "help_requested_count",
        "CHAPTER_STARTED": "chapter_started_count",
        "CHAPTER_FINISHED": "chapter_finished_count",
        "SECTION_READ": "section_read_count",
        "KNOWLEDGE_CARD_VIEWED": "knowledge_card_viewed_count",
        "BOOK_STARTED": "book_started_count",
        "BOOK_FINISHED": "book_finished_count",
        "VOICE_SESSION_STARTED": "voice_session_count",
        "ROLE_SWITCHED": "role_switched_count",
    }
    key = counters.get(event_type)
    if key is not None:
        facts[key] = int(facts.get(key, 0)) + 1
    if event_type == "TEXT_SELECTED":
        selected_text = None
        payload = event.payload or {}
        if isinstance(payload.get("selected_text"), str):
            selected_text = payload["selected_text"]
        elif isinstance(payload.get("screen_context"), dict):
            selected_text = payload["screen_context"].get("selected_text")
        if isinstance(selected_text, str) and selected_text.strip():
            samples = facts.setdefault("sample_texts", [])
            if selected_text not in samples and len(samples) < MAX_SAMPLE_TEXTS:
                samples.append(selected_text)


def _merge_facts(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if key == "sample_texts":
            samples = target.setdefault("sample_texts", [])
            for item in value:
                if item not in samples and len(samples) < MAX_SAMPLE_TEXTS:
                    samples.append(item)
        elif isinstance(value, int):
            target[key] = int(target.get(key, 0)) + value


def _candidate_content(source_type: str, facts: dict[str, Any]) -> str:
    if source_type == "QUIZ":
        if facts.get("correct_count", 0) >= facts.get("wrong_count", 0):
            return "在测验中多次答对，概念掌握稳定"
        return "在测验中多次尝试，需要更多练习巩固"
    if source_type == "CONVERSATION":
        return "多次主动请求解释或总结，倾向于通过讲解学习"
    if source_type == "LEARNING_SESSION":
        return "持续阅读章节，学习节奏稳定"
    return "持续学习多本书，阅读进度稳定"


def _memory_content(source_type: str, facts: dict[str, Any]) -> str:
    if source_type == "QUIZ":
        if facts.get("correct_count", 0) >= facts.get("wrong_count", 0):
            return "在测验中多次答对，对概念理解较稳"
        return "在测验中多次答错，需要更多练习巩固"
    if source_type == "CONVERSATION":
        return "喜欢通过主动提问和讲解来理解内容"
    if source_type == "LEARNING_SESSION":
        return "有持续阅读章节的学习习惯"
    return "阅读多本书并持续推进学习进度"


def _candidate_type(source_type: str) -> str:
    if source_type == "QUIZ":
        return "LEARNING"
    if source_type == "CONVERSATION":
        return "PREFERENCE"
    if source_type == "LEARNING_SESSION":
        return "EPISODIC"
    return "PROFILE"


def _episode_meta(source_type: str, facts: dict[str, Any]) -> tuple[str, str, str]:
    if source_type == "QUIZ":
        importance = "HIGH" if facts.get("correct_count", 0) >= 2 else "MEDIUM"
        title = "完成了一组随堂练习"
        summary = "在随堂练习中多次作答，并通过结果反馈理解概念。"
    elif source_type == "CONVERSATION":
        importance = "MEDIUM"
        title = "主动向霜铃提问"
        summary = "多次主动请求解释、总结或选中文字提问，通过讲解理解内容。"
    elif source_type == "LEARNING_SESSION":
        importance = "MEDIUM"
        title = "阅读了一组章节"
        summary = "连续阅读章节并记录学习进度，保持稳定的阅读节奏。"
    else:
        importance = "LOW"
        title = "开启新的阅读"
        summary = "开始阅读新书并持续推进学习进度。"
    return title, summary, importance


class MemoryPipeline:
    """Deterministic, idempotent pipeline over LearningEvent facts."""

    async def _llm_text(self, prompt: str) -> str | None:
        if settings.ai_provider.strip().lower() != "openai_compatible":
            return None
        try:
            chunks = []
            async for chunk in get_ai_provider().stream_chat([], prompt):
                chunks.append(chunk)
            text = "".join(chunks).strip()
            return text or None
        except Exception:
            return None

    async def _all_evidence(
        self, session: AsyncSession, student_id: UUID
    ) -> list[MemoryEvidence]:
        rows = (
            await session.execute(
                select(MemoryEvidence)
                .where(MemoryEvidence.student_id == student_id)
                .order_by(MemoryEvidence.derived_at.asc())
            )
        ).scalars().all()
        return list(rows)

    async def _aggregate_group(
        self,
        session: AsyncSession,
        student_id: UUID,
        source_type: str,
        dimension: str,
        new_events: list[LearningEvent],
    ) -> None:
        all_evidence = await self._all_evidence(session, student_id)
        related = [
            row
            for row in all_evidence
            if row.source_type == source_type
            and (row.payload or {}).get("dimension") == dimension
        ]
        facts: dict[str, Any] = {}
        for row in related:
            _merge_facts(facts, row.payload or {})
        event_ids: list[str] = []
        for event in new_events:
            _apply_event_facts(facts, event)
            event_ids.append(str(event.event_id))
        now = datetime.now(timezone.utc)
        evidence = MemoryEvidence(
            evidence_id=uuid4(),
            student_id=student_id,
            source_type=source_type,
            event_ids=event_ids,
            payload={"dimension": dimension, **facts},
            count=len(event_ids),
            first_occurred_at=new_events[0].occurred_at,
            last_occurred_at=new_events[-1].occurred_at,
            derived_at=now,
            rule_version=RULE_VERSION,
        )
        session.add(evidence)
        await session.flush()

        total_count = len(event_ids) + sum(
            len(row.event_ids or []) for row in related
        )
        llm_prompt = (
            "请用一句中文描述这位学生的稳定学习表现，只描述事实与表现，不评分。"
            f"来源类型：{source_type}；事实：{facts}"
        )
        llm_content = await self._llm_text(llm_prompt)
        content = llm_content or _candidate_content(source_type, facts)
        candidate_model_info = (
            {"provider": "openai_compatible", "model": settings.ai_model}
            if llm_content
            else MODEL_INFO
        )
        candidate_type = _candidate_type(source_type)
        confidence = "MEDIUM" if total_count >= 2 else "LOW"
        existing_candidate = (
            await session.execute(
                select(MemoryCandidate)
                .where(
                    MemoryCandidate.student_id == student_id,
                    MemoryCandidate.candidate_type == candidate_type,
                    MemoryCandidate.content == content,
                    MemoryCandidate.status.in_(["PENDING", "APPROVED"]),
                )
                .order_by(MemoryCandidate.created_at.desc())
            )
        ).scalars().first()
        if existing_candidate is not None:
            existing_candidate.evidence_ids = sorted(
                set(existing_candidate.evidence_ids or []) | {str(evidence.evidence_id)}
            )
            existing_candidate.confidence = confidence
            existing_candidate.status = "APPROVED" if total_count >= 2 else "PENDING"
            candidate = existing_candidate
        else:
            candidate = MemoryCandidate(
                candidate_id=uuid4(),
                student_id=student_id,
                candidate_type=candidate_type,
                content=content,
                proposed_memory={
                    "content": llm_content or _memory_content(source_type, facts),
                    "tags": [source_type.lower()],
                    "confidence": confidence,
                },
                evidence_ids=[str(evidence.evidence_id)],
                confidence=confidence,
                status="APPROVED" if total_count >= 2 else "PENDING",
                rule_version=RULE_VERSION,
                model_info=candidate_model_info,
            )
            session.add(candidate)
            await session.flush()

        if total_count >= 2:
            memory_content = llm_content or _memory_content(source_type, facts)
            existing_memory = (
                await session.execute(
                    select(StudentMemory)
                    .where(
                        StudentMemory.student_id == student_id,
                        StudentMemory.status == "ACTIVE",
                        StudentMemory.memory_type == candidate_type,
                        StudentMemory.content == memory_content,
                    )
                    .order_by(StudentMemory.updated_at.desc())
                )
            ).scalars().first()
            if existing_memory is not None:
                existing_memory.evidence_ids = sorted(
                    set(existing_memory.evidence_ids or [])
                    | {str(evidence.evidence_id)}
                )
                existing_memory.confidence = confidence
                existing_memory.origin_candidate_id = candidate.candidate_id
            else:
                session.add(
                    StudentMemory(
                        memory_id=uuid4(),
                        student_id=student_id,
                        memory_type=candidate_type,
                        content=memory_content,
                        tags=[source_type.lower()],
                        confidence=confidence,
                        status="ACTIVE",
                        evidence_ids=[str(evidence.evidence_id)],
                        origin_candidate_id=candidate.candidate_id,
                        user_confirmed=False,
                    )
                )

        existing_episode_event_ids: set[str] = set()
        episodes = (
            await session.execute(
                select(StudentEpisode).where(StudentEpisode.student_id == student_id)
            )
        ).scalars().all()
        for episode in episodes:
            existing_episode_event_ids.update(str(item) for item in (episode.event_ids or []))
        if not set(event_ids) & existing_episode_event_ids:
            title, summary, importance = _episode_meta(source_type, facts)
            session.add(
                StudentEpisode(
                    episode_id=uuid4(),
                    student_id=student_id,
                    title=title,
                    summary=summary,
                    occurred_at=new_events[-1].occurred_at,
                    event_ids=event_ids,
                    book_id=new_events[-1].book_id,
                    chapter_id=new_events[-1].chapter_id,
                    knowledge_point_ids=sorted(
                        {
                            str(item)
                            for event in new_events
                            for item in (event.knowledge_point_ids or [])
                        }
                    ),
                    embedding=None,
                    importance=importance,
                    tags=[source_type.lower()],
                )
            )

    def _quiz_insight(
        self, facts: dict[str, Any], evidence_ids: list[str]
    ) -> dict[str, Any] | None:
        correct = facts.get("correct_count", 0)
        wrong = facts.get("wrong_count", 0)
        if correct + wrong == 0:
            return None
        if correct >= 2 and wrong == 0:
            level = "较强"
            description = "在多次练习中能稳定答对，概念理解比较扎实。"
        elif correct >= 2 and wrong <= 2:
            level = "较稳定"
            description = "在多次练习中多数能答对，概念掌握较稳定。"
        elif wrong > correct:
            level = "偏弱"
            description = "在多次练习中答错较多，建议先从基础概念巩固。"
        else:
            level = "一般"
            description = "在练习中既有答对也有答错，理解正在形成。"
        return {
            "insight_type": "WEAKNESS" if level == "偏弱" else "UNDERSTANDING",
            "dimension": "concept_weakness" if level == "偏弱" else "concept_understanding",
            "level": level,
            "description": description,
            "evidence_ids": evidence_ids,
        }

    def _conversation_insight(
        self, facts: dict[str, Any], evidence_ids: list[str]
    ) -> dict[str, Any] | None:
        requests = (
            facts.get("explain_requested_count", 0)
            + facts.get("summary_requested_count", 0)
            + facts.get("question_asked_count", 0)
            + facts.get("selected_text_count", 0)
        )
        if requests == 0:
            return None
        if requests >= 3:
            level = "较强"
        elif requests >= 2:
            level = "较稳定"
        else:
            level = "仍需观察"
        return {
            "insight_type": "INTEREST",
            "dimension": "example_learning",
            "level": level,
            "description": "多次主动请求解释或总结，喜欢借助具体讲解理解概念。",
            "evidence_ids": evidence_ids,
        }

    def _reading_insight(
        self, facts: dict[str, Any], evidence_ids: list[str]
    ) -> dict[str, Any] | None:
        finished = facts.get("chapter_finished_count", 0)
        started = facts.get("chapter_started_count", 0)
        if finished + started == 0:
            return None
        if finished >= 2:
            level = "较稳定"
        elif finished >= 1:
            level = "一般"
        else:
            level = "仍需观察"
        return {
            "insight_type": "HABIT",
            "dimension": "reading_habit",
            "level": level,
            "description": "持续阅读章节并推进学习进度，阅读节奏稳定。",
            "evidence_ids": evidence_ids,
        }

    def _book_insight(
        self, facts: dict[str, Any], evidence_ids: list[str]
    ) -> dict[str, Any] | None:
        if facts.get("book_finished_count", 0) >= 1:
            return {
                "insight_type": "STRENGTH",
                "dimension": "reading_progress",
                "level": "较强",
                "description": "完成了整本书的阅读，能够持续推进长期学习。",
                "evidence_ids": evidence_ids,
            }
        if facts.get("book_started_count", 0) >= 2:
            return {
                "insight_type": "HABIT",
                "dimension": "reading_progress",
                "level": "一般",
                "description": "已开始多本书的学习，阅读范围正在扩展。",
                "evidence_ids": evidence_ids,
            }
        return None

    async def _rebuild_insights(
        self, session: AsyncSession, student_id: UUID
    ) -> None:
        all_evidence = await self._all_evidence(session, student_id)
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for row in all_evidence:
            key = (row.source_type, (row.payload or {}).get("dimension", "general"))
            bucket = grouped.setdefault(key, {"facts": {}, "evidence_ids": []})
            _merge_facts(bucket["facts"], row.payload or {})
            bucket["evidence_ids"].append(str(row.evidence_id))

        candidates: list[dict[str, Any]] = []
        for (source_type, _dimension), bucket in grouped.items():
            if source_type == "QUIZ":
                insight = self._quiz_insight(bucket["facts"], bucket["evidence_ids"])
            elif source_type == "CONVERSATION":
                insight = self._conversation_insight(
                    bucket["facts"], bucket["evidence_ids"]
                )
            elif source_type == "LEARNING_SESSION":
                insight = self._reading_insight(
                    bucket["facts"], bucket["evidence_ids"]
                )
            elif source_type == "BOOK_PROGRESS":
                insight = self._book_insight(bucket["facts"], bucket["evidence_ids"])
            else:  # pragma: no cover - schema constrains source_type
                insight = None
            if insight is not None:
                candidates.append(insight)

        if not candidates:
            return
        for candidate in candidates:
            llm_description = await self._llm_text(
                "请用一句中文、定性描述学生的画像表现，不要使用数字评分。"
                f"类型：{candidate['insight_type']}；维度：{candidate['dimension']}；"
                f"档位：{candidate['level']}；原描述：{candidate['description']}"
            )
            if llm_description:
                candidate["description"] = llm_description
                candidate["model_info"] = {
                    "provider": "openai_compatible",
                    "model": settings.ai_model,
                }
            else:
                candidate["model_info"] = MODEL_INFO
        now = datetime.now(timezone.utc)
        active_rows = (
            await session.execute(
                select(ProfileInsight).where(
                    ProfileInsight.student_id == student_id,
                    ProfileInsight.status == "ACTIVE",
                )
            )
        ).scalars().all()
        for row in active_rows:
            row.status = "SUPERSEDED"
            row.valid_until = now
        for candidate in candidates:
            session.add(
                ProfileInsight(
                    insight_id=uuid4(),
                    student_id=student_id,
                    insight_type=candidate["insight_type"],
                    dimension=candidate["dimension"],
                    level=candidate["level"],
                    description=candidate["description"],
                    evidence_ids=candidate["evidence_ids"],
                    status="ACTIVE",
                    valid_from=now,
                    valid_until=None,
                    rule_version=INSIGHT_RULE_VERSION,
                    model_info=candidate["model_info"],
                )
            )

    async def process_student(
        self,
        session: AsyncSession,
        student_id: UUID,
        *,
        force_insights: bool = False,
    ) -> dict[str, Any]:
        events = (
            await session.execute(
                select(LearningEvent)
                .where(LearningEvent.student_id == student_id)
                .order_by(LearningEvent.occurred_at.asc())
            )
        ).scalars().all()
        all_evidence = await self._all_evidence(session, student_id)
        existing_event_ids = {
            str(item) for row in all_evidence for item in (row.event_ids or [])
        }
        pending = [event for event in events if str(event.event_id) not in existing_event_ids]
        if not pending and not force_insights:
            return {"processed_events": 0, "groups": 0}

        groups: dict[tuple[str, str], list[LearningEvent]] = defaultdict(list)
        for event in pending:
            key = classify_event(event)
            if key is not None:
                groups[key].append(event)
        for (source_type, dimension), group_events in groups.items():
            await self._aggregate_group(
                session,
                student_id,
                source_type,
                dimension,
                group_events,
            )
        await self._rebuild_insights(session, student_id)
        await session.commit()
        return {
            "processed_events": len(pending),
            "groups": len(groups),
        }
