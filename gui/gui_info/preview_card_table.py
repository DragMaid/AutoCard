import pygame
from gui.cards_gui.card_gui import CardGUI
from gui.cache import load_image


class CardPreview:
    def __init__(self, x, y, width, height, border_color=(0, 0, 0), border_width=2):
        image_path = "assets/card-preview.png"
        self.image = load_image(image_path)
        self.image = pygame.transform.scale(self.image, (width, height))
        self.rect = pygame.Rect(x, y, width, height)
        self.border_color = border_color
        self.border_width = border_width
        self.card_gui = None  # Will hold a resized CardGUI

    def set_card(self, card_ui, game_state):
        """Create a fresh CardGUI scaled to the preview size"""

        owner = game_state.players_lookup[card_ui.logic_card.owner_id]
        if owner.is_opponent and \
                (card_ui.logic_card.is_face_down
                 or card_ui.is_face_down):
            return

        self.card_gui = CardGUI(
            card_ui.logic_card,
            pos=self.rect.topleft,
            size=(self.rect.width, self.rect.height)
        )
        self.card_gui.image = self.card_gui.annotated_image

    def draw(self, screen):
        if self.card_gui:
            self.card_gui.rect.center = self.rect.center
            self.card_gui.draw(screen)

        else:
            screen.blit(self.image, self.rect)
