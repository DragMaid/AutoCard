/**
 * Static board furniture.
 *
 * Draws the board panel, the field tiles and the two hand trays. Nothing here
 * reacts to pointer input; the sprite and arrow layers sit above it.
 *
 * The tile art is 80x40 — a wide, flat plinth — so each tile is drawn at its
 * native 2:1 ratio inside its slot rather than stretched to fill it. That is
 * what opens the gutters between rows, which is where the cards' drop shadows
 * and the arrow layer now have room to read.
 */

import { tileUrl } from "../game/assets";
import {
  COLS,
  LAYOUT,
  OPPONENT_COLOR,
  PLAYER_COLOR,
  ROWS,
  getSlotRect,
  type Rect,
} from "../game/layout";
import { COLORS, PIXEL_FONT, pixelWell } from "../game/theme";

/** Turns a layout rect into absolute-positioning styles. */
export function rectStyle(rect: Rect): React.CSSProperties {
  return {
    left: rect.x,
    top: rect.y,
    width: rect.width,
    height: rect.height,
  };
}

/** Native aspect of `tile1.png` / `tile2.png`. */
const TILE_ASPECT = 80 / 40;

/**
 * Renders the board beneath the cards.
 *
 * @returns The static board layers.
 */
export function Board() {
  const { areas, grid } = LAYOUT;

  const tileHeight = Math.min(grid.slotHeight, grid.slotWidth / TILE_ASPECT);
  const tileOffset = (grid.slotHeight - tileHeight) / 2;

  return (
    <div className="pointer-events-none absolute inset-0">
      <div
        className="absolute"
        style={{
          ...rectStyle(areas.boardColumn),
          backgroundColor: "rgba(8, 8, 22, 0.55)",
          border: `2px solid ${COLORS.edge}`,
          boxShadow: "inset 0 0 0 2px rgba(0, 0, 0, 0.5)",
        }}
      />

      {/* Field tiles: the top half belongs to the opponent. */}
      {Array.from({ length: ROWS }, (_, row) =>
        Array.from({ length: COLS }, (_, col) => {
          const rect = getSlotRect(row, col);
          if (!rect) return null;
          return (
            <img
              key={`${row}-${col}`}
              src={tileUrl(row)}
              alt=""
              draggable={false}
              className="pixel-art absolute"
              style={{
                left: rect.x + 3,
                top: rect.y + tileOffset,
                width: rect.width - 6,
                height: tileHeight,
              }}
            />
          );
        }),
      )}

      {/* The seam between the two halves of the field. */}
      <div
        className="absolute"
        style={{
          left: grid.originX,
          top: grid.originY + grid.height / 2 - 1,
          width: grid.width,
          height: 2,
          backgroundColor: "rgba(255, 255, 255, 0.14)",
        }}
      />

      <HandTray
        rect={areas.opponentHand}
        color={OPPONENT_COLOR}
        label="Opponent Hand"
      />
      <HandTray rect={areas.myHand} color={PLAYER_COLOR} label="Your Hand" />
    </div>
  );
}

/** A sunken tray a hand of cards rests in. */
function HandTray({
  rect,
  color,
  label,
}: {
  rect: Rect;
  color: string;
  label: string;
}) {
  return (
    <div className="absolute" style={rectStyle(rect)}>
      <div
        className="absolute inset-0"
        style={pixelWell(`${color}66`)}
        aria-hidden
      />
      <span
        className="absolute left-2 top-1 leading-none"
        style={{
          fontFamily: PIXEL_FONT,
          fontSize: 8,
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: `${color}99`,
        }}
      >
        {label}
      </span>
    </div>
  );
}
