from abc import ABC, abstractmethod
from core.game_info.effect_tracker import EffectType
from core.game_info.events import SpellActiveEvent
from .utils import log_action


class SpellPolicy(ABC):
    @abstractmethod
    def can_execute(self, engine, spell, target_id):
        pass

    @abstractmethod
    def execute(self, engine, spell, target_id, details):
        pass


class DrawTwoCardsPolicy(SpellPolicy):
    def can_execute(self, engine, spell, target_id):
        return True

    def execute(self, engine, spell, target_id, details):
        engine.draw_card(spell.owner_id, check=False)
        engine.draw_card(spell.owner_id, check=False)
        details["effect"] = "Drew 2 cards"
        return True


class BuffAttackPolicy(SpellPolicy):
    def can_execute(self, engine, spell, target_id):
        if not target_id:
            return False
        target = engine.game_state.get_card_by_id(target_id)
        if target and target.ctype == "monster" and spell.owner_id != target.owner_id:
            log_action("CAST_SPELL", spell.owner_id, {
                "spell": spell.name,
                "reason": "Cannot target enemy monsters with buff spells"
            }, False)
            return False
        return True

    def execute(self, engine, spell, target_id, details):
        engine.effect_tracker.add_effect(
            EffectType.BUFF, target_id, "atk", spell.value, spell.duration, engine.game_state)
        target = engine.game_state.get_card_by_id(target_id)
        details["target"] = target.name if target else target_id
        details["effect"] = f"+{spell.value} ATK for {spell.duration} turns"
        return True


class BuffDefensePolicy(SpellPolicy):
    def can_execute(self, engine, spell, target_id):
        if not target_id:
            return False
        target = engine.game_state.get_card_by_id(target_id)
        if target and target.ctype == "monster" and spell.owner_id != target.owner_id:
            log_action("CAST_SPELL", spell.owner_id, {
                "spell": spell.name,
                "reason": "Cannot target enemy monsters with buff spells"
            }, False)
            return False
        return True

    def execute(self, engine, spell, target_id, details):
        engine.effect_tracker.add_effect(
            EffectType.BUFF, target_id, "defend", spell.value, spell.duration, engine.game_state)
        target = engine.game_state.get_card_by_id(target_id)
        details["target"] = target.name if target else target_id
        details["effect"] = f"+{spell.value} DEF for {spell.duration} turns"
        return True


class DestroyTrapPolicy(SpellPolicy):
    def can_execute(self, engine, spell, target_id):
        if not target_id:
            return False
        target = engine.game_state.get_card_by_id(target_id)
        if target and target.ctype == "trap" and spell.owner_id == target.owner_id:
            log_action("CAST_SPELL", spell.owner_id, {
                "spell": spell.name,
                "target": target.name,
                "reason": "Cannot destroy your own trap"
            }, False)
            return False
        return True

    def execute(self, engine, spell, target_id, details):
        target = engine.game_state.get_card_by_id(target_id)
        if target and target.ctype == "trap":
            engine.move_card_to_graveyard(target_id)
            details["target"] = target.name
            details["effect"] = "Trap destroyed"
            return True
        details["reason"] = f"Invalid trap target - {target_id}"
        log_action("CAST_SPELL", spell.owner_id, details, False)
        return False


class CallOfBravePolicy(SpellPolicy):
    def can_execute(self, engine, spell, target_id):
        # Only allow the usage if the player has already summoned a monster this turn
        able = not engine.game_state.player_info[spell.owner_id]['has_summoned_monster']
        if not able:
            log_action("CAST_SPELL", spell.owner_id, {
                "spell": spell.name,
                "reason": "User need to summon first before using this card"
            }, False)
        return able

    def execute(self, engine, spell, target_id, details):
        engine.game_state.player_info[spell.owner_id]['has_summoned_monster'] = False
        details["effect"] = "Extra summon enabled"
        return True


# spell_engine.py
SPELL_POLICIES: dict[str, SpellPolicy] = {
    "draw_two_cards": DrawTwoCardsPolicy(),
    "buff_attack": BuffAttackPolicy(),
    "buff_defense": BuffDefensePolicy(),
    "destroy_trap": DestroyTrapPolicy(),
    "summon_monster_from_hand": CallOfBravePolicy(),
}


class SpellEngine:
    def __init__(self, engine):
        self.engine = engine

    def cast_spell(self, spell_id: str, target_id: str | None = None):
        spell = self.engine.game_state.get_card_by_id(spell_id)
        if not spell or spell.ctype != "spell":
            log_action("CAST_SPELL", None, {
                "reason": "Not a spell card"
            }, False)
            return False

        current_player = self.engine.turn_manager.get_current_player()
        if spell.owner_id != current_player.id:
            log_action("CAST_SPELL", spell.owner_id, {
                "spell": spell.name,
                "reason": f"Not your turn (current: {current_player.name})"
            }, False)
            return False

        policy = SPELL_POLICIES.get(spell.ability)
        if not policy:
            log_action("CAST_SPELL", spell.owner_id, {
                "spell": spell.name,
                "reason": f"Unknown ability: {spell.ability}"
            }, False)
            return False

        details = {"spell": spell.name, "ability": spell.ability}

        if not policy.can_execute(self.engine, spell, target_id):
            return False

        if not policy.execute(self.engine, spell, target_id, details):
            return False

        self.engine.event_logger.add_event(SpellActiveEvent(
            spell_id=spell.id, target_id=target_id))
        self.engine.game_state.player_info[spell.owner_id]["held_cards"].remove(
            spell_id)
        self.engine.game_state.player_info[spell.owner_id]["graveyard_cards"].add(
            spell_id)

        log_action("CAST_SPELL", spell.owner_id, details, True)
        return True
