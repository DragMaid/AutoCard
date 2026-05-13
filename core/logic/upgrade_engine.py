from __future__ import annotations

from core.cards.monster_card import MonsterCard
from core.data.events import MergeEvent
from .utils import log_action
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.logic.game_engine import GameEngine


class UpgradeEngine:
    """
    Handles monster upgrade (fusion/merge) logic.
    """

    def __init__(self, game_engine: GameEngine):
        self.game_engine = game_engine

    def upgrade_monster(self,
                        player_id: str,
                        own_card_id: str,
                        target_card_id: str) -> bool:
        """
        Processes an upgrade request for two monsters.

        Args:
            player_id (str): ID of the player performing the upgrade.
            own_card_id (str): ID of the first card (typically the one dragged).
            target_card_id (str): ID of the target card.

        Returns:
            bool: True if upgrade successful, False otherwise.
        """
        can_upgrade = self.game_engine.rule_engine.can_upgrade(
            player_id, own_card_id, target_card_id)

        own_card: MonsterCard = self.game_engine.game_state.get_card_by_id(
            own_card_id)
        target_card: MonsterCard = self.game_engine.game_state.get_card_by_id(
            target_card_id)

        if not can_upgrade:
            reasons = []
            if own_card.monster_type != target_card.monster_type:
                reasons.append(f"Type mismatch: {own_card.monster_type.value} vs {
                               target_card.monster_type.value}")
            if own_card.star != target_card.star:
                reasons.append(f"Level mismatch: {
                               own_card.star} vs {target_card.star}")
            if own_card.owner_id != player_id or target_card.owner_id != player_id:
                reasons.append("Not your cards")

            log_action("UPGRADE", player_id, {
                "card1": f"{own_card.name} (Lv{own_card.star})",
                "card2": f"{target_card.name} (Lv{target_card.star})",
                "reason": ", ".join(reasons) if reasons else "Rule check failed"
            }, False)
            return False

        upgrade_position = target_card.pos_in_matrix
        old_level = own_card.star
        new_level = old_level + 1

        # Remove the base monsters from the field and move them to graveyard
        self.game_engine.move_card_to_graveyard(own_card_id)
        self.game_engine.move_card_to_graveyard(target_card_id)

        # Create the upgraded monster
        upgraded_monster = self.game_engine.draw_system.monster_factory.load_by_type_and_level(
            player_id, own_card.monster_type, new_level)

        if upgraded_monster is None:
            log_action("UPGRADE", player_id, {
                "type": own_card.monster_type.value,
                "from_level": old_level,
                "to_level": new_level,
                "reason": f"No monster of type {own_card.monster_type.value} at level {new_level}"
            }, False)
            return False

        # Place the upgraded monster on the field
        self.game_engine.game_state.entity_lookup[upgraded_monster.id] = upgraded_monster
        if upgrade_position:
            self.game_engine.game_state.modify_field(
                "add", upgraded_monster, upgrade_position)
            upgraded_monster.is_placed = True
            upgraded_monster.pos_in_matrix = upgrade_position

            log_action("UPGRADE", player_id, {
                "from": f"{own_card.name} + {target_card.name}",
                "to": f"{upgraded_monster.name} (Lv{new_level})",
                "position": upgrade_position,
                "stats": f"ATK:{upgraded_monster.attack}/DEF:{upgraded_monster.defend}"
            }, True)

            self.game_engine.event_logger.add_event(MergeEvent(
                card_id=own_card_id,
                target_id=target_card_id,
                result_card_id=upgraded_monster.id
            ))
            return True

        return False
