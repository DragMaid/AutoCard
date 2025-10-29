from .animation import Animation


class DeathAnimation(Animation):
    def __init__(self, sprite, duration, on_finish):
        super().__init__({sprite}, duration)
        self.sprite = sprite
        self.on_finish = on_finish

    def _apply(self, t):
        alpha = 255 * (1 - t)
        self.sprite.image.set_alpha(alpha)

    def update(self, dt):
        super().update(dt)
        if self.is_finished and self.on_finish:
            self.on_finish()
