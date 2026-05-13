from __future__ import annotations

from abc import ABC, abstractmethod
from core.cards.card import CardType
from core.cards.monster_card import MonsterCard
from core.data.effects import EffectType
from core.data.events import TrapTriggerEvent, TrapTriggerableEvent
from core.cards.trap_card import ActivateCondition, TrapAbility
from typing import Tuple, List, Optional, TYPE_CHECKING
from .utils import log_action

if TYPE_CHECKING:
    from core.logic.game_engine import GameEngine


class TrapPolicy(ABC):
    """
    Abstract base class defining the resolution strategy for a trap's effect.
    """
    @abstractmethod
    def resolve(self, engine: GameEngine, target: MonsterCard, **kwargs) -> tuple[bool, Optional[str]]:
        """
        Resolves the trap effect against a target.

        Args:
            engine (GameEngine): The main game engine instance.
            target (MonsterCard): The card being targeted by the trap.
            **kwargs: Additional parameters such as effect value or duration.

        Returns:
            tuple[bool, Optional[str]]: A tuple containing a boolean indicating if the 
            attack should be cancelled and a description of the resolution.
        """
        raise NotImplementedError


class DebuffAttackPolicy(TrapPolicy):
    """Policy to apply an attack debuff."""

    def resolve(self, engine, target, value, duration):
        engine.effect_tracker.add_effect(
            EffectType.DEBUFF, target.id, "atk", value, duration, engine.game_state)
        return False, f"{target.name} ATK -{value} for {duration} turns"


class DebuffDefendPolicy(TrapPolicy):
    """Policy to apply a defense debuff."""

    def resolve(self, engine, target, value, duration):
        engine.effect_tracker.add_effect(
            EffectType.DEBUFF, target.id, "defend", value, duration, engine.game_state)
        return False, f"{target.name} DEF -{value} for {duration} turns"


class DodgeAttackPolicy(TrapPolicy):
    """Policy to negate an incoming attack."""

    def resolve(self, engine, attacker):
        attacker.has_attacked = True
        return True, f"Attack negated from {attacker.name}"


class ReflectAttackPolicy(TrapPolicy):
    """Policy to destroy the attacking card."""

    def resolve(self, engine, trap, attacker):
        engine.move_card_to_graveyard(attacker.id)
        return True, f"Attack reflected, attacker {attacker.name} destroyed"


