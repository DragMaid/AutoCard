from core.cards.card import Card
from typing import Literal
import logging

cardMode = Literal["attack", "defense"]


class MonsterCard(Card):
    def __init__(self,
                 name: str,
                 description: str,
                 owner_id: str,
                 ability: str | None = None,
                 atk: int = 0,
                 defend: int = 0,
                 level_star: int = 1,
                 mode: cardMode = 'attack',
                 image_path: str | None = None,
                 has_attack: bool = False,
                 type: str = "Unknown",
                 is_summoned: bool = False,
                 is_alive: bool = True,
                 **kwargs,
                 ):
        params = {
            "name": name,
            "description": description,
            "ctype": "monster",
            "ability": ability,
            "owner_id": owner_id,
        }
        params.update(kwargs)
        super().__init__(**params)
        self.atk = atk
        self.defend = defend
        self.level_star = level_star
        self.mode = mode  # 'attack' or 'defense'
        self.image_path = str(image_path)
        self.is_summoned = is_summoned
        self.is_alive = is_alive
        self.has_attack = has_attack
        # TODO: should create an enum for this instead
        self.type = type  # Monster type (Scholar, Conqueror, etc.)

    def __str__(self):
        return f"Name: {self.name} \
                OwnerID: {self.owner_id} \
                ATK: {self.atk} \
                DEF: {self.defend} \
                Star: {self.level_star}\
                Mode: {self.mode} \
                Type: {self.type}"

    def switch_position(self):
        """Change the card mode to either attack or defense."""
        self.mode = "defense" if self.mode == "attack" else "attack"
        logging.getLogger("GameEngine").info(f"{self.name} switched to {self.mode} position.")
        return self.mode
