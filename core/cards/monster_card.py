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
    """Represents a monster card in the game.

    Attributes:
        card_type: Category of the card, fixed to MONSTER.
        monster_type: Type of the monster (e.g., SCHOLAR, CONQUEROR).
        attack: Monster attack power.
        defend: Monster defense power.
        star: Monster star rating (level).
        mode: Current field mode (ATTACK or DEFEND).
        has_attacked: Whether the monster has already attacked this turn.
        is_summoned: Whether the monster has been summoned.
        is_alive: Whether the monster is still in play.
    """
    card_type: Literal[CardType.MONSTER] = CardType.MONSTER

    monster_type: MonsterType

    attack: int = 0
    defend: int = 0
    star: int = 1

    mode: CardMode = CardMode.ATTACK

    has_attacked: bool = False
    is_summoned: bool = False
    is_alive: bool = True

    def switch_position(self) -> CardMode:
        """Switches the monster's current mode between ATTACK and DEFEND.

        Returns:
            The new CardMode after the switch.
        """
        self.mode = CardMode.DEFEND if self.mode is CardMode.ATTACK else CardMode.ATTACK
        return self.mode
