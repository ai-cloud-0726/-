from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .constants import MAX_SKILL_SLOTS
from .skills import SkillDefinition


@dataclass
class PlayerState:
    name: str
    color: str
    score: int = 0
    skills: List[Optional[SkillDefinition]] = field(
        default_factory=lambda: [None] * MAX_SKILL_SLOTS
    )
    turns_without_skill: int = 0

    def add_skill(self, skill: SkillDefinition) -> bool:
        for index, slot in enumerate(self.skills):
            if slot is None:
                self.skills[index] = skill
                self.turns_without_skill = 0
                return True
        return False

    def consume_skill(self, slot_index: int) -> SkillDefinition:
        if not 0 <= slot_index < len(self.skills):
            raise IndexError("Invalid skill slot")
        skill = self.skills[slot_index]
        if skill is None:
            raise ValueError("Skill slot is empty")
        self.skills[slot_index] = None
        return skill

    def discard_skill(self, slot_index: int) -> SkillDefinition:
        skill = self.consume_skill(slot_index)
        return skill

    def has_shield(self) -> bool:
        return any(skill and skill.id == "shield" for skill in self.skills)

    def remove_shield(self) -> None:
        for index, skill in enumerate(self.skills):
            if skill and skill.id == "shield":
                self.skills[index] = None
                return

    def available_skill_slots(self) -> int:
        return sum(1 for slot in self.skills if slot is None)
