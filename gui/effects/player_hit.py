import pygame


class HitPlayerEffect(pygame.sprite.Sprite):
    def __init__(self, game_area, duration=0.3):
        super().__init__()
        self.game_area = game_area
        self.duration = duration
        self.start_time = pygame.time.get_ticks()

        # Initial surface same size as GameArea rect
        self.image = pygame.Surface(self.game_area.rect.size, pygame.SRCALPHA)
        self.rect = self.image.get_rect(topleft=self.game_area.rect.topleft)

    def update(self):
        elapsed = (pygame.time.get_ticks() - self.start_time) / 1000.0
        t = elapsed / self.duration
        if t >= 1:
            self.kill()
            return

        # Fade alpha from 180 → 0 over duration
        alpha = int(180 * (1 - t))

        # Red fill
        self.image.fill((255, 0, 0, alpha))
