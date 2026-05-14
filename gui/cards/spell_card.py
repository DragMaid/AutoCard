from gui.cards.card_gui import CardGUI
from core.cards.spell_card import SpellCard as LogicSpellCard

from gui.background.matrix_field import Matrix
from core.logic.game_engine import GameEngine


class SpellCardGUI(CardGUI):
    def __init__(self, spell_info: LogicSpellCard, *args, **kwargs):
        super().__init__(spell_info, *args, **kwargs)

    def on_drop(self, matrix: Matrix, game_engine: GameEngine):
        cell = matrix.get_slot_at_pos(self.rect.center)
        success = False

        if cell:
            card_id = matrix.game_state.field_matrix[cell[0]][cell[1]]
            success = self.on_activate(game_engine, card_id)

        self.is_selected = False
        return success

    def on_activate(self, game_engine, target_id):
        success = game_engine.cast_spell(self.logic_card.id, target_id)
        self.kill()
        return success
