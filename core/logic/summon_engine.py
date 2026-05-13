from __future__ import annotations
from typing import Tuple, Optional
from core.cards.card import CardType
from core.cards.monster_card import MonsterCard
from core.cards.trap_card import ActivateCondition
from .utils import log_action
from .game_engine import GameEngine


class SummonEngine:
    """
    Handles card summoning and placement logic.
    """

    def __init__(self, game_engine: GameEngine):
        self.game_engine = game_engine

    def summon_card(self,
                    player_id: str,
                    card_id: str,
                    cell: Optional[Tuple[int, int]],
                    check: bool = True) -> bool:
        """
        Processes a summon request from a player.

        Args:
            player_id (str): ID of the player summoning.
            card_id (str): ID of the card being summoned.
            cell (Optional[Tuple[int, int]]): Target field position.
            check (bool): Whether to enforce rule validation.

        Returns:
            bool: True if successfully summoned, False otherwise.
        """
        can_summon = self.game_engine.rule_engine.can_summon(
            player_id, card_id, self.game_engine.game_state.field_matrix, cell) or not check

        card = self.game_engine.game_state.get_card_by_id(card_id)
        if not card:
            return False

        if not can_summon:
            reasons = []
            if card.card_type == CardType.MONSTER:
                if self.game_engine.game_state.player_info[player_id]["has_summoned_monster"]:
                    reasons.append("Already summoned monster this turn")
                if card_id not in self.game_engine.game_state.player_info[player_id]["held_cards"].cards:
                    reasons.append("Card not in hand")

            log_action("SUMMON", player_id, {
                "card": card.name,
                "type": card.card_type.value,
                "target_cell": cell,
                "reason": ", ".join(reasons) if reasons else "Rule check failed"
            }, False)
            return False

        if cell is None:
            cell = self.game_engine.game_state.get_random_empty_slot(player_id)
            if cell is None:
                log_action("SUMMON", player_id, {
                    "card": card.name,
                    "reason": "No empty slots available"
                }, False)
                return False

        self.game_engine.game_state.player_info[player_id]["held_cards"].remove(
            card_id)
        if card.card_type == CardType.MONSTER:
            self.game_engine.game_state.player_info[player_id]["has_summoned_monster"] = True
        elif card.card_type == CardType.TRAP:
            self.game_engine.game_state.player_info[player_id]["has_summoned_trap"] = True

        self.game_engine.game_state.modify_field("add", card, cell)
        card.is_placed = True
        card.pos_in_matrix = cell

        details = {
            "card": card.name,
            "type": card.card_type.value,
            "position": cell
        }
        if isinstance(card, MonsterCard):
            details.update({
                "atk": card.attack,
                "def": card.defend,
                "level": card.star
            })

        log_action("SUMMON", player_id, details, True)

        if self.game_engine.trap_engine.check_traps(
            condition=ActivateCondition.SUMMON,
            target_id=card_id
        ):
            self.game_engine.turn_manager.toggle_trap_stage(state=True)

        return True
