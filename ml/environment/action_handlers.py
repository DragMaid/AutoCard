import logging
from typing import Optional, Dict, Any

from core.data.player import Player
from core.cards.card import CardType

logger = logging.getLogger(__name__)


class ActionHandler:
    """Base class for action handlers.

    Subclasses must implement :meth:`perform` to execute the action.
    """

    def perform(env: Any, player: Player, params: Optional[Dict[str, Any]]) -> bool:
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

    def perform(env: Any, player: Player, params: Optional[Dict[str, Any]]) -> bool:
        """Activate a triggerable trap in a specific slot.

        Args:
            env: The game environment.
            player: The player performing the action.
            params: Parameters including 'card_id' or 'trap' slot index.

        Returns:
            bool: True if activation was successful, False otherwise.
        """
        if not params:
            return False

        card_id = params.get("card_id")
        if not card_id:
            slot_idx = params.get("trap")
            if slot_idx is None:
                return False
            card_id = env._get_card_id_at_slot(player.id, slot_idx)

        if not card_id:
            return False

        gs = env.engine.game_state
        if card_id in gs.triggerable_traps:
            # We use toggle_trap_activation to mark it for resolution
            env.engine.toggle_trap_activation(card_id, activated=True)
            logger.debug(
                "Trap activated",
                extra={"card_id": card_id}
            )
            return True

        return False


class SummonHandler(ActionHandler):
    """Handler for summoning monsters."""

    def perform(env: Any, player: Player, params: Optional[Dict[str, Any]]) -> bool:
        """Summon a monster from a hand slot.

        Args:
            env: The game environment.
            player: The player performing the action.
            params: Parameters including 'card_id' or 'monster' hand index.

        Returns:
            bool: True if summoning was successful, False otherwise.
        """
        if not params:
            return False

        gs = env.engine.game_state
        card_id = params.get("card_id")

        if not card_id:
            hand_idx = params.get("monster")
            player_hand_ids = gs.player_info[player.id].held_cards.card_ids
            if hand_idx is None or hand_idx >= len(player_hand_ids):
                return False
            card_id = player_hand_ids[hand_idx]

        card = gs.get_card_by_id(card_id)
        if not card or card.card_type != CardType.MONSTER:
            return False

        # Attempt to summon
        success = env.engine.summon_card(
            player.id, card.id, cell=None, check=False)

        if success:
            logger.debug(f"Summoned {card.name}")
        return success


class AttackHandler(ActionHandler):
    """Handler for attacking with monsters."""

    def perform(env: Any, player: Player, params: Optional[Dict[str, Any]]) -> bool:
        """Perform an attack from an attacker slot to a target slot.

        Args:
            env: The game environment.
            player: The player performing the action.
            params: Parameters including 'attacker_id', 'target_id', or slot indices.

        Returns:
            bool: True if attack was successful, False otherwise.
        """
        if not params:
            return False

        gs = env.engine.game_state
        attacker_id = params.get("attacker_id")
        target_id = params.get("target_id")
        target_is_player = params.get("target_is_player", False)

        if not attacker_id:
            attacker_slot = params.get("attacker", 0)
            attacker_id = env._get_card_id_at_slot(player.id, attacker_slot)

        attacker = gs.get_card_by_id(attacker_id)
        if not attacker or attacker.card_type != CardType.MONSTER:
            return False

        opp_id = gs.get_opponent_id(player.id)

        if not target_id:
            target_slot = params.get("target", 0)
            if target_slot == 10:
                target_id = opp_id
                target_is_player = True
            else:
                target_id = env._get_card_id_at_slot(opp_id, target_slot)

        if not target_id:
            return False

        # Attempt attack
        success = env.engine.attack(
            player.id, opp_id, attacker.id, target_id, target_is_player)

        if success:
            logger.debug(
                f"{attacker.name} attacked {target_id}")
        return success


