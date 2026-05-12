from pydantic import Field
from core.cards.card import Card, CardType
from typing import Optional, List
from enum import Enum


class SpellAbility(Enum):
    BUFF_ATTACK = "BUFF_ATTACK"
    BUFF_DEFEND = "BUFF_DEFEND"
    DESTROY_TRAP = "DESTROY_TRAP"
    EXTRA_SUMMON = "EXTRA_SUMMON"
    DRAW_CARD = "DRAW_CARD"


class SpellCard(Card):
    card_type: CardType = Field(default=CardType.SPELL, frozen=True)

    ability: List[SpellAbility]

    effectiveness: Optional[List[int]] = None
    duration: Optional[List[int]] = None

    image_path: Optional[str] = None
