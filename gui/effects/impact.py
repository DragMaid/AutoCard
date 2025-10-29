import pygame


class ImpactEffect(pygame.sprite.Sprite):
    def __init__(self, pos, duration=0.4):
        super().__init__()
        self.pos = pos
        self.duration = duration
        self.start_time = pygame.time.get_ticks()
        self.image = pygame.Surface((1, 1), pygame.SRCALPHA)  # start tiny
        self.rect = self.image.get_rect(center=pos)

    def update(self):
        elapsed = (pygame.time.get_ticks() - self.start_time) / 1000.0
        t = elapsed / self.duration
        if t >= 1:
            self.kill()
            return

        alpha = int(255 * (1 - t))
        radius = int(30 + 90 * t)

        # resize surface to fit circle
        size = radius * 2 + 10
        self.image = pygame.Surface((size, size), pygame.SRCALPHA)
        self.rect = self.image.get_rect(center=self.pos)

        # redraw circle each frame
        pygame.draw.circle(
            self.image,
            (255, 255, 200, alpha),
            (size // 2, size // 2),
            radius,
            6
        )
