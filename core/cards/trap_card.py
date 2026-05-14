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
    """Represents a trap card in the game.

    Attributes:
        card_type: Category of the card, fixed to TRAP.
        abilities: List of abilities triggered by the trap.
        activation: Condition that triggers the trap.
        effectiveness: Optional list of effectiveness values for abilities.
        duration: Optional list of durations for abilities.
        is_triggered: Whether the trap has been activated.
        triggerable: Whether the trap is currently in a state to be triggered.
    """
    card_type: Literal[CardType.TRAP] = CardType.TRAP

    abilities: List[TrapAbility]
    activation: ActivateCondition

    effectiveness: Optional[List[int]] = None
    duration: Optional[List[int]] = None

    is_triggered: bool = False
    triggerable: bool = False

    def reveal(self) -> None:
        """Reveals the trap and marks it as triggered."""
        self.is_face_down = False
        self.is_triggered = True
