import math
import pygame
from gui.effects.manager import EffectManager
from gui.audio_manager import AudioManager
from .animation import Animation


class AttackAnimation(Animation):
    def __init__(self, card1, card2, duration):
        super().__init__({card1, card2}, duration)
        self.card1 = card1
        self.card2 = card2
        self.start_pos1 = pygame.Vector2(card1.placed_pos)
        self.start_pos2 = pygame.Vector2(card2.placed_pos)
        self.midpoint = (self.start_pos1 + self.start_pos2) / 2
        self.impact_done = False

        # Final facing directions
        direction1 = pygame.Vector2(
            0, 1) if card1.logic_card.owner.is_opponent else pygame.Vector2(0, -1)
        self.final_angle1 = self._signed_angle(
            self.start_pos2 - self.start_pos1, direction1)

        direction2 = pygame.Vector2(
            0, 1) if card2.logic_card.owner.is_opponent else pygame.Vector2(0, -1)
        self.final_angle2 = self._signed_angle(
            self.start_pos1 - self.start_pos2, direction2)

        # Start from 0° rotation (upright card orientation)
        self.start_angle1 = 0
        self.start_angle2 = 0

    @staticmethod
    def _signed_angle(vec, facing):
        v1 = facing.normalize()
        v2 = vec.normalize()
        dot = v1.dot(v2)
        det = v1.x * v2.y - v1.y * v2.x
        return math.degrees(math.atan2(det, dot))

    @staticmethod
    def _ease_in(x):
        return x * x

    @staticmethod
    def _ease_out(x):
        return 1 - (1 - x) * (1 - x)

    def _apply(self, t):
        if t < 0.5:
            # Approach phase
            p = self._ease_in(t / 0.5)

            # Move toward midpoint
            self.card1.rect.center = self.start_pos1.lerp(
                self.midpoint, p * 0.6)
            self.card2.rect.center = self.start_pos2.lerp(
                self.midpoint, p * 0.6)

            # Spin the cards toward their final angle
            current_a1 = self.start_angle1 + \
                (self.final_angle1 - self.start_angle1) * p
            current_a2 = self.start_angle2 + \
                (self.final_angle2 - self.start_angle2) * p

            self.card1.image = pygame.transform.rotate(
                self.card1.original_image, -current_a1)
            self.card2.image = pygame.transform.rotate(
                self.card2.original_image, -current_a2)

        else:
            # Bounce back phase
            p = self._ease_out((t - 0.5) / 0.5)
            self.card1.rect.center = self.midpoint.lerp(self.start_pos1, p)
            self.card2.rect.center = self.midpoint.lerp(self.start_pos2, p)

            if not self.impact_done:
                EffectManager.spawn("slam", self.midpoint)
                AudioManager.play_sound("assets/sounds/sword-clash.mp3")

                # Add squash/stretch impact
                self.card1.image = pygame.transform.scale(
                    self.card1.original_image,
                    (int(self.card1.rect.width * 1.1),
                     int(self.card1.rect.height * 0.9))
                )
                self.card2.image = pygame.transform.scale(
                    self.card2.original_image,
                    (int(self.card2.rect.width * 1.1),
                     int(self.card2.rect.height * 0.9))
                )
                self.impact_done = True

        if t >= 1:
            # Reset state
            self.card1.image = self.card1.original_image
            self.card2.image = self.card2.original_image
            self.card1.rect.center = self.start_pos1
            self.card2.rect.center = self.start_pos2
