"""当前章节内容驱动的题目来源（Phase 2-B）。

优先级：
1. 真实 LLM（openai_compatible）基于本章真实内容生成；
2. mock/失败时：基于本章真实 Chapter/ContentBlock/KnowledgePoint 确定性生成，
   覆盖 SINGLE_CHOICE / TRUE_FALSE / MULTIPLE_CHOICE / FILL_BLANK 四种题型；
3. 未携带章节上下文的测验才允许回退到与章节无关的内置题库。

任何带章节上下文的生成失败都必须显式抛错，禁止静默给出无关题。
所有确定性生成的选项、答案与解析均来自数据库中的真实内容，可判分、可追溯。
"""

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.models import (
    Book,
    Chapter,
    ContentBlock,
    KnowledgePoint,
)

logger = logging.getLogger(__name__)

_SNIPPET_MAX = 64


@dataclass(frozen=True)
class ChapterSourceData:
    """从 DB 提取的章节出题素材。"""

    book_id: str | None
    chapter_id: str
    book_title: str
    chapter_title: str
    texts: tuple[str, ...] = field(default_factory=tuple)
    section_keys: tuple[str, ...] = field(default_factory=tuple)
    knowledge_points: tuple[dict[str, str], ...] = field(default_factory=tuple)
    foreign_kp_names: tuple[str, ...] = field(default_factory=tuple)
    # 其他章节的真实句子（用于“不属于本章”的判断题反例）
    outside_snippets: tuple[str, ...] = field(default_factory=tuple)


def _block_text(content: dict[str, Any] | None) -> str | None:
    if not isinstance(content, dict):
        return None
    for key in ("text", "caption", "body"):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _clip(text: str, limit: int = _SNIPPET_MAX) -> str:
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"


async def load_chapter_source(
    session: AsyncSession, book_id: Any, chapter_id: Any
) -> ChapterSourceData | None:
    """读取章节真实内容；章节不存在、不可见或完全无可出题素材时返回 None。

    可见性：仅当章节与其所属书均为 PUBLISHED 时返回内容（T03）；
    若调用方指定的 book_id 与章节实际归属不符，也视为不可见。
    """
    chapter = await session.get(Chapter, chapter_id)
    if chapter is None or chapter.status != "PUBLISHED":
        return None
    if book_id is not None and chapter.book_id is not None and chapter.book_id != book_id:
        # T03：篡改 chapter/book 组合（章节不属于指定书）被拒绝。
        return None
    book = await session.get(Book, book_id) if book_id is not None else None
    if book is None and chapter.book_id is not None:
        book = await session.get(Book, chapter.book_id)
    if book is None or book.status != "PUBLISHED":
        return None

    blocks = (
        await session.execute(
            select(ContentBlock)
            .where(ContentBlock.chapter_id == chapter_id)
            .order_by(ContentBlock.block_order.asc())
        )
    ).scalars().all()

    texts: list[str] = []
    section_keys: list[str] = []
    kp_ids: set[UUID] = set()
    for block in blocks:
        text = _block_text(block.content)
        if text:
            texts.append(text)
        if block.section_key:
            section_keys.append(str(block.section_key))
        for raw_id in block.knowledge_point_ids or []:
            try:
                kp_ids.add(UUID(str(raw_id)))
            except (ValueError, TypeError, AttributeError):
                continue

    chapter_kps: list[dict[str, str]] = []
    foreign_kp_names: list[str] = []
    if kp_ids:
        rows = (
            await session.execute(
                select(KnowledgePoint).where(KnowledgePoint.knowledge_point_id.in_(kp_ids))
            )
        ).scalars().all()
        chapter_kps = [
            {"id": str(row.knowledge_point_id), "slug": row.slug, "name": row.name}
            for row in rows
        ]
        foreign_rows = (
            await session.execute(
                select(KnowledgePoint)
                .where(KnowledgePoint.knowledge_point_id.not_in(kp_ids))
                .limit(12)
            )
        ).scalars().all()
        foreign_kp_names = [row.name for row in foreign_rows]

    outside_snippets: list[str] = []
    if chapter.chapter_id is not None:
        outside_blocks = (
            await session.execute(
                select(ContentBlock)
                .where(
                    ContentBlock.chapter_id != chapter.chapter_id,
                    ContentBlock.chapter_id.is_not(None),
                )
                .limit(8)
            )
        ).scalars().all()
        outside_snippets = [
            clipped
            for clipped in (
                _clip(text)
                for text in (_block_text(b.content) for b in outside_blocks)
                if text
            )
            if clipped
        ]

    if not texts and not chapter_kps:
        return None
    return ChapterSourceData(
        book_id=str(book.book_id) if book is not None else None,
        chapter_id=str(chapter.chapter_id),
        book_title=book.title if book is not None else "",
        chapter_title=chapter.title,
        texts=tuple(texts),
        section_keys=tuple(section_keys),
        knowledge_points=tuple(chapter_kps),
        foreign_kp_names=tuple(foreign_kp_names),
        outside_snippets=tuple(outside_snippets[:6]),
    )


def _feasible_templates(source: ChapterSourceData) -> list[str]:
    """按数据可用性筛选可行的确定性题型；顺序即生成轮转顺序。"""
    feasible: list[str] = []
    if source.knowledge_points and len(source.foreign_kp_names) >= 3:
        feasible.append("single_choice")
    if source.knowledge_points and len(source.foreign_kp_names) >= 2:
        feasible.append("multiple_choice")
    if any(
        kp["name"] in text
        for kp in source.knowledge_points
        for text in source.texts
    ):
        feasible.append("fill_blank")
    if source.outside_snippets:
        feasible.append("true_false_false")
    if source.texts:
        # 只要有真实正文就始终可行——保证任意非空章节至少能出题。
        feasible.append("true_false_true")
    return feasible


