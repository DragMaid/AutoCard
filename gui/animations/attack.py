import math
import pygame
from gui.effects.manager import EffectManager
from gui.audio_manager import AudioManager
from .animation import Animation


class AttackAnimation(Animation):
    def __init__(self, card1, card2, game_state, duration):
        super().__init__({card1, card2}, duration)
        self.card1 = card1
        self.card2 = card2
        self.start_pos1 = pygame.Vector2(card1.placed_pos)
        self.start_pos2 = pygame.Vector2(card2.placed_pos)
        self.midpoint = (self.start_pos1 + self.start_pos2) / 2
        self.impact_done = False

        # Final facing directions
        owner1 = game_state.players_lookup[card1.logic_card.owner_id]
        direction1 = pygame.Vector2(
            0, 1) if owner1.is_opponent else pygame.Vector2(0, -1)
        self.final_angle1 = self._signed_angle(
            self.start_pos2 - self.start_pos1, direction1)

        owner2 = game_state.players_lookup[card2.logic_card.owner_id]
        direction2 = pygame.Vector2(
            0, 1) if owner2.is_opponent else pygame.Vector2(0, -1)
        self.final_angle2 = self._signed_angle(
            self.start_pos1 - self.start_pos2, direction2)

        # Base angles from card mode (defense = 90 deg)
        self.start_angle1 = 90 if getattr(card1.logic_card, "mode", "attack") == "defense" else 0
        self.start_angle2 = 90 if getattr(card2.logic_card, "mode", "attack") == "defense" else 0

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
            self.card1.angle = self.start_angle1 + (self.final_angle1 - self.start_angle1) * p
            self.card2.angle = self.start_angle2 + (self.final_angle2 - self.start_angle2) * p

        else:
            # Bounce back phase
            p = self._ease_out((t - 0.5) / 0.5)
            self.card1.rect.center = self.midpoint.lerp(self.start_pos1, p)
            self.card2.rect.center = self.midpoint.lerp(self.start_pos2, p)

            if not self.impact_done:
                EffectManager.spawn("slam", self.midpoint)
                AudioManager.play_sound("assets/sounds/sword-clash.mp3")
                
                # Apply impact squash
                self.card1.scale_factor_x = 1.1
                self.card1.scale_factor_y = 0.9
                self.card2.scale_factor_x = 1.1
                self.card2.scale_factor_y = 0.9
                
                self.card1.angle = self.final_angle1
                self.card2.angle = self.final_angle2
                self.impact_done = True
            
            # Fade out impact squash
            self.card1.scale_factor_x = 1.1 - 0.1 * p
            self.card1.scale_factor_y = 0.9 + 0.1 * p
            self.card2.scale_factor_x = 1.1 - 0.1 * p
            self.card2.scale_factor_y = 0.9 + 0.1 * p

        if t >= 1:
            # Reset state to original rotation and position
            self.card1.angle = self.start_angle1
            self.card2.angle = self.start_angle2
            self.card1.rect.center = self.start_pos1
            self.card2.rect.center = self.start_pos2
            self.card1.scale_factor_x = self.card1.scale_factor_y = 1.0
            self.card2.scale_factor_x = self.card2.scale_factor_y = 1.0
