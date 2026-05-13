from __future__ import annotations

from abc import ABC, abstractmethod
from core.data.effects import EffectType
from core.data.events import SpellActiveEvent
from core.cards.spell_card import SpellCard
from typing import Optional
from .game_engine import GameEngine
from .utils import log_action


# TODO: refactor this
class SpellPolicy(ABC):
    """
    Abstract base class defining the policy interface for spell execution.
    """
    @abstractmethod
    def can_execute(self, engine: GameEngine, spell: SpellCard, target_id: str) -> bool:
        """
        Determines if a spell can be executed given the current state.
        """
        raise NotImplementedError

    @abstractmethod
    def execute(self, engine: GameEngine, spell: SpellCard, target_id: str, details: dict) -> bool:
        """
        Executes the spell effect.
        """
        raise NotImplementedError


class DrawTwoCardsPolicy(SpellPolicy):
    """
    Policy for drawing two cards from the player's deck.
    """

    def can_execute(self, engine, spell, target_id):
        return True

    def execute(self, engine, spell, target_id, details):
        engine.draw_card(spell.owner_id, check=True)
        engine.draw_card(spell.owner_id, check=True)
        details["effect"] = "Drew 2 cards"
        return True


class BuffAttackPolicy(SpellPolicy):
    """
    Policy for applying an attack buff to a monster.
    """

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
    """
    Policy for applying a defense buff to a monster.
    """

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
    """
    Policy for destroying a target trap card.
    """

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
    """
    Policy that enables an extra summon for the current turn.
    """

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
    """
    Handles spell casting logic and orchestration with policies.
    """

    def __init__(self, engine: GameEngine):
        """
        Initializes the SpellEngine.

        Args:
            engine: The main game engine instance.
        """
        self.engine = engine

    def cast_spell(self, spell_id: str, target_id: Optional[str] = None) -> bool:
        """
        Processes a spell cast request, validates requirements, and executes the spell effect.

        Args:
            spell_id (str): The ID of the spell card to be cast.
            target_id (str, optional): The ID of the target card.

        Returns:
            bool: True if the spell was successfully cast, False otherwise.
        """
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

        # Remove card from hand before execution so it doesn't count towards hand size limits
        self.engine.game_state.player_info[spell.owner_id]["held_cards"].remove(
            spell_id)

        if not policy.execute(self.engine, spell, target_id, details):
            # If execution fails, return card to hand
            self.engine.game_state.player_info[spell.owner_id]["held_cards"].add(
                spell_id)
            return False

        self.engine.event_logger.add_event(SpellActiveEvent(
            spell_id=spell.id, target_id=target_id))

        self.engine.game_state.player_info[spell.owner_id]["graveyard_cards"].add(
            spell_id)

        log_action("CAST_SPELL", spell.owner_id, details, True)
        return True
