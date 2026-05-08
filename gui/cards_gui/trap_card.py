from gui.cards_gui.card_gui import CardGUI
from core.cards.trap_card import TrapCard as LogicTrapCard


class TrapCardGUI(CardGUI):
    def __init__(self, trap_info: LogicTrapCard, *args, **kwargs):
        super().__init__(trap_info, *args, **kwargs)
        self.is_face_down = True

    def on_set(self, game_engine):
        game_engine.set_trap(self.logic_card.id)
        # Trap stays face-down until triggered

    def on_drop(self, matrix, game_engine):
        cell = matrix.get_slot_at_pos(self.rect.center)
        success = False

        if cell and self.logic_card.owner_id:
            ownership = game_engine.game_state.field_matrix_ownership[cell[0]][cell[1]]
            if ownership == self.logic_card.owner_id:
                success = game_engine.set_trap(self.logic_card.id, cell)
                if success:
                    self.is_draggable = False

        self.is_selected = False
        return success

    def draw(self, surface):
        super().draw(surface)
