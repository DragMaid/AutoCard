import math
import pygame
from gui.effects.manager import EffectManager
from gui.audio import AudioManager
from .animation import Animation


class TrapTriggerAnimation(Animation):
    def __init__(self, trap_card, duration=1.0):
        super().__init__({trap_card}, duration)
        self.card = trap_card
        self.start_pos = pygame.Vector2(trap_card.rect.center)
        self.glow_done = False

    @staticmethod
    def _ease_out(x):
        return 1 - (1 - x) * (1 - x)

    def _apply(self, t):
        # Phase 1: Flip (0.0 to 0.3)
        if t < 0.3:
            p = t / 0.3
            scale_y = abs(math.cos(p * math.pi))
            self.card.scale_factor_y = max(0.01, scale_y)
            if p >= 0.5:
                self.card.logic_card.is_face_down = False
        else:
            # Ensure flip is complete if we jumped past it
            self.card.logic_card.is_face_down = False

        # Phase 2: Glow & Sound Trigger (at 0.3)
        if t >= 0.3:
            if not self.glow_done:
                self.card.scale_factor_y = 1.0
                AudioManager.play_sound("assets/sounds/trap-reveal.mp3")
                EffectManager.spawn("trap-glow", self.start_pos)
                self.glow_done = True

        # Phase 3: Shake (0.6 to 1.0)
        if t >= 0.6:
            p = (t - 0.6) / 0.4
            offset_x = math.sin(p * 20 * math.pi) * 5 * (1 - p)
            self.card.rect.center = (
                self.start_pos.x + offset_x, self.start_pos.y)
            self.card.scale_factor_y = 1.0
        elif t >= 0.3:
            # Maintain scale during glow phase before shake
            self.card.scale_factor_y = 1.0
