from gui.cards_gui.card_gui import CardGUI
from core.cards.monster_card import MonsterCard as LogicMonsterCard


class MonsterCardGUI(CardGUI):
    def __init__(self, monster_info: LogicMonsterCard, *args, **kwargs):
        super().__init__(monster_info, *args, **kwargs)

    def on_toggle(self, game_engine):
        return game_engine.toggle_card(self.logic_card.id)

    # TODO: not sure about this one but should reconsider this design
    def on_drop(self, matrix, game_engine):
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
