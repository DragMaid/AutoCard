from gui.gui_info.game_area import GameArea
from gui.cache import get_font


class TextArea(GameArea):
    def __init__(self, player, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player = player
        self.font = get_font(80)

    def draw(self, screen):
        super().draw(screen)

        lp = self.player.life_points
        text_surf = self.font.render(str(lp), True, (255, 255, 255))

        x = self.rect.centerx - text_surf.get_width() // 2
        y = self.rect.centery - text_surf.get_height() // 2

        screen.blit(text_surf, (x, y))
