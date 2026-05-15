from __future__ import annotations

import random
from typing import Tuple, Optional, TYPE_CHECKING
from core.cards.card import CardType
from core.cards.monster_card import MonsterCard
from core.cards.trap_card import ActivateCondition
from core.data.game_state import ModifyMode
from .utils import log_action

if TYPE_CHECKING:
    from core.logic.game_engine import GameEngine


class SummonEngine:
    """Handles card summoning and placement logic."""

    def __init__(self, game_engine: GameEngine) -> None:
        """Initializes the SummonEngine.

        Args:
            game_engine (GameEngine): The main game engine instance.
        """
        self.game_engine = game_engine

    def summon_card(
        self,
        player_id: str,
        card_id: str,
        cell: Optional[Tuple[int, int]],
        check: bool = True
    ) -> bool:
        """Processes a summon request from a player.

        Args:
            player_id (str): ID of the player summoning.
            card_id (str): ID of the card being summoned.
            cell (Optional[Tuple[int, int]]): Target field position.
            check (bool): Whether to enforce rule validation.

        Returns:
            bool: True if successfully summoned, False otherwise.
        """
        card = self.game_engine.game_state.get_card_by_id(card_id)
        if cell is None:
            cell = random.choice(
                self.game_engine.game_state.get_empty_slots(player_id))
            if cell is None:
                log_action("SUMMON", player_id, {
                    "card": card.name,
                    "reason": "No empty slots available"
                }, False)
                return False

        can_summon = self.game_engine.rule_engine.can_summon(
            player_id, card_id, cell) or not check

        if not card:
            return False

        if not can_summon:
            return False

        self.game_engine.game_state.player_info[player_id].held_cards.remove(
            card_id)
        if card.card_type == CardType.MONSTER:
            self.game_engine.game_state.player_info[player_id].has_summoned_monster = True
        elif card.card_type == CardType.TRAP:
            self.game_engine.game_state.player_info[player_id].has_summoned_trap = True

        self.game_engine.game_state.modify_field(ModifyMode.ADD, card, cell)
        card.is_placed = True
        card.pos_in_matrix = cell

        details = {
            "card": card.name,
            "type": card.card_type.value,
            "position": cell
        }
        if isinstance(card, MonsterCard):
            details.update({
                "attack": card.attack,
                "defened": card.defend,
                "level": card.star
            })

        log_action("SUMMON", player_id, details, True)

        if self.game_engine.trap_engine.check_traps(
            condition=ActivateCondition.SUMMON,
            target_id=card_id
        ):
            self.game_engine.turn_manager.toggle_trap_stage(state=True)

        return True
