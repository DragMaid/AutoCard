from abc import ABC, abstractmethod
from core.game_info.effect_tracker import EffectType
from core.game_info.events import TrapTriggerEvent
from core.cards.trap_card import ActivateCondition
from typing import Tuple


class TrapPolicy(ABC):
    @abstractmethod
    def can_handle(self, ability: str) -> bool:
        ...

    @abstractmethod
    def resolve(self, engine: "TrapEngine", trap, target) -> tuple[bool, str | None]:
        """Returns (result, effect_desc)"""
        ...


class DebuffEnemyAtkPolicy(TrapPolicy):
    def can_handle(self, ability: str) -> bool:
        return ability == "debuff_enemy_atk"

    def resolve(self, engine, trap, attacker):
        engine.effect_tracker.add_effect(
            EffectType.DEBUFF, attacker.id, "atk", trap.value, trap.duration, engine.game_state)
        trap.reveal()
        engine.event_logger.add_event(TrapTriggerEvent(trap.id, attacker.id))
        engine.move_card_to_graveyard(trap.id)
        return False, f"{attacker.name} ATK -{trap.value} for {trap.duration} turns"


class DebuffEnemyDefPolicy(TrapPolicy):
    def can_handle(self, ability: str) -> bool:
        return ability == "debuff_enemy_def"

    def resolve(self, engine, trap, attacker):
        engine.effect_tracker.add_effect(
            EffectType.DEBUFF, attacker.id, "defend", trap.value, trap.duration, engine.game_state)
        trap.reveal()
        engine.event_logger.add_event(TrapTriggerEvent(trap.id, attacker.id))
        engine.move_card_to_graveyard(trap.id)
        return False, f"{attacker.name} DEF -{trap.value} for {trap.duration} turns"


class DodgeAttackPolicy(TrapPolicy):
    def can_handle(self, ability: str) -> bool:
        return ability == "dodge_attack"

    def resolve(self, engine, trap, attacker):
        attacker.has_attack = True
        engine.move_card_to_graveyard(trap.id)
        trap.reveal()
        engine.event_logger.add_event(TrapTriggerEvent(trap.id, attacker.id))
        return True, "Attack negated"


class ReflectAttackPolicy(TrapPolicy):
    def can_handle(self, ability: str) -> bool:
        return ability == "reflect_attack"

    def resolve(self, engine, trap, attacker):
        engine.move_card_to_graveyard(attacker.id)
        engine.move_card_to_graveyard(trap.id)
        trap.reveal()
        engine.event_logger.add_event(TrapTriggerEvent(trap.id, attacker.id))
        return True, "Attack reflected, attacker destroyed"


class DebuffDefendTogglePolicy(TrapPolicy):
    def can_handle(self, ability: str) -> bool:
        return ability == "debuff_defend_toggle"

    def resolve(self, engine, trap, toggled_card):
        engine.effect_tracker.add_effect(
            EffectType.DEBUFF, toggled_card.id, "defend",
            trap.value, trap.duration, engine.game_state)
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
    def __init__(self, game_state, event_logger, rule_engine):
        self.game_state = game_state
        self.event_logger = event_logger
        self.rule_engine = rule_engine
        self.condition_rule_map = {
            ActivateCondition.TOGGLE: self.rule_engine.get_toggle_traps,
            ActivateCondition.ATTACK: self.rule_engine.get_attack_traps,
            ActivateCondition.SUMMON: self.rule_engine.get_toggle_traps,
        }
        self.condition_resolve_map = {
            ActivateCondition.TOGGLE: self._resolve_toggle_trap,
            ActivateCondition.ATTACK: self._resolve_attack_trap,
            ActivateCondition.SUMMON: self._resolve_summon_trap
        }

    def _resolve_with_policies(self, policies: list[TrapPolicy], trap_id: str, target_id: str) -> bool:
        trap = self.game_state.get_card_by_id(trap_id)
        target = self.game_state.get_card_by_id(target_id)

        if not trap or not target:
            return False

        for policy in policies:
            if policy.can_handle(trap.ability):
                result, effect_desc = policy.resolve(self, trap, target)
                if effect_desc:
                    print(f"Effect: {effect_desc}")
                return result

        return False

    def _resolve_attack_trap(self, trap_id: str, attacker_id: str) -> bool:
        trap = self.game_state.get_card_by_id(trap_id)
        attacker = self.game_state.get_card_by_id(attacker_id)

        if not trap or trap.ctype != "trap" or not attacker:
            return False

        print(f"TRAP ACTIVATED: {trap.name} (Owner: {trap.owner_id})")
        print(f"Trigger: {attacker.name} (Owner: {attacker.owner_id})")

        return self._resolve_with_policies(ATTACK_POLICIES, trap_id, attacker_id)

    def _resolve_toggle_trap(self, trap_id: str, toggled_card_id: str) -> bool:
        return self._resolve_with_policies(TOGGLE_POLICIES, trap_id, toggled_card_id)

    def _resolve_summon_trap(self, trap_id: str, summoned_card_id: str) -> bool:
        return self._resolve_with_policies(SUMMON_POLICIES, trap_id, summoned_card_id)

    def check_traps(self, condition: ActivateCondition, **kwargs) -> bool:
        triggerable = self.condition_rule_map[condition](**kwargs)
        for trap_id, target_id, trigger_type in triggerable:
            self.game_state.triggerable_traps[trap_id] = {
                "target_id": target_id, "trigger_type": trigger_type}
        return len(triggerable) > 0

    def get_triggerable_traps(self) -> list:
        return list(self.game_state.triggerable_traps.keys())

    def has_triggerable_traps(self) -> bool:
        return len(self.game_state.triggerable_traps) > 0

    def resolve_traps(self):
        for card_id in self.game_state.activated_traps:
            target_id, trigger_type = self.game_state.triggerable_traps[card_id]
            self.condition_resolve_map[trigger_type](card_id, target_id)
            del self.game_state.triggerable_traps[card_id]

        for card_id in self.game_state.triggerable_traps:
            trap = self.game_state.get_card_by_id(card_id)
            trap.is_face_down = True
            trap.triggerable = False

        self.game_state.activated_traps.clear()

    def set_trap(self, trap_id: str, position: Tuple[int, int] | None, check=True) -> Tuple[bool, dict]:
        """Set a trap card face-down on the field"""
        trap = self.game_state.get_card_by_id(trap_id)
        log = {"action_type": "SET_TRAP", "player_id": trap.owner_id}
        if not trap or trap.ctype != "trap":
            return False, log

        can_set = self.rule_engine.can_summon(
            trap.owner_id, trap_id, self.game_state.field_matrix, position) or not check

        if not can_set:
            log["success"] = False
            log["details"] = {
                "trap": trap.name,
                "position": position,
                "reason": "Cannot set trap (already set one or no space)"
            }
            return False, log

        if position is None:
            position = self.game_state.get_random_empty_slot(trap.owner_id)
            if position is None:
                log["success"] = False
                log["details"] = {
                    "trap": trap.name,
                    "reason": "No empty slots available"
                }
                return False

        # Place trap face-down
        self.game_state.player_info[trap.owner_id]["held_cards"].remove(
            trap_id)
        self.game_state.modify_field("add", trap, position)
        self.game_state.player_info[trap.owner_id]["has_summoned_trap"] = True
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
        return True, log
