from datetime import datetime, timezone
from uuid import uuid4

from app.modules.recommendation.service import (
    BookCandidate,
    BookProgressSignal,
    QuizAnswerSignal,
    build_recommendation_drafts,
)


def test_continue_reading_rule_uses_incomplete_progress() -> None:
    progress_id = uuid4()
    book_id = uuid4()

    drafts = build_recommendation_drafts(
        progress_signals=[
            BookProgressSignal(
                progress_id=progress_id,
                book_id=book_id,
                book_title="AI 不是魔法",
                status="READING",
                position_percent=42,
                last_read_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
                completed_at=None,
            )
        ],
        quiz_answer_signals=[],
        completed_progress_signals=[],
        book_candidates=[],
    )

    assert [draft.recommendation_type for draft in drafts] == ["CONTINUE_READING"]
    assert drafts[0].related_book_id == book_id
    assert str(progress_id) in drafts[0].evidence_ids
    assert "42%" in drafts[0].reason


def test_continue_reading_rule_ignores_completed_or_unstarted_progress() -> None:
    drafts = build_recommendation_drafts(
        progress_signals=[
            BookProgressSignal(
                progress_id=uuid4(),
                book_id=uuid4(),
                book_title="已完成的书",
                status="COMPLETED",
                position_percent=100,
                last_read_at=None,
                completed_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
            ),
            BookProgressSignal(
                progress_id=uuid4(),
                book_id=uuid4(),
                book_title="还没开始的书",
                status="NOT_STARTED",
                position_percent=0,
                last_read_at=None,
                completed_at=None,
            ),
        ],
        quiz_answer_signals=[],
        completed_progress_signals=[],
        book_candidates=[],
    )

    assert drafts == []


def test_review_weak_rule_uses_recent_accuracy_and_answer_evidence() -> None:
    book_id = uuid4()
    answer_ids = [uuid4(), uuid4(), uuid4()]
    drafts = build_recommendation_drafts(
        progress_signals=[],
        quiz_answer_signals=[
            QuizAnswerSignal(answer_id=answer_ids[0], book_id=book_id, book_title="科学实验", is_correct=False),
            QuizAnswerSignal(answer_id=answer_ids[1], book_id=book_id, book_title="科学实验", is_correct=False),
            QuizAnswerSignal(answer_id=answer_ids[2], book_id=book_id, book_title="科学实验", is_correct=True),
        ],
        completed_progress_signals=[],
        book_candidates=[],
    )

    weak = next(draft for draft in drafts if draft.recommendation_type == "REVIEW_WEAK")
    assert weak.related_book_id == book_id
    assert set(weak.evidence_ids) == {str(answer_id) for answer_id in answer_ids}
    assert "33%" in weak.reason


def test_review_weak_rule_does_not_trigger_when_accuracy_is_at_least_sixty_percent() -> None:
    book_id = uuid4()
    drafts = build_recommendation_drafts(
        progress_signals=[],
        quiz_answer_signals=[
            QuizAnswerSignal(answer_id=uuid4(), book_id=book_id, book_title="数学基础", is_correct=True),
            QuizAnswerSignal(answer_id=uuid4(), book_id=book_id, book_title="数学基础", is_correct=True),
            QuizAnswerSignal(answer_id=uuid4(), book_id=book_id, book_title="数学基础", is_correct=False),
        ],
        completed_progress_signals=[],
        book_candidates=[],
    )

    assert all(draft.recommendation_type != "REVIEW_WEAK" for draft in drafts)


def test_read_next_rule_picks_an_unstarted_related_book_after_completion() -> None:
    completed_book_id = uuid4()
    next_book_id = uuid4()
    drafts = build_recommendation_drafts(
        progress_signals=[],
        quiz_answer_signals=[],
        completed_progress_signals=[
            BookProgressSignal(
                progress_id=uuid4(),
                book_id=completed_book_id,
                book_title="科学启蒙",
                status="COMPLETED",
                position_percent=100,
                last_read_at=None,
                completed_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
            )
        ],
        book_candidates=[
            BookCandidate(
                book_id=next_book_id,
                title="科学探索",
                description="从实验继续探索科学。",
                grade_min=7,
                grade_max=9,
                tags=("科学",),
                is_started=False,
            )
        ],
    )

    next_draft = next(draft for draft in drafts if draft.recommendation_type == "READ_NEXT")
    assert next_draft.related_book_id == next_book_id
    assert str(completed_book_id) in next_draft.evidence_ids
    assert "科学启蒙" in next_draft.reason


def test_read_next_rule_does_not_recommend_a_started_book() -> None:
    completed_book_id = uuid4()
    drafts = build_recommendation_drafts(
        progress_signals=[],
        quiz_answer_signals=[],
        completed_progress_signals=[
            BookProgressSignal(
                progress_id=uuid4(),
                book_id=completed_book_id,
                book_title="科学启蒙",
                status="COMPLETED",
                position_percent=100,
                last_read_at=None,
                completed_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
            )
        ],
        book_candidates=[
            BookCandidate(
                book_id=uuid4(),
                title="已开始的候选书",
                description="不应重复推荐。",
                grade_min=7,
                grade_max=9,
                tags=("科学",),
                is_started=True,
            )
        ],
    )

    assert all(draft.recommendation_type != "READ_NEXT" for draft in drafts)
