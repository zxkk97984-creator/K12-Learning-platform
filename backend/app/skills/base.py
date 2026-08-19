from typing import Protocol


class Skill(Protocol):
    """Minimal stable metadata contract shared by domain Skills."""

    name: str
    skill_version: str
