import pygame
from functools import lru_cache
from pygame.image import load

_font_cache = {}


def get_font(size):
    """Cache pygame font objects by size"""
    if size not in _font_cache:
        _font_cache[size] = pygame.font.SysFont(None, size)
    return _font_cache[size]


@lru_cache(maxsize=512)
def load_image(path: str):
    return load(path).convert_alpha()
