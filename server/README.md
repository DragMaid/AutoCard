# AutoCard relay (C#)

The room server the browser talks to. It owns seats, room lifecycle and message
fan-out, and it decides nothing about the game — every rule lives in the Python
engine behind it. See [`docs/BACKEND.md`](../docs/BACKEND.md) for the protocol.

```
browser ──Socket.IO──► relay ──WebSocket──► engine (python -m engine)
        ◄──patches───        ◄──patches───
```

## Run it

```bash
# terminal 1 — the authoritative engine
python -m engine

# terminal 2 — this relay
cd server/AutoCard.Server
ASPNETCORE_ENVIRONMENT=Development dotnet run     # http://localhost:8080

# terminal 3 — the frontend
cd web && npm run dev                             # http://localhost:5173
```

Or start the two backend processes together:

```bash
./server/dev.sh
```

Requires the .NET 10 SDK. `GET /health` reports liveness and the live room count.

## Playing

The lobby offers four ways in, and all four end in the same `SeatAsync`:

| Lobby action | Event | Room |
|---|---|---|
| Quick Match | `matchmake` | a fresh room, opened once two players are waiting |
| Create Room | `create_room` | a fresh room; you get the code to share |
| Join | `join` | the code you typed |
| Play vs AI | `create_room` with `mode: "ai"` | a fresh room, seat 1 driven by the agent |

A room code of `ai`, `solo`, or anything starting with `ai-` also opens an AI
room, which is how single player worked before the lobby had a button for it.

### Client events

| Event | Direction | Payload |
|---|---|---|
| `join` | in | `{ room_id, player_name, mode?, player_id? }` |
| `create_room` | in | `{ player_name, mode? }` |
| `matchmake` | in | `{ player_name }` |
| `cancel_matchmake` | in | `{}` |
| `action` | in | an Intent |
| `assign` | out | `{ room_id, player_id, player_index, opponent_id?, mode }` |
| `room_status` | out | `{ room_id, mode, seated, capacity, started, waiting }` |
| `queued` | out | `{ position, size }` |
| `patch` | out | a Patch, holding only what that player may see |
| `game_error` | out | `{ message }` |

`player_id` on `join` is a reconnect hint. It grants nothing — the engine
re-validates every action — it only lets a returning player reclaim the seat it
already held, within `ReconnectGraceSeconds`.

## Configuration

`appsettings.json`, section `AutoCard`. The defaults are development defaults;
the two worth changing before a public deployment are `AllowedOrigins` (narrow
it from `*` to your site) and `EngineUri`.

| Key | Default | Purpose |
|---|---|---|
| `EngineUri` | `ws://127.0.0.1:9000` | Where the Python engine service listens. |
| `AllowedOrigins` | `["*"]` | Browser origins allowed by CORS. |
| `ReconnectGraceSeconds` | `90` | How long a vacated seat is held for its occupant. |
| `EngineHandshakeTimeoutSeconds` | `10` | How long to wait for `room_ready`. |
| `IntentsPerSecond` / `IntentBurst` | `20` / `40` | Per-session rate limit. |
| `MaxRooms` | `500` | Cap on concurrent rooms. |
| `SweepIntervalSeconds` | `15` | How often idle rooms are disposed. |

Kestrel's bind address lives under `Kestrel:Endpoints:Http:Url`, and every key
can be overridden by environment variable, e.g. `AutoCard__EngineUri`.

## Layout

| Path | What it does |
|---|---|
| `Program.cs` | Host, CORS, the `/socket.io/` endpoint and `/health`. |
| `SocketIO/` | Socket.IO v5 over WebSocket, implemented directly. |
| `Protocol/Wire.cs` | Event names and DTOs shared with Python and TypeScript. |
| `Game/GameGateway.cs` | The entry, action and disconnect handlers — the whole API. |
| `Game/Matchmaker.cs` | The quick-match queue. |
| `Rooms/` | `Room`, `Seat`, `RoomRegistry`, `RoomJanitor`. |
| `Engine/EngineSocket.cs` | One WebSocket per room to the Python engine. |
| `Util/TokenBucket.cs` | Per-session intent rate limiting. |

### Why the Socket.IO layer is hand-written

The frontend connects with `transports: ["websocket"]`, so the protocol surface
actually in use is a handshake, named events in one namespace, and heartbeats —
about 250 lines. No maintained .NET Socket.IO *server* tracks the v4 protocol
`socket.io-client` 4.x speaks, and an unmaintained one would put a compatibility
risk in the layer that must never surprise you.

## Three rules for changing this code

1. **Never transform coordinates.** Everything on the wire is in the engine's
   canonical frame and each client mirrors from its own seat. A helpful-looking
   rotation here is the classic "works for the host, not the guest" bug.
2. **Never trust client identity.** `actor_id` is overwritten from the socket's
   seat on every intent. That single line is what stops a player acting as their
   opponent.
3. **Never decide gameplay.** If you find yourself reading a card id to work out
   what should happen, the change belongs in the Python engine instead.
