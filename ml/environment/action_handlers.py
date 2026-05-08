from .utils import safe_index
from core.player import Player
from typing import Optional, Dict
import logging


class ActionHandler:
    """Base class for action handlers.

    Subclasses must implement :meth:`perform` to execute the action.
    Returns True if action was successful, False otherwise.
    """

    def __init__(self):
        self.logger = logging.getLogger("GameEngine")

    def perform(self, env, player: Player, params: Optional[Dict]) -> bool:
        """Perform the action. Return True if successful."""
        return True


class SummonHandler(ActionHandler):
    def perform(self, env, player: Player, params: Optional[Dict]) -> bool:
        """Summon a monster from hand to field."""
        if not params:
            self.logger.debug("[HANDLER] Summon failed: No parameters")
            return False

        gs = env.engine.game_state
        player_hand_ids = gs.player_info[player.id]["held_cards"].cards
        monsters = [gs.get_card_by_id(cid) for cid in player_hand_ids if gs.get_card_by_id(cid).ctype == "monster"]

        if not monsters:
            self.logger.debug("[HANDLER] Summon failed: No monsters in hand")
            return False

        idx = params.get("monster", 0)
        card = safe_index(monsters, idx)

        if not card:
            self.logger.debug(
                f"[HANDLER] Summon failed: Invalid monster index {idx}")
            return False

        # Attempt to summon
        success = env.engine.summon_card(player.id, card.id, cell=None, check=False)

        if success:
            self.logger.debug(f"[HANDLER] ✓ Summoned {card.name}")
        else:
            self.logger.debug(f"[HANDLER] ✗ Failed to summon {card.name}")

        return success


class AttackHandler(ActionHandler):
    def perform(self, env, player: Player, params: Optional[Dict]) -> bool:
        """Perform an attack with a monster."""
        if not params:
            self.logger.debug("[HANDLER] Attack failed: No parameters")
            return False

        gs = env.engine.game_state
        opp_id = gs.get_opponent_id(player.id)

        # Get available attackers
        my_monsters = [
            c for c in gs.get_player_cards(player.id)
            if c.ctype == "monster" and c.mode == "attack" and not c.has_attack
        ]

        if not my_monsters:
            self.logger.debug(
                "[HANDLER] Attack failed: No available attackers")
            return False

        attacker_idx = params.get("attacker", 0)
        attacker = safe_index(my_monsters, attacker_idx)

        if not attacker:
            self.logger.debug(
                f"[HANDLER] Attack failed: Invalid attacker index {attacker_idx}")
            return False

        # Get available targets
        opp_monsters = gs.get_cards_typed(opp_id, "monster")
        target_idx = params.get("target", 0)

        target_id = None
        target_is_player = False

        if opp_monsters:
            target = safe_index(opp_monsters, target_idx)
            if target:
                target_id = target.id
        else:
            # Direct attack on player
            target_id = opp_id
            target_is_player = True

        if not target_id:
            self.logger.debug("[HANDLER] Attack failed: Invalid target")
            return False

        # Attempt attack
        success = env.engine.attack(player.id, opp_id, attacker.id, target_id, target_is_player)

        if success:
            self.logger.debug(
                f"[HANDLER] ✓ {attacker.name} attacked {target_id}")
        else:
            self.logger.debug("[HANDLER] ✗ Attack failed")

        return success


class CastSpellHandler(ActionHandler):
    def perform(self, env, player: Player, params: Optional[Dict]) -> bool:
        """Cast a spell card."""
        if not params:
            self.logger.debug("[HANDLER] Cast spell failed: No parameters")
            return False

        gs = env.engine.game_state
        player_hand_ids = gs.player_info[player.id]["held_cards"].cards
        spells = [gs.get_card_by_id(cid) for cid in player_hand_ids if gs.get_card_by_id(cid).ctype == "spell"]

        if not spells:
            self.logger.debug(
                "[HANDLER] Cast spell failed: No spells in hand")
            return False

        spell_idx = params.get("spell", 0)
        spell_card = safe_index(spells, spell_idx)

        if not spell_card:
            self.logger.debug(
                f"[HANDLER] Cast spell failed: Invalid spell index {spell_idx}")
            return False

        opp_id = gs.get_opponent_id(player.id)
        target_id = None

        # Determine valid targets based on spell ability
        if spell_card.ability in ("buff_attack", "buff_defense"):
            targets = gs.get_cards_typed(player.id, "monster")
            if targets:
                target_idx = params.get("target", 0)
                target = safe_index(targets, target_idx)
                if target:
                    target_id = target.id

        elif spell_card.ability == "destroy_trap":
            targets = gs.get_cards_typed(opp_id, "trap")
            if targets:
                target_idx = params.get("target", 0)
                target = safe_index(targets, target_idx)
                if target:
                    target_id = target.id

        elif spell_card.ability == "draw_two_cards":
            # No target needed
            pass

        elif spell_card.ability == "summon_monster_from_hand":
            # No target needed
            pass

        # Attempt to cast spell
        success = env.engine.cast_spell(spell_card.id, target_id)

        if success:
            self.logger.debug(f"[HANDLER] ✓ Cast {spell_card.name}")
        else:
            self.logger.debug(f"[HANDLER] ✗ Failed to cast {spell_card.name}")

        return success


