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
        self.card_base_image = card.image.copy()
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
            offset_y = -20 * p
            scale = 1 + 0.3 * p
            angle = 15 * math.sin(p * math.pi * 2)
            new_w = int(self.card.rect.width * scale)
            new_h = int(self.card.rect.height * scale)
            img = pygame.transform.scale(self.card_base_image, (new_w, new_h))
            img = pygame.transform.rotate(img, angle)
            self.card.image = img
            self.card.rect = img.get_rect(
                center=(self.start_pos.x, self.start_pos.y + offset_y))

        # Phase 2: spell burst (0.3 → 0.6)
        elif t < 0.6:
            if not self.effect_spawned:
                EffectManager.spawn("spell-glow", self.start_pos)
                AudioManager.play_sound("assets/sounds/spell-activate.mp3")
                self.effect_spawned = True

        # Phase 3: settle back (0.6 → 1.0)
        else:
            p = self._ease_in_out((t - 0.6) / 0.4)
            offset_y = -20 * (1 - p)
            scale = 1 + 0.3 * (1 - p)
            new_w = int(self.card.rect.width * scale)
            new_h = int(self.card.rect.height * scale)
            self.card.image = pygame.transform.scale(
                self.card_base_image, (new_w, new_h))
            self.card.rect = self.card.image.get_rect(
                center=(self.start_pos.x, self.start_pos.y + offset_y))
