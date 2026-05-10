from abc import ABC, abstractmethod
from core.game_info.effect_tracker import EffectType
from core.game_info.events import TrapTriggerEvent
from core.cards.trap_card import ActivateCondition
from typing import Tuple
from .utils import log_action


class TrapPolicy(ABC):
    @abstractmethod
    def can_handle(self, ability: str) -> bool:
        ...

    @abstractmethod
    def resolve(self, engine, trap, target) -> tuple[bool, str | None]:
        """Returns (result, effect_desc)"""
        ...


class DebuffEnemyAtkPolicy(TrapPolicy):
    def can_handle(self, ability: str) -> bool:
        return ability == "debuff_enemy_atk"

    def resolve(self, engine, trap, attacker):
        engine.effect_tracker.add_effect(
            EffectType.DEBUFF, attacker.id, "atk", trap.value, trap.duration, engine.game_state)
        trap.reveal()
        engine.event_logger.add_event(
            TrapTriggerEvent(trap.id, attacker.id))
        engine.move_card_to_graveyard(trap.id)
        return False, f"{attacker.name} ATK -{trap.value} for {trap.duration} turns"


class DebuffEnemyDefPolicy(TrapPolicy):
    def can_handle(self, ability: str) -> bool:
        return ability == "debuff_enemy_def"

    def resolve(self, engine, trap, attacker):
        engine.effect_tracker.add_effect(
            EffectType.DEBUFF, attacker.id, "defend", trap.value, trap.duration, engine.game_state)
        trap.reveal()
        engine.event_logger.add_event(
            TrapTriggerEvent(trap.id, attacker.id))
        engine.move_card_to_graveyard(trap.id)
        return False, f"{attacker.name} DEF -{trap.value} for {trap.duration} turns"


class DodgeAttackPolicy(TrapPolicy):
    def can_handle(self, ability: str) -> bool:
        return ability == "dodge_attack"

    def resolve(self, engine, trap, attacker):
        attacker.has_attack = True
        engine.move_card_to_graveyard(trap.id)
        trap.reveal()
        engine.event_logger.add_event(
            TrapTriggerEvent(trap.id, attacker.id))
        return True, "Attack negated"


class ReflectAttackPolicy(TrapPolicy):
    def can_handle(self, ability: str) -> bool:
        return ability == "reflect_attack"

    def resolve(self, engine, trap, attacker):
        engine.move_card_to_graveyard(attacker.id)
        engine.move_card_to_graveyard(trap.id)
        trap.reveal()
        engine.event_logger.add_event(
            TrapTriggerEvent(trap.id, attacker.id))
        return True, "Attack reflected, attacker destroyed"


class DebuffDefendTogglePolicy(TrapPolicy):
    def can_handle(self, ability: str) -> bool:
        return ability == "debuff_defend_toggle"

    def resolve(self, engine, trap, toggled_card):
        engine.effect_tracker.add_effect(
            EffectType.DEBUFF, toggled_card.id, "defend",
            trap.value, trap.duration, engine.game_state)
        engine.event_logger.add_event(
            TrapTriggerEvent(trap.id, toggled_card.id))
        engine.move_card_to_graveyard(trap.id)
        engine.logger.info(f"[TRAP] {trap.name} debuffed {
                           toggled_card.name} DEF")
        return True, None


class DebuffSummonPolicy(TrapPolicy):
    def can_handle(self, ability: str) -> bool:
        return ability == "debuff_summon"

    def resolve(self, engine, trap, summoned_card):
        for stat in ("atk", "defend"):
            engine.effect_tracker.add_effect(
                EffectType.DEBUFF, summoned_card.id, stat,
                trap.value, trap.duration, engine.game_state)
        engine.event_logger.add_event(
            TrapTriggerEvent(trap.id, summoned_card.id))
        engine.move_card_to_graveyard(trap.id)
        engine.logger.info(f"[TRAP] {trap.name} debuffed {summoned_card.name}")
        return True, None


