from core.cards.card import Card
from typing import Any


class SpellCard(Card):
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
        params = {
            "name": name,
            "description": description,
            "ctype": "spell",
            "ability": ability,
            "owner_id": owner_id,
            "is_placed": False,  # Spells are not placed on field
        }
        params.update(kwargs)
        super().__init__(**params)
        self.value = value
        self.duration = duration
        self.image_path = str(image_path)

    def __str__(self):
        return f"Spell: {self.name} - {self.description} (Ability: {self.ability})"

    def can_target(self, target) -> bool:
        """Check if this spell can target the given target"""
        if self.ability in ["draw_two_cards"]:
            return True  # No target needed
        elif self.ability == "summon_monster_from_hand":
            return True  # No target
        elif self.ability in ["buff_attack", "buff_defense"]:
            return target is not None and target.ctype == "monster"
        elif self.ability == "destroy_trap":
            return target is not None and target.ctype == "trap"
        return False
