import pygame
from gui.cards.card_gui import CardGUI
from core.cards.trap_card import TrapCard as LogicTrapCard
from gui.screen.components import Button


class TrapCardGUI(CardGUI):
    def __init__(self, trap_info: LogicTrapCard, *args, **kwargs):
        self.is_face_down = True
        self.triggerable = False
        self.activated = False
        super().__init__(trap_info, *args, **kwargs)

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

    def update_activate_button(self):
        # Update the triggerable button
        btn_w, btn_h = self.rect.width, 30
        activate_button_rect = pygame.Rect(
            self.rect.x, self.rect.y + self.rect.height - btn_h - 10, btn_w, btn_h)
        bg_color = (40, 167, 69) if self.activated else (220, 53, 69)
        text_str = "ACTIVATED" if self.activated else "ACTIVATE"
        if not hasattr(self, "activate_button"):
            self.activate_button = Button(
                rect=activate_button_rect,
                text=text_str,
                font_size=14,
                color=bg_color,
                border_radius=8
            )
        else:
            self.activate_button.rect = activate_button_rect
            self.activate_button.text = text_str
            self.activate_button.color = bg_color

    def update(self):
        # Update our triggerable state from the logic card
        self.triggerable = self.logic_card.triggerable and not self.logic_card.is_opponent

        # If the card is on the field (pos_in_matrix is set)
        if self.logic_card.pos_in_matrix is not None:
            # When triggerable, the trap should be revealed (not face down)
            if self.triggerable:
                self.logic_card.is_face_down = False
                self.update_activate_button()
        super().update()

    def draw(self, surface):
        super().draw(surface)
        if self.triggerable and self.activate_button:
            self.activate_button.draw(surface)
