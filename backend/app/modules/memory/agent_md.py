""".agent.md rendering + rule-based evidence citation (Phase 7, 16.6/16.7).

The database is the single source of truth; .agent.md is only a rendered view.
"""

import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    MemoryEvidence,
    ProfileInsight,
    StudentEpisode,
    StudentMemory,
    StudentPreference,
    StudentProfile,
)

SOURCE_LABEL = {
    "QUIZ": "测验",
    "LEARNING_SESSION": "阅读",
    "CONVERSATION": "对话",
    "BOOK_PROGRESS": "阅读进度",
}

PROFILE_KEYWORDS = (
    "喜欢",
    "擅长",
    "弱",
    "兴趣",
    "学习",
    "理解",
    "习惯",
    "例子",
)

# 「为什么你觉得/认为/判断」类质询需要画像词，避免「为什么你觉得这道题很难」误伤。
REQUIRE_PROFILE_PATTERNS = (
    re.compile(r"为什么(?:你|您)?(?:会)?(?:这么)?(?:觉得|认为)"),
    re.compile(r"为什么(?:你|您)?(?:会)?(?:这么)?判断"),
)

# 其余变体只要是对 AI 判断依据的追问即可触发。
FREE_PATTERNS = (
    re.compile(r"为什么(?:这么|这样)(?:觉得|认为|判断|说)"),
    re.compile(r"为什么(?:你|您)?(?:会)?(?:这么)?(?:看出|说)"),
    re.compile(r"凭什么(?:这么)?(?:判断|觉得|认为|说|看出)"),
    re.compile(r"怎么(?:会)?(?:看出来(?:的)?|看出|判断(?:的)?)"),
)

FIRST_PERSON_CUE = re.compile(r"(?:我|咱)(?:觉得|认为|判断|看出)")
SECOND_PERSON_CUE = re.compile(r"(?:你|您)(?:觉得|认为|判断|看出)")


def is_evidence_question(content: str) -> bool:
    normalized = content.casefold()
    # 第一人称陈述（「我觉得这题很难」）不触发；除非同时包含对第二人称的质询。
    if FIRST_PERSON_CUE.search(normalized) and not SECOND_PERSON_CUE.search(normalized):
        return False
    has_profile_keyword = any(
        keyword in normalized for keyword in PROFILE_KEYWORDS
    )
    if any(pattern.search(normalized) for pattern in FREE_PATTERNS):
        return True
    if any(pattern.search(normalized) for pattern in REQUIRE_PROFILE_PATTERNS):
        return has_profile_keyword
    return False


def _payload_summary(payload: dict[str, Any]) -> str:
    items = [
        f"{key}: {value if isinstance(value, str) else str(value)}"
        for key, value in payload.items()
        if key != "dimension"
    ]
    return "；".join(items) if items else "有相关记录"


async def _evidence_by_ids(
    session: AsyncSession,
    student_id: UUID,
    evidence_ids: list[str],
) -> dict[str, MemoryEvidence]:
    if not evidence_ids:
        return {}
    rows = (
        await session.execute(
            select(MemoryEvidence).where(
                MemoryEvidence.student_id == student_id,
                MemoryEvidence.evidence_id.in_(
                    [UUID(item) for item in evidence_ids]
                ),
            )
        )
    ).scalars().all()
    return {str(row.evidence_id): row for row in rows}


async def _evidence_summary(
    session: AsyncSession,
    student_id: UUID,
    evidence_ids: list[str],
) -> str:
    evidence = await _evidence_by_ids(session, student_id, evidence_ids)
    if not evidence:
        return "（暂无证据）"
    parts = []
    for evidence_id in evidence_ids:
        row = evidence.get(evidence_id)
        if row is None:
            continue
        parts.append(
            f"证据：{evidence_id}（{SOURCE_LABEL.get(row.source_type, row.source_type)}，"
            f"{_payload_summary(row.payload)}）"
        )
    return "；".join(parts)


