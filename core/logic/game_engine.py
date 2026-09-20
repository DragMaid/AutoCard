import logging
from collections.abc import Iterator
from contextlib import contextmanager
from enum import Enum
from typing import Any, Generator

from core.cards.card import CardType
from core.cards.monster_card import MonsterCard
from core.cards.trap_card import ActivateCondition
from core.config import Config
from core.data.effects import EffectTracker
from core.data.events import EventLogger, ToggleEvent
from core.data.game_state import AttackEntry, GameState, ModifyMode
from core.data.player import Player
from core.factory.draw_system import DrawSystem
from core.logic.rule_engine import RuleEngine
from core.logic.spell_engine import SpellEngine
from core.logic.trap_engine import TrapEngine
from core.logic.turn_manager import TurnManager
from core.network.actions import (
    Intent,
    IntentType,
    Patch,
    cell_to_list,
    list_to_cell,
    make_intent,
)
from core.network.patch import diff_state, full_sync_patch, snapshot

from .battle_engine import BattleEngine
from .summon_engine import SummonEngine
from .upgrade_engine import UpgradeEngine
from .utils import is_local_turn, log_action

logger = logging.getLogger(__name__)


class EngineMode(str, Enum):
    """How an engine instance participates in a networked match.

    Attributes:
        LOCAL: Offline play (single player, AI, training). Mutations apply
            immediately and nothing is emitted.
        AUTHORITATIVE: The server's source-of-truth engine. Mutations apply and
            emit a :class:`~core.network.actions.Patch` describing the delta.
        REMOTE: A client engine. Mutations are not applied locally; they are sent
            to the server as an :class:`~core.network.actions.Intent` and come
            back as patches.
    """

    LOCAL = "LOCAL"
    AUTHORITATIVE = "AUTHORITATIVE"
    REMOTE = "REMOTE"


