import pygame
from .impact import ImpactEffect
from .trap_glow import TrapGlowEffect
from .spell_glow import SpellGlowEffect
from .merge import MergeEffect
from .player_hit import HitPlayerEffect


class EffectManager:
    effects_group = pygame.sprite.Group()
    train_mode = False

    def __init__(self, train_mode=False):
        self.train_mode = train_mode

    @classmethod
    def set_train_mode(cls, mode):
        cls.train_mode = mode

    @classmethod
    def spawn(cls, effect_type, arg):
        """Spawn a visual effect with optional duration control."""
        if cls.train_mode:
            return

        if effect_type == "slam":
            cls.effects_group.add(ImpactEffect(arg))
        elif effect_type == "trap-glow":
            cls.effects_group.add(TrapGlowEffect(arg))
        elif effect_type == "spell-glow":
            cls.effects_group.add(SpellGlowEffect(arg))
        elif effect_type == "merge":
            cls.effects_group.add(MergeEffect(arg))
        elif effect_type == "hit_player":
            cls.effects_group.add(HitPlayerEffect(arg))
        else:
            return  # silently ignore unknown types

    @classmethod
    def update(cls):
        cls.effects_group.update()

    @classmethod
    def draw(cls, screen):
        cls.effects_group.draw(screen)
