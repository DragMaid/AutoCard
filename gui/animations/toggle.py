import pygame
from .animation import Animation


class ToggleRotateAnimation(Animation):
    def __init__(self,
                 sprite,
                 duration=1.0,
                 start_angle=0,
                 end_angle=180,
                 on_finished=None):
        """
        sprite      : the pygame.sprite.Sprite to animate
        duration    : total time for the rotation
        start_angle : initial rotation angle (degrees)
        end_angle   : target rotation angle (degrees)
        """
        super().__init__({sprite}, duration)
        self.sprite = sprite
        self.start_angle = start_angle
        self.end_angle = end_angle
        self.on_finished = on_finished
        self.callback_done = False

    @staticmethod
    def _ease_in_out(x):
        return 3*x**2 - 2*x**3  # smoothstep easing

    def _apply(self, t):
        p = self._ease_in_out(t)
        self.sprite.angle = self.start_angle + (self.end_angle - self.start_angle) * p

        # Trigger sound/callback slightly before end
        if t >= 0.8 and not self.callback_done:
            if self.on_finished:
                self.on_finished()
            self.callback_done = True
