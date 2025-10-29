import pygame
from gui.gui_info.game_area import GameArea


class DeckArea(GameArea):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        image_path = "assets/card-back.png"
        self.image = pygame.image.load(image_path).convert_alpha()
        self.image = pygame.transform.scale(
            self.image, (self.rect.height, self.rect.width))
        self.image = pygame.transform.rotate(self.image, 90)

    def draw(self, screen):
        screen.blit(self.image, self.rect)
