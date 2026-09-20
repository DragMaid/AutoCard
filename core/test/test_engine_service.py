"""Tests for the engine service's room wiring.

These cover the seams the relay depends on — the handshake it reads player ids
from, the single-worker ordering guarantee, and the AI seat driving itself — not
the game rules, which `test_patch_sync.py` already covers.
"""

from __future__ import annotations

import asyncio
from typing import Any, List

import pytest

from core.network.actions import IntentType, make_intent
from engine.config import EngineConfig
from engine.room import MODE_AI, MODE_PVP, Room


class FakeRelay:
    """Stands in for the relay's WebSocket, collecting what the room sends."""

    def __init__(self) -> None:
        self.sent: List[dict] = []
        self.closed = False

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    def of_type(self, kind: str) -> List[dict]:
        """Returns every message of one envelope type."""
        return [message for message in self.sent if message["type"] == kind]

    def patches_for(self, player_id: str) -> List[dict]:
        """Returns the patches addressed to one seat.

        Patches are written per seat now that each one sees a different board,
        so a test that wants the sequence of a match has to pick a viewer.
        """
        return [message for message in self.of_type("patch")
                if message["player_id"] == player_id]


class FastConfig(EngineConfig):
    """Engine settings with the AI's pacing removed, so tests do not sleep."""

    AI_DELAY = 0.0
    AI_MAX_STEPS = 24


async def settle(room: Room, timeout: float = 30.0) -> None:
    """Waits until the room's inbox is drained and its patches are pumped."""
    await asyncio.wait_for(room.inbox.join(), timeout)
    # The pump is a separate task, so give it a turn to flush.
    for _ in range(3):
        await asyncio.sleep(0)


@pytest.fixture
def relay() -> FakeRelay:
    return FakeRelay()


def run(coro: Any) -> Any:
    """Runs one coroutine on a fresh loop, as the service would."""
    return asyncio.run(coro)


def test_describe_reports_seats_and_mode(relay: FakeRelay) -> None:
    """The handshake carries the ids the relay must not invent."""

    async def scenario() -> dict:
        room = Room("ROOM1", MODE_PVP, asyncio.get_running_loop(), FastConfig)
        try:
            return room.describe()
        finally:
            await room.close()

    described = run(scenario())

    assert described["room_id"] == "ROOM1"
    assert described["mode"] == MODE_PVP
    assert described["ai_seats"] == []
    assert len(described["player_ids"]) == 2
    assert len(set(described["player_ids"])) == 2


def test_ai_room_marks_the_guest_seat(relay: FakeRelay) -> None:
    """Seat 1 belongs to the agent and must be unclaimable by a client."""

    async def scenario() -> dict:
        room = Room("ROOM2", MODE_AI, asyncio.get_running_loop(), FastConfig)
        try:
            return room.describe()
        finally:
            await room.close()

    assert run(scenario())["ai_seats"] == [1]


def test_intents_produce_patches_in_order(relay: FakeRelay) -> None:
    """Patches leave with strictly increasing seq, one action at a time."""

    async def scenario() -> List[dict]:
        room = Room("ROOM3", MODE_PVP, asyncio.get_running_loop(), FastConfig)
        room.attach(relay)
        host = room.players[0]
        try:
            for intent_type in (IntentType.START_GAME, IntentType.DRAW,
                                IntentType.END_TURN):
                room.submit({
                    "type": "intent",
                    "intent": make_intent("ROOM3", host.id, intent_type).model_dump(
                        mode="json"),
                })
            await settle(room)
            return relay.patches_for(host.id)
        finally:
            await room.close()

    patches = run(scenario())
    seqs = [message["patch"]["seq"] for message in patches]

    assert seqs == sorted(seqs)
    assert len(seqs) == len(set(seqs))
    assert [message["patch"]["cause"] for message in patches][:2] == [
        "START_GAME", "DRAW"]


def test_refused_intent_is_reported_not_applied(relay: FakeRelay) -> None:
    """A rule break tells only the actor and changes nothing."""

    async def scenario() -> tuple[List[dict], List[dict]]:
        room = Room("ROOM4", MODE_PVP, asyncio.get_running_loop(), FastConfig)
        room.attach(relay)
        guest = room.players[1]
        try:
            room.submit({
                "type": "intent",
                "intent": make_intent(
                    "ROOM4", room.players[0].id, IntentType.START_GAME
                ).model_dump(mode="json"),
            })
            await settle(room)
            before = len(relay.of_type("patch"))

            # The guest cannot end a turn that is not theirs.
            room.submit({
                "type": "intent",
                "intent": make_intent(
                    "ROOM4", guest.id, IntentType.END_TURN
                ).model_dump(mode="json"),
            })
            await settle(room)
            return relay.of_type("rejected"), relay.of_type("patch")[before:]
        finally:
            await room.close()

    rejected, patches = run(scenario())

    assert len(rejected) == 1
    assert rejected[0]["intent_type"] == IntentType.END_TURN.value
    assert patches == []


def test_intent_for_another_room_is_ignored(relay: FakeRelay) -> None:
    """A misrouted intent must never touch this room's engine."""

    async def scenario() -> List[dict]:
        room = Room("ROOM5", MODE_PVP, asyncio.get_running_loop(), FastConfig)
        room.attach(relay)
        try:
            room.submit({
                "type": "intent",
                "intent": make_intent(
                    "SOMEWHERE-ELSE", room.players[0].id, IntentType.START_GAME
                ).model_dump(mode="json"),
            })
            await settle(room)
            return relay.sent
        finally:
            await room.close()

    assert run(scenario()) == []


def test_ai_plays_its_turn_unprompted(relay: FakeRelay) -> None:
    """Handing the turn to the agent produces its actions as separate patches."""

    async def scenario() -> List[str]:
        room = Room("ROOM6", MODE_AI, asyncio.get_running_loop(), FastConfig)
        room.attach(relay)
        host = room.players[0]
        try:
            for intent_type in (IntentType.START_GAME, IntentType.END_TURN):
                room.submit({
                    "type": "intent",
                    "intent": make_intent("ROOM6", host.id, intent_type).model_dump(
                        mode="json"),
                })
            await settle(room)
            return [message["patch"]["cause"]
                    for message in relay.patches_for(host.id)]
        finally:
            await room.close()

    causes = run(scenario())

    # Everything after the human's END_TURN is the agent acting on its own.
    assert causes[:2] == ["START_GAME", "END_TURN"]
    assert len(causes) > 2, f"the AI never moved: {causes}"
    assert causes[-1] == "END_TURN", f"the AI never gave the turn back: {causes}"