class SetTrapHandler(ActionHandler):
    def perform(self, env, player: Player, params: Optional[Dict]) -> bool:
        """Set a trap card face-down."""
        if not params:
            self.logger.debug("[HANDLER] Set trap failed: No parameters")
            return False

        gs = env.engine.game_state
        player_hand_ids = gs.player_info[player.id]["held_cards"].cards
        traps = [gs.get_card_by_id(cid) for cid in player_hand_ids if gs.get_card_by_id(cid).ctype == "trap"]

        if not traps:
            self.logger.debug("[HANDLER] Set trap failed: No traps in hand")
            return False

        trap_idx = params.get("trap", 0)
        trap_card = safe_index(traps, trap_idx)

        if not trap_card:
            self.logger.debug(
                f"[HANDLER] Set trap failed: Invalid trap index {trap_idx}")
            return False

        # Attempt to set trap
        success = env.engine.set_trap(trap_card.id, position=None, check=False)

        if success:
            self.logger.debug(f"[HANDLER] ✓ Set trap {trap_card.name}")
        else:
            self.logger.debug(
                f"[HANDLER] ✗ Failed to set trap {trap_card.name}")

        return success


class ToggleHandler(ActionHandler):
    def perform(self, env, player: Player, params: Optional[Dict]) -> bool:
        """Toggle a monster's position (attack/defense)."""
        if not params:
            self.logger.debug("[HANDLER] Toggle failed: No parameters")
            return False

        gs = env.engine.game_state
        my_monsters = gs.get_cards_typed(player.id, "monster")

        if not my_monsters:
            self.logger.debug("[HANDLER] Toggle failed: No monsters on field")
            return False

        toggle_idx = params.get("toggle", 0)
        card = safe_index(my_monsters, toggle_idx)

        if not card:
            self.logger.debug(
                f"[HANDLER] Toggle failed: Invalid monster index {toggle_idx}")
            return False

        # Store old mode for logging
        old_mode = card.mode

        # Attempt to toggle
        env.engine.toggle_card(card.id)

        # Check if toggle was successful
        success = card.mode != old_mode

        if success:
            self.logger.debug(f"[HANDLER] ✓ Toggled {card.name} from {
                              old_mode} to {card.mode}")
        else:
            self.logger.debug(f"[HANDLER] ✗ Failed to toggle {card.name}")

        return success


class CombineHandler(ActionHandler):
    def perform(self, env, player: Player, params: Optional[Dict]) -> bool:
        """Combine two monsters to create a higher-level monster."""
        if not params:
            self.logger.debug("[HANDLER] Combine failed: No parameters")
            return False

        # Get pair from params (support multiple key names for compatibility)
        pair = params.get("pair") or params.get(
            "pairs") or params.get("pair_indices")

        if not pair or len(pair) != 2:
            self.logger.debug(f"[HANDLER] Combine failed: Invalid pair {pair}")
            return False

        gs = env.engine.game_state

        # Get cards by ID
        card1 = gs.get_card_by_id(pair[0])
        card2 = gs.get_card_by_id(pair[1])

        if not card1 or not card2:
            self.logger.debug(
                f"[HANDLER] Combine failed: Cards not found (IDs: {pair})")
            return False

        if card1.ctype != "monster" or card2.ctype != "monster":
            self.logger.debug(
                "[HANDLER] Combine failed: Cards are not monsters")
            return False

        # Attempt to upgrade
        success = env.engine.upgrade_monster(player.id, card1.id, card2.id)

        if success:
            self.logger.debug(f"[HANDLER] ✓ Combined {
                              card1.name} + {card2.name}")
        else:
            self.logger.debug(f"[HANDLER] ✗ Failed to combine {
                              card1.name} + {card2.name}")

        return success


class EndTurnHandler(ActionHandler):
    def perform(self, env, player: Player, params: Optional[Dict]) -> bool:
        """End the current player's turn."""
        env.engine.end_turn()
        self.logger.debug(f"[HANDLER] ✓ {player.name} ends turn")
        return True
