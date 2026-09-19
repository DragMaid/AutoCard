# Backend guide: hosting AutoCard globally

How to build the server side for the React frontend in `web/`, and how the three
processes fit together.

```
┌────────────────┐   Socket.IO    ┌──────────────────┐   WebSocket    ┌──────────────────────┐
│  React client  │ ─────────────► │  C# relay        │ ─────────────► │  Python engine       │
│  (web/)        │                │  rooms, seats,   │                │  GameEngine + AI     │
│                │ ◄───────────── │  fan-out         │ ◄───────────── │  (source of truth)   │
└────────────────┘   patches      └──────────────────┘   patches      └──────────────────────┘
        intents        server/           intents          engine/
```

The rules live in exactly one place: the Python `GameEngine`. The C# relay owns
rooms, identity and message routing but never inspects or decides gameplay. The
browser draws state and sends requests; it validates nothing that matters.

Single player is the same picture with one seat filled by the trained agent
inside the engine service, not by a socket. Nothing about the protocol changes,
which is why the browser needs no code for it.

Both services are implemented:

| Path | What it is | Run it with |
|---|---|---|
| `server/AutoCard.Server` | The C# relay (ASP.NET Core, .NET 10) | `dotnet run` |
| `engine/` | The authoritative engine service (aiohttp) | `python -m engine` |

## Table of contents

