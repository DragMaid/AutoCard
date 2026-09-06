# Backend guide: hosting AutoCard globally

How to build the server side for the React frontend in `web/`, and how the three
processes fit together.

```
┌────────────────┐   Socket.IO    ┌──────────────────┐   WebSocket    ┌──────────────────────┐
│  React client  │ ─────────────► │  Java game API   │ ─────────────► │  Python engine       │
│  (web/)        │                │  rooms, auth,    │                │  GameEngine          │
│                │ ◄───────────── │  matchmaking     │ ◄───────────── │  (source of truth)   │
└────────────────┘   patches      └──────────────────┘   patches      └──────────────────────┘
        intents                        intents
```

The rules live in exactly one place: the Python `GameEngine`. The Java API owns
rooms, identity and message routing but never inspects or decides gameplay. The
browser draws state and sends requests; it validates nothing that matters.

## Table of contents

1. [The two message types](#1-the-two-message-types)
2. [Intents (client to engine)](#2-intents-client-to-engine)
3. [Patches (engine to clients)](#3-patches-engine-to-clients)
4. [Board orientation: the one rule you must not get wrong](#4-board-orientation)
5. [The Java API](#5-the-java-api)
6. [The Python engine service](#6-the-python-engine-service)
7. [Message flows](#7-message-flows)
8. [Wiring up the frontend](#8-wiring-up-the-frontend)
9. [Failure handling and resync](#9-failure-handling-and-resync)
10. [Security checklist](#10-security-checklist)

---

## 1. The two message types

Everything on the wire is one of two shapes, defined once in
`core/network/actions.py` and mirrored in `web/src/net/actions.ts`. Keep those
two files in lockstep — they are one protocol with two implementations.

| Direction | Message | Carries |
|---|---|---|
| client → engine | **Intent** | What a player wants to do, as IDs only |
| engine → clients | **Patch** | A list of single-field state mutations, plus animation events |

An intent never carries an outcome. The player says *"summon card X to cell
(3,1)"*, never *"I drew the Fire Mage"*. Every random draw and every battle
result is decided by the engine, which is what makes a public server safe.

A patch is a delta, not a snapshot. Previously the engine re-broadcast its whole
serialized state on every mutation (the old `GameEngine.synchronize`); now a
summon sends about six operations instead of the entire board.

Socket.IO event names (constants in both `transport.py` and `actions.ts`):

| Event | Direction | Payload |
|---|---|---|
| `join` | client → API | `{ room_id, player_name }` |
| `assign` | API → client | `{ room_id, player_id, player_index, opponent_id? }` |
| `action` | client → API → engine | an Intent |
| `patch` | engine → API → clients | a Patch |
| `game_error` | API → client | `{ message }` |

---

## 2. Intents (client to engine)

```json
{
  "version": 1,
  "room_id": "ABC123",
  "actor_id": "e5f1c2...-player-uuid",
  "type": "SUMMON",
  "payload": { "card_id": "7bb81218-...", "cell": [3, 1] },
  "seq": 12
}
```

| Field | Meaning |
|---|---|
| `version` | Protocol version. Reject mismatches at the API edge. |
| `room_id` | Which match this belongs to. The API routes on this. |
| `actor_id` | Who is acting. **The API must overwrite this** with the identity bound to the socket — never trust the client's value. |
| `type` | One of the intent types below. |
| `payload` | IDs and plain scalars only. |
| `seq` | Client-side counter, echoed in logs for debugging. |

### Intent types and payloads

| `type` | `payload` | Notes |
|---|---|---|
| `START_GAME` | `{}` | Deals opening hands. |
| `DRAW` | `{}` | Actor draws; the engine picks the card. |
| `SUMMON` | `{ card_id, cell: [row, col] }` | Monster from hand to field. |
| `SET_TRAP` | `{ card_id, cell: [row, col] }` | Trap placed face-down. |
| `CAST_SPELL` | `{ card_id, target_id? }` | `target_id` may be `null`. |
| `TOGGLE` | `{ card_id }` | Switch attack/defence position. |
| `ATTACK` | `{ card_id, target_id, target_is_player }` | Target is a card id, or a player id when `target_is_player` is true. |
| `UPGRADE` | `{ card_id, target_id }` | Merge two matching monsters. |
| `TOGGLE_TRAP_ACTIVATION` | `{ card_id, activated }` | Flag a triggerable trap during the trap stage. |
| `END_TURN` | `{}` | Ends the turn, or resolves the trap stage. |
| `SURRENDER` | `{}` | Concede. |
| `REQUEST_SYNC` | `{}` | Ask for a full snapshot. |

`GameEngine.dispatch` re-validates every one of these. It takes the acting player
from `actor_id` (never from the payload), checks card ownership via `_owns`, and
then runs the normal rule engines. An intent that breaks a rule returns `False`
and produces no patch.

---

## 3. Patches (engine to clients)

```json
{
  "version": 1,
  "room_id": "ABC123",
  "seq": 45,
  "cause": "SUMMON",
  "ops": [
    { "op": "ZONE_REMOVE", "player_id": "e5f1...", "zone": "hand", "card_id": "7bb8..." },
    { "op": "FIELD_SET", "row": 3, "col": 1, "card_id": "7bb8..." },
    { "op": "CARD_UPDATE", "card_id": "7bb8...",
      "fields": { "is_placed": true, "pos_in_matrix": [3, 1] } },
    { "op": "PLAYER_INFO_UPDATE", "player_id": "e5f1...",
      "fields": { "has_summoned_monster": true } }
  ],
  "events": []
}
```

`seq` increases by one per patch, per room. Clients apply patches in order and
ask for a resync when they see a gap.

### Operation types

| `op` | Fields | Effect |
|---|---|---|
| `CARD_UPSERT` | `card_id`, `card` | Insert/replace a full card object. |
| `CARD_UPDATE` | `card_id`, `fields` | Merge changed fields into a card. |
| `CARD_REMOVE` | `card_id` | Drop a card from the lookup. |
| `ZONE_ADD` / `ZONE_REMOVE` | `player_id`, `zone`, `card_id` | Move between `hand` / `graveyard` / `deck`. |
| `FIELD_SET` | `row`, `col`, `card_id` | Set or clear one grid slot (`card_id: null` clears). |
| `PLAYER_UPDATE` | `player_id`, `fields` | Life points, name, etc. |
| `PLAYER_INFO_UPDATE` | `player_id`, `fields` | Per-turn flags, or a whole zone list. |
| `TURN_UPDATE` | `fields` | `current_player_index`, `is_trap_stage`, `turn_count`. |
| `TRIGGERABLE_TRAPS_SET` | `value` | Map of trap id → `{ target_id }`. |
| `ACTIVATED_TRAPS_SET` | `value` | Array of trap ids. |
| `ATTACK_QUEUE_SET` | `value` | Array of attack entries. |
| `EFFECTS_SET` | `value` | Array of active effects. |
| `GAME_OVER_SET` | `value` | Boolean. |
| `FULL_SYNC` | `value` | A complete `GameEngine.serialize()` snapshot. |

`events` carries the animation events from `core/data/events.py` (attack, trap
trigger, toggle, spell, merge). They drive visuals only — state comes from `ops`.

### How patches are produced

The engine does not hand-write deltas at each mutation site. `GameEngine._transaction`
snapshots the engine, runs the action through the ordinary rule engines, snapshots
again, and calls `diff_state` to derive the minimal op list. One player action
produces exactly one patch, because nested calls (a spell that draws a card)
collapse into the outermost transaction.

The practical consequence for you: **you never write patch code.** Add a rule to
the engine and the protocol follows automatically.

---

## 4. Board orientation

> This is the single most common source of "it works for the host, not the guest"
> bugs. Read this section before writing routing code.

All wire data is in the **server's canonical frame**: row 0 is the host's far
edge, and `player_index == 0` is the host.

The guest sits on the other side of the table and renders the board rotated 180°.
So the guest's client:

* mirrors incoming cells: `(row, col) → (ROWS-1-row, COLS-1-col)`;
* converts outgoing cells back before sending;
* recomputes `is_opponent` and `is_face_down` locally from its own seat.

That is already implemented — `PatchApplier` (`core/network/patch.py` and
`web/src/net/patch.ts`) and `SocketConnection.canonicalCell`. Two rules for the
backend:

1. **Never transform coordinates in the Java API.** Pass intents and patches
   through byte-for-byte. Both endpoints already agree on the canonical frame.
2. **`player_index` in the `assign` message decides orientation.** Send `0` to
   the host and `1` to the guest. Sending the wrong index silently mirrors a
   player's board and every move lands in the wrong slot.

`is_opponent` is deliberately stripped from patches (see `diff_state`) because it
is a per-viewer concept, not shared state.

---

## 5. The Java API

Responsibilities: authentication, room lifecycle, seat assignment, and message
fan-out. Nothing else.

### 5.1 Dependencies

Socket.IO (not raw WebSocket) because the frontend uses `socket.io-client`:

```xml
<dependency>
  <groupId>com.corundumstudio.socketio</groupId>
  <artifactId>netty-socketio</artifactId>
  <version>2.0.9</version>
</dependency>
```

### 5.2 Data model

```java
/** One live match. */
public final class Room {
    public final String roomId;
    /** Seat index 0 = host, 1 = guest. */
    public final Map<Integer, String> seatToPlayerId = new ConcurrentHashMap<>();
    public final Map<UUID, Integer> sessionToSeat  = new ConcurrentHashMap<>();
    /** Connection to this room's Python engine. */
    public EngineSocket engine;
    /** Last patch seq forwarded, for gap detection. */
    public final AtomicInteger lastSeq = new AtomicInteger(0);
}
```

Keep a `Map<String, Room>` for lookup, and a `Map<UUID, String>` from session id
to room id so a disconnect can find its room in O(1).

### 5.3 Handling `join`

```java
server.addEventListener("join", JoinRequest.class, (client, data, ack) -> {
    Room room = rooms.computeIfAbsent(data.roomId, this::createRoom);

    synchronized (room) {
        if (room.sessionToSeat.size() >= 2) {
            client.sendEvent("game_error", Map.of("message", "Room is full"));
            return;
        }
        int seat = room.sessionToSeat.size();          // 0 then 1
        String playerId = room.seatToPlayerId.get(seat); // from the engine

        room.sessionToSeat.put(client.getSessionId(), seat);
        client.joinRoom(data.roomId);                  // Socket.IO room fan-out

        client.sendEvent("assign", Map.of(
            "room_id",      room.roomId,
            "player_id",    playerId,
            "player_index", seat));

        // Hand the newcomer the current board.
        room.engine.send(intent(room.roomId, playerId, "REQUEST_SYNC"));

        if (room.sessionToSeat.size() == 2) {
            room.engine.send(intent(room.roomId, playerId, "START_GAME"));
        }
    }
});
```

The player ids come from the engine when the room is created (see §6). The API
does not invent them: they must match the ids inside the engine's game state.

### 5.4 Handling `action`

```java
server.addEventListener("action", Map.class, (client, intent, ack) -> {
    String roomId = sessionToRoom.get(client.getSessionId());
    Room room = rooms.get(roomId);
    if (room == null) return;

    Integer seat = room.sessionToSeat.get(client.getSessionId());
    if (seat == null) return;

    // Never trust client-supplied identity.
    intent.put("room_id",  roomId);
    intent.put("actor_id", room.seatToPlayerId.get(seat));

    room.engine.send(intent);   // forward verbatim; do not interpret
});
```

Rate-limit here (a token bucket of ~20 intents/second per session is plenty).
The engine is single-threaded per room, so a flood is a denial-of-service risk
even though it cannot corrupt state.

### 5.5 Forwarding patches

```java
void onEnginePatch(Room room, Map<String, Object> patch) {
    room.lastSeq.set(((Number) patch.get("seq")).intValue());
    server.getRoomOperations(room.roomId).sendEvent("patch", patch);
}
```

Broadcast the same patch to both seats. Do **not** filter it per player: hidden
information is already handled, because a face-down card's identity is only
revealed by the engine when it should be, and each client derives
`is_face_down` from its own seat.

> If you later want strict hidden-information guarantees (a modified client
> currently could read an opponent's hand from the patch stream), the fix belongs
> in the engine: filter `CARD_UPSERT` payloads per recipient before emitting.
> That is a change to `GameEngine._send_patch`, not to the Java layer.

---

## 6. The Python engine service

One `GameEngine` per room, wrapped in a small WebSocket service. The engine is
already built for this — construct it in `AUTHORITATIVE` mode with a transport
and it emits patches on its own.

```python
"""Minimal engine service. One GameEngine per room."""
import asyncio, json, logging, uuid
import websockets

from core.logger import DebugLogger
logging.setLoggerClass(DebugLogger)          # must precede core imports

from core.data.player import Player
from core.logic.game_engine import EngineMode, GameEngine
from core.network.actions import Intent, Patch


class WebSocketTransport:
    """Pushes patches onto the room's outbound queue."""

    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self.queue = queue
        self.loop = loop

    def send_patch(self, patch: Patch) -> None:
        # Called synchronously from engine code, so hop back to the loop.
        self.loop.call_soon_threadsafe(
            self.queue.put_nowait, patch.model_dump(mode="json"))


class Room:
    def __init__(self, room_id: str, loop):
        self.room_id = room_id
        self.outbox: asyncio.Queue = asyncio.Queue()

        host = Player(player_index=0, name="host")
        guest = Player(player_index=1, name="guest", is_opponent=True)
        self.player_ids = [host.id, guest.id]

        self.engine = GameEngine(
            [host, guest],
            transport=WebSocketTransport(self.outbox, loop),
            mode=EngineMode.AUTHORITATIVE,
            room_id=room_id,
            local_player_id=host.id,
        )

    def dispatch(self, raw: dict) -> None:
        try:
            intent = Intent.model_validate(raw)
        except Exception as exc:
            logging.getLogger(__name__).warning("Bad intent: %s", exc)
            return
        if intent.room_id != self.room_id:
            return
        self.engine.dispatch(intent)      # emits a patch through the transport


rooms: dict[str, Room] = {}


async def handler(ws):
    loop = asyncio.get_running_loop()
    room_id = ws.request.path.strip("/") or str(uuid.uuid4())

    room = rooms.get(room_id)
    if room is None:
        room = rooms[room_id] = Room(room_id, loop)
        # Tell the Java API which player ids this room uses.
        await ws.send(json.dumps({"type": "room_ready",
                                  "room_id": room_id,
                                  "player_ids": room.player_ids}))

    async def pump():
        while True:
            patch = await room.outbox.get()
            await ws.send(json.dumps({"type": "patch", "patch": patch}))

    pump_task = asyncio.create_task(pump())
    try:
        async for message in ws:
            room.dispatch(json.loads(message))
    finally:
        pump_task.cancel()


async def main():
    async with websockets.serve(handler, "0.0.0.0", 9000):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
```

Three things that matter:

* **Install `DebugLogger` before importing `core`.** Engine modules call
  `logger.debugx` / `warningx` / `errorx`, which only exist on that subclass, and
  loggers are created at import time. `main.py` and `conftest.py` do the same.
* **One engine per room, and one thread per engine.** `GameEngine` is not
  thread-safe. Serialise intents for a room through a single queue or task.
* **`local_player_id=host.id`** puts the authoritative engine in the host's
  frame, which is the canonical frame described in §4.

For a working reference of the same idea in-process, read
`core/network/server.py` and `core/network/utils.py` — the desktop host runs an
authoritative engine and relays patches over Socket.IO in exactly this shape.

---

## 7. Message flows

### Joining

```
guest ──join{room_id}──────────► API
API   ──assign{player_id, player_index:1}──► guest
API   ──REQUEST_SYNC───────────► engine
engine──patch{ops:[FULL_SYNC]}─► API ──► guest
guest applies snapshot, mirrors the board for seat 1
```

### Playing a card

```
guest drags a card onto its slot (2,3) in ITS OWN frame
guest converts to canonical (1,1) and sends:
      action{type:SUMMON, payload:{card_id, cell:[1,1]}}
API   overwrites actor_id, forwards to engine
engine validates ownership + rules, mutates, diffs
engine──patch{seq:46, ops:[ZONE_REMOVE, FIELD_SET, CARD_UPDATE, ...]}──►
API   broadcasts to both seats
host  applies at (1,1); guest applies mirrored at (2,3)
```

### A rejected move

The engine returns `False`, emits nothing, and the board simply does not change.
If you want the player to see why, have the API send `game_error` when
`dispatch` reports a rejection.

---

## 8. Wiring up the frontend

```bash
cd web
npm install
cp .env.example .env      # set VITE_GAME_API to your Java API
npm run dev               # http://localhost:5173
```

| Variable | Purpose |
|---|---|
| `VITE_GAME_API` | Base URL of the Java Socket.IO endpoint. |
| `VITE_ASSET_BASE` | Where `assets/` is served from (default `/assets`). |

In development, `web/public/assets` is a symlink to the repository's `assets/`
directory, so card art is shared with the desktop build. In production, serve
that directory as a static path (or a CDN) and point `VITE_ASSET_BASE` at it.

The frontend needs no other configuration: `SocketConnection` emits `join` on
connect, and everything else follows from `assign` and `patch`.

Without a backend, the lobby's **Demo** buttons load a captured snapshot
(`web/src/demo/snapshot.json`) so the board and layout can be inspected. Demo
mode is view-only, because all rules live server-side. To refresh that fixture,
serialize any engine: `json.dump(engine.serialize(), f)`.

### CORS

`netty-socketio` needs the browser origin allowed:

```java
config.setOrigin("https://yourgame.example");
```

The frontend connects with `transports: ["websocket"]`, so long-polling does not
need to be configured.

---

## 9. Failure handling and resync

**Sequence gaps.** Patches carry a per-room `seq`. If a client applies `seq` 44
and then receives 46, it has missed a delta and its board is wrong. Send
`REQUEST_SYNC`; the engine replies with a `FULL_SYNC` op. `ClientState.seq`
already tracks the last applied value.

**Reconnects.** Treat a reconnect as a fresh join that reuses the seat: match the
returning session to its previous `player_id`, re-send `assign`, then
`REQUEST_SYNC`. State lives in the engine, so nothing is lost as long as the room
outlives the socket. Give rooms a grace period (60–120s) before disposal.

**Engine crash.** The room's state is gone; there is no persistence. Either
accept the loss and tell both players, or periodically store
`engine.serialize()` and rebuild with `engine.deserialize(snapshot)`.

**Idle rooms.** Dispose a room once both sockets have been gone past the grace
period, otherwise engines accumulate.

---

## 10. Security checklist

- [ ] **Overwrite `actor_id` at the API edge** from the authenticated session.
      This is the one check that stops a player acting as their opponent.
- [ ] **Verify room membership** before forwarding any intent.
- [ ] **Rate-limit intents** per session.
- [ ] **Reject `version` mismatches** so an old client fails loudly.
- [ ] **Never transform coordinates** in the API (see §4).
- [ ] **Cap payload size**; intents are small, so a few KB is a generous limit.
- [ ] Remember the engine re-validates everything — the API is defence in depth,
      not the only line.

Two things the current design deliberately does not do: it does not hide the
opponent's hand from a modified client (§5.5), and it does not persist matches
(§9). Both are engine-side changes if you need them.
