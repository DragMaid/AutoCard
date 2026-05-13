from pydantic import Field
from core.cards.card import Card, CardType
from typing import Optional, List
from enum import Enum


class TrapAbility(Enum):
    REFLECT_ATTACK = "REFLECT_ATTACK"
    DODGE_ATTACK = "DODGE_ATTACK"
    DEBUFF_ATTACK = "DEBUFF_ATTACK"
    DEBUFF_DEFEND = "DEBUFF_DEFEND"


class ActivateCondition(Enum):
    TOGGLE = "TOGGLE"
    ATTACK = "ATTACK"
    SUMMON = "SUMMON"


class TrapCard(Card):
    card_type: CardType = Field(default=CardType.TRAP, frozen=True)

    abilities: List[TrapAbility]
    activation: ActivateCondition

    effectiveness: Optional[List[int]] = None
    duration: Optional[List[int]] = None
    image_path: Optional[str] = None

    is_triggered: bool = False
    triggerable: bool = False
