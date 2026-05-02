from gui.cache import get_font


class CardStatOverlay:
    def __init__(self, card_gui, font_size=20, position="bottom"):
        self._card = card_gui
        self.font = get_font(font_size)
        self.position = position

    def __getattr__(self, name):
        """
        Delegate attribute access to the underlying card.
        This means overlay.attr -> card.attr if overlay doesn't have it.
        """
        return getattr(self._card, name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            setattr(self._card, name, value)

    def draw(self, surface):
        # First draw the card itself
        self._card.draw(surface)

        # Then draw the ATK/DEF overlay
        atk = getattr(self._card.logic_card, "atk", 0)
        defe = getattr(self._card.logic_card, "defend", 0)
        star = getattr(self._card.logic_card, "level_star", 0)

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