class CastSpellHandler(ActionHandler):
    """Handler for casting spells."""

    def perform(env: Any, player: Player, params: Optional[Dict[str, Any]]) -> bool:
        """Cast a spell from a hand slot on a target slot.

        Args:
            env: The game environment.
            player: The player performing the action.
            params: Parameters including 'card_id' or 'spell' hand index.

        Returns:
            bool: True if spell cast was successful, False otherwise.
        """
        if not params:
            return False

        gs = env.engine.game_state
        card_id = params.get("card_id")
        target_id = params.get("target_id")

        if not card_id:
            hand_idx = params.get("spell", 0)
            player_hand_ids = gs.player_info[player.id].held_cards.card_ids
            if hand_idx >= len(player_hand_ids):
                return False
            card_id = player_hand_ids[hand_idx]

        spell_card = gs.get_card_by_id(card_id)
        if not spell_card or spell_card.card_type != CardType.SPELL:
            return False

        if not target_id and "target_id" not in params:  # target_id can be None for non-targeted spells
            target_val = params.get("target", 0)  # 0=None, 1-10=Own, 11-20=Opp
            if 1 <= target_val <= 10:
                target_id = env._get_card_id_at_slot(player.id, target_val - 1)
            elif 11 <= target_val <= 20:
                opp_id = gs.get_opponent_id(player.id)
                target_id = env._get_card_id_at_slot(opp_id, target_val - 11)

        # Attempt to cast spell
        success = env.engine.cast_spell(spell_card.id, target_id)

        if success:
            logger.debug(f"Cast {spell_card.name}")
        return success


class SetTrapHandler(ActionHandler):
    """Handler for setting traps."""

    def perform(env: Any, player: Player, params: Optional[Dict[str, Any]]) -> bool:
        """Set a trap from a hand slot.

        Args:
            env: The game environment.
            player: The player performing the action.
            params: Parameters including 'card_id' or 'trap' hand index.

        Returns:
            bool: True if trap set was successful, False otherwise.
        """
        if not params:
            return False

        gs = env.engine.game_state
        card_id = params.get("card_id")

        if not card_id:
            hand_idx = params.get("trap", 0)
            player_hand_ids = gs.player_info[player.id].held_cards.card_ids
            if hand_idx >= len(player_hand_ids):
                return False
            card_id = player_hand_ids[hand_idx]

        trap_card = gs.get_card_by_id(card_id)
        if not trap_card or trap_card.card_type != CardType.TRAP:
            return False

        # Attempt to set trap
        success = env.engine.set_trap(trap_card.id, position=None, check=False)

        if success:
            logger.debug(f"Set trap {trap_card.name}")
        return success


class ToggleHandler(ActionHandler):
    """Handler for toggling monster modes."""

    def perform(env: Any, player: Player, params: Optional[Dict[str, Any]]) -> bool:
        """Toggle a monster in a specific slot.

        Args:
            env: The game environment.
            player: The player performing the action.
            params: Parameters including 'card_id' or 'toggle' slot index.

        Returns:
            bool: True if toggle was successful, False otherwise.
        """
        if not params:
            return False

        gs = env.engine.game_state
        card_id = params.get("card_id")

        if not card_id:
            slot_idx = params.get("toggle", 0)
            card_id = env._get_card_id_at_slot(player.id, slot_idx)

        card = gs.get_card_by_id(card_id)
        if not card or card.card_type != CardType.MONSTER:
            return False

        old_mode = card.mode
        env.engine.toggle_card(card.id)
        success = card.mode != old_mode

        if success:
            logger.debug(f"Toggled {card.name} to {card.mode}")
            return True
        return False


class CombineHandler(ActionHandler):
    """Handler for combining monsters."""

    def perform(env: Any, player: Player, params: Optional[Dict[str, Any]]) -> bool:
        """Combine two monsters in specific slots.

        Args:
            env: The game environment.
            player: The player performing the action.
            params: Parameters including 'card1_id', 'card2_id', or 'pair' slot indices.

        Returns:
            bool: True if combination was successful, False otherwise.
        """
        if not params:
            return False

        card1_id = params.get("card1_id")
        card2_id = params.get("card2_id")

        if not card1_id or not card2_id:
            pair_slots = params.get("pair")
            if not pair_slots or len(pair_slots) != 2:
                return False
            card1_id = env._get_card_id_at_slot(player.id, pair_slots[0])
            card2_id = env._get_card_id_at_slot(player.id, pair_slots[1])

        if not card1_id or not card2_id:
            return False

        # Attempt to upgrade
        success = env.engine.upgrade_monster(player.id, card1_id, card2_id)

        if success:
            logger.debug(f"Combined {card1_id} and {card2_id}")
            return True
        return False


class EndTurnHandler(ActionHandler):
    """Handler for ending a player's turn."""

    def perform(env: Any, player: Player, params: Optional[Dict[str, Any]]) -> bool:
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
