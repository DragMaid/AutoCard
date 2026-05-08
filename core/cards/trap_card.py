from core.cards.card import Card
from typing import Any
from enum import Enum


class ActivateCondition(Enum):
    TOGGLE = "TOGGLE"
    ATTACK = "ATTACK"
    SUMMON = "SUMMON"


class TrapCard(Card):
    def __init__(self,
                 name: str,
                 description: str,
                 owner_id: str,
                 ability: str,
                 value: int | None,
                 duration: int | None,
                 image_path: str | None = None,
                 is_trigger: bool = False,
                 triggerable: bool = False,
                 **kwargs: Any
                 ):
        params = {
            "name": name,
            "description": description,
            "ctype": "trap",
            "ability": ability,
            "owner_id": owner_id,
            "is_placed": True,  # Traps are placed on field
            "is_face_down": True,
        }
        params.update(kwargs)
        super().__init__(**params)
        self.value = value
        self.duration = duration
        self.image_path = str(image_path)
        self.is_trigger = is_trigger
        self.triggerable = triggerable

    def __str__(self):
        return f"Trap: {self.name} - {self.description} (Ability: {self.ability})"

    def reveal(self):
        """Reveal the trap (flip face-up)"""
        self.is_face_down = False
        self.is_trigger = True
