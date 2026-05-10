import pygame
import math


class TrapPulseEffect(pygame.sprite.Sprite):
    def __init__(self, pos, duration=0.8):
        super().__init__()
        self.pos = pos
        self.duration = duration
        self.start_time = pygame.time.get_ticks()
        self.image = pygame.Surface((100, 100), pygame.SRCALPHA)
        self.rect = self.image.get_rect(center=pos)

    def update(self):
        elapsed = (pygame.time.get_ticks() - self.start_time) / 1000.0
        t = elapsed / self.duration
        if t >= 1:
            self.kill()
            return

        # Pulsing ring effect
        alpha = int(180 * math.sin(t * math.pi))
        radius = int(40 + 20 * t)

        self.image.fill((0, 0, 0, 0))
        pygame.draw.circle(
            self.image,
            (255, 255, 0, alpha),
            (50, 50),
            radius,
            width=2
        )
