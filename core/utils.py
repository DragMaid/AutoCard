import random
from typing import List, Optional
from core.data.game_state import GameState, LogicCard
from core.cards.card import CardType
from core.cards.monster_card import MonsterType, MonsterCard
from core.factory.monster_factory import MonsterFactory


def load_by_type_and_level(
    factory: MonsterFactory,
    player_id: str,
    monster_type: MonsterType,
    star: int
) -> Optional[MonsterCard]:
    """Specific loader for monsters filtering by type and level.

    Args:
        factory: The monster factory to use.
        player_id: The ID of the owner player.
        monster_type: The type of monster to filter by.
        star: The star level of the monster to filter by.

    Returns:
        A loaded MonsterCard instance, or None if not found.
    """
    candidates = [
        name for name, info in factory.get_cards().items()
        if info.get("monster_type") == monster_type
        and info.get("star") == star
    ]

    if not candidates:
        return None

    selected_name = random.choice(candidates)
    return factory.load(player_id, name=selected_name)


def get_cards_typed(
    game_state: GameState,
    player_id: str,
    card_type: CardType
) -> List[LogicCard]:
    """Get list of field cards that belong in same card_type."""
    cards = game_state.get_player_field_cards(player_id)
    return [c for c in cards if c.card_type == card_type]
