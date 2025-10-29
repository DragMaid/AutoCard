import pygame


class MergeEffect(pygame.sprite.Sprite):
    def __init__(self, pos, duration=0.6):
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

        # Fade + expansion curve
        alpha = int(255 * (1 - t))
        radius = int(20 + 80 * t)  # starts smaller, grows faster

        # resize surface
        size = radius * 2 + 20
        self.image = pygame.Surface((size, size), pygame.SRCALPHA)
        self.rect = self.image.get_rect(center=self.pos)

        # inner bright core
        pygame.draw.circle(
            self.image,
            (255, 255, 180, alpha),
            (size // 2, size // 2),
            max(1, int(radius * 0.4)),
        )

        # middle ring
        pygame.draw.circle(
            self.image,
            (255, 230, 120, alpha),
            (size // 2, size // 2),
            max(1, int(radius * 0.7)),
            4
        )

        # outer shimmering ring
        pygame.draw.circle(
            self.image,
            (255, 200, 80, int(alpha * 0.7)),
            (size // 2, size // 2),
            radius,
            3
        )
