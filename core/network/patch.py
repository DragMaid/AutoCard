"""Diffing and application of :class:`~core.network.actions.Patch` messages.

The authoritative engine snapshots itself before an action, runs the action
through the ordinary rule engines, snapshots again, and calls :func:`diff_state`
to turn the two snapshots into the minimal list of
:class:`~core.network.actions.PatchOp` entries that describe the change. Clients
feed those ops to a :class:`PatchApplier`, which mutates their single local
:class:`~core.data.game_state.GameState` in place.

Diffing keeps every rule in one place (the Python engine) instead of forcing
every mutation site to hand-write its own delta.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from core.cards.card import CardType
from core.config import Config
from core.data.game_state import GameState, LogicCardAdapter
from core.network.actions import OpType, Patch, PatchOp, Zone

logger = logging.getLogger(__name__)

ZONE_FIELDS: Dict[Zone, str] = {
    Zone.HAND: "held_cards",
    Zone.GRAVEYARD: "graveyard_cards",
    Zone.DECK: "deck_cards",
}

PLAYER_INFO_FLAGS = ("has_summoned_trap", "has_summoned_monster",
                     "has_toggled", "active_traps")


def snapshot(engine: Any) -> Dict[str, Any]:
    """Captures a JSON-safe snapshot of everything a patch can describe.

    Args:
        engine: The :class:`~core.logic.game_engine.GameEngine` to snapshot.

    Returns:
        A dictionary with ``game_state``, ``effects`` and ``turn`` entries.
    """
    return {
        "game_state": engine.game_state.serialize(),
        "effects": engine.effect_tracker.serialize(),
        "turn": engine.turn_manager.serialize(),
    }


def _diff_zone(
    ops: List[PatchOp],
    player_id: str,
    zone: Zone,
    before: List[str],
    after: List[str],
) -> None:
    """Appends ops that turn ``before`` into ``after`` for one card collection.

    Emits individual add/remove ops when the change is a pure insertion or
    deletion, and falls back to assigning the whole list when the ordering
    changed (hand order drives on-screen card order).

    Args:
        ops: Output list to append to.
        player_id: Owner of the collection.
        zone: Which collection changed.
        before: Card ids before the action.
        after: Card ids after the action.
    """
    if before == after:
        return

    removed = [cid for cid in before if cid not in after]
    added = [cid for cid in after if cid not in before]

    # Verify that remove-then-append reproduces the target ordering exactly.
    simulated = [cid for cid in before if cid in after] + added
    if simulated == after:
        for card_id in removed:
            ops.append(PatchOp(op=OpType.ZONE_REMOVE, player_id=player_id,
                               zone=zone, card_id=card_id))
        for card_id in added:
            ops.append(PatchOp(op=OpType.ZONE_ADD, player_id=player_id,
                               zone=zone, card_id=card_id))
        return

    # Ordering changed in a way add/remove cannot express: send the list.
    ops.append(PatchOp(
        op=OpType.PLAYER_INFO_UPDATE,
        player_id=player_id,
        fields={ZONE_FIELDS[zone]: list(after)},
    ))


def _changed_fields(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Returns the entries of ``after`` that differ from ``before``.

    Args:
        before: Mapping before the action.
        after: Mapping after the action.

    Returns:
        Only the changed key/value pairs, taken from ``after``.
    """
    return {k: v for k, v in after.items() if before.get(k) != v}


