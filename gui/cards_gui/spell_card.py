from gui.cards_gui.card_gui import CardGUI
from core.cards.spell_card import SpellCard as LogicSpellCard

from gui.gui_info.matrix_field import Matrix
from core.handle_game_logic.game_engine import GameEngine


class SpellCardGUI(CardGUI):
    def __init__(self, spell_info: LogicSpellCard, *args, **kwargs):
        super().__init__(spell_info, *args, **kwargs)

    def on_drop(self, matrix: Matrix, game_engine: GameEngine):
        cell = matrix.get_slot_at_pos(self.rect.center)
        success = False

        if cell:
            card_id = matrix.game_state.field_matrix[cell[0]][cell[1]]
            card_info = matrix.game_state.entity_lookup.get(card_id)
            if self.logic_card.can_target(card_info):
                success = self.on_activate(game_engine, card_id)

        self.is_selected = False
        return success

    def on_activate(self, game_engine, target_id):
        success = game_engine.cast_spell(self.logic_card.id, target_id)
        self.kill()
        return success
