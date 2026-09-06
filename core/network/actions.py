"""Wire protocol for room-based networked play.

Two families of messages travel between a client and the authoritative engine:

* :class:`Intent` — client → server. Describes *what a player wants to do* using
  nothing but IDs already known to both sides (card ids, player ids, grid cells).
  Intents never carry resolved outcomes: the server owns every random draw and
  every battle result.

* :class:`Patch` — server → clients. A list of :data:`PatchOp` entries that each
  mutate a *single* piece of a :class:`~core.data.game_state.GameState`. This
  replaces the previous behaviour of re-broadcasting the whole serialized engine
  on every mutation.

Both models are plain pydantic so the same JSON shape is consumed by the Python
pygame client, the Java relay API and the React frontend.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

PROTOCOL_VERSION = 1


class IntentType(str, Enum):
    """Player-initiated requests sent to the authoritative engine."""

    START_GAME = "START_GAME"
    DRAW = "DRAW"
    SUMMON = "SUMMON"
    SET_TRAP = "SET_TRAP"
    CAST_SPELL = "CAST_SPELL"
    TOGGLE = "TOGGLE"
    ATTACK = "ATTACK"
    UPGRADE = "UPGRADE"
    TOGGLE_TRAP_ACTIVATION = "TOGGLE_TRAP_ACTIVATION"
    END_TURN = "END_TURN"
    SURRENDER = "SURRENDER"
    REQUEST_SYNC = "REQUEST_SYNC"


class OpType(str, Enum):
    """Granular state mutations produced by the authoritative engine."""

    CARD_UPSERT = "CARD_UPSERT"
    CARD_UPDATE = "CARD_UPDATE"
    CARD_REMOVE = "CARD_REMOVE"
    ZONE_ADD = "ZONE_ADD"
    ZONE_REMOVE = "ZONE_REMOVE"
    FIELD_SET = "FIELD_SET"
    PLAYER_UPDATE = "PLAYER_UPDATE"
    PLAYER_INFO_UPDATE = "PLAYER_INFO_UPDATE"
    TURN_UPDATE = "TURN_UPDATE"
    TRIGGERABLE_TRAPS_SET = "TRIGGERABLE_TRAPS_SET"
    ACTIVATED_TRAPS_SET = "ACTIVATED_TRAPS_SET"
    ATTACK_QUEUE_SET = "ATTACK_QUEUE_SET"
    EFFECTS_SET = "EFFECTS_SET"
    GAME_OVER_SET = "GAME_OVER_SET"
    FULL_SYNC = "FULL_SYNC"


class Zone(str, Enum):
    """Card collections owned by a player."""

    HAND = "hand"
    GRAVEYARD = "graveyard"
    DECK = "deck"


class Intent(BaseModel):
    """A client request routed to the room's authoritative engine.

    Attributes:
        version: Protocol version, so a relay can reject mismatched clients.
        room_id: Room this intent belongs to. The relay uses it for fan-out.
        actor_id: Player id claiming the action; the engine re-validates it.
        type: Which action is being requested.
        payload: ID-only arguments for the action.
        seq: Client-side monotonic counter, echoed back for ack/debugging.
    """

    version: int = PROTOCOL_VERSION
    room_id: str
    actor_id: str
    type: IntentType
    payload: Dict[str, Any] = Field(default_factory=dict)
    seq: int = 0


class PatchOp(BaseModel):
    """A single state mutation.

    Only the fields relevant to :attr:`op` are populated; everything else stays
    ``None`` so the JSON stays small on the wire.

    Attributes:
        op: The mutation kind.
        card_id: Target card for card/zone operations.
        card: Full serialized card for :attr:`OpType.CARD_UPSERT`.
        fields: Partial field map for the ``*_UPDATE`` operations.
        player_id: Owning player for zone/player operations.
        zone: Which collection a zone operation targets.
        row: Field matrix row for :attr:`OpType.FIELD_SET`.
        col: Field matrix column for :attr:`OpType.FIELD_SET`.
        value: Generic payload for the ``*_SET`` operations.
    """

    op: OpType
    card_id: Optional[str] = None
    card: Optional[Dict[str, Any]] = None
    fields: Optional[Dict[str, Any]] = None
    player_id: Optional[str] = None
    zone: Optional[Zone] = None
    row: Optional[int] = None
    col: Optional[int] = None
    value: Any = None


class Patch(BaseModel):
    """A batch of mutations plus the animation events they produced.

    Attributes:
        version: Protocol version.
        room_id: Room the patch applies to.
        seq: Server-side monotonic counter. Clients apply patches in order and
            can request a full resync when they detect a gap.
        cause: The intent type that produced this patch, for logging/debugging.
        ops: Ordered mutations to apply.
        events: Serialized :mod:`core.data.events` entries that drive animations.
    """

    version: int = PROTOCOL_VERSION
    room_id: str = ""
    seq: int = 0
    cause: Optional[str] = None
    ops: List[PatchOp] = Field(default_factory=list)
    events: List[Dict[str, Any]] = Field(default_factory=list)

    def is_empty(self) -> bool:
        """Returns True when the patch would not change anything."""
        return not self.ops and not self.events


def make_intent(
    room_id: str,
    actor_id: str,
    intent_type: IntentType,
    seq: int = 0,
    **payload: Any,
) -> Intent:
    """Builds an :class:`Intent` from keyword payload arguments.

    Args:
        room_id: Room the intent targets.
        actor_id: Player id performing the action.
        intent_type: Which action is requested.
        seq: Client-side sequence number.
        **payload: ID-only arguments for the action.

    Returns:
        The constructed intent.
    """
    return Intent(
        room_id=room_id,
        actor_id=actor_id,
        type=intent_type,
        seq=seq,
        payload={k: v for k, v in payload.items() if v is not None},
    )


def cell_to_list(cell: Optional[Tuple[int, int]]) -> Optional[List[int]]:
    """Normalizes a grid cell to a JSON-safe list.

    Args:
        cell: A ``(row, col)`` tuple, or None.

    Returns:
        A two-element list, or None when no cell was given.
    """
    if cell is None:
        return None
    return [int(cell[0]), int(cell[1])]


def list_to_cell(value: Any) -> Optional[Tuple[int, int]]:
    """Parses a JSON grid cell back into a tuple.

    Args:
        value: A two-element sequence, or None.

    Returns:
        A ``(row, col)`` tuple, or None when the value was empty.
    """
    if value is None:
        return None
    return (int(value[0]), int(value[1]))
