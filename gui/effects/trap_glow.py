import pygame
import math


class TrapGlowEffect(pygame.sprite.Sprite):
    def __init__(self, pos, duration=0.6):
        super().__init__()
        self.pos = pos
        self.duration = duration
        self.start_time = pygame.time.get_ticks()
        self.image = pygame.Surface((1, 1), pygame.SRCALPHA)  # placeholder
        self.rect = self.image.get_rect(center=pos)

    def update(self):
        elapsed = (pygame.time.get_ticks() - self.start_time) / 1000.0
        t = elapsed / self.duration
        if t >= 1:
            self.kill()
            return

        # Expansion + fade
        max_radius = 60
        radius = int(max_radius * t)
        alpha = int(255 * (1 - t))

        # Resize surface dynamically to fit circle
        size = radius * 2 + 10
        self.image = pygame.Surface((size, size), pygame.SRCALPHA)
        self.rect = self.image.get_rect(center=self.pos)

        # Glow layers
        pygame.draw.circle(
            self.image,
            (255, 0, 200, alpha),
            (size // 2, size // 2),
            radius
        )
        pygame.draw.circle(
            self.image,
            (200, 0, 255, alpha // 2),
            (size // 2, size // 2),
            int(radius * 0.7)
        )


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
            (255, 255, 0, alpha), # Yellowish pulse for triggerable
            (50, 50),
            radius,
            width=2
        )

