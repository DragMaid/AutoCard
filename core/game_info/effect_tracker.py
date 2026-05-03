from core.game_info.game_state import GameState
from dataclasses import dataclass
from enum import Enum
from typing import List


class EffectType(Enum):
    """Different types of effects a spell can apply"""
    BUFF = "BUFF"
    DEBUFF = "DEBUFF"
    INSTANT = "INSTANT"  # one-time effects like destroy, heal, etc.


@dataclass
class Effect:
    """Represents a single active effect"""
    effect_type: EffectType
    stat: str            # e.g. "atk", "defense"
    target_id: str
    value: int
    duration: int        # how many rounds it lasts
    rounds_remaining: int


class EffectTracker:
    """Tracks active spell/ability effects and their duration"""

    def __init__(self):
        self.active_effects: List[Effect] = []

    def add_effect(self,
                   effect_type: EffectType,
                   target_id: str,
                   stat: str,
                   value: int,
                   duration: int,
                   game_state: GameState):
        """Add a new timed effect and apply it immediately"""
        effect = Effect(
            effect_type=effect_type,
            stat=stat,
            target_id=target_id,
            value=value,
            duration=duration,
            rounds_remaining=duration,
        )

        self._apply_effect(effect, game_state)
        self.active_effects.append(effect)

    def apply_instant_effect(self,
                             effect_type: EffectType,
                             target_id: str,
                             stat: str = "",
                             value: int = 0,
                             game_state: 'GameState' = None):
        """Apply a one-time effect like destroy or heal"""
        if effect_type == EffectType.INSTANT:
            target = game_state.get_card_by_id(target_id)
            if target and stat and hasattr(target, stat):
                setattr(target, stat, getattr(target, stat) + value)

    def update_round(self, game_state: 'GameState' = None):
        """Advance to the next round and expire old effects"""
        expired_effects = []

        for effect in self.active_effects:
            effect.rounds_remaining -= 1
            if effect.rounds_remaining <= 0:
                expired_effects.append(effect)

        # Remove expired
        for effect in expired_effects:
            if game_state:
                self._remove_effect(effect, game_state)
            self.active_effects.remove(effect)

    def _apply_effect(self, effect: Effect, game_state: 'GameState'):
        """Apply the effect to the target"""
        target = game_state.get_card_by_id(effect.target_id)
        if target and hasattr(target, effect.stat):
            if effect.effect_type == EffectType.BUFF:
                setattr(target, effect.stat,
                        getattr(target, effect.stat) + effect.value)
            elif effect.effect_type == EffectType.DEBUFF:
                setattr(target, effect.stat,
                        getattr(target, effect.stat) - effect.value)

    def _remove_effect(self, effect: Effect, game_state: 'GameState'):
        """Revert the effect when it expires"""
        target = game_state.get_card_by_id(effect.target_id)
        if target and hasattr(target, effect.stat):
            if effect.effect_type == EffectType.BUFF:
                setattr(target, effect.stat,
                        getattr(target, effect.stat) - effect.value)
            elif effect.effect_type == EffectType.DEBUFF:
                setattr(target, effect.stat,
                        getattr(target, effect.stat) + effect.value)

    def get_effects_on_target(self, target_id: str) -> List[Effect]:
        """Get all active effects on a monster"""
        return [e for e in self.active_effects if e.target_id == target_id]

    def clear_all_effects(self, game_state: 'GameState' = None):
        """Clear all active effects immediately"""
        for effect in self.active_effects:
            if game_state:
                self._remove_effect(effect, game_state)
        self.active_effects.clear()

    def get_round_info(self):
        return {"active_effects_count": len(self.active_effects)}

    def serialize(self):
        return [vars(e) for e in self.active_effects]

    def deserialize(self, content):
        for c in content:
            c["effect_type"] = EffectType(c["effect_type"])
        self.active_effects = [Effect(**c) for c in content]
