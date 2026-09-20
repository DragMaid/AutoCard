"""Per-seat redaction: what one player is allowed to know about the other.

The authoritative engine keeps one complete board and diffs it into patches. Sent
as-is, those patches carry everything: the names and stats of the cards in the
opponent's hand, and what each of their face-down traps actually is. A player who
opens the network tab sees the whole hand. Drawing a card back on top of that data
is a costume, not a rule.

So the room redacts the board once per seat before diffing it, and every viewer is
diffed against the board *they* were last shown. Hidden cards are replaced with an
identical blank: same id, same owner, same square, nothing else. Because the
blanks are stable across patches, a card only produces a patch op when what the
viewer may know about it actually changes — and when a card is revealed, the
reveal is an ordinary update carrying the real values for the first time.

What stays visible is everything both players can already see at the table: cards
on the field that are face up, graveyards, life totals, hand *counts*, and whose
turn it is.

The AI in single-player is not filtered here. It reads the engine directly rather
than through patches, the same way the training environment does.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Iterable, List, Optional, Set

#: Card type used for every blank, whatever the real card is.
#:
#: A face-down card on the field is always a trap, so this tells an opponent
#: nothing there. In hand it is a deliberate lie: sending the true type would
#: leak how many traps, spells or monsters the other player is holding.
_BLANK_TYPE = "TRAP"

#: Field names a blank has to carry to satisfy the trap card schema.
_BLANK_TRAP_FIELDS: Dict[str, Any] = {
    "abilities": [],
    "activation": "ATTACK",
    "effectiveness": None,
    "duration": None,
    "is_triggered": False,
    "triggerable": False,
}


def _blank(card: Dict[str, Any]) -> Dict[str, Any]:
    """Builds the placeholder shown in place of a card a viewer may not see.

    Keeps only what is needed to draw a card back in the right place: the id the
    rest of the patch refers to, who owns it, and where it sits.

    Args:
        card (dict): The real serialized card.

    Returns:
        dict: A card the viewer's client can validate and render face down.
    """
    return {
        "id": card["id"],
        "name": "",
        "description": "",
        "card_type": _BLANK_TYPE,
        "owner_id": card.get("owner_id", ""),
        "image_path": None,
        "is_placed": bool(card.get("is_placed", False)),
        "is_face_down": True,
        "is_opponent": bool(card.get("is_opponent", False)),
        "pos_in_matrix": card.get("pos_in_matrix"),
        **_BLANK_TRAP_FIELDS,
    }


def _is_concealed_trap(card: Dict[str, Any]) -> bool:
    """Whether a card is a trap set on the field that has not gone off yet.

    Args:
        card (dict): A serialized card.

    Returns:
        bool: True while the trap's identity is still secret.
    """
    return (
        card.get("card_type") == "TRAP"
        and card.get("pos_in_matrix") is not None
        and not card.get("is_triggered", False)
    )


def _held_by_others(player_info: Dict[str, Any], viewer_id: str) -> Set[str]:
    """Collects the card ids held in every hand but the viewer's.

    Args:
        player_info (dict): The ``player_info`` map from a serialized state.
        viewer_id (str): The seat being served.

    Returns:
        set: Card ids the viewer is not entitled to see.
    """
    hidden: Set[str] = set()
    for player_id, info in player_info.items():
        if player_id == viewer_id:
            continue
        held = (info.get("held_cards") or {}).get("card_ids") or []
        hidden.update(held)
    return hidden


def redact_game_state(game_state: Dict[str, Any], viewer_id: str) -> Dict[str, Any]:
    """Returns the board as one seat is allowed to see it.

    Args:
        game_state (dict): A serialized :class:`~core.data.game_state.GameState`.
        viewer_id (str): The player this copy is for.

    Returns:
        dict: A deep copy with every card the viewer may not see blanked out.
    """
    view = copy.deepcopy(game_state)
    entities: Dict[str, Any] = view.get("entity_lookup") or {}
    info: Dict[str, Any] = view.get("player_info") or {}

    owners = {card_id: card.get("owner_id") for card_id, card in entities.items()}
    concealed = _held_by_others(info, viewer_id)

    for card_id, card in list(entities.items()):
        if card.get("owner_id") == viewer_id:
            continue
        if card_id in concealed or _is_concealed_trap(card):
            entities[card_id] = _blank(card)
            concealed.add(card_id)

    # Which of the opponent's traps are armed, and what each one is waiting for,
    # is the tell that makes a face-down card readable. Both are dropped; the
    # viewer keeps their own, which is what the ARM button needs.
    view["triggerable_traps"] = {
        trap_id: context
        for trap_id, context in (view.get("triggerable_traps") or {}).items()
        if owners.get(trap_id) == viewer_id
    }
    view["activated_traps"] = [
        trap_id
        for trap_id in (view.get("activated_traps") or [])
        if owners.get(trap_id) == viewer_id
    ]

    for player_id, player in info.items():
        if player_id != viewer_id:
            player["active_traps"] = []

    return view


def redact_snapshot(snapshot: Dict[str, Any], viewer_id: str) -> Dict[str, Any]:
    """Redacts a :func:`core.network.patch.snapshot` result.

    Args:
        snapshot (dict): ``{"game_state", "effects", "turn"}``.
        viewer_id (str): The player this copy is for.

    Returns:
        dict: The same shape, with the board redacted.
    """
    return {
        **snapshot,
        "game_state": redact_game_state(snapshot.get("game_state") or {}, viewer_id),
    }


def redact_engine(serialized: Dict[str, Any], viewer_id: str) -> Dict[str, Any]:
    """Redacts a :meth:`~core.logic.game_engine.GameEngine.serialize` payload.

    Args:
        serialized (dict): The full-sync body.
        viewer_id (str): The player this copy is for.

    Returns:
        dict: The same shape, with the board redacted.
    """
    return {
        **serialized,
        "game_state": redact_game_state(serialized.get("game_state") or {}, viewer_id),
    }


def visible_events(
    events: Iterable[Dict[str, Any]],
    game_state: Dict[str, Any],
    viewer_id: str,
) -> List[Dict[str, Any]]:
    """Drops animation events that would give a hidden card away.

    Every event carries ids only, so nothing in one describes a card. The
    exception is the pulse that marks a trap as armable: played on an opponent's
    face-down card it announces both that the card is a trap and that it is about
    to fire, which is exactly what the card back is hiding.

    Args:
        events: Serialized events from the patch.
        game_state (dict): The unredacted board the events were produced from.
        viewer_id (str): The player these events are for.

    Returns:
        list: The events this viewer may see.
    """
    entities: Dict[str, Any] = game_state.get("entity_lookup") or {}

    def allowed(event: Dict[str, Any]) -> bool:
        card_id: Optional[str] = event.get("card_id")
        if card_id is None or set(event) != {"card_id"}:
            # TrapTriggerableEvent is the only single-field event.
            return True
        owner = (entities.get(card_id) or {}).get("owner_id")
        return owner is None or owner == viewer_id

    return [event for event in events if allowed(event)]


def repair_reveals(
    ops: List[Any],
    game_state: Dict[str, Any],
) -> List[Any]:
    """Re-sends whole cards whose type changed when they were revealed.

    Every blank is a trap, so the patch that reveals a hidden monster or spell
    contains a ``card_type`` change — and both appliers ignore that field on
    purpose, because a card's type never changes under the rules. The update is
    swapped for an upsert carrying the real card, which is the one op that can
    replace a card wholesale.

    Args:
        ops: Ops from a per-viewer diff.
        game_state (dict): The redacted board those ops produce.

    Returns:
        list: The same ops, with reveals expressed as upserts.
    """
    from core.network.actions import OpType, PatchOp

    entities: Dict[str, Any] = game_state.get("entity_lookup") or {}
    repaired: List[Any] = []

    for op in ops:
        changes_type = (
            op.op is OpType.CARD_UPDATE
            and "card_type" in (op.fields or {})
            and op.card_id in entities
        )
        repaired.append(
            PatchOp(op=OpType.CARD_UPSERT, card_id=op.card_id,
                    card=entities[op.card_id])
            if changes_type else op
        )

    return repaired
