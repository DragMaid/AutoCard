from pygame.sprite import Sprite as PySprite
from pygame.transform import scale
from typing import Tuple
from gui.cache import load_image


class Sprite(PySprite):
    def __init__(self,
                 pos: Tuple[float, float],
                 size: Tuple[float, float],
                 image_path: str):
        super().__init__()

        self.image = load_image(str(image_path))
        self.image = scale(self.image, size)
        self.original_image = self.image.copy()
        self.base_image = self.image.copy()

        self.rect = self.image.get_rect(
            topleft=(int(pos[0]), int(pos[1])))