class TrapEngine:
    """
    Orchestrates trap placement, trigger checking, and effect resolution.
    """

    def __init__(self, game_engine: GameEngine):
        """
        Initializes the TrapEngine.

        Args:
            game_engine (GameEngine): The main game engine instance.
        """
        self.game_engine = game_engine
        self.ABILITY_POLICY = {
            TrapAbility.REFLECT_ATTACK: ReflectAttackPolicy,
            TrapAbility.DODGE_ATTACK: DodgeAttackPolicy,
            TrapAbility.DEBUFF_ATTACK: DebuffAttackPolicy,
            TrapAbility.DEBUFF_DEFEND: DebuffDefendPolicy
        }

    def resolve(self, trap_id: str, target_id: str) -> Tuple[bool, Optional[str]]:
        """
        Resolves a triggered trap's effect.

        Args:
            trap_id (str): The ID of the trap card being resolved.
            target_id (str): The ID of the target card.

        Returns:
            Tuple[bool, Optional[str]]: Whether the action was cancelled and the resolution description.
        """
        trap = self.game_engine.game_state.get_card_by_id(trap_id)
        target = self.game_engine.game_state.get_card_by_id(trap_id)

        # NOTE: Just stop if this is the case
        if not trap or not target:
            raise

        if not (trap.effectiveness and trap.duration):
            cancel, desc = self.ABILITY_POLICY[trap.ability[0]].resolve(
                self.game_engine, target)
        else:
            for ability, effectiveness, duration in zip(trap.abilities, trap.effectiveness, trap.duration):
                cancel, desc = self.ABILITY_POLICY[ability].resolve(
                    self.game_engine, target, effectiveness, duration)

        trap.reveal()
        self.game_engine.event_logger.add_event(
            TrapTriggerEvent(trap_id, target_id))
        self.game_engine.move_card_to_graveyard(trap_id)
        return cancel, desc

    def check_traps(
        self,
        *,
        target_id: str,
        condition: ActivateCondition,
        **kwargs
    ) -> bool:
        """
        Identifies and marks potential traps that can be triggered.

        Args:
            target_id (str): The ID of the targeted card or player.
            condition (ActivateCondition): The game event condition.

        Returns:
            bool: True if traps were found to be triggerable, False otherwise.
        """
        triggerables = self._get_triggerable_traps(
            target_id=target_id, activation=condition)
        for trap_id, target_id in triggerables:
            self.game_engine.game_state.triggerable_traps[trap_id] = {
                "target_id": target_id}
            trap = self.game_engine.game_state.get_card_by_id(trap_id)
            trap.triggerable = True
            self.game_engine.event_logger.add_event(
                TrapTriggerableEvent(trap_id))
        return len(triggerables) > 0

    def get_triggerable_traps(self) -> list:
        """Returns IDs of currently triggerable traps."""
        return list(self.game_engine.game_state.triggerable_traps.keys())

    def has_triggerable_traps(self) -> bool:
        """Checks if there are any pending triggerable traps."""
        return len(self.game_engine.game_state.triggerable_traps) > 0

    def resolve_traps(self):
        """
        Processes all traps currently activated by the player.

        Returns:
            bool: Whether any trap cancelled the triggering action.
        """
        cancel_resolve = False
        trigger_map = self.game_engine.game_state.triggerable_traps
        for card_id in self.game_engine.game_state.activated_traps:
            target_id = trigger_map[card_id]["target_id"]
            status, log = self.resolve(card_id, target_id)
            cancel_resolve = cancel_resolve or status
            trap = self.game_engine.game_state.get_card_by_id(card_id)
            log_action(**{
                "action_type": "RESOLVE_TRAP",
                "player_id": trap.owner_id,
                "success": True,
                "details": {"description": log}
            })
            del trigger_map[card_id]

        for card_id in trigger_map.keys():
            trap = self.game_engine.game_state.get_card_by_id(card_id)
            trap.triggerable = False

        self.game_engine.game_state.triggerable_traps.clear()
        self.game_engine.game_state.activated_traps.clear()
        return cancel_resolve

    def set_trap(self, trap_id: str, position: Tuple[int, int] | None, check=True) -> bool:
        """Set a trap card face-down on the field"""
        trap = self.game_engine.game_state.get_card_by_id(trap_id)
        log = {"action_type": "SET_TRAP",
               "player_id": trap.owner_id, "success": False}
        if not trap or trap.card_type != CardType.TRAP:
            log["details"] = {
                "trap": trap.name,
                "reason": "This is not a trap"
            }
            log_action(**log)
            return False

        can_set = self.game_engine.rule_engine.can_summon(
            trap.owner_id,
            trap_id,
            self.game_engine.game_state.field_matrix,
            position) or not check

        if not can_set:
            log["details"] = {
                "trap": trap.name,
                "position": position,
                "reason": "Cannot set trap (already set one or no space)"
            }
            log_action(**log)
            return False

        if position is None:
            position = self.game_engine.game_state.get_random_empty_slot(
                trap.owner_id)
            if position is None:
                log["details"] = {
                    "trap": trap.name,
                    "reason": "No empty slots available"
                }
                log_action(**log)
                return False

        # Place trap face-down
        self.game_engine.game_state.player_info[trap.owner_id]["held_cards"].remove(
            trap_id)
        self.game_engine.game_state.modify_field("add", trap, position)
        self.game_engine.game_state.player_info[trap.owner_id]["has_summoned_trap"] = True
        trap.is_placed = True
        trap.is_face_down = True
        trap.pos_in_matrix = position

        log["success"] = True
        log["details"] = {
            "trap": trap.name,
            "ability": trap.ability,
            "position": position,
            "state": "face-down"
        }
        log_action(**log)
        return True

    def _get_triggerable_traps(
        self,
        *,
        target_id: str,
        activation: ActivateCondition,
    ) -> List[Tuple[str, str]]:
        """
        Finds traps owned by opponents matching the activation condition.

        Args:
            target_id (str): The ID of the triggering target.
            activation (ActivateCondition): The activation trigger.

        Returns:
            List[Tuple[str, str]]: A list of tuples containing (trap_id, target_id).
        """

        triggerable = []

        owner_id = self.game_engine.game_state.get_card_by_id(target_id)
        opponent_ids = [
            pid
            for pid in self.game_state.player_info
            if pid != owner_id
        ]

        for opponent_id in opponent_ids:
            for card in self.game_state.get_player_cards(opponent_id):

                if card.card_type != CardType.TRAP:
                    continue

                if card.is_triggered:
                    continue

                if card.activation != activation:
                    continue

                triggerable.append((card.id, target_id))

        return triggerable
