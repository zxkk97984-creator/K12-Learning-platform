"""完整 TeacherContext 构建（Phase 2-C）。

在构造 system prompt 前从数据库聚合学生档案、偏好、长期记忆、画像洞察、
最近学习事件与最近测验，并叠加当前阅读位置。所有内容真实来自 DB；
无数据时输出明确的「暂无」，绝不伪造。记忆/洞察仅作为可质疑的观察
（保留 evidence 可追溯语义），不当作学生已确认的事实。

各分节设有条数与字符上限，避免 prompt 超长。
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    Book,
    Chapter,
    ContentBlock,
    LearningEvent,
    ProfileInsight,
    QuizAnswer,
    QuizQuestion,
    QuizSession,
    StudentMemory,
    StudentPreference,
)

logger = logging.getLogger(__name__)

MEMORY_LIMIT = 5
INSIGHT_LIMIT = 5
EVENT_LIMIT = 10
QUIZ_LIMIT = 5
SECTION_CHAR_LIMIT = 900
READING_TEXT_LIMIT = 3
READING_TEXT_CHARS = 160

_INSIGHT_TYPE_ZH = {
    "STRENGTH": "优势",
    "WEAKNESS": "薄弱",
    "UNDERSTANDING": "理解力",
    "HABIT": "习惯",
    "CHANGE": "变化",
    "INTEREST": "兴趣",
}

_PREFERENCE_STYLE_ZH = {
    "EXAMPLE_BASED": "例子驱动",
    "VISUAL": "可视化",
    "STORY": "故事化",
    "DIRECT_DEFINITION": "直接定义",
    "STEP_BY_STEP": "分步讲解",
    "CODE": "代码示例",
    "INTERACTIVE": "互动问答",
}
_DIFFICULTY_ZH = {"EASY": "简单", "MEDIUM": "中等", "HARD": "较难"}
_LENGTH_ZH = {"SHORT": "短时", "MEDIUM": "适中", "LONG": "长时间"}

_NOT_AVAILABLE = "暂无"


def _fmt_time(value: datetime | None) -> str:
    if value is None:
        return _NOT_AVAILABLE
    return value.astimezone(timezone.utc).strftime("%m-%d %H:%M")


async def build_teacher_context(
    session: AsyncSession,
    *,
    student_id: UUID,
    grade: int | None,
    language: str | None,
    learning_goal: str | None,
    current_context: dict[str, Any],
) -> str:
    """聚合 DB 真实数据为 system prompt 的上下文块。"""
    sections: list[str] = []

    profile_lines = [
        f"- 年级：{grade if grade is not None else _NOT_AVAILABLE}",
        f"- 语言：{language or _NOT_AVAILABLE}",
        f"- 学习目标：{learning_goal or _NOT_AVAILABLE}",
    ]
    sections.append("【学生档案】\n" + "\n".join(profile_lines))

    preference_row = (
        await session.execute(
            select(StudentPreference).where(StudentPreference.student_id == student_id)
        )
    ).scalar_one_or_none()
    if preference_row is not None:
        sections.append(
            "【学习偏好】\n"
            "- 讲解方式：" + _PREFERENCE_STYLE_ZH.get(
                preference_row.preferred_explanation_style,
                preference_row.preferred_explanation_style,
            ) + "\n"
            "- 难度偏好：" + _DIFFICULTY_ZH.get(
                preference_row.preferred_difficulty, preference_row.preferred_difficulty
            ) + "\n"
            "- 单次时长：" + _LENGTH_ZH.get(
                preference_row.preferred_session_length,
                preference_row.preferred_session_length,
            )
        )
    else:
        sections.append(f"【学习偏好】\n- {_NOT_AVAILABLE}")

    memories = (
        await session.execute(
            select(StudentMemory)
            .where(
                StudentMemory.student_id == student_id,
                StudentMemory.status == "ACTIVE",
            )
            .order_by(StudentMemory.updated_at.desc())
            .limit(MEMORY_LIMIT)
        )
    ).scalars().all()
    memory_lines = [
        f"- [{m.memory_type}] {m.content}（置信度：{m.confidence}，id={m.memory_id}）"
        for m in memories
    ]
    sections.append(
        "【长期记忆·系统观察，学生可能质疑】\n"
        + ("\n".join(memory_lines) if memory_lines else f"- {_NOT_AVAILABLE}")
    )

    insights = (
        await session.execute(
            select(ProfileInsight)
            .where(
                ProfileInsight.student_id == student_id,
                ProfileInsight.status == "ACTIVE",
            )
            .order_by(ProfileInsight.valid_from.desc())
            .limit(INSIGHT_LIMIT)
        )
    ).scalars().all()
    insight_lines = [
        f"- [{_INSIGHT_TYPE_ZH.get(i.insight_type, i.insight_type)}·{i.level}] "
        f"{i.description}（证据数={len(i.evidence_ids or [])}，id={i.insight_id}）"
        for i in insights
    ]
    sections.append(
        "【画像洞察·基于证据的定性判断】\n"
        + ("\n".join(insight_lines) if insight_lines else f"- {_NOT_AVAILABLE}")
    )

    events = (
        await session.execute(
            select(LearningEvent)
            .where(LearningEvent.student_id == student_id)
            .order_by(LearningEvent.occurred_at.desc())
            .limit(EVENT_LIMIT)
        )
    ).scalars().all()
    event_lines = []
    for event in events:
        line = f"- [{event.event_type}] {_fmt_time(event.occurred_at)}"
        if event.payload:
            line += f" payload={json.dumps(event.payload, ensure_ascii=False)}"
        event_lines.append(line)
    sections.append(
        "【最近学习事件】\n"
        + ("\n".join(event_lines) if event_lines else f"- {_NOT_AVAILABLE}")
    )

    quiz_sessions = (
        await session.execute(
            select(QuizSession)
            .where(QuizSession.student_id == student_id)
            .order_by(QuizSession.created_at.desc())
            .limit(QUIZ_LIMIT)
        )
    ).scalars().all()
    quiz_lines: list[str] = []
    for quiz_session in quiz_sessions:
        question_ids = (
            await session.execute(
                select(QuizQuestion.question_id).where(
                    QuizQuestion.quiz_session_id == quiz_session.quiz_session_id
                )
            )
        ).scalars().all()
        answers = (
            await session.execute(
                select(QuizAnswer).where(
                    QuizAnswer.quiz_session_id == quiz_session.quiz_session_id,
                    QuizAnswer.is_final.is_(True),
                )
            )
        ).scalars().all()
        correct = sum(1 for answer in answers if answer.is_correct)
        quiz_lines.append(
            f"- 《{quiz_session.title}》[{quiz_session.status}] "
            f"最终正确 {correct}/{len(question_ids)} · 创建 {_fmt_time(quiz_session.created_at)}"
        )
    sections.append(
        "【最近测验】\n" + ("\n".join(quiz_lines) if quiz_lines else f"- {_NOT_AVAILABLE}")
    )

    reading_lines: list[str] = []
    chapter_uuid: UUID | None = None
    chapter_id_raw = current_context.get("chapterId") or current_context.get("chapter_id")
    try:
        chapter_uuid = UUID(str(chapter_id_raw)) if chapter_id_raw else None
    except (ValueError, TypeError):
        chapter_uuid = None
    if chapter_uuid is not None:
        chapter = await session.get(Chapter, chapter_uuid)
        if chapter is not None:
            book_title = _NOT_AVAILABLE
            if chapter.book_id is not None:
                book = await session.get(Book, chapter.book_id)
                book_title = book.title if book is not None else _NOT_AVAILABLE
            reading_lines.append(f"- 当前章节：《{chapter.title}》（书：{book_title}）")
        else:
            reading_lines.append(f"- 当前章节：{_NOT_AVAILABLE}")

    visible_section = current_context.get("visibleSection") or current_context.get(
        "visible_section"
    )
    reading_lines.append(f"- 可见小节：{visible_section if visible_section else _NOT_AVAILABLE}")

    # ---- 当前正文节选：优先学生可见内容块，否则取本章前几个文本块 ----
    def _block_text(content: Any) -> str | None:
        if not isinstance(content, dict):
            return None
        for key in ("text", "caption", "body"):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    body_lines: list[str] = []
    if chapter_uuid is not None:
        block_id_raw = (
            current_context.get("contentBlockId") or current_context.get("content_block_id")
        )
        focused_block = None
        try:
            focused_block = (
                await session.get(ContentBlock, UUID(str(block_id_raw)))
                if block_id_raw
                else None
            )
        except (ValueError, TypeError):
            focused_block = None
        if focused_block is not None and focused_block.chapter_id == chapter_uuid:
            text = _block_text(focused_block.content)
            if text:
                body_lines.append(text[:READING_TEXT_CHARS])
        if not body_lines:
            blocks = (
                await session.execute(
                    select(ContentBlock)
                    .where(ContentBlock.chapter_id == chapter_uuid)
                    .order_by(ContentBlock.block_order.asc())
                    .limit(READING_TEXT_LIMIT * 2)
                )
            ).scalars().all()
            for block in blocks:
                text = _block_text(block.content)
                if text:
                    body_lines.append(text[:READING_TEXT_CHARS])
                if len(body_lines) >= READING_TEXT_LIMIT:
                    break
    sections_body = "\n".join(
        f"  · {line}" for line in body_lines[:READING_TEXT_LIMIT]
    )
    reading_lines.append(
        "- 当前正文节选：" + (sections_body if sections_body else _NOT_AVAILABLE)
    )
    kps = current_context.get("knowledgePoints") or current_context.get("knowledge_points")
    if isinstance(kps, list) and kps:
        reading_lines.append("- 页面知识点：" + "、".join(str(kp) for kp in kps[:6]))
    else:
        reading_lines.append(f"- 页面知识点：{_NOT_AVAILABLE}")
    selected_text = current_context.get("selectedText") or current_context.get("selected_text")
    reading_lines.append(
        "- 学生选中文本：" + (str(selected_text)[:120] if selected_text else _NOT_AVAILABLE)
    )
    sections.append("【当前阅读位置】\n" + "\n".join(reading_lines))

    context_block = "\n\n".join(sections)
    logger.info(
        "teacher_context built",
        extra={
            "student_id": str(student_id),
            "memories": len(memories),
            "insights": len(insights),
            "events": len(events),
            "quizzes": len(quiz_sessions),
            "chars": len(context_block),
        },
    )
    return context_block


def teacher_usage_note() -> str:
    """注入 prompt 的使用约束：观察≠事实；引用需可追溯；禁止编造。"""
    return (
        "【上下文使用约束】\n"
        "1.【长期记忆】与【画像洞察】是系统基于学习记录做出的观察，不是学生确认过的事实；"
        "学生质疑时应引用对应 id 指向的证据并允许修正。\n"
        "2. 回答应结合【学习偏好】调整讲解方式与难度。\n"
        "3. 只引用上下文中真实出现的内容，禁止编造数据、事件或知识点。"
    )
