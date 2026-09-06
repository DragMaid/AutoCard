/**
 * Static board furniture, ported from `Matrix.draw`.
 *
 * Draws the background, the row-tiled grid, the deck plates, the life-point
 * panels and the hand backdrops. Nothing here reacts to pointer input; the
 * sprite and arrow layers sit above it.
 */

import { backgroundUrl, deckUrl, tileUrl } from "../game/assets";
import {
  COLS,
  LAYOUT,
  OPPONENT_COLOR,
  PLAYER_COLOR,
  ROWS,
  getSlotRect,
  type Rect,
} from "../game/layout";
import { CARD_FONT_FAMILY } from "../game/text";

/** Turns a layout rect into absolute-positioning styles. */
export function rectStyle(rect: Rect): React.CSSProperties {
  return {
    left: rect.x,
    top: rect.y,
    width: rect.width,
    height: rect.height,
  };
}

export interface BoardProps {
  localName: string;
  localLife: number;
  opponentName: string;
  opponentLife: number;
  localDeckCount: number;
  opponentDeckCount: number;
}

/**
 * Renders the board beneath the cards.
 *
 * @param props - Player names, life totals and deck sizes.
 * @returns The static board layers.
 */
export function Board({
  localName,
  localLife,
  opponentName,
  opponentLife,
  localDeckCount,
  opponentDeckCount,
}: BoardProps) {
  const { areas } = LAYOUT;

  return (
    <div className="pointer-events-none absolute inset-0">
      <img
        src={backgroundUrl()}
        alt=""
        draggable={false}
        className="absolute inset-0 h-full w-full"
        style={{ objectFit: "fill" }}
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
              className="absolute"
              style={{ ...rectStyle(rect), objectFit: "fill" }}
            />
          );
        }),
      )}

      <DeckPlate rect={areas.opponentDeck} count={opponentDeckCount} />
      <DeckPlate rect={areas.myDeck} count={localDeckCount} />

      <LifePanel
        rect={areas.opponentLp}
        name={opponentName}
        life={opponentLife}
        color={OPPONENT_COLOR}
      />
      <LifePanel
        rect={areas.myLp}
        name={localName}
        life={localLife}
        color={PLAYER_COLOR}
      />

      <HandPlate rect={areas.opponentHand} color={OPPONENT_COLOR} />
      <HandPlate rect={areas.myHand} color={PLAYER_COLOR} />
    </div>
  );
}

/** The deck image, rotated to lie flat as `DeckArea` does. */
function DeckPlate({ rect, count }: { rect: Rect; count: number }) {
  return (
    <div className="absolute" style={rectStyle(rect)}>
      <img
        src={deckUrl()}
        alt=""
        draggable={false}
        className="h-full w-full"
        style={{ objectFit: "fill" }}
      />
      {count > 0 && (
        <span
          className="absolute bottom-1 right-1 rounded bg-black/70 px-1.5 py-0.5 text-xs font-semibold text-white"
          style={{ fontFamily: CARD_FONT_FAMILY }}
        >
          {count}
        </span>
      )}
    </div>
  );
}

/**
 * Life-point readout, ported from `TextArea.draw`.
 *
 * The original centres a large white number inside a bordered box; the player
 * name is added here because the web build has room for it.
 */
function LifePanel({
  rect,
  name,
  life,
  color,
}: {
  rect: Rect;
  name: string;
  life: number;
  color: string;
}) {
  return (
    <div
      className="absolute flex flex-col items-center justify-center"
      style={{ ...rectStyle(rect), border: `2px solid ${color}` }}
    >
      <span
        className="text-[11px] uppercase tracking-wider text-white/70"
        style={{ fontFamily: CARD_FONT_FAMILY }}
      >
        {name}
      </span>
      <span
        className="font-bold leading-none text-white"
        style={{
          fontFamily: CARD_FONT_FAMILY,
          fontSize: 56,
          textShadow: "0 2px 6px rgba(0,0,0,0.8)",
        }}
      >
        {life}
      </span>
    </div>
  );
}

/** Hand backdrop, ported from `HandUI.draw`. */
function HandPlate({ rect, color }: { rect: Rect; color: string }) {
  return (
    <div className="absolute" style={rectStyle(rect)}>
      <img
        src={deckUrl()}
        alt=""
        draggable={false}
        className="h-full w-full opacity-90"
        style={{ objectFit: "fill" }}
      />
      <div
        className="absolute inset-0"
        style={{ border: `2px solid ${color}` }}
      />
    </div>
  );
}