1. [The two message types](#1-the-two-message-types)
2. [Intents (client to engine)](#2-intents-client-to-engine)
3. [Patches (engine to clients)](#3-patches-engine-to-clients)
4. [Board orientation: the one rule you must not get wrong](#4-board-orientation)
5. [The C# relay](#5-the-c-relay)
6. [The Python engine service](#6-the-python-engine-service), including
   [single player](#64-single-player) and [hidden information](#65-hidden-information)
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
| `join` | client → relay | `{ room_id, player_name, mode?, player_id? }` |
| `create_room` | client → relay | `{ player_name, mode? }` |
| `matchmake` | client → relay | `{ player_name }` |
| `cancel_matchmake` | client → relay | `{}` |
| `assign` | relay → client | `{ room_id, player_id, player_index, opponent_id?, mode }` |
| `room_status` | relay → client | `{ room_id, mode, seated, capacity, started, waiting }` |
| `queued` | relay → client | `{ position, size }` |
| `action` | client → relay → engine | an Intent |
| `patch` | engine → relay → clients | a Patch |
| `game_error` | relay → client | `{ message }` |

Only `action` and `patch` are gameplay. The rest is lobby traffic: how you got
into a room, and how full it is.

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

Two players in the same room receive patches with the same `seq` and `cause` but
**different ops**: each one is diffed against the board that player is allowed to
see. A seat with nothing to learn from an action receives no patch for it at all,
so a seat's sequence numbers have gaps by design. See §6.5.

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

1. **Never transform coordinates in the relay.** Pass intents and patches
   through byte-for-byte. Both endpoints already agree on the canonical frame.
2. **`player_index` in the `assign` message decides orientation.** Send `0` to
   the host and `1` to the guest. Sending the wrong index silently mirrors a
   player's board and every move lands in the wrong slot.

`is_opponent` is deliberately stripped from patches (see `diff_state`) because it
is a per-viewer concept, not shared state.

---

## 5. The C# relay

Source: `server/AutoCard.Server`. Responsibilities: seat assignment, room
lifecycle, rate limiting and message fan-out. Nothing else.

```
Program.cs            host, CORS, /socket.io/ endpoint, /health
SocketIO/             Socket.IO v5 over WebSocket, by hand
Game/GameGateway.cs   join + action handlers; the whole "API"
Rooms/                Room, Seat, RoomRegistry, RoomJanitor
Engine/EngineSocket.cs   one WebSocket per room to the Python engine
```

### 5.1 Why there is no Socket.IO dependency

The frontend connects with `transports: ["websocket"]`, so the only protocol
surface in use is a handshake, named events in one namespace, and heartbeats.
`SocketIO/SocketIoCodec.cs` implements exactly that — no polling transport, no
session upgrade, no binary attachments. There is no maintained .NET Socket.IO
*server* tracking the v4 protocol that `socket.io-client` 4.x speaks, and taking
an unmaintained one would put a compatibility risk in the one layer that must
never surprise you.

### 5.2 Data model

`Room` holds the seats and the engine socket; `Seat` outlives the socket sitting
in it, which is what makes reconnects cheap.

```csharp
public sealed class Room
{
    public string RoomId { get; }
    public string Mode { get; }                  // "pvp" or "ai"
    public IReadOnlyList<Seat> Seats { get; }    // index 0 = canonical frame
    public EngineSocket Engine { get; }
    public int LastSeq { get; private set; }
}
```

Seat ids are **not invented by the relay**. They arrive in the engine's
`room_ready` handshake and must match the ids inside the engine's game state.

### 5.3 Getting into a room

Three events land a client in a seat, and all three end in the same
`GameGateway.SeatAsync`:

| Event | Room | Used by |
|---|---|---|
| `join` | the code the client names | "join a code", and every reconnect |
| `create_room` | a fresh server-generated code | "create room", "play vs AI" |
| `matchmake` | a fresh room opened once two players are waiting | "quick match" |

The relay picks the code for the latter two. `RoomRegistry.CreateFreshAsync`
generates five characters from an alphabet with no `I`, `O`, `0` or `1` — a code
gets read aloud and typed by hand, so the pairs that get confused cost more than
the combinations they would add — and reserves it across creation so two
simultaneous creates cannot land two strangers in the same room.

Seat changes run under `Room.EnterAsync`, so two clients hitting join in the same
millisecond cannot be handed the same seat:

```csharp
using (await room.EnterAsync(lifetime.ApplicationStopping))
{
    var seat = room.ClaimSeat(claimedPlayerId, _options.ReconnectGrace);
    if (seat is null) { /* game_error: "Room is full" */ return; }

    seat.Connection = connection;
    connection.UserState = new PlayerSession(room, seat, new TokenBucket(...));

    SendAssignment(connection, room, seat);

    if (!room.Started && room.IsFull)
    {
        room.Started = true;
        room.Engine.SendIntent(room.SystemIntent(seat.PlayerId, "START_GAME"));
    }

    room.Engine.SendIntent(room.SystemIntent(seat.PlayerId, "REQUEST_SYNC"));
    room.BroadcastStatus();
}
```

`START_GAME` is sent before `REQUEST_SYNC` deliberately: the player who
completes the table then sees its opening hand in the first patch it applies,
rather than an empty board followed by a deal.

`room_status` is what drives the browser's "waiting for opponent" screen. It
carries the room code to share and goes `waiting: false` the moment the other
seat fills.

An optional `player_id` on the join payload is a reconnect hint. It grants
nothing — the engine re-validates every action regardless — it only lets a
returning player reclaim the seat it already held. The browser uses it on every
socket.io reconnect, because repeating the original entry would otherwise open a
*second* room for someone who was briefly offline.

### 5.4 Matchmaking

`Game/Matchmaker.cs` is a first-come, first-served queue and nothing more.
There is no rating to match on — the relay holds no accounts and no history — so
anything cleverer would be inventing signal it does not have.

`TryTakePair` drops sockets that closed without a disconnect event before it
pairs, because pairing a dead socket with a live player strands that player in a
room nobody is coming to. Everyone still waiting is re-sent `queued` with their
position after any change.

### 5.5 Handling `action`

`GameGateway.OnActionAsync`:

```csharp
if (!session.Intents.TryConsume()) { /* game_error: throttled */ return; }
if (intent["version"]?.GetValue<int>() is { } v && v != Wire.Version) { /* fail loudly */ }

// Identity comes from the seat, never from the client.
intent["version"]  = Wire.Version;
intent["room_id"]  = session.Room.RoomId;
intent["actor_id"] = session.Seat.PlayerId;

session.Room.Engine.SendIntent(intent);   // forward verbatim; do not interpret
```

The token bucket defaults to 20 intents/second with a burst of 40. A flood
cannot corrupt state, because the engine re-validates everything, but each room's
engine is single-threaded, so an unthrottled client can starve its opponent.

### 5.6 Forwarding patches

`Room.Deliver` sends one patch to the seat named in the engine's envelope, or to
every seat when the envelope names none, and records `seq`. The relay does not
read the patch and does not decide who may see what — the engine has already
written a separate patch per seat (§6.5). Adding a filter here would be both
redundant and the wrong layer: the relay has no idea what a card is.

### 5.7 Configuration

`appsettings.json`, section `AutoCard`:

| Key | Default | Purpose |
|---|---|---|
| `EngineUri` | `ws://127.0.0.1:9000` | Where the Python engine service listens. |
| `AllowedOrigins` | `["*"]` | Browser origins for CORS. Narrow this in production. |
| `ReconnectGraceSeconds` | `90` | How long a vacated seat is held for its occupant. |
| `EngineHandshakeTimeoutSeconds` | `10` | How long to wait for `room_ready`. |
| `IntentsPerSecond` / `IntentBurst` | `20` / `40` | Per-session rate limit. |
| `MaxRooms` | `500` | Cap on concurrent rooms. |
| `SweepIntervalSeconds` | `15` | How often idle rooms are disposed. |

---

## 6. The Python engine service

Source: `engine/`. One `GameEngine` per room, in `AUTHORITATIVE` mode, behind an
aiohttp WebSocket server.

```
engine/service.py    the WebSocket server and room registry
engine/room.py       one match: engine, mailbox, optional AI seat
engine/ai.py         drives the AI seat through GameEnv
engine/transport.py  pushes patches onto the room's outbound queue
engine/config.py     environment-backed settings
```

Run it with `python -m engine`. The entry point installs `DebugLogger` before any
`core` import, because engine modules call `logger.debugx` / `warningx` /
`errorx`, which exist only on that subclass, and loggers are created at import
time. `main.py` and `conftest.py` observe the same ordering.

### 6.1 The relay-to-engine protocol

The relay opens **one socket per room** at `/<room_id>?mode=pvp|ai`.

| `type` | Direction | Payload |
|---|---|---|
| `room_ready` | engine → relay | `{ room_id, player_ids, ai_seats, mode }` |
| `patch` | engine → relay | `{ player_id, patch }` — `player_id` is the seat it is addressed to, or `null` for the room |
| `rejected` | engine → relay | `{ actor_id, intent_type, reason }` |
| `intent` | relay → engine | `{ intent }` |
| `dispose` | relay → engine | `{}` |

`room_ready` is what tells the relay which player ids the room uses, and which
seats are the agent's and therefore unclaimable.

### 6.2 Concurrency

`GameEngine` is not thread-safe and not re-entrant. Every intent for a room —
including the agent's — is funnelled through `Room.inbox` and applied by one
worker task. That single rule is the whole concurrency design, and it is why the
relay can forward messages from two sockets without coordinating anything.

Patches leave through `AsyncQueueTransport`, which hops to the event loop with
`call_soon_threadsafe`. That is correct whether the engine call ran on the loop
or on the worker thread AI inference is offloaded to, and it preserves the order
patches were produced in.

### 6.3 Room lifetime

A room survives its relay socket for `AUTOCARD_ROOM_TTL` seconds (default 300),
so a relay restart resumes the same match instead of dropping it. The relay's own
`RoomJanitor` disposes rooms whose players have all been gone past the reconnect
grace, which sends `dispose` and frees the engine.

### 6.4 Single player

A room is a versus-AI room when the join payload carries `mode: "ai"` (or
`"solo"` / `"single"`), **or** when the room code is `AI`, `SOLO`, or starts with
`AI-`. The room-code convention exists so single player works against the current
frontend, which has no mode selector yet: type `ai-anything` as the room code and
you are seated opposite the agent.

The agent plays through `ml.environment.environment.GameEnv`, the same path
training uses, so a checkpoint behaves in a live match exactly as it did in
self-play. `engine/ai.py`:

* imports torch lazily, so a server hosting only PvP rooms never pays for it;
* runs inference in a thread executor, so it cannot stall the service's loop;
* spaces actions out by `AUTOCARD_AI_DELAY` (default 0.8s), so each one arrives
  as its own patch and the browser can animate it;
* ends the turn rather than guessing when the legal-action mask is empty, and
  caps a turn at `AUTOCARD_AI_MAX_STEPS` actions in case a policy loops.

#### Supplying the model

The agent loads `saves/checkpoint.pth` at the repository root, overridable with
`AUTOCARD_CHECKPOINT`. The file is the one `ml.utils.save_model` writes — a dict
with `dqn`, `policy` and `encoder` state dicts.

**A missing checkpoint is not an error.** The service logs a warning and plays
with untrained weights, so the whole stack is runnable and testable before a
model exists. Drop the file in and restart the engine service; nothing else
changes.

| Variable | Default | Purpose |
|---|---|---|
| `AUTOCARD_ENGINE_HOST` / `AUTOCARD_ENGINE_PORT` | `0.0.0.0` / `9000` | Bind address. |
| `AUTOCARD_CHECKPOINT` | `saves/checkpoint.pth` | Trained weights. |
| `AUTOCARD_AI_DEVICE` | `cpu` | Torch device for inference. |
| `AUTOCARD_AI_DELAY` | `0.8` | Seconds between AI actions. |
| `AUTOCARD_AI_MAX_STEPS` | `64` | Cap on actions in one AI turn. |
| `AUTOCARD_ROOM_TTL` | `300` | Seconds a room outlives its relay socket. |

### 6.5 Hidden information

`engine/visibility.py` decides what each seat may know, and `Room._fanout` applies
it. For every patch the engine produces, the room takes a fresh snapshot, redacts
it once per seat, and diffs that against the board the seat was last shown. The
engine's own ops are never forwarded — they describe the whole board.

Hidden cards are replaced by a blank: the same id, owner and square, an empty
name, and `card_type: "TRAP"` whatever the card really is. On the field that is
no lie, because a face-down card is always a trap; in hand it is deliberate, so
the count of traps, spells and monsters a player holds stays private. Alongside
the cards, the opponent's armed and triggerable trap lists are dropped, as is the
pulse event that marks a trap as about to fire.

What stays visible is what both players can see at a real table: face-up cards on
the field, graveyards, life totals, hand *counts*, and whose turn it is.

Two consequences worth knowing:

* A card is revealed by an ordinary patch carrying its real values for the first
  time. Because a blank is a trap, a revealed monster changes `card_type`, and
  appliers ignore that field on an update — so `visibility.repair_reveals` re-sends
  the whole card as a `CARD_UPSERT` instead.
* A patch that tells a seat nothing is not sent, so per-seat `seq` has gaps.
  Nothing on either client requires them to be contiguous.

The AI is not filtered here: it reads the engine directly, exactly as the training
environment does, so single player has the same information asymmetry as the
trained policy saw in self-play.

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

### Quick match

```
p1 ──matchmake{player_name}──► relay          (queue: [p1])
relay ──queued{position:1, size:1}──► p1
p2 ──matchmake{player_name}──► relay          (queue: [p1, p2] → pair)
relay opens a fresh room, seats p1 at 0 and p2 at 1
relay ──assign + room_status{waiting:false}──► both
relay ──START_GAME──► engine ──patch──► both
```

### A rejected move

The engine returns `False` and emits nothing, so the board simply does not
change. It also sends the relay a `rejected` envelope, which the relay turns
into a `game_error` — to the acting player only, since the opponent's board
never moved and has nothing to explain.

---

## 8. Wiring up the frontend

Three processes, three terminals:

```bash
# 1. the authoritative engine
python -m engine                                  # ws://localhost:9000

# 2. the relay
cd server/AutoCard.Server && dotnet run            # http://localhost:8080

# 3. the frontend
cd web
npm install
cp .env.example .env      # set VITE_GAME_API to your C# relay
npm run dev               # http://localhost:5173
```

Or start the two backend processes together with `./server/dev.sh`.

The lobby offers four ways in: **Quick Match** (be paired with a stranger),
**Create Room** (get a code to share), **Join** (type a code you were sent), and
**Play vs AI**. A room code of `ai`, `solo`, or anything starting with `ai-` also
opens an AI room, which is how single player worked before the lobby had a
button for it.

| Variable | Purpose |
|---|---|
| `VITE_GAME_API` | Base URL of the relay's Socket.IO endpoint. |
| `VITE_ASSET_BASE` | Where `assets/` is served from (default `/assets`). |

In development, `web/public/assets` is a symlink to the repository's `assets/`
directory, so card art is shared with the desktop build. In production, serve
that directory as a static path (or a CDN) and point `VITE_ASSET_BASE` at it.

The frontend needs no other configuration: `SocketConnection` emits one entry
event on connect, and everything else follows from `assign`, `room_status` and
`patch`.

The offline demo mode is gone. It replayed a captured snapshot so the board could
be inspected with no backend running, but it was view-only — every rule lives
server-side, so nothing it showed could be played — and it became a screen that
mainly taught people the game was broken. Run `python -m engine` and press
**Play vs AI** instead; that is a real match, and it works without a checkpoint.

### CORS

Allow the browser origin in `appsettings.json`:

```json
"AutoCard": { "AllowedOrigins": [ "https://yourgame.example" ] }
```

The WebSocket handshake itself is not subject to CORS, so this governs `/health`
and any HTTP route added later. The frontend connects with
`transports: ["websocket"]`, so long-polling does not need to be configured.

---

## 9. Failure handling and resync

**Sequence gaps.** Patches carry a per-room `seq`. If a client applies `seq` 44
and then receives 46, it has missed a delta and its board is wrong. Send
`REQUEST_SYNC`; the engine replies with a `FULL_SYNC` op. `ClientState.seq`
already tracks the last applied value. The relay's per-connection send channel
drops the oldest frame rather than growing without bound behind a slow client,
which is precisely the gap this mechanism exists to repair.

**Reconnects.** Implemented. A vacated `Seat` outlives its socket for
`ReconnectGraceSeconds` (default 90). A returning client that passes its previous
`player_id` on `join` reclaims that seat; it is then re-`assign`ed and sent a
fresh `REQUEST_SYNC`. State lives in the engine, so nothing is lost.

**Relay restart.** The engine keeps a room for `AUTOCARD_ROOM_TTL` seconds
(default 300) after its relay socket drops, so a redeployed relay reconnects and
resumes the same match with the same player ids.

**Engine crash.** The room's state is gone; there is no persistence. The relay
detects the closed engine socket, sends `game_error` to both players and discards
the room. If you want to survive this, periodically store `engine.serialize()`
and rebuild with `engine.deserialize(snapshot)` — an engine-side change.

**Idle rooms.** `RoomJanitor` sweeps every `SweepIntervalSeconds` and disposes
rooms whose human seats have all been vacant past the grace period, which sends
`dispose` to the engine. Without it, every abandoned match leaks a `GameEngine`.

---

## 10. Security checklist

Everything here is implemented in `server/AutoCard.Server`; the file in
parentheses is where to look when changing it.

- [x] **Overwrite `actor_id` at the relay edge** from the socket's seat, never
      from the client's own field (`Game/GameGateway.cs`). This is the one check
      that stops a player acting as their opponent.
- [x] **Verify room membership** before forwarding any intent — an unseated
      socket has no `PlayerSession` and its actions are refused.
- [x] **Rate-limit intents** per session, 20/s with a burst of 40
      (`Util/TokenBucket.cs`).
- [x] **Reject `version` mismatches** so an old client fails loudly.
- [x] **Never transform coordinates** in the relay (see §4). Intents and patches
      pass through byte for byte.
- [x] **Cap payload size** at 64 KB per frame (`SocketIO/SocketIoServer.cs`),
      and cap concurrent rooms at `MaxRooms`.
- [x] **Restrict room ids** to `[A-Za-z0-9_-]{1,24}` at both ends. A room id
      becomes a URL path segment on the engine connection, so it is restricted
      rather than escaped.
- [x] Remember the engine re-validates everything — the relay is defence in
      depth, not the only line.
- [x] **Keep hidden cards off the wire** — the engine writes a separate patch per
      seat, so an opponent's hand and face-down traps are never sent to a client
      that may not see them (`engine/visibility.py`, §6.5). A modified client can
      only read what its player is entitled to.

What the current design deliberately does not do is persist matches (§9), which
is an engine-side change if you need it. There is also no account system — a room
code is the only credential, which is the right trade for drop-in play and the
wrong one if you ever add ranked matches.
