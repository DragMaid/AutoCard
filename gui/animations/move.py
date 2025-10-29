from .animation import Animation
from gui.audio_manager import AudioManager


class MoveAnimation(Animation):
    def __init__(self, sprite, start_pos, end_pos, duration):
        super().__init__({sprite}, duration)
        self.sprite = sprite
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.impact_done = False

    def _apply(self, t):
        ease_t = 2 * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 2) / 2
        x = self.start_pos[0] + (self.end_pos[0] - self.start_pos[0]) * ease_t
        y = self.start_pos[1] + (self.end_pos[1] - self.start_pos[1]) * ease_t
        self.sprite.rect.center = (x, y)
        if not self.impact_done and t >= 0.1:
            self.impact_done = True
            AudioManager.play_sound("assets/sounds/card-draw.mp3")
