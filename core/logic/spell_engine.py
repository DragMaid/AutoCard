from __future__ import annotations

from abc import ABC, abstractmethod
from core.data.effects import EffectType
from core.data.events import SpellActiveEvent
from core.cards.spell_card import SpellCard, SpellAbility
from core.cards.card import CardType
from typing import Optional, Dict, TYPE_CHECKING
from .utils import log_action

if TYPE_CHECKING:
    from core.logic.game_engine import GameEngine


class SpellPolicy(ABC):
    """
    Abstract base class defining the policy interface for spell execution.
    """
    @abstractmethod
    def can_execute(self, engine: GameEngine, spell: SpellCard, target_id: Optional[str]) -> bool:
        """
        Determines if a spell can be executed given the current state.
        """
        raise NotImplementedError

    @abstractmethod
    def execute(self, engine: GameEngine, spell: SpellCard, target_id: Optional[str], details: dict, effectiveness: int, duration: int) -> bool:
        """
        Executes the spell effect.
        """
        raise NotImplementedError


class DrawCardPolicy(SpellPolicy):
    """
    Policy for drawing cards from the player's deck.
    """

    def can_execute(self, engine, spell, target_id):
        return True

    def execute(self, engine, spell, target_id, details, effectiveness, duration):
        for _ in range(effectiveness):
            engine.draw_card(spell.owner_id, check=True)
        details.setdefault("effects", []).append(f"Drew {effectiveness} cards")
        return True


class BuffAttackPolicy(SpellPolicy):
    """
    Policy for applying an attack buff to a monster.
    """

    def can_execute(self, engine, spell, target_id):
        if not target_id:
            return False
        target = engine.game_state.get_card_by_id(target_id)
        if target and target.card_type == CardType.MONSTER and spell.owner_id != target.owner_id:
            log_action("CAST_SPELL", spell.owner_id, {
                "spell": spell.name,
                "reason": "Cannot target enemy monsters with buff spells"
            }, False)
            return False
        return True

    def execute(self, engine, spell, target_id, details, effectiveness, duration):
        engine.effect_tracker.add_effect(
            EffectType.BUFF, target_id, "atk", effectiveness, duration, engine.game_state)
        target = engine.game_state.get_card_by_id(target_id)
        details["target"] = target.name if target else target_id
        details.setdefault("effects", []).append(
            f"+{effectiveness} ATK for {duration} turns")
        return True


class BuffDefensePolicy(SpellPolicy):
    """
    Policy for applying a defense buff to a monster.
    """

    def can_execute(self, engine, spell, target_id):
        if not target_id:
            return False

        target = engine.game_state.get_card_by_id(target_id)
        if target and target.card_type == CardType.MONSTER and spell.owner_id != target.owner_id:
            log_action("CAST_SPELL", spell.owner_id, {
                "spell": spell.name,
                "reason": "Cannot target enemy monsters with buff spells"
            }, False)
            return False
        return True

    def execute(self, engine, spell, target_id, details, effectiveness, duration):
        engine.effect_tracker.add_effect(
            EffectType.BUFF, target_id, "defend", effectiveness, duration, engine.game_state)
        target = engine.game_state.get_card_by_id(target_id)
        details["target"] = target.name if target else target_id
        details.setdefault("effects", []).append(
            f"+{effectiveness} DEF for {duration} turns")
        return True


class DestroyTrapPolicy(SpellPolicy):
    """
    Policy for destroying a target trap card.
    """

    def can_execute(self, engine, spell, target_id):
        if not target_id:
            return False
        target = engine.game_state.get_card_by_id(target_id)
        if target and target.card_type == CardType.TRAP and spell.owner_id == target.owner_id:
            log_action("CAST_SPELL", spell.owner_id, {
                "spell": spell.name,
                "target": target.name,
                "reason": "Cannot destroy your own trap"
            }, False)
            return False
        return True

    def execute(self, engine, spell, target_id, details, effectiveness, duration):
        target = engine.game_state.get_card_by_id(target_id)
        if target and target.card_type == CardType.TRAP:
            engine.move_card_to_graveyard(target_id)
            details["target"] = target.name
            details.setdefault("effects", []).append("Trap destroyed")
            return True
        details["reason"] = f"Invalid trap target - {target_id}"
        log_action("CAST_SPELL", spell.owner_id, details, False)
        return False


class ExtraSummonPolicy(SpellPolicy):
    """
    Policy that enables an extra summon for the current turn.
    """

    def can_execute(self, engine, spell, target_id):
        return True

    def execute(self, engine, spell, target_id, details, effectiveness, duration):
        # Reset the summon flag to allow another monster summon
        engine.game_state.player_info[spell.owner_id]['has_summoned_monster'] = False
        details.setdefault("effects", []).append("Extra summon enabled")
        return True


class SpellEngine:
    """
    Handles spell casting logic and orchestration with policies.
    """
    SPELL_POLICIES: Dict[SpellAbility, SpellPolicy] = {
        SpellAbility.DRAW_CARD: DrawCardPolicy(),
        SpellAbility.BUFF_ATTACK: BuffAttackPolicy(),
        SpellAbility.BUFF_DEFEND: BuffDefensePolicy(),
        SpellAbility.DESTROY_TRAP: DestroyTrapPolicy(),
        SpellAbility.EXTRA_SUMMON: ExtraSummonPolicy(),
    }

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
        spell: SpellCard = self.engine.game_state.get_card_by_id(spell_id)
        if not spell or spell.card_type != CardType.SPELL:
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

        details = {
            "spell": spell.name,
            "abilities": [a.value for a in spell.abilities]
        }

        # Validate all abilities can be executed
        for i, ability in enumerate(spell.abilities):
            policy = self.SPELL_POLICIES.get(ability)
            if not policy:
                log_action("CAST_SPELL", spell.owner_id, {
                    "spell": spell.name,
                    "reason": f"Unknown ability: {ability}"
                }, False)
                return False
            if not policy.can_execute(self.engine, spell, target_id):
                return False

        # Remove card from hand before execution
        held_collection = self.engine.game_state.player_info[spell.owner_id].held_cards
        held_collection.remove(spell_id)

        # Execute all abilities
        success = True
        for i, ability in enumerate(spell.abilities):
            policy = self.SPELL_POLICIES.get(ability)
            eff = spell.effectiveness[i] if spell.effectiveness and i < len(
                spell.effectiveness) else 0
            dur = spell.duration[i] if spell.duration and i < len(
                spell.duration) else 0

            if not policy.execute(self.engine, spell, target_id, details, eff, dur):
                success = False
                break

        if not success:
            # If execution fails, return card to hand
            held_collection.add(spell_id)
            return False

        self.engine.event_logger.add_event(SpellActiveEvent(
            spell_id=spell.id, target_id=target_id))

        self.engine.move_card_to_graveyard(spell_id)

        log_action("CAST_SPELL", spell.owner_id, details, True)
        return True
