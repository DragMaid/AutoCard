from core.data.game_state import GameState
from enum import Enum
from typing import List
from pydantic import BaseModel
from core.cards.card import Card


class EffectType(Enum):
    """Different types of effects a spell can apply"""
    BUFF = "BUFF"
    DEBUFF = "DEBUFF"


class Effect(BaseModel):
    """Represents a single active effect"""
    effect_type: EffectType
    stat: str
    target_id: str
    value: int
    duration: int
    remaining: int


class EffectPolicy:
    """Base class for implementing effect management."""

    def apply(self, card: Card, effect: Effect, game_state: GameState):
        raise NotImplementedError

    def remove(self, card: Card, effect: Effect, game_state: GameState):
        raise NotImplementedError


class BuffPolicy(EffectPolicy):
    def apply(self, target, effect, game_state):
        setattr(target, effect.stat,
                getattr(target, effect.stat) + effect.value)

    def remove(self, target, effect, game_state):
        setattr(target, effect.stat,
                getattr(target, effect.stat) - effect.value)


class DebuffPolicy(EffectPolicy):
    def apply(self, target, effect, game_state):
        # NOTE: update effect effectiveness so it wouldn't buff the card
        # ex: 500 atk -> -100 atk -> 0 atk -> 500 atk instead of 600 atk
        new_stat = getattr(target, effect.stat) - effect.value
        new_stat_filtered = max(new_stat, 0)
        effect.value = abs(new_stat_filtered - new_stat)
        setattr(target, effect.stat, new_stat_filtered)

    def remove(self, target, effect, game_state):
        setattr(target, effect.stat,
                getattr(target, effect.stat) + effect.value)


class EffectTracker:
    """Tracks active spell/ability effects and their duration"""
    EFFECT_MAP = {
        EffectType.BUFF: BuffPolicy,
        EffectType.DEBUFF: DebuffPolicy
    }

    def __init__(self):
        self.active_effects: List[Effect] = []

    def add_effect(
        self,
        effect_type: EffectType,
        target_id: str,
        stat: str,
        value: int,
        duration: int,
        game_state: GameState
    ):
        """Add a new timed effect and apply it immediately"""
        effect = Effect(
            effect_type=effect_type,
            stat=stat,
            target_id=target_id,
            value=value,
            duration=duration,
            remaining=duration,
        )

        self._apply_effect(effect, game_state)
        self.active_effects.append(effect)

    def update_round(self, game_state: GameState):
        """Advance to the next round and expire old effects"""
        expired_effects = []

        for effect in self.active_effects:
            effect.remaining -= 1
            if effect.remaining <= 0:
                expired_effects.append(effect)

        # Remove expired
        for effect in expired_effects:
            if game_state:
                self._remove_effect(effect, game_state)
            self.active_effects.remove(effect)

    def _apply_effect(self, effect: Effect, game_state: GameState):
        """Apply the effect to the target"""
        target = game_state.get_card_by_id(effect.target_id)
        if target and hasattr(target, effect.stat):
            self.EFFECT_MAP[effect.effect_type].apply(target, effect, game_state)

    def _remove_effect(self, effect: Effect, game_state: GameState):
        """Revert the effect when it expires"""
        target = game_state.get_card_by_id(effect.target_id)
        if target and hasattr(target, effect.stat):
            self.EFFECT_MAP[effect.effect_type].remove(target, effect, game_state)

    def get_effects_on_target(self, target_id: str) -> List[Effect]:
        """Get all active effects on a monster"""
        return [e for e in self.active_effects if e.target_id == target_id]

    def clear_all_effects(self, game_state: 'GameState' = None):
        """Clear all active effects immediately"""
        for effect in self.active_effects:
            if game_state:
                self._remove_effect(effect, game_state)
        self.active_effects.clear()
