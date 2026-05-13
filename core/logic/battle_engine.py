from __future__ import annotations

from core.cards.monster_card import MonsterCard
from typing import TYPE_CHECKING
from .utils import log_action
from core.data.events import AttackEvent

if TYPE_CHECKING:
    from core.logic.game_engine import GameEngine


class BattleEngine:
    """
    Handles battle resolution logic between cards and players.
    """

    def __init__(self, game_engine: GameEngine):
        self.game_engine = game_engine

    def resolve_battle(
        self,
        attacker_id: str,
        defender_id: str,
        card_id: str,
        target_id: str,
        target_is_player: bool = False
    ) -> None:
        """
        Resolves a battle between a card and a target (card or player).

        Args:
            attacker_id (str): ID of the attacking player.
            defender_id (str): ID of the defending player.
            card_id (str): ID of the attacking card.
            target_id (str): ID of the target card or player.
            target_is_player (bool): True if the target is a player.
        """

        card: MonsterCard = self.game_engine.game_state.get_card_by_id(card_id)
        if not card:
            return

        self.game_engine.event_logger.add_event(AttackEvent(
            card_id=card.id, target_id=target_id, target_is_player=target_is_player))

        if not target_is_player:
            target: MonsterCard = self.game_engine.game_state.get_card_by_id(
                target_id)
            if not target:
                return
            defender = self.game_engine.game_state.players_lookup[defender_id]
            attacker = self.game_engine.game_state.players_lookup[attacker_id]

            battle_details = {
                "attacker_card": f"{card.name} (ATK:{card.attack})",
                "target_card": f"{target.name} ({'ATK' if target.mode == 'attack' else 'DEF'}:{target.attack if target.mode == 'attack' else target.defend})"
            }

            from core.cards.monster_card import CardMode
            if target.mode == CardMode.ATTACK:
                if card.attack > target.attack:
                    damage = abs(card.attack - target.attack)
                    defender.life_points = max(
                        defender.life_points - damage, 0)
                    self.game_engine.move_card_to_graveyard(target_id)
                    battle_details["result"] = f"Target destroyed, {
                        defender.name} -{damage}LP"
                elif card.attack < target.attack:
                    damage = abs(target.attack - card.attack)
                    attacker.life_points = max(
                        attacker.life_points - damage, 0)
                    self.game_engine.move_card_to_graveyard(card_id)
                    battle_details["result"] = f"Attacker destroyed, {
                        attacker.name} -{damage}LP"
                else:
                    self.game_engine.move_card_to_graveyard(card_id)
                    self.game_engine.move_card_to_graveyard(target_id)
                    battle_details["result"] = "Both destroyed (tie)"
            else:  # defense position
                if card.attack > target.defend:
                    self.game_engine.move_card_to_graveyard(target_id)
                    battle_details["result"] = "Target destroyed (defense pierced)"
                elif card.attack < target.defend:
                    damage = abs(target.defend - card.attack)
                    attacker.life_points = max(
                        attacker.life_points - damage, 0)
                    battle_details["result"] = f"Attack got reflected, {
                        attacker.name} -{damage}LP"
                else:
                    battle_details["result"] = "Attack tied defense (no effect)"

            log_action("ATTACK", attacker_id, battle_details, True)
        else:  # direct attack to player
            target_player = self.game_engine.game_state.players_lookup[target_id]
            damage = card.attack
            target_player.life_points = max(
                target_player.life_points - damage, 0)
            log_action("ATTACK", attacker_id, {
                "attacker_card": f"{card.name} (ATK:{card.attack})",
                "target": f"Player {target_player.name}",
                "damage": damage,
                "target_remaining_LP": target_player.life_points
            }, True)

        card.has_attacked = True
