from core.data.player import Player
from typing import Optional, Dict
from core.utils import get_logger


class ActionHandler:
    """Base class for action handlers.

    Subclasses must implement :meth:`perform` to execute the action.
    Returns True if action was successful, False otherwise.
    """

    def __init__(self):
        self.logger = get_logger()

    def perform(self, env, player: Player, params: Optional[Dict]) -> bool:
        """Perform the action. Return True if successful."""
        return True


class ActivateHandler(ActionHandler):
    def perform(self, env, player: Player, params: Optional[Dict]) -> bool:
        """Activate a triggerable trap in a specific slot."""
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
            self.logger.debug(
                "Trap activated",
                extra={"card_id": card_id}
            )
            return True

        return False


class SummonHandler(ActionHandler):
    def perform(self, env, player: Player, params: Optional[Dict]) -> bool:
        """Summon a monster from a hand slot."""
        if not params:
            return False

        gs = env.engine.game_state
        card_id = params.get("card_id")

        if not card_id:
            hand_idx = params.get("monster")
            player_hand_ids = gs.player_info[player.id]["held_cards"].cards
            if hand_idx >= len(player_hand_ids):
                return False
            card_id = player_hand_ids[hand_idx]

        card = gs.get_card_by_id(card_id)
        if not card or card.ctype != "monster":
            return False

        # Attempt to summon
        success = env.engine.summon_card(
            player.id, card.id, cell=None, check=False)

        if success:
            self.logger.debug(f"[HANDLER] ✓ Summoned {card.name}")
        return success


class AttackHandler(ActionHandler):
    def perform(self, env, player: Player, params: Optional[Dict]) -> bool:
        """Perform an attack from an attacker slot to a target slot."""
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
        if not attacker or attacker.ctype != "monster":
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
            self.logger.debug(
                f"[HANDLER] ✓ {attacker.name} attacked {target_id}")
        return success


class CastSpellHandler(ActionHandler):
    def perform(self, env, player: Player, params: Optional[Dict]) -> bool:
        """Cast a spell from a hand slot on a target slot."""
        if not params:
            return False

        gs = env.engine.game_state
        card_id = params.get("card_id")
        target_id = params.get("target_id")

        if not card_id:
            hand_idx = params.get("spell", 0)
            player_hand_ids = gs.player_info[player.id]["held_cards"].cards
            if hand_idx >= len(player_hand_ids):
                return False
            card_id = player_hand_ids[hand_idx]

        spell_card = gs.get_card_by_id(card_id)
        if not spell_card or spell_card.ctype != "spell":
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
            self.logger.debug(f"[HANDLER] ✓ Cast {spell_card.name}")
        return success


class SetTrapHandler(ActionHandler):
    def perform(self, env, player: Player, params: Optional[Dict]) -> bool:
        """Set a trap from a hand slot."""
        if not params:
            return False

        gs = env.engine.game_state
        card_id = params.get("card_id")

        if not card_id:
            hand_idx = params.get("trap", 0)
            player_hand_ids = gs.player_info[player.id]["held_cards"].cards
            if hand_idx >= len(player_hand_ids):
                return False
            card_id = player_hand_ids[hand_idx]

        trap_card = gs.get_card_by_id(card_id)
        if not trap_card or trap_card.ctype != "trap":
            return False

        # Attempt to set trap
        success = env.engine.set_trap(trap_card.id, position=None, check=False)

        if success:
            self.logger.debug(f"[HANDLER] ✓ Set trap {trap_card.name}")
        return success


class ToggleHandler(ActionHandler):
    def perform(self, env, player: Player, params: Optional[Dict]) -> bool:
        """Toggle a monster in a specific slot."""
        if not params:
            return False

        gs = env.engine.game_state
        card_id = params.get("card_id")

        if not card_id:
            slot_idx = params.get("toggle", 0)
            card_id = env._get_card_id_at_slot(player.id, slot_idx)

        card = gs.get_card_by_id(card_id)
        if not card or card.ctype != "monster":
            return False

        old_mode = card.mode
        env.engine.toggle_card(card.id)
        success = card.mode != old_mode

        if success:
            self.logger.debug(f"[HANDLER] ✓ Toggled {
                              card.name} to {card.mode}")
        return success


class CombineHandler(ActionHandler):
    def perform(self, env, player: Player, params: Optional[Dict]) -> bool:
        """Combine two monsters in specific slots."""
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
            self.logger.debug(f"[HANDLER] ✓ Combined {
                              card1_id} and {card2_id}")
        return success


class EndTurnHandler(ActionHandler):
    def perform(self, env, player: Player, params: Optional[Dict]) -> bool:
        """End the current player's turn."""
        env.engine.end_turn()
        self.logger.debug(f"[HANDLER] ✓ {player.name} ends turn")
        return True
