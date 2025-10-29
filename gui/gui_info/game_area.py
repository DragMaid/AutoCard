import pygame


class GameAreaConfig:
    """Configuration constants for the game layout"""
    # Layout ratios
    LEFT_RATIO = 0.25
    RIGHT_RATIO = 0.01
    BOTTOM_RATIO = 0.18
    TOP_RATIO = 0.18

    # Spacing constants
    AREA_PADDING = 10
    AREA_BORDER_WIDTH = 2
    GRID_LINE_WIDTH = 2

    # Colors
    GRID_COLOR = (255, 255, 255)
    PLAYER_COLOR = (100, 100, 255)
    OPPONENT_COLOR = (255, 100, 100)
    CARD_COLOR = (255, 215, 0)


class GameArea:
    """Represents a rectangular game area with position and dimensions"""

    def __init__(self, x, y, width, height, color=None, border_width=2):
        self.rect = pygame.Rect(x, y, width, height)
        self.color = color
        self.border_width = border_width

    def draw(self, screen):
        if self.color:
            pygame.draw.rect(screen, self.color, self.rect, self.border_width)

    def contains_point(self, pos):
        return self.rect.collidepoint(pos)
