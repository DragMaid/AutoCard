import pygame
from .animation import Animation
from gui.effects.manager import EffectManager
from gui.audio_manager import AudioManager


class MergeAnimation(Animation):
    def __init__(self, card1, card2, result_card, duration=1.0, on_finish=None):
        """
        - card1, card2: cards being merged
        - result_card: the new upgraded card
        - target_pos: tuple(x, y) for the result_card's slot in the matrix
        """
        super().__init__({card1, card2}, duration)
        self.card1 = card1
        self.card2 = card2
        self.result_card = result_card
        self.start_pos1 = pygame.Vector2(card1.rect.center)
        self.start_pos2 = pygame.Vector2(card2.rect.center)
        self.midpoint = (self.start_pos1 + self.start_pos2) / 2
        self.on_finish = on_finish
        self.impact_done = False

        # Hide result until merge finishes
        self.result_card.image.set_alpha(0)

    @staticmethod
    def _ease_in_out(x: float) -> float:
        # smoothstep
        return x * x * (3 - 2 * x)

    def _apply(self, t: float):
        p = self._ease_in_out(t)

        # Move old cards slightly toward each other (not necessarily exact midpoint)
        lean_factor = 0.3  # tweak to control how much they "lean in"
        self.card1.rect.center = self.start_pos1.lerp(
            self.midpoint, p * lean_factor)
        self.card2.rect.center = self.start_pos2.lerp(
            self.midpoint, p * lean_factor)

        # Fade out old cards
        alpha = int(255 * (1 - p))
        self.card1.image.set_alpha(alpha)
        self.card2.image.set_alpha(alpha)

        # Trigger merge effect once near end
        if not self.impact_done and t >= 0.8:
            EffectManager.spawn("merge", self.midpoint)
            AudioManager.play_sound("assets/sounds/merge.mp3")
            self.impact_done = True

        # Finish: hide old cards and show result card at its slot
        if t >= 1:
            self.result_card.image.set_alpha(255)
            if self.on_finish:
                self.on_finish(self.result_card)
