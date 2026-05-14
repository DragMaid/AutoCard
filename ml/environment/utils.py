from typing import Any, Optional, Sequence
from core.cards.monster_card import MonsterCard
from core.cards.spell_card import SpellCard
from core.cards.trap_card import TrapCard


def safe_index(seq: Sequence[Any], idx: Optional[int]) -> Optional[Any]:
    """Safely retrieve an item from a sequence by index with bounds checking.

    Args:
        seq: The sequence to access.
        idx: The index of the item to retrieve.

    Returns:
        The item at the index, or None if the sequence is empty or index is invalid.
    """
    if not seq:
        return None
    if idx is None:
        idx = 0
    try:
        i = int(idx)
    except (TypeError, ValueError):
        i = 0
    i = max(0, min(i, len(seq) - 1))
    return seq[i]


def ability_to_float(card: Any) -> float:
    """Convert a card's ability to a normalized float representation.

    Args:
        card: The card object to analyze.

    Returns:
        A float between 0.0 and 1.0 representing the card's ability.
    """
    if hasattr(card, "ability") and card.ability is not None:
        return float(sum(ord(c) for c in str(card.ability)) % 1000) / 1000.0
    return 0.0


def card_type_to_int(card: Any) -> int:
    """Convert a card type to an integer identifier.

    Args:
        card: The card object to convert.

    Returns:
        An integer identifier (1: Monster, 2: Spell, 3: Trap, 0: Unknown).
    """
    if isinstance(card, MonsterCard):
        return 1
    if isinstance(card, SpellCard):
        return 2
    if isinstance(card, TrapCard):
        return 3
    return 0
