"""Round-trip tests for the intent/patch protocol.

Verifies that an authoritative engine's granular patches reproduce its state on a
remote client, including the 180-degree board flip the joining player renders.
"""

import random
from typing import List

import pytest

from core.cards.card import CardType
from core.config import Config
from core.data.player import Player
from core.logic.game_engine import EngineMode, GameEngine
from core.network.actions import Intent, IntentType, Patch
from core.network.patch import PatchApplier, full_sync_patch


class RecordingTransport:
    """Collects patches instead of sending them over a socket."""

    def __init__(self) -> None:
        self.patches: List[Patch] = []
        self.intents: List[Intent] = []

    def send_patch(self, patch: Patch) -> None:
        self.patches.append(patch)

    def send_intent(self, intent: Intent) -> None:
        self.intents.append(intent)


def first_monster(engine: GameEngine, player_id: str) -> str:
    """Returns a monster card id from a player's hand.

    Draws are weighted-random, so a hand is not guaranteed to contain a monster.
    Rather than let that make the suite flaky, top the hand up until one appears.

    Args:
        engine: The engine holding the hand.
        player_id: Whose hand to search.

    Returns:
        The id of a monster card in that player's hand.
    """
    for _ in range(50):
        for card_id in engine.game_state.player_info[player_id].held_cards.card_ids:
            card = engine.game_state.get_card_by_id(card_id)
            if card and card.card_type == CardType.MONSTER:
                return card_id
        engine.draw_card(player_id, check=False)
    raise AssertionError(f"No monster reached {player_id}'s hand")


@pytest.fixture
def match():
    """Builds a started server engine plus a synced remote client."""
    # Card draws are random; pin them so failures are reproducible.
    random.seed(20260906)

    host = Player(player_index=0, name="host")
    guest = Player(player_index=1, name="guest", is_opponent=True)

    transport = RecordingTransport()
    server = GameEngine([host, guest], transport=transport,
                        mode=EngineMode.AUTHORITATIVE, room_id="R1")
    server.start_game()

    client_transport = RecordingTransport()
    client = GameEngine(
        [Player(player_index=0, name="host"),
         Player(player_index=1, name="guest", is_opponent=True)],
        transport=client_transport,
        mode=EngineMode.REMOTE,
        room_id="R1",
    )
    applier = PatchApplier(client, local_player_id=guest.id, flip=True)
    applier.apply(full_sync_patch(server))

    transport.patches.clear()
    return server, client, applier, transport, host, guest


def drain(server, client, applier, transport) -> None:
    """Applies every patch the server emitted since the last drain."""
    for patch in transport.patches:
        applier.apply(patch)
    transport.patches.clear()


def test_full_sync_gives_client_its_own_perspective(match):
    """The joining player sees itself as the local (bottom) player."""
    server, client, _, _, host, guest = match

    assert {p.id for p in client.game_state.players} == {host.id, guest.id}
    assert client.game_state.players_lookup[guest.id].is_opponent is False
    assert client.game_state.players_lookup[host.id].is_opponent is True

    for player in (host, guest):
        assert (len(client.game_state.player_info[player.id].held_cards.card_ids)
                == len(server.game_state.player_info[player.id].held_cards.card_ids))


def test_summon_patch_lands_on_mirrored_cell(match):
    """A host summon appears on the client at the 180-degree mirrored cell."""
    server, client, applier, transport, host, _ = match

    card_id = first_monster(server, host.id)
    assert server.summon_card(host.id, card_id, (2, 0))
    assert len(transport.patches) == 1

    drain(server, client, applier, transport)

    mirrored = (Config.ROWS - 1 - 2, Config.COLS - 1 - 0)
    assert client.game_state.field_matrix[mirrored[0]][mirrored[1]] == card_id
    assert client.game_state.get_card_by_id(card_id).pos_in_matrix == mirrored
    # The host is the opponent from this client's seat.
    assert client.game_state.get_card_by_id(card_id).is_opponent is True


def test_patch_carries_only_the_delta(match):
    """A single summon emits a handful of ops, not the whole game state."""
    server, _, _, transport, host, _ = match

    card_id = first_monster(server, host.id)
    server.summon_card(host.id, card_id, (2, 0))

    ops = transport.patches[0].ops
    assert 0 < len(ops) <= 8
    assert all(op.op.value != "FULL_SYNC" for op in ops)


def test_end_turn_and_draw_stay_in_sync(match):
    """Turn state and the drawn card both reach the client."""
    server, client, applier, transport, host, guest = match

    server.end_turn()
    drain(server, client, applier, transport)

    assert (client.turn_manager.turn_state.turn_count
            == server.turn_manager.turn_state.turn_count)
    assert (client.turn_manager.turn_state.current_player_index
            == server.turn_manager.turn_state.current_player_index)
    assert (client.game_state.player_info[guest.id].held_cards.card_ids
            == server.game_state.player_info[guest.id].held_cards.card_ids)
    # It is now the guest's turn, and the guest is the local client player.
    assert client.is_local_turn() is True


