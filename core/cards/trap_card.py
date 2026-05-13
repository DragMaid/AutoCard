from core.cards.card import Card, CardType
from typing import Optional, List, Literal
from enum import Enum


class TrapAbility(str, Enum):
    REFLECT_ATTACK = "REFLECT_ATTACK"
    DODGE_ATTACK = "DODGE_ATTACK"
    DEBUFF_ATTACK = "DEBUFF_ATTACK"
    DEBUFF_DEFEND = "DEBUFF_DEFEND"


class ActivateCondition(str, Enum):
    TOGGLE = "TOGGLE"
    ATTACK = "ATTACK"
    SUMMON = "SUMMON"


class TrapCard(Card):
    card_type: Literal[CardType.TRAP] = CardType.TRAP

    abilities: List[TrapAbility]
    activation: ActivateCondition

    effectiveness: Optional[List[int]] = None
    duration: Optional[List[int]] = None

    is_triggered: bool = False
    triggerable: bool = False

    def reveal(self):
        self.is_face_down = False
        self.is_triggered = True
