from __future__ import annotations

from typing import TYPE_CHECKING
from .utils import log_action
from core.data.game_state import AttackEntry
from core.data.events import AttackEvent
from core.cards.monster_card import CardMode

if TYPE_CHECKING:
    from core.logic.game_engine import GameEngine


class BattleEngine:
    """Handles battle resolution logic between cards and players."""

    def __init__(self, game_engine: GameEngine) -> None:
        """Initializes the BattleEngine.

        Args:
            game_engine (GameEngine): The main game engine instance.
        """
        self.game_engine = game_engine

    def resolve_battle(self, attack: AttackEntry) -> None:
        """Resolves a battle between a card and a target (card or player).

        Args:
            attack (AttackEntry): The attack details containing attacker, defender,
                card IDs, and target information.
        """

        card = self.game_engine.game_state.get_card_by_id(attack.card_id)
        if not card:
            return

        self.game_engine.event_logger.add_event(AttackEvent(
            card_id=attack.card_id,
            target_id=attack.target_id,
            target_is_player=attack.target_is_player
        ))

        if not attack.target_is_player:
            target = self.game_engine.game_state.get_card_by_id(attack.target_id)
            if not target:
                return
            defender = self.game_engine.game_state.players_lookup[attack.defender_id]
            attacker = self.game_engine.game_state.players_lookup[attack.attacker_id]

            if target.mode == CardMode.ATTACK:
                stat_text = f"ATK:{target.attack}"
            else:
                stat_text = f"DEF:{target.defend}"

            battle_details = {
                "attacker_card": f"{card.name} (ATK:{card.attack})",
                "target_card": f"{target.name} ({stat_text})",
            }

            if target.mode == CardMode.ATTACK:
                if card.attack > target.attack:
                    damage = abs(card.attack - target.attack)
                    defender.life_points = max(
                        defender.life_points - damage, 0)
                    self.game_engine.move_card_to_graveyard(attack.target_id)
                    battle_details["result"] = f"Target destroyed, {defender.name} -{damage}LP"
                elif card.attack < target.attack:
                    damage = abs(target.attack - card.attack)
                    attacker.life_points = max(
                        attacker.life_points - damage, 0)
                    self.game_engine.move_card_to_graveyard(attack.card_id)
                    battle_details["result"] = f"Attacker destroyed, {attacker.name} -{damage}LP"
                else:
                    self.game_engine.move_card_to_graveyard(attack.card_id)
                    self.game_engine.move_card_to_graveyard(attack.target_id)
                    battle_details["result"] = "Both destroyed (tie)"
            else:  # defense position
                if card.attack > target.defend:
                    self.game_engine.move_card_to_graveyard(attack.target_id)
                    battle_details["result"] = "Target destroyed (defense pierced)"
                elif card.attack < target.defend:
                    damage = abs(target.defend - card.attack)
                    attacker.life_points = max(
                        attacker.life_points - damage, 0)
                    battle_details["result"] = f"Attack got reflected, {attacker.name} -{damage}LP"
                else:
                    battle_details["result"] = "Attack tied defense (no effect)"

            log_action("ATTACK", attack.attacker_id, battle_details, True)
        else:  # direct attack to player
            target_player = self.game_engine.game_state.players_lookup[attack.target_id]
            damage = card.attack
            target_player.life_points = max(
                target_player.life_points - damage, 0)
            log_action("ATTACK", attack.attacker_id, {
                "attacker_card": f"{card.name} (ATK:{card.attack})",
                "target": f"Player {target_player.name}",
                "damage": damage,
                "target_remaining_LP": target_player.life_points
            }, True)

        card.has_attacked = True
