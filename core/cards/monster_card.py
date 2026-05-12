from core.cards.card import Card, CardType
from typing import Optional
from enum import Enum
from pydantic import Field


class MonsterType(Enum):
    SCHOLAR = "SCHOLAR"
    CONQUEROR = "CONQUEROR"
    FOREST_MONSTER = "FOREST_MONSTER"
    DEMON = "DEMON"
    FOREST_GUARD = "FOREST_GUARD"


class CardMode(Enum):
    ATTACK = "ATTACK"
    DEFEND = "DEFEND"


class MonsterCard(Card):
    card_type: CardType = Field(default=CardType.MONSTER, frozen=True)

    monster_type: MonsterType

    attack: int = 0
    defend: int = 0
    star: int = 1

    mode: CardMode = CardMode.ATTACK

    image_path: Optional[str] = None

    has_attack: bool = False
    is_summoned: bool = False
    is_alive: bool = True