def diff_state(before: Dict[str, Any], after: Dict[str, Any]) -> List[PatchOp]:
    """Computes the ops that turn snapshot ``before`` into snapshot ``after``.

    Args:
        before: Snapshot taken before the action.
        after: Snapshot taken after the action.

    Returns:
        An ordered list of patch operations.
    """
    ops: List[PatchOp] = []
    gs_before: Dict[str, Any] = before["game_state"]
    gs_after: Dict[str, Any] = after["game_state"]

    # Ownership only changes on a full reset, which is broadcast as FULL_SYNC.
    if gs_before.get("field_matrix_ownership") != gs_after.get("field_matrix_ownership"):
        return [PatchOp(op=OpType.FULL_SYNC, value=after)]

    # --- Cards -------------------------------------------------------------
    entities_before: Dict[str, Any] = gs_before.get("entity_lookup", {})
    entities_after: Dict[str, Any] = gs_after.get("entity_lookup", {})

    for card_id, card in entities_after.items():
        old = entities_before.get(card_id)
        if old is None:
            ops.append(PatchOp(op=OpType.CARD_UPSERT,
                               card_id=card_id, card=card))
        else:
            fields = _changed_fields(old, card)
            if fields:
                ops.append(PatchOp(op=OpType.CARD_UPDATE,
                                   card_id=card_id, fields=fields))

    for card_id in entities_before:
        if card_id not in entities_after:
            ops.append(PatchOp(op=OpType.CARD_REMOVE, card_id=card_id))

    # --- Players -----------------------------------------------------------
    players_before = {p["id"]: p for p in gs_before.get("players", [])}
    for player in gs_after.get("players", []):
        old = players_before.get(player["id"])
        if old is None:
            continue
        # is_opponent is a per-viewer concern, never sent over the wire.
        fields = _changed_fields(old, player)
        fields.pop("is_opponent", None)
        if fields:
            ops.append(PatchOp(op=OpType.PLAYER_UPDATE,
                               player_id=player["id"], fields=fields))

    # --- Player info (flags + card collections) ----------------------------
    info_before: Dict[str, Any] = gs_before.get("player_info", {})
    info_after: Dict[str, Any] = gs_after.get("player_info", {})

    for player_id, info in info_after.items():
        old = info_before.get(player_id, {})

        flags = {k: info[k] for k in PLAYER_INFO_FLAGS
                 if k in info and old.get(k) != info[k]}
        if flags:
            ops.append(PatchOp(op=OpType.PLAYER_INFO_UPDATE,
                               player_id=player_id, fields=flags))

        for zone, field in ZONE_FIELDS.items():
            old_ids = (old.get(field) or {}).get("card_ids", [])
            new_ids = (info.get(field) or {}).get("card_ids", [])
            _diff_zone(ops, player_id, zone, old_ids, new_ids)

    # --- Field matrix ------------------------------------------------------
    matrix_before = gs_before.get("field_matrix", [])
    matrix_after = gs_after.get("field_matrix", [])
    for row, cells in enumerate(matrix_after):
        for col, card_id in enumerate(cells):
            try:
                old_id = matrix_before[row][col]
            except (IndexError, TypeError):
                old_id = None
            if old_id != card_id:
                ops.append(PatchOp(op=OpType.FIELD_SET, row=row,
                                   col=col, card_id=card_id))

    # --- Scalar collections ------------------------------------------------
    if gs_before.get("triggerable_traps") != gs_after.get("triggerable_traps"):
        ops.append(PatchOp(op=OpType.TRIGGERABLE_TRAPS_SET,
                           value=gs_after.get("triggerable_traps", {})))

    if gs_before.get("activated_traps") != gs_after.get("activated_traps"):
        ops.append(PatchOp(op=OpType.ACTIVATED_TRAPS_SET,
                           value=gs_after.get("activated_traps", [])))

    if gs_before.get("attack_queue") != gs_after.get("attack_queue"):
        ops.append(PatchOp(op=OpType.ATTACK_QUEUE_SET,
                           value=gs_after.get("attack_queue", [])))

    if gs_before.get("game_over") != gs_after.get("game_over"):
        ops.append(PatchOp(op=OpType.GAME_OVER_SET,
                           value=gs_after.get("game_over", False)))

    if before.get("effects") != after.get("effects"):
        ops.append(PatchOp(op=OpType.EFFECTS_SET, value=after.get("effects", [])))

    turn_fields = _changed_fields(before.get("turn", {}), after.get("turn", {}))
    if turn_fields:
        ops.append(PatchOp(op=OpType.TURN_UPDATE, fields=turn_fields))

    return ops


def full_sync_patch(engine: Any, room_id: str = "", seq: int = 0) -> Patch:
    """Builds a patch carrying a complete engine snapshot.

    Used when a client joins, reconnects, or detects a gap in patch sequence
    numbers.

    Args:
        engine: The authoritative engine.
        room_id: Room the patch belongs to.
        seq: Server sequence number for this patch.

    Returns:
        A patch containing a single :attr:`OpType.FULL_SYNC` op.
    """
    return Patch(
        room_id=room_id,
        seq=seq,
        cause="FULL_SYNC",
        ops=[PatchOp(op=OpType.FULL_SYNC, value=engine.serialize())],
    )


