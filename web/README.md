# AutoCard web client

React + Tailwind port of the pygame interface in `gui/` and `core/gui/`.

The browser renders game state and sends player intents. It contains no game
rules: the Python `GameEngine` is the source of truth, reached through the Java
API. See [`docs/BACKEND.md`](../docs/BACKEND.md) for the protocol and how to
build the server side.

## Running

```bash
npm install
cp .env.example .env     # point VITE_GAME_API at your Java API
npm run dev              # http://localhost:5173
```

No backend yet? The lobby's **Demo** buttons load a captured engine snapshot so
the board, layout and card rendering can be inspected. Demo mode is view-only —
actions are recorded and reported, not resolved, because rules live server-side.

```bash
npm run build       # production bundle
npm run typecheck   # tsc --noEmit
```

## How it maps to the pygame build

| Web | Ports |
|---|---|
| `game/layout.ts` | `gui/background/matrix_field.py`, `game_area.py` |
| `game/renderEngine.ts` | `core/gui/render_engine.py` |
| `game/eventHandler.ts` | `core/gui/event_handler.py` |
| `game/inputManager.ts` | `core/gui/input_manager.py` |
| `game/animations.ts` | `gui/animations/*` |
| `game/sprites.ts` | `gui/sprites/*` |
| `render/CardFace.tsx` | `gui/cards/card_gui.py`, `stat_overlay.py` |
| `render/Board.tsx` | `Matrix.draw`, `DeckArea`, `TextArea`, `HandUI` |
| `render/Overlays.tsx` | `gui/screen/arrow.py`, `preview_card_table.py` |
| `render/Hud.tsx` | `gui/screen/hud.py` |
| `net/patch.ts` | `core/network/patch.py` (applier half) |
| `net/actions.ts` | `core/network/actions.py` |

`types/game.ts` mirrors the pydantic serialization format exactly, so a payload
travels Python → Java → browser with no field renaming.

## Design notes

**Fixed stage, uniform scale.** Everything is laid out against the same
1280×720 design resolution the desktop build uses (`Config.SCREEN_SIZE`), then
scaled to fit the viewport by `render/Stage.tsx`. Slot geometry is computed with
the same integer arithmetic as Python (`int()` → `Math.trunc`, `//` →
`Math.floor`), so the grid lands on identical coordinates: origin (321, 130),
189×115 slots, 945×460 board.

**Landscape only.** In portrait the stage is replaced by a rotate prompt rather
than reflowing into a layout the engine has no concept of.

**Animation off the reconciler.** React mounts sprites and re-renders only when a
card's *appearance* changes. Position, rotation and opacity are written straight
to the DOM by the frame loop in `render/useGameLoop.ts`.

**Rotation is scoped to the card surface.** A monster in defence position rotates
90°, but its ATK/DEF line, merge highlight and trap button stay upright — pygame
blits those in screen space around the card's bounding box, so they must not spin
with it. That is why each sprite has both an outer node (position) and an inner
face node (rotation).

**The board is mirrored per seat.** Wire data is always in the server's frame.
Seat 1 renders rotated 180°, mirrors incoming cells, and converts outgoing cells
back before sending. `net/patch.ts` and `net/client.ts` handle this; see §4 of
the backend guide.