def test_toggle_defence_syncs_mode(match):
    """Switching a monster to defence propagates as a single card update."""
    server, client, applier, transport, host, _ = match

    card_id = first_monster(server, host.id)
    server.summon_card(host.id, card_id, (2, 0))
    drain(server, client, applier, transport)

    assert server.toggle_card(card_id)
    drain(server, client, applier, transport)

    assert (client.game_state.get_card_by_id(card_id).mode
            == server.game_state.get_card_by_id(card_id).mode)


def test_surrender_ends_the_match_on_both_sides(match):
    """Conceding zeroes life points and flags game over through a patch."""
    server, client, applier, transport, host, guest = match

    assert server.surrender(guest.id)
    drain(server, client, applier, transport)

    assert client.game_state.players_lookup[guest.id].life_points == 0
    assert client.game_state.game_over is True


def test_remote_engine_sends_intent_without_mutating(match):
    """A client action forwards an ID-only intent and changes nothing locally."""
    server, client, _, _, host, guest = match

    before = list(client.game_state.player_info[guest.id].held_cards.card_ids)
    card_id = before[0]

    assert client.summon_card(guest.id, card_id, (3, 1)) is False

    intents = client.transport.intents
    assert len(intents) == 1
    assert intents[0].type is IntentType.SUMMON
    assert intents[0].room_id == "R1"
    assert intents[0].actor_id == ""  # set by the client wiring, not the engine
    assert intents[0].payload == {"card_id": card_id, "cell": [3, 1]}
    assert client.game_state.player_info[guest.id].held_cards.card_ids == before


def test_dispatch_rejects_acting_on_someone_elses_card(match):
    """The server refuses an intent whose actor does not own the card."""
    server, _, _, transport, host, guest = match

    host_card = server.game_state.player_info[host.id].held_cards.card_ids[0]
    intent = Intent(room_id="R1", actor_id=guest.id, type=IntentType.SUMMON,
                    payload={"card_id": host_card, "cell": [2, 0]})

    assert server.dispatch(intent) is False
    assert transport.patches == []


def test_dispatch_rejects_end_turn_out_of_turn(match):
    """Only the player whose turn it is may end it."""
    server, _, _, transport, _, guest = match

    intent = Intent(room_id="R1", actor_id=guest.id, type=IntentType.END_TURN)
    assert server.dispatch(intent) is False
    assert transport.patches == []


def test_dispatch_summon_applies_and_emits(match):
    """A well-formed intent mutates the server and produces one patch."""
    server, client, applier, transport, host, _ = match

    card_id = first_monster(server, host.id)
    intent = Intent(room_id="R1", actor_id=host.id, type=IntentType.SUMMON,
                    payload={"card_id": card_id, "cell": [3, 2]})

    assert server.dispatch(intent) is True
    assert len(transport.patches) == 1

    drain(server, client, applier, transport)
    mirrored = (Config.ROWS - 1 - 3, Config.COLS - 1 - 2)
    assert client.game_state.field_matrix[mirrored[0]][mirrored[1]] == card_id


def test_full_wire_loop_through_json(match):
    """Drives a client action through JSON intents and JSON patches.

    Mirrors the production path: the React/pygame client serializes an intent,
    the relay forwards the dictionary untouched, the engine dispatches it, and
    the resulting patch is serialized back and applied by the client.
    """
    server, client, applier, transport, host, guest = match

    # Hand the turn to the guest so its action is legal.
    server.end_turn()
    drain(server, client, applier, transport)
    assert server.turn_manager.get_current_player().id == guest.id

    # Pick a monster from the guest's hand. Card ids are identical on both
    # sides, so resolve it against the authoritative engine (a remote engine
    # cannot draw locally), then re-sync whatever that top-up produced.
    card_id = first_monster(server, guest.id)
    drain(server, client, applier, transport)
    assert card_id in client.game_state.player_info[guest.id].held_cards.card_ids

    client.local_player_id = guest.id
    client.flip = True  # the guest renders the board mirrored
    client.summon_card(guest.id, card_id, (3, 4))

    # --- client -> wire -> server -----------------------------------------
    wire_intent = client.transport.intents[-1].model_dump(mode="json")
    assert wire_intent["room_id"] == "R1"
    assert wire_intent["actor_id"] == guest.id
    # The engine converted the guest's mirrored cell into the server's frame.
    assert wire_intent["payload"] == {
        "card_id": card_id,
        "cell": [Config.ROWS - 1 - 3, Config.COLS - 1 - 4],
    }
    assert server.dispatch(Intent.model_validate(wire_intent)) is True

    # --- server -> wire -> client -----------------------------------------
    assert len(transport.patches) == 1
    wire_patch = transport.patches[0].model_dump(mode="json")
    applier.apply(Patch.model_validate(wire_patch))

    assert client.game_state.field_matrix[3][4] == card_id
    assert client.game_state.get_card_by_id(card_id).is_opponent is False
    assert card_id not in client.game_state.player_info[guest.id].held_cards.card_ids
