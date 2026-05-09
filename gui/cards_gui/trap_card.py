import pygame
from gui.cards_gui.card_gui import CardGUI
from core.cards.trap_card import TrapCard as LogicTrapCard
from gui.cache import get_font


class TrapCardGUI(CardGUI):
    def __init__(self, trap_info: LogicTrapCard, *args, **kwargs):
        super().__init__(trap_info, *args, **kwargs)
        self.is_face_down = True
        self.triggerable = False
        self.activated = False
        self.activate_button_rect = None

    def set_triggerable(self, value: bool):
        self.triggerable = value

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
        if self.triggerable:
            # Draw an "Activate" button above or on the card
            btn_w, btn_h = self.rect.width, 30
            self.activate_button_rect = pygame.Rect(
                self.rect.x, self.rect.y - btn_h - 10, btn_w, btn_h)

            # Button color changes based on activated state
            bg_color = (40, 167, 69) if self.activated else (220, 53, 69)
            pygame.draw.rect(surface, bg_color,
                             self.activate_button_rect, border_radius=8)
            pygame.draw.rect(surface, (255, 255, 255),
                             self.activate_button_rect, 2, border_radius=8)

            font = get_font(14)
            text_str = "ACTIVATED" if self.activated else "ACTIVATE"
            text_surf = font.render(text_str, True, (255, 255, 255))
            text_rect = text_surf.get_rect(
                center=self.activate_button_rect.center)
            surface.blit(text_surf, text_rect)

        super().draw(surface)
