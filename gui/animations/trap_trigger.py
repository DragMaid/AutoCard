import math
import pygame
from gui.effects.manager import EffectManager
from gui.audio_manager import AudioManager
from .animation import Animation


class TrapTriggerAnimation(Animation):
    def __init__(self, trap_card, duration=1.0):
        super().__init__({trap_card}, duration)
        self.card = trap_card
        self.start_pos = pygame.Vector2(trap_card.rect.center)
        self.flip_done = False
        self.glow_done = False

    @staticmethod
    def _ease_out(x):
        return 1 - (1 - x) * (1 - x)

    def _apply(self, t):
        if t < 0.3:
            # Flip animation (face-down → face-up)
            p = t / 0.3
            # shrink to 0 then expand
            scale_y = max(0.05, abs(math.cos(p * math.pi)))
            new_img = pygame.transform.scale(
                self.card.original_image,
                (self.card.rect.width, max(1, int(self.card.rect.height * scale_y)))
            )
            self.card.image = new_img
            self.card.rect = new_img.get_rect(center=self.start_pos)

        elif t < 0.6:
            # Glow phase
            if not self.glow_done:
                AudioManager.play_sound("assets/sounds/trap-reveal.mp3")
                EffectManager.spawn("trap-glow", self.start_pos)
                self.glow_done = True

        else:
            # Shake phase
            p = (t - 0.6) / 0.4
            offset_x = math.sin(p * 20 * math.pi) * 5 * \
                (1 - p)  # decaying shake
            self.card.rect.center = (
                self.start_pos.x + offset_x, self.start_pos.y)