async def render_agent_md(
    session: AsyncSession,
    user_id: UUID,
) -> str:
    profile = (
        await session.execute(
            select(StudentProfile).where(StudentProfile.user_id == user_id)
        )
    ).scalar_one_or_none()
    if profile is None:
        return "# xiaoming.agent.md\n\n> 学生档案不存在，无法渲染。\n"

    preference = (
        await session.execute(
            select(StudentPreference).where(
                StudentPreference.student_id == profile.student_id
            )
        )
    ).scalar_one_or_none()
    memories = (
        await session.execute(
            select(StudentMemory)
            .where(
                StudentMemory.student_id == profile.student_id,
                StudentMemory.status == "ACTIVE",
            )
            .order_by(StudentMemory.updated_at.desc())
        )
    ).scalars().all()
    insights = (
        await session.execute(
            select(ProfileInsight)
            .where(
                ProfileInsight.student_id == profile.student_id,
                ProfileInsight.status == "ACTIVE",
            )
            .order_by(ProfileInsight.valid_from.desc())
        )
    ).scalars().all()
    episodes = (
        await session.execute(
            select(StudentEpisode)
            .where(StudentEpisode.student_id == profile.student_id)
            .order_by(StudentEpisode.occurred_at.desc())
        )
    ).scalars().all()

    lines = [
        "# xiaoming.agent.md",
        "",
        "> 本文件是结构化记忆的**渲染视图，不是数据事实源**；事实源为数据库 "
        "（student_memories / memory_evidence / profile_insights）。",
        "",
        "## 学生档案",
        "",
        f"- 昵称：{profile.nickname}",
        f"- 年级：{profile.grade}",
        f"- 语言：{profile.language}",
    ]
    if preference is not None:
        lines += [
            f"- 讲解偏好：{preference.preferred_explanation_style}",
            f"- 难度偏好：{preference.preferred_difficulty}",
            f"- 时长偏好：{preference.preferred_session_length}",
        ]

    lines += ["", "## AI 学习画像", ""]
    if not insights:
        lines.append("- 暂无画像判断。")
    for insight in insights:
        evidence_summary = await _evidence_summary(
            session, profile.student_id, list(insight.evidence_ids or [])
        )
        lines.append(
            f"- [{insight.insight_type}] {insight.dimension}：{insight.level} — "
            f"{insight.description}（{evidence_summary}）"
        )

    lines += ["", "## 稳定记忆", ""]
    if not memories:
        lines.append("- 暂无稳定记忆。")
    for memory in memories:
        evidence_summary = await _evidence_summary(
            session, profile.student_id, list(memory.evidence_ids or [])
        )
        lines.append(
            f"- [{memory.memory_type}] {memory.content}（confidence={memory.confidence}）"
            f"（{evidence_summary}）"
        )

    lines += ["", "## 学习情节", ""]
    if not episodes:
        lines.append("- 暂无情节记录。")
    for episode in episodes:
        lines.append(
            f"- [{episode.importance}] {episode.title}（{episode.occurred_at.date().isoformat()}）："
            f"{episode.summary}"
        )
    lines.append("")
    return "\n".join(lines)


async def build_evidence_reply(
    session: AsyncSession,
    student_id: UUID,
    content: str,
) -> str | None:
    """Return a deterministic evidence-cited reply, or None when not an evidence question."""
    if not is_evidence_question(content):
        return None
    insights = (
        await session.execute(
            select(ProfileInsight)
            .where(
                ProfileInsight.student_id == student_id,
                ProfileInsight.status == "ACTIVE",
            )
            .order_by(ProfileInsight.valid_from.desc())
        )
    ).scalars().all()
    if not insights:
        return "我还在观察中，暂时没有足够证据来回答这个判断。"

    def insight_score(insight: ProfileInsight, question: str) -> int:
        score = 0
        if "例子" in question and (
            "example" in insight.dimension or "讲解" in insight.description
        ):
            score += 3
        if "喜欢" in question and insight.insight_type == "INTEREST":
            score += 2
        if "擅长" in question and insight.insight_type in {
            "STRENGTH",
            "UNDERSTANDING",
        }:
            score += 2
        if "弱" in question and insight.insight_type == "WEAKNESS":
            score += 2
        if "习惯" in question and insight.insight_type == "HABIT":
            score += 1
        if "学习" in question and insight.insight_type in {"HABIT", "INTEREST"}:
            score += 1
        return score

    ranked = sorted(
        insights,
        key=lambda item: (
            insight_score(item, content),
            item.valid_from,
        ),
        reverse=True,
    )
    for insight in ranked:
        evidence = await _evidence_by_ids(
            session, student_id, list(insight.evidence_ids or [])
        )
        if not evidence:
            continue
        first_evidence = evidence[list(evidence.keys())[0]]
        source_label = SOURCE_LABEL.get(first_evidence.source_type, first_evidence.source_type)
        facts = _payload_summary(first_evidence.payload)
        return (
            f"我观察到你在 {first_evidence.count} 条{source_label}记录中有 "
            f"{facts}（证据：{first_evidence.evidence_id}）。基于这些真实记录，"
            f"我判断：{insight.description}"
        )
    return "我还在观察中，暂时没有足够证据来回答这个判断。"
