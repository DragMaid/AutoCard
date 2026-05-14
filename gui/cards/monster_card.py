from typing import Any
from gui.cards.card_gui import CardGUI
from core.cards.monster_card import MonsterCard as LogicMonsterCard


class MonsterCardGUI(CardGUI):
    """GUI representation of a monster card."""

    def __init__(self, monster_info: LogicMonsterCard, *args: Any, **kwargs: Any) -> None:
        """Initializes the MonsterCardGUI.

        Args:
            monster_info (LogicMonsterCard): The logic representation of the monster card.
            *args (Any): Variable length argument list.
            **kwargs (Any): Arbitrary keyword arguments.
        """
        super().__init__(monster_info, *args, **kwargs)

    def on_toggle(self, game_engine: Any) -> bool:
        """Handles card toggle event.

        Args:
            game_engine (Any): The game engine instance.

        Returns:
            bool: Result of the toggle operation.
        """
        return game_engine.toggle_card(self.logic_card.id)

    def on_drop(self, matrix: Any, game_engine: Any) -> bool:
        """Handles card drop event.

        Args:
            matrix (Any): The field matrix.
            game_engine (Any): The game engine instance.

        Returns:
            bool: True if drop was successful, False otherwise.
        """
        cell = matrix.get_slot_at_pos(self.rect.center)
        success = False

        if cell and self.logic_card.owner_id:
            ownership = game_engine.game_state.field_matrix_ownership[cell[0]][cell[1]]
            if ownership == self.logic_card.owner_id:
                success = game_engine.summon_card(
                    self.logic_card.owner_id, self.logic_card.id, cell)
                if success:
                    self.is_draggable = False

        self.is_selected = False
        return success
