from core.cards.monster_card import MonsterCard
from core.cards.spell_card import SpellCard
from core.cards.trap_card import TrapCard
from typing import Optional, Sequence, Any


def safe_index(seq: Sequence[Any], idx: Optional[int]) -> Optional[Any]:
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
    if hasattr(card, "ability") and card.ability is not None:
        return float(sum(ord(c) for c in str(card.ability)) % 1000) / 1000.0
    return 0.0


def card_type_to_int(card: Any) -> int:
    if isinstance(card, MonsterCard):
        return 1
    if isinstance(card, SpellCard):
        return 2
    if isinstance(card, TrapCard):
        return 3
    return 0