class PatchApplier:
    """Applies patch ops to one local engine, translating for the viewer.

    The wire format is always in the authoritative server's frame of reference:
    row 0 is the host's far edge and ``player_index == 0`` is the host. A client
    that plays as ``player_index == 1`` renders the board rotated 180 degrees, so
    this applier mirrors grid coordinates on the way in and recomputes the
    ``is_opponent`` / ``is_face_down`` view flags after every batch.

    Attributes:
        engine: The local engine being mutated.
        local_player_id: The player this client controls, or None for a spectator.
        flip: Whether to mirror the field matrix into the viewer's frame.
    """

    def __init__(self, engine: Any, local_player_id: Optional[str] = None,
                 flip: bool = False) -> None:
        """Initializes the applier.

        Args:
            engine: The local :class:`~core.logic.game_engine.GameEngine`.
            local_player_id: Id of the player controlled by this client.
            flip: True when the viewer sits on the far side of the board.
        """
        self.engine = engine
        self.local_player_id = local_player_id
        self.flip = flip

    # -- coordinate helpers -------------------------------------------------

    def _cell(self, row: int, col: int) -> Tuple[int, int]:
        """Maps a canonical cell into the viewer's frame.

        Args:
            row: Canonical row index.
            col: Canonical column index.

        Returns:
            The ``(row, col)`` pair to use locally.
        """
        if not self.flip:
            return row, col
        return Config.ROWS - 1 - row, Config.COLS - 1 - col

    def _pos(self, value: Any) -> Any:
        """Maps a serialized ``pos_in_matrix`` value into the viewer's frame.

        Args:
            value: A two-element sequence or None.

        Returns:
            The translated position, or None.
        """
        if value is None:
            return None
        row, col = self._cell(int(value[0]), int(value[1]))
        return (row, col)

    # -- entry point --------------------------------------------------------

    def apply(self, patch: Patch) -> None:
        """Applies every op in a patch and refreshes derived view flags.

        Args:
            patch: The patch received from the authoritative engine.
        """
        for op in patch.ops:
            try:
                self._apply_op(op)
            except Exception as exc:  # keep the client alive on a bad op
                logger.error("Failed to apply patch op %s: %s", op.op, exc)

        for event in patch.events:
            self._add_event(event)

        self.normalize()

    def _add_event(self, event: Dict[str, Any]) -> None:
        """Feeds one serialized animation event into the local event logger.

        Args:
            event: A serialized :mod:`core.data.events` entry.
        """
        from core.data.events import GameEventAdapter
        try:
            self.engine.event_logger.add_event(
                GameEventAdapter.validate_python(event))
        except Exception as exc:
            logger.error("Failed to decode event %s: %s", event, exc)

    # -- individual operations ---------------------------------------------

    def _apply_op(self, op: PatchOp) -> None:
        """Dispatches a single op to its handler.

        Args:
            op: The operation to apply.
        """
        state: GameState = self.engine.game_state

        if op.op is OpType.FULL_SYNC:
            self._apply_full_sync(op.value)

        elif op.op is OpType.CARD_UPSERT:
            if op.card_id is None:
                return
            data = dict(op.card or {})
            data["pos_in_matrix"] = self._pos(data.get("pos_in_matrix"))
            state.entity_lookup[op.card_id] = LogicCardAdapter.validate_python(
                data)

        elif op.op is OpType.CARD_UPDATE:
            card = state.entity_lookup.get(op.card_id) if op.card_id else None
            if card is None:
                return
            for key, value in (op.fields or {}).items():
                if key in ("id", "card_type"):
                    continue
                if key == "pos_in_matrix":
                    value = self._pos(value)
                setattr(card, key, value)

        elif op.op is OpType.CARD_REMOVE:
            if op.card_id is not None:
                state.entity_lookup.pop(op.card_id, None)

        elif op.op is OpType.ZONE_ADD:
            collection = self._collection(op.player_id, op.zone)
            if collection is not None and op.card_id not in collection.card_ids:
                collection.add(op.card_id)

        elif op.op is OpType.ZONE_REMOVE:
            collection = self._collection(op.player_id, op.zone)
            if collection is not None and op.card_id in collection.card_ids:
                collection.remove(op.card_id)

        elif op.op is OpType.FIELD_SET:
            if op.row is None or op.col is None:
                return
            row, col = self._cell(op.row, op.col)
            state.field_matrix[row][col] = op.card_id

        elif op.op is OpType.PLAYER_UPDATE:
            player = state.players_lookup.get(op.player_id or "")
            if player is not None:
                for key, value in (op.fields or {}).items():
                    if key in ("id", "is_opponent"):
                        continue
                    setattr(player, key, value)

        elif op.op is OpType.PLAYER_INFO_UPDATE:
            self._apply_player_info(op)

        elif op.op is OpType.TURN_UPDATE:
            for key, value in (op.fields or {}).items():
                setattr(self.engine.turn_manager.turn_state, key, value)

        elif op.op is OpType.TRIGGERABLE_TRAPS_SET:
            from core.data.game_state import TrapContext
            state.triggerable_traps = {
                trap_id: TrapContext.model_validate(ctx)
                for trap_id, ctx in (op.value or {}).items()
            }

        elif op.op is OpType.ACTIVATED_TRAPS_SET:
            state.activated_traps = list(op.value or [])

        elif op.op is OpType.ATTACK_QUEUE_SET:
            from core.data.game_state import AttackEntry
            state.attack_queue = [AttackEntry.model_validate(entry)
                                  for entry in (op.value or [])]

        elif op.op is OpType.EFFECTS_SET:
            self.engine.effect_tracker.deserialize(op.value or [])

        elif op.op is OpType.GAME_OVER_SET:
            state.game_over = bool(op.value)

    def _apply_full_sync(self, value: Dict[str, Any]) -> None:
        """Replaces the whole local state from a server snapshot.

        Args:
            value: A serialized engine as produced by ``GameEngine.serialize``.
        """
        if self.flip:
            # GameState.deserialize already rotates the board and inverts the
            # ownership flags for a viewer on the opposite side.
            self.engine.deserialize(value)
            return

        self.engine.game_state.deserialize_absolute(value["game_state"])
        self.engine.effect_tracker.deserialize(value["effect_tracker"])
        self.engine.event_logger.deserialize(value["event_logger"])
        self.engine.turn_manager.deserialize(value["turn_manager"])

    def _apply_player_info(self, op: PatchOp) -> None:
        """Applies flag and collection updates for one player.

        Args:
            op: A :attr:`OpType.PLAYER_INFO_UPDATE` operation.
        """
        info = self.engine.game_state.player_info.get(op.player_id or "")
        if info is None:
            return
        for key, value in (op.fields or {}).items():
            if key in ZONE_FIELDS.values():
                getattr(info, key).card_ids = list(value)
            else:
                setattr(info, key, value)

    def _collection(self, player_id: Optional[str], zone: Optional[Zone]) -> Any:
        """Looks up a player's card collection for a zone.

        Args:
            player_id: Owning player.
            zone: Which collection to fetch.

        Returns:
            The ``CollectionInfo``, or None when the player/zone is unknown.
        """
        info = self.engine.game_state.player_info.get(player_id or "")
        if info is None or zone is None:
            return None
        return getattr(info, ZONE_FIELDS[zone])

    # -- derived view state -------------------------------------------------

    def normalize(self) -> None:
        """Recomputes the per-viewer flags that are never sent over the wire.

        ``is_opponent`` follows from who the local player is, and ``is_face_down``
        follows from ownership and placement — matching the rules the old
        full-state ``deserialize`` applied.
        """
        state: GameState = self.engine.game_state
        if self.local_player_id is None:
            return

        for player in state.players:
            player.is_opponent = player.id != self.local_player_id

        for card in state.entity_lookup.values():
            owner = state.players_lookup.get(card.owner_id)
            card.is_opponent = bool(owner and owner.is_opponent)

            if card.is_opponent:
                card.is_face_down = (card.card_type == CardType.TRAP
                                     or card.pos_in_matrix is None)
            else:
                card.is_face_down = (card.card_type == CardType.TRAP
                                     and card.pos_in_matrix is not None)
