import logging
from core.cards.card import CardType

logger = logging.getLogger(__name__)


def draw_specific_card(engine, player_id: str, name: str, card_type: CardType):
    """Draw a specific card required for debugging."""
    factory_map = {
        CardType.MONSTER: engine.draw_system.monster_factory,
        CardType.TRAP: engine.draw_system.trap_factory,
        CardType.SPELL: engine.draw_system.spell_factory
    }
    card = factory_map[card_type].load(player_id, name)
    engine.game_state.entity_lookup[card.id] = card
    engine.game_state.player_info[player_id].held_cards.add(card.id)
    logger.debug(f"{player_id} received specific card: {name}")


def log_action(action_type: str, player_id: str, details: dict, success: bool):
    """Central logging method for all game actions"""
    log = logger.debug if success else logger.error

    payload = {
        "event": action_type,
        "player_id": player_id,
        "success": success,
        **details,
    }

    log(payload)


# TODO: should I move this elsewhere
def is_local_turn(turn_manager, players) -> bool:
    """Return a boolean indicating whether it is the player turn."""
    trapper = turn_manager.get_trapper()
    current = turn_manager.get_current_player()
    for p in players:
        if not p.is_opponent:
            local = p
            break

    if trapper:
        return trapper.id == local.id

    return current.id == local.id
