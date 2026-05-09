import math
import pygame
from .animation import Animation
from gui.effects.manager import EffectManager
from gui.audio_manager import AudioManager


class SpellAnimation(Animation):
    def __init__(self, card, duration=1.0):
        super().__init__({card}, duration)
        self.card = card
        self.start_pos = pygame.Vector2(card.rect.center)
        self.effect_spawned = False

    @staticmethod
    def _ease_out(x):
        return 1 - (1 - x) * (1 - x)

    @staticmethod
    def _ease_in_out(x):
        return 3*x**2 - 2*x**3

    def _apply(self, t):
        # Phase 1: quick pop + rotation (0 → 0.3)
        if t < 0.3:
            p = self._ease_out(t / 0.3)
            self.card.offset_y = -20 * p
            self.card.scale_factor_x = 1 + 0.3 * p
            self.card.scale_factor_y = 1 + 0.3 * p
            self.card.angle = 15 * math.sin(p * math.pi * 2)

        # Phase 2: spell burst trigger (at 0.3)
        if t >= 0.3:
            if not self.effect_spawned:
                EffectManager.spawn("spell-glow", self.start_pos)
                AudioManager.play_sound("assets/sounds/spell-activate.mp3")
                self.effect_spawned = True

        # Phase 3: settle back (0.6 → 1.0)
        if t >= 0.6:
            p = self._ease_in_out((t - 0.6) / 0.4)
            self.card.offset_y = -20 * (1 - p)
            self.card.scale_factor_x = 1 + 0.3 * (1 - p)
            self.card.scale_factor_y = 1 + 0.3 * (1 - p)
            self.card.angle = 0
        elif t >= 0.3:
            # Maintain the pop state during burst phase before settling
            self.card.offset_y = -20
            self.card.scale_factor_x = 1.3
            self.card.scale_factor_y = 1.3
            self.card.angle = 0
