"""Quiz Skill contract tests (pure, deterministic, no database)."""

from app.modules.quiz.quiz_bank import QUIZ_BANK
from app.modules.quiz.skill import QuizSkill
from app.skills.registry import get_skill


def test_quiz_skill_is_registered_with_a_stable_version() -> None:
    skill = get_skill("quiz")

    assert isinstance(skill, QuizSkill)
    assert skill.skill_version == "quiz-v1"
    assert skill.name == "quiz"


def test_quiz_skill_grades_authoritatively_and_returns_layered_hints() -> None:
    skill = get_skill("quiz")
    question = QUIZ_BANK[0]

    assert skill.grade(question, question.correct_answer) is True
    assert skill.grade(question, {"key": "A"}) is False
    assert skill.hint(question, 1) == question.hints[0]
    assert skill.hint(question, 3) == question.hints[2]
