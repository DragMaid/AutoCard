import math
import pygame
from gui.effects.manager import EffectManager
from .animation import Animation


class TrapTriggerableAnimation(Animation):
    def __init__(self, trap_card, duration=0.8):
        super().__init__({trap_card}, duration)
        self.card = trap_card
        self.start_pos = pygame.Vector2(trap_card.rect.center)
        self.effect_spawned = False

    def _apply(self, t):
        # Pulsing scale effect
        pulse = math.sin(t * math.pi) * 0.05
        self.card.scale_factor_y = 1.0 + pulse
        
        if t >= 0.2 and not self.effect_spawned:
            EffectManager.spawn("trap-pulse", self.start_pos)
            self.effect_spawned = True
            
        if t >= 1.0:
            self.card.scale_factor_y = 1.0
