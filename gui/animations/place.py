import math
from gui.effects.manager import EffectManager
from gui.audio_manager import AudioManager
from .animation import Animation


class PlaceAnimation(Animation):
    def __init__(self, sprite, end_pos, duration):
        super().__init__({sprite}, duration)
        self.sprite = sprite
        self.start_pos = (end_pos[0], end_pos[1] - 100)
        self.end_pos = end_pos
        self.impact_done = False

    def _apply(self, t):
        ease_t = t * t * (3 - 2 * t)
        x = self.start_pos[0] + (self.end_pos[0] - self.start_pos[0]) * ease_t
        y = self.start_pos[1] + (self.end_pos[1] - self.start_pos[1]) * ease_t
        self.sprite.rect.center = (x, y)
        if t < 0.95:
            scale_y = 1.0
        else:
            squash_t = (t - 0.95) / 0.05
            scale_y = 1.0 - 0.2 * math.sin(squash_t * math.pi)
        self.sprite.scale_y = scale_y
        if not self.impact_done and t >= 0.95:
            self.impact_done = True
            EffectManager.spawn("slam", self.end_pos)
            AudioManager.play_sound("assets/sounds/card-disappear.mp3")
