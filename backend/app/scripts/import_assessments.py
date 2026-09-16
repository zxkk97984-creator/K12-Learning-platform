"""审校题源幂等导入器：assessments/<slug>/<chapter>.json → reviewed_questions。

用法：
    uv run python -m app.scripts.import_assessments                # 全部
    uv run python -m app.scripts.import_assessments --slug ai-primary-fun

约定：
- 按 stable_key 幂等 upsert（存在即更新 revision/status），导入两次数量不翻倍；
- 每个 question 记录其 review_status（DRAFT/PENDING/APPROVED/REJECTED 原样入库）；
- 只允许 chapter_id 指向真实已发布章节；找不到时跳过该题并告警；
- 只有 review_status='APPROVED' 的题会被 quiz 选择器选中（见 select_reviewed_questions）；
  DRAFT/PENDING 题入库备审，但**不会被出题选中**（未审校题不能被选出）。
- 不扫描生产请求路径：本脚本仅在管理/初始化时运行，运行时请求走 DB 查询。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.infrastructure.database.models import Chapter, ReviewedQuestion
from app.infrastructure.database.session import async_session

logger = logging.getLogger(__name__)

ASSESSMENTS_DIR = Path(__file__).resolve().parents[2] / "data" / "library" / "assessments"

VALID_STATUS = {"DRAFT", "PENDING", "APPROVED", "REJECTED"}


def _uuid(value: str) -> UUID | None:
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


def _payload(question: dict, grade_min: int, grade_max: int) -> dict:
    return {
        "question_type": question["type"],
        "stem": question["stem"],
        "options": question["options"],
        "correct_answer": question["correct_answer"],
        "explanation": question["explanation"],
        "hints": question.get("hints", []),
        "difficulty": question.get("difficulty", "MEDIUM"),
        "knowledge_point": question.get("knowledge_point"),
        "learning_objective": question.get("learning_objective"),
        "source_block": question.get("source_block"),
        "distractor_rationale": question.get("distractor_rationale"),
        "grade_min": grade_min,
        "grade_max": grade_max,
        "source_slug": question.get("slug"),
    }


async def import_assessments(slug: str | None = None, dir_override: Path | None = None) -> dict[str, int]:
    """导入 <slug>/<chapter>.json；返回 {imported, skipped_no_chapter, errors}。"""
    base_dir = dir_override or ASSESSMENTS_DIR
    files = (
        [Path(f) for f in base_dir.rglob("*.json")]
        if slug is None
        else [p for p in base_dir.rglob("*.json") if p.parts[-2] == slug]
    )
    imported = 0
    skipped_no_chapter = 0
    errors = 0
    async with async_session() as session:
        for file_path in sorted(files):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                logger.warning("skip %s: %s", file_path, exc)
                errors += 1
                continue
            grade_min = int(data.get("grade_min", 1))
            grade_max = int(data.get("grade_max", 12))
            # 章节关联：题源 JSON 可显式携带 chapter_id；缺省则不强行关联（chapter_id=NULL）。
            # 理由：assessments 文件不含 book_id/slug 到 Book 的可靠映射，按 chapter_order
            # 跨书匹配会错连到别的书。关联由内容侧在 JSON 中显式声明，选择器按 chapter_id 查询。
            chapter_id_raw = data.get("chapter_id")
            chapter: Chapter | None = None
            if chapter_id_raw:
                chapter = await session.get(Chapter, _uuid(chapter_id_raw))
            for question in data.get("questions", []):
                stable_key = question.get("stable_key")
                if not stable_key:
                    errors += 1
                    continue
                review_status = question.get("review_status", "DRAFT")
                if review_status not in VALID_STATUS:
                    review_status = "DRAFT"
                q_grade_min = int(question.get("grade_min", grade_min))
                q_grade_max = int(question.get("grade_max", grade_max))
                existing = (
                    await session.execute(
                        select(ReviewedQuestion).where(
                            ReviewedQuestion.stable_key == stable_key
                        )
                    )
                ).scalar_one_or_none()
                if existing is None:
                    session.add(
                        ReviewedQuestion(
                            stable_key=stable_key,
                            chapter_id=chapter.chapter_id if chapter else None,
                            grade_min=q_grade_min,
                            grade_max=q_grade_max,
                            revision=1,
                            payload=_payload(question, q_grade_min, q_grade_max),
                            review_status=review_status,
                            reviewed_at=None,
                        )
                    )
                    imported += 1
                else:
                    existing.payload = _payload(question, q_grade_min, q_grade_max)
                    existing.review_status = review_status
                    existing.revision = int(existing.revision or 1) + 1
                    imported += 1
        await session.commit()
    return {"imported": imported, "skipped_no_chapter": skipped_no_chapter, "errors": errors}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", default=None, help="仅导入指定 slug 的题源")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    result = asyncio.run(import_assessments(slug=args.slug))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
