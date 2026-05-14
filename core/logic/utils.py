import logging
from typing import TYPE_CHECKING
from core.cards.card import CardType

if TYPE_CHECKING:
    from core.logic.game_engine import GameEngine
    from core.logic.turn_manager import TurnManager
    from core.data.player import Player

logger = logging.getLogger(__name__)


def draw_specific_card(engine: "GameEngine", player_id: str, name: str, card_type: CardType) -> None:
    """
    Draw a specific card required for debugging.

    Args:
        engine (GameEngine): The game engine instance.
        player_id (str): ID of the player receiving the card.
        name (str): Name of the card to draw.
        card_type (CardType): Type of the card.
    """
    factory_map = {
        CardType.MONSTER: engine.draw_system.monster_factory,
        CardType.TRAP: engine.draw_system.trap_factory,
        CardType.SPELL: engine.draw_system.spell_factory
    }
    card = factory_map[card_type].load(player_id, name)
    engine.game_state.entity_lookup[card.id] = card
    engine.game_state.player_info[player_id].held_cards.add(card.id)
    logger.debug(f"{player_id} received specific card: {name}")


def log_action(action_type: str, player_id: str, details: dict, success: bool) -> None:
    """
    Central logging method for all game actions.

    Args:
        action_type (str): Type of action being logged.
        player_id (str): ID of the player performing the action.
        details (dict): Additional information about the action.
        success (bool): Whether the action was successful.
    """
    log = logger.debug if success else logger.error

    payload = {
        "event": action_type,
        "player_id": player_id,
        "success": success,
        **details,
    }

    log(payload)


def is_local_turn(turn_manager: "TurnManager", players: list["Player"]) -> bool:
    """
    Return a boolean indicating whether it is the local player's turn.

    Args:
        turn_manager (TurnManager): The turn manager instance.
        players (list[Player]): List of players in the game.

    Returns:
        bool: True if it is the local player's turn, False otherwise.
    """
    trapper = turn_manager.get_trapper()
    current = turn_manager.get_current_player()
    local = next((p for p in players if not p.is_opponent), None)

    if local is None:
        return False

    if trapper:
        return trapper.id == local.id

    return current.id == local.id