def generate_chapter_questions(
    source: ChapterSourceData,
    *,
    count: int,
) -> list[dict[str, Any]]:
    """基于本章真实内容确定性生成可判分的多题型题目。

    题型轮转起点由章节数据规模决定：同一章节结果可复现，不同章节
    天然错开首题型。无法构造足够题目时显式抛错。
    """
    if count <= 0:
        raise ValueError("question_count must be positive")
    feasible = _feasible_templates(source)
    if not feasible:
        raise ValueError(
            f"当前章节《{source.chapter_title}》缺少可用于出题的真实内容"
        )

    questions: list[dict[str, Any]] = []
    start = len(source.texts) % len(feasible)
    for index in range(count * 2):  # 允许跳过个别不可行模板后仍凑足 count
        if len(questions) >= count:
            break
        template = feasible[(start + index) % len(feasible)]
        question = _TEMPLATE_BUILDERS[template](source, index)
        if question is not None:
            questions.append(question)
    if not questions:
        raise ValueError(
            f"当前章节《{source.chapter_title}》无法生成可判分的题目"
        )
    return questions


def _build_single_choice(source: ChapterSourceData, index: int) -> dict[str, Any] | None:
    if not source.knowledge_points or len(source.foreign_kp_names) < 3:
        return None
    correct_kp = source.knowledge_points[index % len(source.knowledge_points)]
    distractors = [n for n in source.foreign_kp_names if n != correct_kp["name"]]
    if len(distractors) < 3:
        return None
    wrong_texts = [distractors[(index + offset) % len(distractors)] for offset in range(3)]
    keys = ["A", "B", "C", "D"]
    correct_index = index % 4
    option_texts = wrong_texts.copy()
    option_texts.insert(correct_index, correct_kp["name"])
    options = [{"key": keys[i], "text": option_texts[i]} for i in range(4)]
    return {
        "question_type": "SINGLE_CHOICE",
        "stem": f"以下哪一项是《{source.chapter_title}》这一章的核心知识点？",
        "options": options,
        "correct_answer": {"key": keys[correct_index]},
        "explanation": (
            f"「{correct_kp['name']}」是本章明确讲解的知识点；"
            "其余选项属于其他章节的内容。"
        ),
        "knowledge_point_ids": [correct_kp["id"]],
    }


def _build_true_false_true(source: ChapterSourceData, index: int) -> dict[str, Any] | None:
    if not source.texts:
        return None
    snippet = _clip(source.texts[index % len(source.texts)])
    return {
        "question_type": "TRUE_FALSE",
        "stem": f"判断：《{source.chapter_title}》中是否讲到——「{snippet}」",
        "options": [{"key": "TRUE", "text": "正确"}, {"key": "FALSE", "text": "错误"}],
        "correct_answer": {"key": "TRUE"},
        "explanation": f"这句话出自本章内容：「{snippet}」。",
        "knowledge_point_ids": [],
    }


def _build_true_false_false(source: ChapterSourceData, index: int) -> dict[str, Any] | None:
    if not source.outside_snippets:
        return None
    snippet = source.outside_snippets[index % len(source.outside_snippets)]
    return {
        "question_type": "TRUE_FALSE",
        "stem": f"判断：以下内容是否出自《{source.chapter_title}》——「{snippet}」",
        "options": [{"key": "TRUE", "text": "正确"}, {"key": "FALSE", "text": "错误"}],
        "correct_answer": {"key": "FALSE"},
        "explanation": f"这段内容并不在本章中，它来自其他章节：「{snippet}」。",
        "knowledge_point_ids": [],
    }


def _build_fill_blank(source: ChapterSourceData, index: int) -> dict[str, Any] | None:
    kps = list(source.knowledge_points)
    if not kps:
        return None
    ordered = kps[index % len(kps):] + kps[: index % len(kps)]
    for kp in ordered:
        for text in source.texts:
            if kp["name"] and kp["name"] in text:
                return {
                    "question_type": "FILL_BLANK",
                    "stem": f"根据本章内容填空：{text.replace(kp['name'], '____', 1)}",
                    "options": [],
                    "correct_answer": {"value": kp["name"]},
                    "explanation": (
                        f"本章原文：「{_clip(text, 120)}」，空格处应为「{kp['name']}」。"
                    ),
                    "knowledge_point_ids": [kp["id"]],
                }
    return None


def _build_multiple_choice(source: ChapterSourceData, index: int) -> dict[str, Any] | None:
    if not source.knowledge_points or len(source.foreign_kp_names) < 2:
        return None
    chapter_names = [kp["name"] for kp in source.knowledge_points]
    distractors = [n for n in source.foreign_kp_names if n not in chapter_names][:2]
    if not distractors:
        return None
    option_texts = chapter_names + distractors
    keys = ["A", "B", "C", "D", "E", "F"][: len(option_texts)]
    correct_keys = sorted(keys[: len(chapter_names)])
    return {
        "question_type": "MULTIPLE_CHOICE",
        "stem": f"以下哪些是《{source.chapter_title}》这一章涉及的知识点？（多选）",
        "options": [
            {"key": keys[i], "text": option_texts[i]} for i in range(len(option_texts))
        ],
        "correct_answer": {"keys": correct_keys},
        "explanation": (
            "正确项均为本章讲解的知识点：" + "、".join(chapter_names) + "；其余选项属于其他章节。"
        ),
        "knowledge_point_ids": [kp["id"] for kp in source.knowledge_points],
    }


_TEMPLATE_BUILDERS = {
    "single_choice": _build_single_choice,
    "multiple_choice": _build_multiple_choice,
    "fill_blank": _build_fill_blank,
    "true_false_false": _build_true_false_false,
    "true_false_true": _build_true_false_true,
}
