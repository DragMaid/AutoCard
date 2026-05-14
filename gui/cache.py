import pygame
from functools import lru_cache
from pygame.image import load
from typing import Dict, Any

_font_cache: Dict[int, pygame.font.Font] = {}


def get_font(size: int) -> pygame.font.Font:
    """Gets cached pygame font objects by size.

    Args:
        size (int): The font size.

    Returns:
        pygame.font.Font: The font object.
    """
    if size not in _font_cache:
        _font_cache[size] = pygame.font.SysFont(None, size)
    return _font_cache[size]


@lru_cache(maxsize=512)
def load_image(path: str) -> pygame.Surface:
    """Loads and returns an image, cached.

    Args:
        path (str): The path to the image file.

    Returns:
        pygame.Surface: The loaded image as a Surface.
    """
    return load(path).convert_alpha()