ATTACK_POLICIES: list[TrapPolicy] = [
    DebuffEnemyAtkPolicy(),
    DebuffEnemyDefPolicy(),
    DodgeAttackPolicy(),
    ReflectAttackPolicy(),
]

TOGGLE_POLICIES: list[TrapPolicy] = [
    DebuffDefendTogglePolicy(),
]

SUMMON_POLICIES: list[TrapPolicy] = [
    DebuffSummonPolicy(),
]


class TrapEngine:
    def __init__(self, game_engine):
        self.game_engine = game_engine
        self.condition_rule_map = {
            ActivateCondition.TOGGLE: self.game_engine.rule_engine.get_toggle_traps,
            ActivateCondition.ATTACK: self.game_engine.rule_engine.get_attack_traps,
            ActivateCondition.SUMMON: self.game_engine.rule_engine.get_summon_traps,
        }
        self.condition_resolve_map = {
            ActivateCondition.TOGGLE: self._resolve_toggle_trap,
            ActivateCondition.ATTACK: self._resolve_attack_trap,
            ActivateCondition.SUMMON: self._resolve_summon_trap
        }

    def _resolve_with_policies(self, policies: list[TrapPolicy], trap_id: str, target_id: str) -> bool:
        trap = self.game_engine.game_state.get_card_by_id(trap_id)
        target = self.game_engine.game_state.get_card_by_id(target_id)

        if not trap or not target:
            return False, "Targetted trap or card does not exists"

        for policy in policies:
            if policy.can_handle(trap.ability):
                result, effect_desc = policy.resolve(
                    self.game_engine, trap, target)
                return result, effect_desc

        return False, "No policy can resolve this scenario"

    def _resolve_attack_trap(self, trap_id: str, attacker_id: str) -> bool:
        trap = self.game_engine.game_state.get_card_by_id(trap_id)
        attacker = self.game_engine.game_state.get_card_by_id(attacker_id)

        if not trap or trap.ctype != "trap" or not attacker:
            return False

        return self._resolve_with_policies(ATTACK_POLICIES, trap_id, attacker_id)

    def _resolve_toggle_trap(self, trap_id: str, toggled_card_id: str) -> bool:
        return self._resolve_with_policies(TOGGLE_POLICIES, trap_id, toggled_card_id)

    def _resolve_summon_trap(self, trap_id: str, summoned_card_id: str) -> bool:
        return self._resolve_with_policies(SUMMON_POLICIES, trap_id, summoned_card_id)

    def check_traps(self, condition: ActivateCondition, **kwargs) -> bool:
        triggerable = self.condition_rule_map[condition](**kwargs)
        for trap_id, target_id, trigger_type in triggerable:
            self.game_engine.game_state.triggerable_traps[trap_id] = {
                "target_id": target_id, "trigger_type": trigger_type}

            trap = self.game_engine.game_state.get_card_by_id(trap_id)
            trap.triggerable = True
        return len(triggerable) > 0

    def get_triggerable_traps(self) -> list:
        return list(self.game_engine.game_state.triggerable_traps.keys())

    def has_triggerable_traps(self) -> bool:
        return len(self.game_engine.game_state.triggerable_traps) > 0

    def resolve_traps(self):
        cancel_resolve = False
        for card_id in list(self.game_engine.game_state.activated_traps):
            target_id, trigger_type = self.game_engine.game_state.triggerable_traps[card_id].values(
            )
            status, log = self.condition_resolve_map[trigger_type](
                card_id, target_id)
            cancel_resolve = cancel_resolve or status
            trap = self.game_engine.game_state.get_card_by_id(card_id)
            log_action(**{
                "action_type": "RESOLVE_TRAP",
                "player_id": trap.owner_id,
                "success": True,
                "details": {"description": log}
            })
            del self.game_engine.game_state.triggerable_traps[card_id]

        for card_id in self.game_engine.game_state.triggerable_traps:
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
        if not trap or trap.ctype != "trap":
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
