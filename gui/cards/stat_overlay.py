from typing import Any
import pygame
from gui.cache import get_font


class CardStatOverlay:
    """Provides an overlay for displaying card stats.

    Attributes:
        _card (Any): The card GUI element.
        font (pygame.font.Font): The font used for displaying stats.
        position (str): The position of the overlay (e.g., "bottom").
        game_state (Any): The current game state.
    """

    def __init__(self, card_gui: Any, game_state: Any, font_size: int = 20, position: str = "bottom") -> None:
        """Initializes the CardStatOverlay.

        Args:
            card_gui (Any): The card GUI element.
            game_state (Any): The current game state.
            font_size (int, optional): The font size for stats. Defaults to 20.
            position (str, optional): The overlay position. Defaults to "bottom".
        """
        self._card = card_gui
        self.font = get_font(font_size)
        self.position = position
        self.game_state = game_state

    def __getattr__(self, name: str) -> Any:
        """Delegates attribute access to the underlying card."""
        return getattr(self._card, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            setattr(self._card, name, value)

    def draw(self, surface: pygame.Surface) -> None:
        """Draws the card and its stat overlay.

        Args:
            surface (pygame.Surface): The surface to draw onto.
        """
        # First draw the card itself
        card_id = self._card.logic_card.id
        self._card.logic_card = self.game_state.get_card_by_id(card_id)
        self._card.draw(surface)

        # Do not draw the stat overlay if card is faced down and belongs to the opponent
        if self._card.logic_card.is_face_down and self._card.logic_card.is_opponent:
            return

        # Then draw the ATK/DEF overlay
        atk = getattr(self._card.logic_card, "attack", 0)
        defe = getattr(self._card.logic_card, "defend", 0)
        star = getattr(self._card.logic_card, "star", 0)

        stat_text = f"{
            atk}/{defe}/{star}*" if not self._card.is_face_down else ""
        text_surf = self.font.render(stat_text, True, (255, 255, 255))

        if self.position == "bottom":
            x = self._card.rect.centerx - text_surf.get_width() // 2
            y = self._card.rect.top - 2
        else:
            x = self._card.rect.centerx - text_surf.get_width() // 2
            y = self._card.rect.bottom + 2

        # Outline
        outline = self.font.render(stat_text, True, (0, 0, 0))
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            surface.blit(outline, (x + dx, y + dy))

        surface.blit(text_surf, (x, y))
