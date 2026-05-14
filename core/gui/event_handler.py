import logging
from typing import Dict, Any, Optional, Callable, List
from core.data.events import (
    AttackEvent, TrapTriggerEvent, ToggleEvent,
    SpellActiveEvent, MergeEvent, TrapTriggerableEvent
)
from gui.sprites.sprite_manager import SpriteManager
from gui.animations.manager import AnimationManager
from gui.background.matrix_field import Matrix
from core.data.game_state import GameState
from core.data.events import EventLogger
from gui.sprites.sprite import Sprite
from gui.background.hand import HandUI

logger = logging.getLogger(__name__)


class EventHandler:
    """Handles game events and maps them to appropriate GUI actions."""

    def __init__(
        self,
        sprite_manager: SpriteManager,
        animation_mgr: AnimationManager,
        matrix: Matrix,
        game_state: GameState,
        event_logger: EventLogger
    ):
        """Initializes the EventHandler with necessary managers and state.

        Args:
            sprite_manager: Manager for handling game sprites.
            animation_mgr: Manager for creating animations.
            matrix: The game board matrix field.
            game_state: The current state of the game.
            event_logger: Logger responsible for collecting game events.
        """
        self.sprite_manager = sprite_manager
        self.animation_mgr = animation_mgr
        self.matrix = matrix
        self.game_state = game_state
        self.event_logger = event_logger
        self.pending_merges: List[MergeEvent] = []

        self._handlers: Dict[type, Callable[[Any], None]] = {
            AttackEvent: self._handle_attack,
            TrapTriggerEvent: self._handle_trap_trigger,
            TrapTriggerableEvent: self._handle_trap_triggerable,
            ToggleEvent: self._handle_toggle,
            SpellActiveEvent: self._handle_spell_active,
            MergeEvent: self._handle_merge,
        }

    def handle_events(self) -> None:
        """Processes all pending events in the event logger and triggers handlers."""
        try:
            for event in self.event_logger.get_events():
                handler = self._handlers.get(type(event))
                if handler:
                    handler(event)

            self.event_logger.clear_events()

        except Exception as e:
            logger.error(f"[ERROR] handle_events failed: {e}")

    def _get_sprite(self, sprite_id: str) -> Optional[Sprite]:
        """Retrieves a sprite by its ID.

        Args:
            sprite_id: The ID of the sprite to retrieve.

        Returns:
            The sprite if found, otherwise None.
        """
        return self.sprite_manager.get_sprite(sprite_id)

    def _get_hand_by_player(self, player_id: str) -> Optional[HandUI]:
        """Retrieves a player's hand by player ID.

        Args:
            player_id: The ID of the player.

        Returns:
            The hand of the player if found, otherwise None.
        """
        return next(
            (h for h in getattr(self.matrix, "hands", [])
             if getattr(h, "player_id", None) == player_id),
            None
        )

    def _handle_attack(self, event: AttackEvent) -> None:
        """Handles an attack event.

        Args:
            event: The attack event to handle.
        """
        attacker = self._get_sprite(event.card_id)
        if not attacker:
            return

        if event.target_is_player:
            hand = self._get_hand_by_player(event.target_id)
            if hand:
                self.animation_mgr.create_attack_player_animation(
                    attacker, hand)
        else:
            target = self._get_sprite(event.target_id)
            if target:
                self.animation_mgr.create_attack_animation(attacker, target)

    def _handle_trap_trigger(self, event: TrapTriggerEvent) -> None:
        """Handles a trap trigger event.

        Args:
            event: The trap trigger event.
        """
        trap = self._get_sprite(event.card_id)
        if not trap:
            return

        self.animation_mgr.create_trigger_animation(trap)
        self.matrix.areas["preview_card_table"].set_card(trap, self.game_state)

    def _handle_trap_triggerable(self, event: TrapTriggerableEvent) -> None:
        """Handles a trap triggerable event.

        Args:
            event: The trap triggerable event.
        """
        trap = self._get_sprite(event.card_id)
        if trap:
            self.animation_mgr.create_triggerable_animation(trap)

    def _handle_toggle(self, event: ToggleEvent) -> None:
        """Handles a toggle event.

        Args:
            event: The toggle event.
        """
        card = self._get_sprite(event.card_id)
        if card:
            self.animation_mgr.create_toggle_animation(card, event.mode)

    def _handle_spell_active(self, event: SpellActiveEvent) -> None:
        """Handles a spell activation event.

        Args:
            event: The spell active event.
        """
        spell = self._get_sprite(event.spell_id)
        if spell:
            self.animation_mgr.create_spell_animation(spell)

    def _handle_merge(self, event: MergeEvent) -> None:
        """Handles a merge event by adding it to the pending list.

        Args:
            event: The merge event.
        """
        self.pending_merges.append(event)
