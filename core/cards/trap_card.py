from core.cards.card import Card
from typing import Any


class TrapCard(Card):
    def __init__(self,
                 name: str,
                 description: str,
                 owner_id: str,
                 ability: str,
                 value: int | None,
                 duration: int | None,
                 image_path: str | None = None,
                 **kwargs: Any
                 ):
        super().__init__(
            name=name,
            description=description,
            ctype="trap",
            ability=ability,
            owner_id=owner_id,
            is_placed=True,  # Traps are placed on field
            is_face_down=False,
            **kwargs
        )
        self.value = value
        self.duration = duration
        self.image_path = image_path
        self.is_trigger = False

    def __str__(self):
        return f"Trap: {self.name} - {self.description} (Ability: {self.ability})"

    # TODO: These should also be moved to rule manager instead
    # def can_trigger(self) -> bool:  # attacker, defender
        # """Check if this trap can be triggered by the given attack"""
        # if self.ability in ["debuff_enemy_atk", "debuff_enemy_def", "dodge_attack", "reflect_attack"]:
            # return True  # Triggered by any attack
        # elif self.ability == "debuff_summon":
            # return False  # Triggered by summon, not attack
        # return False

    # def reveal(self):
        # """Reveal the trap (flip face-up)"""
        # self.is_face_down = False
        # self.is_trigger = True
