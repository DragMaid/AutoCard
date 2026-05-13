import os
from pathlib import Path
from pygame.sprite import Sprite as PySprite
from pygame.transform import scale
from typing import Tuple
from gui.cache import load_image


ROOT_PATH = Path(os.path.dirname(__file__)).parent


class Sprite(PySprite):
    def __init__(self,
                 pos: Tuple[float, float],
                 size: Tuple[float, float],
                 image_path: str):
        super().__init__()

        # Resolve image path relative to project root
        abs_image_path = Path(ROOT_PATH, image_path).resolve()
        fallback_path = Path(ROOT_PATH, "assets", "card-back.png").resolve()

        if not abs_image_path.exists():
            abs_image_path = fallback_path

        # Now pygame gets a full absolute path that always works
        self.image = load_image(str(abs_image_path))
        self.image = scale(self.image, size)
        self.original_image = self.image.copy()
        self.base_image = self.image.copy()

        self.rect = self.image.get_rect(topleft=(int(pos[0]), int(pos[1])))
