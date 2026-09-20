"""Tests for what one seat is allowed to learn about the other.

These are the rules that make a card back mean something: they assert on the
bytes a player's socket actually receives, not on what their client chooses to
draw, because a client is the one party in this system that cannot be trusted to
keep a secret.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from core.cards.card import CardType
from core.logic.utils import draw_specific_card
from core.network.actions import IntentType, make_intent
from engine.room import MODE_PVP, Room
from engine import visibility

from core.test.test_engine_service import FakeRelay, FastConfig, run, settle


@pytest.fixture
def relay() -> FakeRelay:
    return FakeRelay()


def _apply(view: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Applies the handful of ops these tests can produce to a plain dict.

    A deliberately dumb stand-in for a real client: enough to reconstruct what a
    seat believes the board looks like after a run of patches.

    Args:
        view (dict): The seat's accumulated game state.
        patch (dict): One serialized patch addressed to that seat.

    Returns:
        dict: The updated view.
    """
    for op in patch["ops"]:
        kind = op["op"]
        if kind == "FULL_SYNC":
            view = op["value"]["game_state"]
        elif kind == "CARD_UPSERT":
            view["entity_lookup"][op["card_id"]] = op["card"]
        elif kind == "CARD_UPDATE":
            card = view["entity_lookup"].get(op["card_id"])
            if card is not None:
                # Mirrors the appliers, which refuse to mutate a card's type.
                card.update({k: v for k, v in op["fields"].items()
                             if k != "card_type"})
        elif kind == "CARD_REMOVE":
            view["entity_lookup"].pop(op["card_id"], None)
        elif kind == "ZONE_ADD":
            _zone(view, op).append(op["card_id"])
        elif kind == "ZONE_REMOVE":
            zone = _zone(view, op)
            if op["card_id"] in zone:
                zone.remove(op["card_id"])
        elif kind == "PLAYER_INFO_UPDATE":
            info = view["player_info"][op["player_id"]]
            for key, value in op["fields"].items():
                if key.endswith("_cards"):
                    info[key]["card_ids"] = list(value)
                else:
                    info[key] = value
        elif kind == "FIELD_SET":
            view["field_matrix"][op["row"]][op["col"]] = op["card_id"]
    return view


def _zone(view: Dict[str, Any], op: Dict[str, Any]) -> List[str]:
    """Returns the card-id list a zone op targets."""
    field = {"hand": "held_cards", "graveyard": "graveyard_cards",
             "deck": "deck_cards"}[op["zone"]]
    return view["player_info"][op["player_id"]][field]["card_ids"]


async def _dealt_room(relay: FakeRelay, room_id: str) -> Room:
    """Opens a pvp room and deals the opening hands."""
    room = Room(room_id, MODE_PVP, asyncio.get_running_loop(), FastConfig)
    room.attach(relay)
    room.submit({
        "type": "intent",
        "intent": make_intent(
            room_id, room.players[0].id, IntentType.START_GAME
        ).model_dump(mode="json"),
    })
    await settle(room)
    return room


def _rebuild(relay: FakeRelay, player_id: str) -> Dict[str, Any]:
    """Replays every patch addressed to one seat into that seat's board."""
    view: Dict[str, Any] = {}
    for message in relay.patches_for(player_id):
        view = _apply(view, message["patch"])
    return view


def test_a_hand_is_never_sent_to_the_other_player(relay: FakeRelay) -> None:
    """The opponent's cards arrive as blanks, not as cards wearing a back."""

    async def scenario() -> tuple[dict, dict, List[str]]:
        room = await _dealt_room(relay, "VIS1")
        host, guest = room.players
        try:
            return (_rebuild(relay, host.id), _rebuild(relay, guest.id),
                    list(room.engine.game_state.player_info[
                        guest.id].held_cards.card_ids))
        finally:
            await room.close()

    host_view, guest_view, guest_hand = run(scenario())

    assert guest_hand, "the guest was never dealt a hand"

    # The host knows how many cards the guest holds, and nothing else.
    assert host_view["player_info"][
        list(host_view["player_info"])[1]]["held_cards"]["card_ids"] == guest_hand

    for card_id in guest_hand:
        blanked = host_view["entity_lookup"][card_id]
        real = guest_view["entity_lookup"][card_id]

        assert blanked["name"] == ""
        assert blanked["description"] == ""
        assert real["name"], "the guest cannot see their own hand"
        assert blanked["id"] == real["id"]
        # Stats are not merely blanked, they are absent from the payload.
        assert "attack" not in blanked


