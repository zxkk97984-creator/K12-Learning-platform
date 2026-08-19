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


def test_quiz_skill_parses_llm_json_with_markdown_fence() -> None:
    skill = get_skill("quiz")
    payload = (
        "```json\n"
        '[{"question_type":"SINGLE_CHOICE","stem":"测试题",'
        '"options":[{"key":"A","text":"正确"},{"key":"B","text":"错误"}],'
        '"correct_answer":{"key":"A"},"explanation":"因为",'
        '"knowledge_point_ids":["kp_001"]}]\n'
        "```"
    )

    items = skill._parse_llm_questions(payload)

    assert items is not None
    assert len(items) == 1
    assert items[0]["stem"] == "测试题"


def test_quiz_skill_rejects_malformed_llm_json() -> None:
    skill = get_skill("quiz")

    assert skill._parse_llm_questions("抱歉，我不能生成题目。") is None
    assert skill._parse_llm_questions("[{}]") is None
