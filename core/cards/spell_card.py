from core.cards.card import Card, CardType
from typing import Optional, List, Literal
from enum import Enum


class SpellAbility(str, Enum):
    BUFF_ATTACK = "BUFF_ATTACK"
    BUFF_DEFEND = "BUFF_DEFEND"
    DESTROY_TRAP = "DESTROY_TRAP"
    EXTRA_SUMMON = "EXTRA_SUMMON"
    DRAW_CARD = "DRAW_CARD"


class SpellCard(Card):
    """Represents a spell card in the game.

    Attributes:
        card_type: Category of the card, fixed to SPELL.
        abilities: List of abilities provided by the spell.
        effectiveness: Optional list of effectiveness values for abilities.
        duration: Optional list of durations for abilities.
    """
    card_type: Literal[CardType.SPELL] = CardType.SPELL

    abilities: List[SpellAbility]

    effectiveness: Optional[List[int]] = None
    duration: Optional[List[int]] = None
