from __future__ import annotations

import logging
from typing import Optional, Dict, Any, TYPE_CHECKING
from core.data.player import Player
from core.data.game_state import AttackEntry

if TYPE_CHECKING:
    from ml.environment.environment import GameEnv

logger = logging.getLogger(__name__)


class ActionHandler:
    """Base class for action handlers.

    Subclasses must implement :meth:`perform` to execute the action.
    """

    def perform(env: GameEnv, player: Player, params: Optional[Dict[str, Any]]) -> bool:
        """Perform the action.

        Args:
            env: The game environment.
            player: The player performing the action.
            params: Optional dictionary of action parameters.

        Returns:
            bool: True if the action was successful, False otherwise.
        """
        return True


class ActivateHandler(ActionHandler):
    """Handler for activating triggerable traps."""

    def perform(env: GameEnv, player: Player, params: Optional[Dict[str, Any]]) -> bool:
        """Activate a triggerable trap in a specific slot.

        Args:
            env: The game environment.
            player: The player performing the action.
            params: Parameters including 'card_id' or 'trap' slot index.

        Returns:
            bool: True if activation was successful, False otherwise.
        """
        gs = env.engine.game_state
        card_id = params["card_id"]
        trap = gs.get_card_by_id(card_id)
        env.engine.toggle_trap_activation(card_id, activated=True)
        logger.debug(f"Trap activated {trap.name}")
        return True


class SummonHandler(ActionHandler):
    """Handler for summoning monsters."""

    def perform(env: GameEnv, player: Player, params: Optional[Dict[str, Any]]) -> bool:
        """Summon a monster from a hand slot.

        Args:
            env: The game environment.
            player: The player performing the action.
            params: Parameters including 'card_id' or 'monster' hand index.

        Returns:
            bool: True if summoning was successful, False otherwise.
        """
        gs = env.engine.game_state
        card_id = params["card_id"]
        card = gs.get_card_by_id(card_id)
        success = env.engine.summon_card(
            player.id, card.id, cell=None, check=False)
        if success:
            logger.debug(f"Summoned {card.name}")
        return success


class AttackHandler(ActionHandler):
    """Handler for attacking with monsters."""

    def perform(env: GameEnv, player: Player, params: Optional[Dict[str, Any]]) -> bool:
        """Perform an attack from an attacker slot to a target slot.

        Args:
            env: The game environment.
            player: The player performing the action.
            params: Parameters including 'attacker_id', 'target_id', or slot indices.

        Returns:
            bool: True if attack was successful, False otherwise.
        """
        gs = env.engine.game_state
        attacker_id = params["attacker_id"]
        target_id = params["target_id"]
        target_is_player = params["target_is_player"]
        attacker = gs.get_card_by_id(attacker_id)
        opp_id = gs.get_opponent_id(player.id)
        attack = AttackEntry(
            attacker_id=player.id,
            defender_id=opp_id,
            card_id=attacker.id,
            target_id=target_id,
            target_is_player=target_is_player
        )
        success = env.engine.attack(attack)

        if success:
            logger.debug(
                f"{attacker.name} attacked {target_id}")
        return success


class CastSpellHandler(ActionHandler):
    """Handler for casting spells."""

    def perform(env: GameEnv, player: Player, params: Optional[Dict[str, Any]]) -> bool:
        """Cast a spell from a hand slot on a target slot.

        Args:
            env: The game environment.
            player: The player performing the action.
            params: Parameters including 'card_id' or 'spell' hand index.

        Returns:
            bool: True if spell cast was successful, False otherwise.
        """
        gs = env.engine.game_state
        card_id = params["card_id"]
        target_id = params["target_id"]
        spell_card = gs.get_card_by_id(card_id)
        success = env.engine.cast_spell(spell_card.id, target_id)

        if success:
            logger.debug(f"Cast {spell_card.name}")
        return success


class SetTrapHandler(ActionHandler):
    """Handler for setting traps."""

    def perform(env: GameEnv, player: Player, params: Optional[Dict[str, Any]]) -> bool:
        """Set a trap from a hand slot.

        Args:
            env: The game environment.
            player: The player performing the action.
            params: Parameters including 'card_id' or 'trap' hand index.

        Returns:
            bool: True if trap set was successful, False otherwise.
        """
        gs = env.engine.game_state
        card_id = params["card_id"]
        trap_card = gs.get_card_by_id(card_id)
        success = env.engine.set_trap(trap_card.id, position=None, check=False)
        if success:
            logger.debug(f"Set trap {trap_card.name}")
        return success


class ToggleHandler(ActionHandler):
    """Handler for toggling monster modes."""

    def perform(env: GameEnv, player: Player, params: Optional[Dict[str, Any]]) -> bool:
        """Toggle a monster in a specific slot.

        Args:
            env: The game environment.
            player: The player performing the action.
            params: Parameters including 'card_id' or 'toggle' slot index.

        Returns:
            bool: True if toggle was successful, False otherwise.
        """
        gs = env.engine.game_state
        card_id = params["card_id"]
        card = gs.get_card_by_id(card_id)
        old_mode = card.mode
        env.engine.toggle_card(card.id)
        success = card.mode != old_mode
        if success:
            logger.debug(f"Toggled {card.name} to {card.mode}")
            return True
        return False


class CombineHandler(ActionHandler):
    """Handler for combining monsters."""

    def perform(env: GameEnv, player: Player, params: Optional[Dict[str, Any]]) -> bool:
        """Combine two monsters in specific slots.

        Args:
            env: The game environment.
            player: The player performing the action.
            params: Parameters including 'card1_id', 'card2_id', or 'pair' slot indices.

        Returns:
            bool: True if combination was successful, False otherwise.
        """
        card1_id = params["card1_id"]
        card2_id = params["card2_id"]
        success = env.engine.upgrade_monster(player.id, card1_id, card2_id)
        if success:
            logger.debug(f"Combined {card1_id} and {card2_id}")
            return True
        return False


class EndTurnHandler(ActionHandler):
    """Handler for ending a player's turn."""

    def perform(env: GameEnv, player: Player, params: Optional[Dict[str, Any]]) -> bool:
        """End the current player's turn.

        Args:
            env: The game environment.
            player: The player performing the action.
            params: Unused.

        Returns:
            bool: Always True.
        """
        env.engine.end_turn()
        logger.debug(f"{player.name} ends turn")
        return True
