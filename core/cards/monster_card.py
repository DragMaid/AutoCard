from core.cards.card import Card
from typing import Literal

cardMode = Literal["attack", "defense"]


class MonsterCard(Card):
    def __init__(self,
                 name: str,
                 description: str,
                 owner_id: str,
                 ability: str | None = None,
                 attack_points: int = 0,
                 defense_points: int = 0,
                 level_star: int = 1,
                 mode: cardMode = 'attack',
                 image_path: str | None = None,
                 has_attack: bool = False,
                 monster_type: str = "Unknown",
                 **kwargs,
                 ):
        super().__init__(
            name=name,
            description=description,
            ctype="monster",
            ability=ability,
            owner_id=owner_id,
            **kwargs
        )
        self.atk = attack_points
        self.defend = defense_points
        self.level_star = level_star
        self.mode = mode  # 'attack' or 'defense'
        self.image_path = image_path
        self.is_summoned = False
        self.is_alive = True
        self.has_attack = has_attack
        # TODO: should create an enum for this instead
        self.type = monster_type  # Monster type (Scholar, Conqueror, etc.)

    def __str__(self):
        return f"Name: {self.name} \
                OwnerID: {self.owner_id} \
                ATK: {self.atk} \
                DEF: {self.defend} \
                Star: {self.level_star}\
                Mode: {self.mode} \
                Type: {self.type}"

    # TODO: move to game engine
    # def switch_position(self):
        # """Change the card mode to either attack or defense."""
        # self.mode = 'defense' if self.mode == 'attack' else 'attack'
        # print(f"{self.name} switched to {self.mode} position.")
        # return self.mode
