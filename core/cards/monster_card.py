from core.cards.card import Card, CardType
from enum import Enum
from typing import Literal


class MonsterType(str, Enum):
    SCHOLAR = "SCHOLAR"
    CONQUEROR = "CONQUEROR"
    FOREST_MONSTER = "FOREST_MONSTER"
    DEMON = "DEMON"
    FOREST_GUARD = "FOREST_GUARD"


class CardMode(str, Enum):
    ATTACK = "ATTACK"
    DEFEND = "DEFEND"


class MonsterCard(Card):
    card_type: Literal[CardType.MONSTER] = CardType.MONSTER

    monster_type: MonsterType

    attack: int = 0
    defend: int = 0
    star: int = 1

    mode: CardMode = CardMode.ATTACK

    has_attacked: bool = False
    is_summoned: bool = False
    is_alive: bool = True

    def switch_position(self):
        self.mode = CardMode.DEFEND if self.mode is CardMode.ATTACK else CardMode.ATTACK
        return self.mode
