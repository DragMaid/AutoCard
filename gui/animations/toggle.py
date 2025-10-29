import pygame
from .animation import Animation


class ToggleRotateAnimation(Animation):
    def __init__(self,
                 sprite,
                 duration=1.0,
                 start_angle=0,
                 end_angle=180,
                 toggle=True,
                 on_finished=None):
        """
        sprite      : the pygame.sprite.Sprite to animate
        duration    : total time for one rotation/toggle cycle
        start_angle : initial rotation angle (degrees)
        end_angle   : target rotation angle (degrees)
        toggle      : True = rotate back and forth, False = continuous spin
        """
        super().__init__({sprite}, duration)
        self.sprite = sprite
        self.start_angle = start_angle
        self.end_angle = end_angle
        self.toggle = toggle
        self.current_angle = start_angle
        self.original_image = sprite.original_image
        self.forward = True  # used for toggling
        self.on_finished = on_finished

    @staticmethod
    def _ease_in_out(x):
        return 3*x**2 - 2*x**3  # smoothstep easing

    def _apply(self, t):
        if self.toggle:
            # Ping-pong rotation between start and end
            p = self._ease_in_out(t)
            if not self.forward:
                p = 1 - p
            self.current_angle = self.start_angle + \
                (self.end_angle - self.start_angle) * p

            if t >= 0.8:
                if self.on_finished:
                    self.on_finished()

            if t >= 1.0:
                self.forward = not self.forward
                self.elapsed = 0  # reset for next toggle
        else:
            # Continuous spin
            self.current_angle = (self.start_angle + 360 * t) % 360

        # Rotate sprite
        self.sprite.image = pygame.transform.rotate(
            self.original_image, -self.current_angle)
        self.sprite.rect = self.sprite.image.get_rect(
            center=self.sprite.rect.center)

        if self.is_finished and not self.toggle:
            # Reset if continuous rotation is finished
            self.sprite.image = self.original_image