class GameEngine:
    """The main orchestrator for game logic, integrating various specialized engines."""

    def __init__(
        self,
        players: list[Player],
        # TODO: annotate this Any typing later
        transport: Any = None,
        mode: EngineMode = EngineMode.LOCAL,
        room_id: str = "",
        local_player_id: str | None = None,
        flip: bool = False,
    ) -> None:
        """Initializes the GameEngine.

        Args:
            players (List[Player]): The list of players in the game.
            transport: Object exposing ``send_intent`` and/or ``send_patch``.
            mode (EngineMode): Whether this engine is offline, authoritative, or remote.
            room_id (str): Room identifier attached to every emitted message.
            local_player_id (Optional[str]): The player this instance controls.
            flip (bool): True when this client renders the board rotated 180
                degrees, so outgoing grid cells must be converted back to the
                authoritative server's frame.
        """
        self.game_state = GameState(players=players)
        self.game_state.reset()

        self.effect_tracker = EffectTracker()
        self.turn_manager = TurnManager(self.game_state, self.effect_tracker)
        self.rule_engine = RuleEngine(self.game_state, self.turn_manager)
        self.draw_system = DrawSystem()
        self.event_logger = EventLogger()

        # Modular Engines
        self.trap_engine = TrapEngine(self)
        self.spell_engine = SpellEngine(self)
        self.battle_engine = BattleEngine(self)
        self.summon_engine = SummonEngine(self)
        self.upgrade_engine = UpgradeEngine(self)

        self.start_hand_count = 5

        self.transport = transport
        self.mode = mode
        self.room_id = room_id
        self.local_player_id = local_player_id
        self.flip = flip
        self._depth = 0
        self._seq = 0
        self._intent_seq = 0

    @contextmanager
    def _transaction(self, cause: str) -> Generator[None]:
        """Emits a granular patch describing whatever the block changed.

        Nested transactions (for example ``cast_spell`` calling ``draw_card``)
        collapse into the outermost one so a player action produces exactly one
        patch. Non-authoritative engines skip snapshotting entirely.

        Args:
            cause (str): Label recorded on the patch for debugging.

        Yields:
            None: Control returns to the caller's block.
        """
        track = (
            # authorative indicate single source of truth mode (by host client)
            self.mode is EngineMode.AUTHORITATIVE
            and self.transport is not None
            and self._depth == 0
        )
        before = snapshot(self) if track else None
        events_before = len(self.event_logger.get_events()) if track else 0

        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1

        if not track:
            return

        # Surface a win/loss triggered by this action in the same patch.
        self.game_state.is_game_over()

        new_events = self.event_logger.get_events()[events_before:]
        patch = Patch(
            room_id=self.room_id,
            seq=self._seq + 1,
            cause=cause,
            ops=diff_state(before, snapshot(self)),
            events=[e.model_dump(mode="json") for e in new_events],
        )

        if patch.is_empty():
            return

        self._seq += 1
        self._send_patch(patch)

    def _send_patch(self, patch: Patch) -> None:
        """Hands a patch to the transport.

        Args:
            patch (Patch): The delta to broadcast to the room.
        """
        if self.transport is None:
            return
        try:
            self.transport.send_patch(patch)
        except Exception as e:
            logger.error("Failed to send patch: %s", e)

    def _send_intent(self, intent_type: IntentType, **payload: Any) -> bool:
        """Sends a player request to the authoritative engine.

        Args:
            intent_type (IntentType): Which action is being requested.
            **payload: ID-only arguments describing the action.

        Returns:
            bool: Always False. Remote engines never mutate optimistically; the
            resulting patch is what changes local state, so callers treat the
            action as pending rather than applied.
        """
        if self.transport is None:
            logger.error("No transport configured for intent %s", intent_type)
            return False

        self._intent_seq += 1
        intent = make_intent(
            room_id=self.room_id,
            actor_id=self.local_player_id or "",
            intent_type=intent_type,
            seq=self._intent_seq,
            **payload,
        )
        try:
            self.transport.send_intent(intent)
        except Exception as e:
            logger.error("Failed to send intent %s: %s", intent_type, e)
        return False

    def _canonical_cell(self, cell: tuple[int, int] | None) -> list[int] | None:
        """Converts a cell from this viewer's frame into the server's frame.

        A guest renders the board rotated 180 degrees, so the slot it dropped a
        card on is not the slot the authoritative engine knows by that name.

        Args:
            cell (Optional[Tuple[int, int]]): A cell in local render coordinates.

        Returns:
            Optional[List[int]]: The equivalent canonical cell, or None.
        """
        if cell is None:
            return None
        if not self.flip:
            return cell_to_list(cell)
        return [Config.ROWS - 1 - cell[0], Config.COLS - 1 - cell[1]]

    def _is_remote(self) -> bool:
        """Returns True when mutations must be forwarded instead of applied."""
        return self.mode is EngineMode.REMOTE

    def send_full_sync(self) -> None:
        """Broadcasts a complete snapshot, for joins and resyncs."""
        self._seq += 1
        self._send_patch(full_sync_patch(self, self.room_id, self._seq))

    def dispatch(self, intent: Intent) -> bool:
        """Validates and applies one client intent on the authoritative engine.

        Payload values are treated as untrusted: the acting player always comes
        from ``intent.actor_id``, never from the payload, and card ownership is
        re-checked before the action reaches the rule engines.

        Args:
            intent (Intent): The client request to apply.

        Returns:
            bool: True if the action was accepted, False otherwise.
        """
        actor_id = intent.actor_id
        payload = intent.payload

        if actor_id not in self.game_state.player_info and \
                intent.type is not IntentType.REQUEST_SYNC:
            logger.warning("Rejected intent from unknown actor %s", actor_id)
            return False

        handler = {
            IntentType.START_GAME: self._dispatch_start_game,
            IntentType.DRAW: self._dispatch_draw,
            IntentType.SUMMON: self._dispatch_summon,
            IntentType.SET_TRAP: self._dispatch_set_trap,
            IntentType.CAST_SPELL: self._dispatch_cast_spell,
            IntentType.TOGGLE: self._dispatch_toggle,
            IntentType.ATTACK: self._dispatch_attack,
            IntentType.UPGRADE: self._dispatch_upgrade,
            IntentType.TOGGLE_TRAP_ACTIVATION: self._dispatch_trap_activation,
            IntentType.END_TURN: self._dispatch_end_turn,
            IntentType.SURRENDER: self._dispatch_surrender,
            IntentType.REQUEST_SYNC: self._dispatch_request_sync,
        }.get(intent.type)

        if handler is None:
            logger.warning("Unknown intent type: %s", intent.type)
            return False

        try:
            return handler(actor_id, payload)
        except Exception as e:
            logger.error("Intent %s failed: %s", intent.type, e)
            return False

    def _owns(self, actor_id: str, card_id: str | None) -> bool:
        """Checks that a player owns a card before acting on it.

        Args:
            actor_id (str): The acting player.
            card_id (Optional[str]): The card being acted on.

        Returns:
            bool: True when the card exists and belongs to the actor.
        """
        card = self.game_state.get_card_by_id(card_id) if card_id else None
        if card is None or card.owner_id != actor_id:
            logger.warning("Actor %s does not own card %s", actor_id, card_id)
            return False
        return True

    def _dispatch_start_game(self, actor_id: str, payload: dict) -> bool:
        """Deals opening hands. See :meth:`dispatch`."""
        self.start_game()
        return True

    def _dispatch_draw(self, actor_id: str, payload: dict) -> bool:
        """Draws a card for the acting player. See :meth:`dispatch`."""
        return self.draw_card(actor_id)

    def _dispatch_summon(self, actor_id: str, payload: dict) -> bool:
        """Summons a card from the acting player's hand. See :meth:`dispatch`."""
        card_id = payload.get("card_id")
        if not card_id or not self._owns(actor_id, card_id):
            return False
        return self.summon_card(actor_id, card_id, list_to_cell(payload.get("cell")))

    def _dispatch_set_trap(self, actor_id: str, payload: dict) -> bool:
        """Sets a trap face-down. See :meth:`dispatch`."""
        trap_id = payload.get("card_id")
        if not trap_id or not self._owns(actor_id, trap_id):
            return False
        return self.set_trap(trap_id, list_to_cell(payload.get("cell")))

    def _dispatch_cast_spell(self, actor_id: str, payload: dict) -> bool:
        """Casts a spell. See :meth:`dispatch`."""
        spell_id = payload.get("card_id")
        if not spell_id or not self._owns(actor_id, spell_id):
            return False
        return self.cast_spell(spell_id, payload.get("target_id"))

    def _dispatch_toggle(self, actor_id: str, payload: dict) -> bool:
        """Switches a monster between attack and defence. See :meth:`dispatch`."""
        card_id = payload.get("card_id")
        if not card_id or not self._owns(actor_id, card_id):
            return False
        return self.toggle_card(card_id)

    def _dispatch_attack(self, actor_id: str, payload: dict) -> bool:
        """Declares an attack. See :meth:`dispatch`."""
        card_id = payload.get("card_id")
        target_id = payload.get("target_id")
        if not card_id or not target_id or not self._owns(actor_id, card_id):
            return False

        defender_id = self.game_state.get_opponent_id(actor_id)
        if defender_id is None:
            return False

        return self.attack(AttackEntry(
            attacker_id=actor_id,
            defender_id=defender_id,
            card_id=card_id,
            target_id=target_id,
            target_is_player=bool(payload.get("target_is_player", False)),
        ))

    def _dispatch_upgrade(self, actor_id: str, payload: dict) -> bool:
        """Merges two monsters. See :meth:`dispatch`."""
        own_id = payload.get("card_id")
        target_id = payload.get("target_id")
        if not own_id or not target_id:
            return False
        if not self._owns(actor_id, own_id) or not self._owns(actor_id, target_id):
            return False
        return self.upgrade_monster(actor_id, own_id, target_id)

    def _dispatch_trap_activation(self, actor_id: str, payload: dict) -> bool:
        """Flags a triggerable trap for activation. See :meth:`dispatch`."""
        trap_id = payload.get("card_id")
        if not trap_id or not self._owns(actor_id, trap_id):
            return False
        self.toggle_trap_activation(trap_id, bool(payload.get("activated", False)))
        return True

    def _dispatch_end_turn(self, actor_id: str, payload: dict) -> bool:
        """Ends the turn or resolves the trap stage. See :meth:`dispatch`."""
        if self.turn_manager.is_trap_stage():
            trapper = self.turn_manager.get_trapper()
            if trapper is None or trapper.id != actor_id:
                logger.warning("End turn denied: %s is not the trapper", actor_id)
                return False
        elif self.turn_manager.get_current_player().id != actor_id:
            logger.warning("End turn denied: not %s's turn", actor_id)
            return False

        self.end_turn()
        return True

    def _dispatch_surrender(self, actor_id: str, payload: dict) -> bool:
        """Concedes the match for the acting player. See :meth:`dispatch`."""
        return self.surrender(actor_id)

    def _dispatch_request_sync(self, actor_id: str, payload: dict) -> bool:
        """Re-sends a full snapshot to the room. See :meth:`dispatch`."""
        self.send_full_sync()
        return True

    def apply_patch(self, patch: Patch, applier: Any) -> None:
        """Applies a server patch to this engine through a viewer-aware applier.

        Args:
            patch (Patch): The delta received from the authoritative engine.
            applier: A :class:`~core.network.patch.PatchApplier`.
        """
        applier.apply(patch)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def serialize(self) -> dict:
        """Serializes the current game state.

        Returns:
            dict: A dictionary representation of the game engine state.
        """
        serialized = {}
        serialized["game_state"] = self.game_state.serialize()
        serialized["effect_tracker"] = self.effect_tracker.serialize()
        serialized["event_logger"] = self.event_logger.serialize()
        serialized["turn_manager"] = self.turn_manager.serialize()
        return serialized

    def deserialize(self, serialized: dict) -> None:
        """Deserializes game state from a dictionary.

        Args:
            serialized (dict): The dictionary representation to restore.
        """
        self.game_state.deserialize(serialized["game_state"])
        self.effect_tracker.deserialize(serialized["effect_tracker"])
        self.event_logger.deserialize(serialized["event_logger"])
        self.turn_manager.deserialize(serialized["turn_manager"])

    def reset(self) -> None:
        """Resets the game state and trackers."""
        self.effect_tracker.clear_all_effects(self.game_state)
        self.event_logger.clear_events()
        self.game_state.reset()

    # ------------------------------------------------------------------
    # Game actions
    # ------------------------------------------------------------------

    def start_game(self) -> None:
        """Starts the game by dealing initial cards."""
        with self._transaction("START_GAME"):
            self.give_init_cards(self.start_hand_count)

    def give_init_cards(self, number: int) -> None:
        """Gives initial cards to all players.

        Args:
            number (int): Number of cards to draw.
        """
        for player in self.game_state.players:
            for _ in range(number):
                self.draw_card(player.id, check=False)

    def draw_card(self, player_id: str, check: bool = True) -> bool:
        """Player draws a card if allowed by rules.

        Args:
            player_id (str): ID of the drawing player.
            check (bool): Whether to enforce rule checks.

        Returns:
            bool: True if card was drawn, False otherwise.
        """
        if self._is_remote():
            return self._send_intent(IntentType.DRAW)

        with self._transaction("DRAW"):
            can_draw = not check or self.rule_engine.can_draw(player_id)

            if can_draw:
                card = self.draw_system.draw(player_id)
                if card:
                    card.is_opponent = self.game_state.players_lookup[player_id].is_opponent
                    self.game_state.entity_lookup[card.id] = card
                    self.game_state.player_info[player_id].held_cards.add(
                        card.id)
                    log_action("DRAW", player_id, {
                        "card": card.name,
                        "type": card.card_type.value,
                        "hand_size": len(self.game_state.player_info[player_id].held_cards.card_ids)
                    }, True)
                    return True

            return False

    def toggle_card(self, card_id: str) -> bool:
        """Toggles a monster's position (Attack/Defense).

        Args:
            card_id (str): ID of the card to toggle.

        Returns:
            bool: True if successful, False otherwise.
        """
        if self._is_remote():
            return self._send_intent(IntentType.TOGGLE, card_id=card_id)

        card = self.game_state.get_card_by_id(card_id)
        if not card or card.card_type != CardType.MONSTER:
            return False

        owner_id = card.owner_id
        if self.rule_engine.can_toggle(owner_id, card_id):
            # NOTE: the _transaction method is used like a way of
            # automatically detecting the difference and updating the game state intent
            with self._transaction("TOGGLE"):
                old_mode = card.mode
                new_mode = card.switch_position()
                self.event_logger.add_event(
                    ToggleEvent(card_id=card.id, mode=new_mode))
                self.game_state.player_info[owner_id].has_toggled = True

                if self.trap_engine.check_traps(
                    condition=ActivateCondition.TOGGLE,
                    target_id=card_id
                ):
                    self.turn_manager.toggle_trap_stage(state=True)

                log_action("TOGGLE", owner_id, {
                    "card": card.name,
                    "position": card.pos_in_matrix,
                    "from": old_mode.value,
                    "to": new_mode.value
                }, True)

            return True

        log_action("TOGGLE", owner_id, {
            "card": card.name,
            "reason": "Already toggled this turn or rule violation"
        }, False)
        return False

    def summon_card(
        self,
        player_id: str,
        card_id: str,
        cell: tuple[int, int] | None,
        check: bool = True
    ) -> bool:
        """Delegates summoning logic to SummonEngine."""
        if self._is_remote():
            return self._send_intent(
                IntentType.SUMMON, card_id=card_id, cell=self._canonical_cell(cell))

        with self._transaction("SUMMON"):
            return self.summon_engine.summon_card(
                player_id, card_id, cell, check)

    def attack(self, attack: AttackEntry) -> bool:
        """Initiates an attack sequence.

        Args:
            attack (AttackEntry): The attack details.

        Returns:
            bool: True if attack sequence started, False if invalid.
        """
        if self._is_remote():
            return self._send_intent(
                IntentType.ATTACK,
                card_id=attack.card_id,
                target_id=attack.target_id,
                target_is_player=attack.target_is_player,
            )

        can_attack = self.rule_engine.can_attack(
            attack.attacker_id,
            attack.defender_id,
            attack.card_id,
            attack.target_id,
            attack.target_is_player
        )

        if not can_attack:
            return False

        with self._transaction("ATTACK"):
            # Check for trap triggers
            if not self.trap_engine.check_traps(
                condition=ActivateCondition.ATTACK,
                target_id=attack.card_id,
            ):
                self.battle_engine.resolve_battle(attack)
            else:
                self.turn_manager.toggle_trap_stage(state=True)
                self.game_state.attack_queue.append(attack)

        return True

    def move_card_to_graveyard(self, card_id: str) -> None:
        """Moves a card from the field or hand to the graveyard.

        Args:
            card_id (str): ID of the card to move.
        """
        card = self.game_state.get_card_by_id(card_id)
        assert card is not None

        if card.pos_in_matrix:
            self.game_state.modify_field(
                ModifyMode.REMOVE, card, card.pos_in_matrix)

        self.game_state.player_info[card.owner_id].graveyard_cards.add(
            card_id)
        logger.debugx(
            "Card moved to graveyard",
            extra={
                "card_name": card.name,
                "owner_id": card.owner_id,
                "card_id": card_id
            }
        )

    def toggle_trap_activation(self, trap_id: str, activated: bool = False) -> None:
        """Toggles player's intent to activate a triggerable trap.

        Args:
            trap_id (str): ID of the trap card.
            activated (bool): Whether the trap is to be activated.
        """
        if self._is_remote():
            self._send_intent(IntentType.TOGGLE_TRAP_ACTIVATION,
                              card_id=trap_id, activated=activated)
            return

        trap = self.game_state.get_card_by_id(trap_id)
        if trap is None:
            return
        owner_id = trap.owner_id
        if self.rule_engine.can_activate(owner_id, trap_id):
            with self._transaction("TOGGLE_TRAP_ACTIVATION"):
                if activated:
                    if trap_id not in self.game_state.activated_traps:
                        self.game_state.activated_traps.append(trap_id)
                elif trap_id in self.game_state.activated_traps:
                    self.game_state.activated_traps.remove(trap_id)

    def resolve_battle(self, attack: AttackEntry) -> None:
        """Delegates battle resolution to BattleEngine."""
        self.battle_engine.resolve_battle(attack)

    def upgrade_monster(self, player_id: str, own_card_id: str, target_card_id: str) -> bool:
        """Delegates upgrade logic to UpgradeEngine."""
        if self._is_remote():
            return self._send_intent(
                IntentType.UPGRADE, card_id=own_card_id, target_id=target_card_id)

        with self._transaction("UPGRADE"):
            return self.upgrade_engine.upgrade_monster(
                player_id, own_card_id, target_card_id)

    def set_trap(self, trap_id: str, position: tuple[int, int] | None, check: bool = True) -> bool:
        """Delegates trap setting to TrapEngine."""
        if self._is_remote():
            return self._send_intent(
                IntentType.SET_TRAP, card_id=trap_id,
                cell=self._canonical_cell(position))

        with self._transaction("SET_TRAP"):
            return self.trap_engine.set_trap(trap_id, position, check)

    def cast_spell(self, spell_id: str, target_id: str | None = None) -> bool:
        """Delegates spell casting to SpellEngine."""
        if self._is_remote():
            return self._send_intent(
                IntentType.CAST_SPELL, card_id=spell_id, target_id=target_id)

        with self._transaction("CAST_SPELL"):
            return self.spell_engine.cast_spell(spell_id, target_id)

    def surrender(self, player_id: str) -> bool:
        """Concedes the match on behalf of a player.

        Args:
            player_id (str): The player giving up.

        Returns:
            bool: True if the player was found and the match ended.
        """
        if self._is_remote():
            return self._send_intent(IntentType.SURRENDER)

        player = self.game_state.players_lookup.get(player_id)
        if player is None:
            return False

        with self._transaction("SURRENDER"):
            player.life_points = 0

        return True

    def end_turn(self) -> None:
        """Ends the current turn and handles phase transitions."""
        if self._is_remote():
            self._send_intent(IntentType.END_TURN)
            return

        with self._transaction("END_TURN"):
            if self.turn_manager.is_trap_stage():
                cancel_resolve = self.trap_engine.resolve_traps()
                if not cancel_resolve:
                    for attack in self.game_state.attack_queue:
                        self.resolve_battle(attack)
                self.game_state.attack_queue.clear()
                self.turn_manager.toggle_trap_stage(state=False)
            else:
                current_player = self.turn_manager.get_current_player()
                for card in self.game_state.get_player_field_cards(current_player.id):
                    if isinstance(card, MonsterCard):
                        card.has_attacked = False

                self.turn_manager.end_turn()
                next_player = self.turn_manager.get_current_player()
                self.draw_card(next_player.id)

    def is_local_turn(self) -> bool:
        """Checks if it's the local player's turn.

        Returns:
            bool: True if it is the local player's turn, False otherwise.
        """
        return is_local_turn(self.turn_manager, self.game_state.players)