def test_a_set_trap_stays_secret_until_it_fires(relay: FakeRelay) -> None:
    """A face-down trap reaches the opponent as a nameless card in a square."""

    async def scenario() -> tuple[dict, str, str]:
        room = await _dealt_room(relay, "VIS2")
        host, guest = room.players
        state = room.engine.game_state
        # Dealt hands are random, so the card under test is planted rather than
        # searched for.
        draw_specific_card(room.engine, host.id, "Mirror Strike", CardType.TRAP)
        trap = state.player_info[host.id].held_cards.card_ids[-1]
        try:
            room.submit({
                "type": "intent",
                "intent": make_intent(
                    "VIS2", host.id, IntentType.SET_TRAP,
                    card_id=trap, cell=(2, 0),
                ).model_dump(mode="json"),
            })
            await settle(room)
            return (_rebuild(relay, guest.id), trap,
                    state.entity_lookup[trap].name)
        finally:
            await room.close()

    guest_view, trap_id, real_name = run(scenario())

    assert guest_view["field_matrix"][2][0] == trap_id, "the guest sees the square"

    card = guest_view["entity_lookup"][trap_id]
    assert card["name"] == "" and card["name"] != real_name
    assert card["abilities"] == []
    assert card["pos_in_matrix"] == [2, 0]


def test_a_summoned_monster_is_revealed_in_full(relay: FakeRelay) -> None:
    """Playing a card hands the opponent the real one, type included.

    The guard that matters: a blank is a trap, so a monster coming out of a hand
    changes type on the wire, and appliers ignore ``card_type`` on an update.
    Without the reveal being sent as an upsert the opponent would be left with a
    monster permanently mislabelled as a face-down trap.
    """

    async def scenario() -> tuple[dict, str, str]:
        room = await _dealt_room(relay, "VIS3")
        host, guest = room.players
        state = room.engine.game_state
        draw_specific_card(room.engine, host.id, "Warrior", CardType.MONSTER)
        monster = state.player_info[host.id].held_cards.card_ids[-1]
        try:
            room.submit({
                "type": "intent",
                "intent": make_intent(
                    "VIS3", host.id, IntentType.SUMMON,
                    card_id=monster, cell=(2, 1),
                ).model_dump(mode="json"),
            })
            await settle(room)
            return (_rebuild(relay, guest.id), monster,
                    state.entity_lookup[monster].name)
        finally:
            await room.close()

    guest_view, card_id, name = run(scenario())

    card = guest_view["entity_lookup"][card_id]
    assert card["card_type"] == "MONSTER", "the reveal did not replace the blank"
    assert card["name"] == name
    assert card["attack"] >= 0


def test_blanks_do_not_churn_the_wire(relay: FakeRelay) -> None:
    """A hidden card produces no ops while nothing visible about it changes."""

    async def scenario() -> List[dict]:
        room = await _dealt_room(relay, "VIS4")
        host, guest = room.players
        try:
            before = len(relay.patches_for(guest.id))
            room.submit({
                "type": "intent",
                "intent": make_intent(
                    "VIS4", host.id, IntentType.DRAW
                ).model_dump(mode="json"),
            })
            await settle(room)
            return [message["patch"] for message in
                    relay.patches_for(guest.id)[before:]]
        finally:
            await room.close()

    patches = run(scenario())
    ops = [op for patch in patches for op in patch["ops"]]

    # The guest is told the host's hand grew — an upsert for the blank and the
    # zone entry — and nothing about what was drawn.
    upserts = [op for op in ops if op["op"] == "CARD_UPSERT"]
    assert len(upserts) == 1
    assert upserts[0]["card"]["name"] == ""
    assert not [op for op in ops if op["op"] == "CARD_UPDATE"]


def test_redaction_leaves_the_viewer_untouched() -> None:
    """A seat's own cards survive redaction exactly as they were."""
    state = {
        "entity_lookup": {
            "mine": {"id": "mine", "owner_id": "me", "card_type": "TRAP",
                     "name": "Mirror Strike", "pos_in_matrix": [2, 0],
                     "is_triggered": False},
            "theirs": {"id": "theirs", "owner_id": "you", "card_type": "TRAP",
                       "name": "Phantom Dodge", "pos_in_matrix": [1, 0],
                       "is_triggered": False},
        },
        "player_info": {
            "me": {"held_cards": {"card_ids": []}, "active_traps": ["mine"]},
            "you": {"held_cards": {"card_ids": []}, "active_traps": ["theirs"]},
        },
        "triggerable_traps": {"mine": {"target_id": "x"},
                              "theirs": {"target_id": "y"}},
        "activated_traps": ["mine", "theirs"],
    }

    view = visibility.redact_game_state(state, "me")

    assert view["entity_lookup"]["mine"]["name"] == "Mirror Strike"
    assert view["entity_lookup"]["theirs"]["name"] == ""
    assert list(view["triggerable_traps"]) == ["mine"]
    assert view["activated_traps"] == ["mine"]
    assert view["player_info"]["me"]["active_traps"] == ["mine"]
    assert view["player_info"]["you"]["active_traps"] == []
    # The input is never mutated: the engine keeps using it.
    assert state["entity_lookup"]["theirs"]["name"] == "Phantom Dodge"
