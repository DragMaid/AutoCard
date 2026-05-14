from .animation import Animation
from gui.effects.manager import EffectManager
from gui.audio import AudioManager
import pygame
import math


class AttackPlayerAnimation(Animation):
    def __init__(self, card, game_area, game_state, duration=0.6, on_finish=None):
        super().__init__({card}, duration)
        self.card = card
        self.start_pos = pygame.Vector2(card.rect.center)
        self.end_pos = pygame.Vector2(game_area.rect.center)
        self.game_area = game_area
        self.impact_done = False
        self.on_finish = on_finish

        # Facing direction for rotation (toward deck center)
        owner = game_state.players_lookup[card.logic_card.owner_id]
        direction = pygame.Vector2(
            0, 1) if owner.is_opponent else pygame.Vector2(0, -1)
        self.final_angle = self._signed_angle(
            self.end_pos - self.start_pos, direction)

        # Start from current orientation
        self.start_angle = card.angle

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

            # Move toward player area
            self.card.rect.center = self.start_pos.lerp(self.end_pos, p * 0.7)

            # Rotate toward final angle
            self.card.angle = self.start_angle + \
                (self.final_angle - self.start_angle) * p

        else:
            # Return phase
            p = self._ease_out((t - 0.5) / 0.5)
            self.card.rect.center = self.end_pos.lerp(self.start_pos, p)

            if not self.impact_done:
                EffectManager.spawn("hit_player", self.game_area)
                EffectManager.spawn("slam", self.end_pos)
                AudioManager.play_sound("assets/sounds/player-hurt.mp3")

                # Squash/stretch impact
                self.card.scale_factor_x = 1.1
                self.card.scale_factor_y = 0.9
                self.impact_done = True

            # Fade out squash
            self.card.scale_factor_x = 1.1 - 0.1 * p
            self.card.scale_factor_y = 0.9 + 0.1 * p

        if t >= 1:
            # Reset state
            self.card.angle = self.start_angle
            self.card.rect.center = self.start_pos
            self.card.scale_factor_x = self.card.scale_factor_y = 1.0

            if self.on_finish:
                self.on_finish(self.card)
