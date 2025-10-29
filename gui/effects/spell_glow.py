import random
import pygame
import math


class SpellGlowEffect(pygame.sprite.Sprite):
    def __init__(self, pos, duration=0.6, particle_count=15):
        super().__init__()
        self.pos = pygame.Vector2(pos)
        self.duration = duration
        self.start_time = pygame.time.get_ticks()
        self.particles = []
        for _ in range(particle_count):
            angle = random.uniform(0, 2*math.pi)
            speed = random.uniform(40, 120)
            self.particles.append({
                "angle": angle,
                "speed": speed,
                "radius": random.randint(3, 6)
            })
        self.image = pygame.Surface((1, 1), pygame.SRCALPHA)
        self.rect = self.image.get_rect(center=pos)

    def update(self):
        elapsed = (pygame.time.get_ticks() - self.start_time) / 1000.0
        t = elapsed / self.duration
        if t >= 1:
            self.kill()
            return

        self.image = pygame.Surface((160, 160), pygame.SRCALPHA)
        self.rect = self.image.get_rect(center=self.pos)
        alpha = int(255 * (1 - t))
        for p in self.particles:
            dx = math.cos(p["angle"]) * p["speed"] * t
            dy = math.sin(p["angle"]) * p["speed"] * t
            pygame.draw.circle(
                self.image,
                (0, 200, 255, alpha),
                (int(80 + dx), int(80 + dy)),
                p["radius"]
            )
