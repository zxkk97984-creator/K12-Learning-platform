from app.modules.quiz.skill import QuizSkill
from app.skills.base import Skill


_SKILLS: dict[str, Skill] = {
    "quiz": QuizSkill(),
}


def get_skill(name: str) -> Skill:
    """Resolve a registered Skill by its stable domain name."""
    try:
        return _SKILLS[name]
    except KeyError as exc:
        raise ValueError(f"unsupported skill: {name}") from exc
