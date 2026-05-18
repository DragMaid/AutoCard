import pygame
from gui.background.game_area import GameArea
from gui.cache import load_image
from core.config import Config


class DeckArea(GameArea):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        back_path = Config.ASSET_DIR / "card-back.png"
        self.image = load_image(back_path).convert_alpha()
        self.image = pygame.transform.scale(
            self.image, (self.rect.height, self.rect.width))
        self.image = pygame.transform.rotate(self.image, 90)

    def draw(self, screen):
        screen.blit(self.image, self.rect)
