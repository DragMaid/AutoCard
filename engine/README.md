# AutoCard engine service

The authoritative game server: one `GameEngine` per room, in `AUTHORITATIVE`
mode, behind an aiohttp WebSocket server. Every rule and every random outcome is
decided here, which is what makes a public relay safe to run.

```bash
python -m engine        # ws://0.0.0.0:9000, GET /health
```

## Layout

| Module | What it does |
|---|---|
| `service.py` | The WebSocket server, room registry and idle sweeper. |
| `room.py` | One match: engine, mailbox, optional AI seat. |
| `ai.py` | Drives the AI seat through `ml.environment.GameEnv`. |
| `transport.py` | Pushes engine patches onto the room's outbound queue. |
| `visibility.py` | Decides what each seat is allowed to see. |
| `config.py` | Environment-backed settings. |

## Protocol

The relay opens one socket per room at `/<room_id>?mode=pvp|ai`.

| `type` | Direction | Payload |
|---|---|---|
| `room_ready` | out | `{ room_id, player_ids, ai_seats, mode }` |
| `patch` | out | `{ player_id, patch }` — addressed to one seat, or `null` for the room |
| `rejected` | out | `{ actor_id, intent_type, reason }` |
| `intent` | in | `{ intent }` |
| `dispose` | in | `{}` |

`room_ready` is how the relay learns the room's player ids. It never invents
them: they must match the ids inside the engine's game state.

## Hidden information

Patches are written per seat. Before diffing, `Room._fanout` redacts the board
once for each player through `visibility.py`: the opponent's hand and their
face-down traps become blanks carrying nothing but an id, an owner and a square,
and their armed-trap lists are dropped. Each seat is then diffed against the
board *it* was last shown, so a card's real values only reach a client at the
moment the rules reveal it.

The consequence to remember when reading patch traffic: two players in the same
room see the same `seq` and `cause` with different ops, and a seat that has
nothing to learn from an action gets no patch at all.

The AI seat is not redacted. It reads the engine directly, exactly as the
training environment does.

## Single player

A room created with `mode=ai` seats the trained agent at index 1. It plays
through `GameEnv`, the same path training uses, so a checkpoint behaves in a live
match exactly as it did in self-play. Each action emits its own patch, so the
browser animates the AI's turn move by move rather than seeing it resolve at
once.

The model is `saves/checkpoint.pth` at the repository root — the file
`ml.utils.save_model` writes, holding `dqn`, `policy` and `encoder` state dicts.
**A missing checkpoint is not an error:** the service warns and plays with
untrained weights, so the stack is runnable before a model exists. Drop the file
in and restart.

## Settings

| Variable | Default | Purpose |
|---|---|---|
| `AUTOCARD_ENGINE_HOST` | `0.0.0.0` | Bind address. |
| `AUTOCARD_ENGINE_PORT` | `9000` | Bind port. |
| `AUTOCARD_CHECKPOINT` | `saves/checkpoint.pth` | Trained weights. |
| `AUTOCARD_AI_DEVICE` | `cpu` | Torch device for inference. |
| `AUTOCARD_AI_DELAY` | `0.8` | Seconds between AI actions. |
| `AUTOCARD_AI_MAX_STEPS` | `64` | Cap on actions in one AI turn. |
| `AUTOCARD_ROOM_TTL` | `300` | Seconds a room outlives its relay socket. |

## Two rules for changing this code

1. **`GameEngine` is not thread-safe or re-entrant.** Every intent for a room,
   including the agent's, goes through `Room.inbox` and is applied by that room's
   single worker task. Keep it that way.
2. **Install `DebugLogger` before importing `core`.** Engine modules call
   `logger.debugx` / `warningx` / `errorx`, which exist only on that subclass,
   and loggers are created at import time. `engine/__main__.py`, `main.py` and
   `conftest.py` all observe this ordering.
