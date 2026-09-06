/**
 * The side rail: player panels, the card inspector's frame and the controls.
 *
 * In the pygame build all of this shared one 320px margin and simply drew over
 * itself. Here each block owns a rectangle from `LAYOUT.areas` and nothing
 * overlaps, which is what makes room for the things that were missing — deck
 * and graveyard counts, whose turn it is, and a life total you can read.
 */

import { cardBackUrl } from "../game/assets";
import { LAYOUT, OPPONENT_COLOR, PLAYER_COLOR, type Rect } from "../game/layout";
import {
  COLORS,
  PIXEL_FONT,
  TEXT_OUTLINE,
  pixelButton,
  pixelPanel,
} from "../game/theme";
import { rectStyle } from "./Board";

export interface PlayerPanelProps {
  rect: Rect;
  deckRect: Rect;
  name: string;
  life: number;
  maxLife: number;
  handCount: number;
  graveyardCount: number;
  deckCount: number;
  isOpponent: boolean;
  /** Draws the active-turn ring around the panel. */
  active: boolean;
}

/**
 * One player's identity, life total, deck and pile counts.
 *
 * @param props - The player's live counters and the rectangles to fill.
 * @returns The panel.
 */
export function PlayerPanel({
  rect,
  deckRect,
  name,
  life,
  maxLife,
  handCount,
  graveyardCount,
  deckCount,
  isOpponent,
  active,
}: PlayerPanelProps) {
  const color = isOpponent ? OPPONENT_COLOR : PLAYER_COLOR;
  const lifeRatio = maxLife > 0 ? Math.max(0, Math.min(1, life / maxLife)) : 0;

  // The seat label already says which side this is, so a display name that
  // only repeats it ("opponent", "you") is dropped rather than shown twice.
  const role = isOpponent ? "OPPONENT" : "YOU";
  const showName = name.trim().toUpperCase() !== role;

  return (
    <>
      <div
        className="absolute"
        style={{
          ...rectStyle(rect),
          ...pixelPanel(active ? color : `${color}55`),
          outline: active ? `2px solid ${color}` : undefined,
          outlineOffset: 2,
        }}
      >
        {/* The right edge is reserved for the deck stack. */}
        <div
          className="flex h-full flex-col justify-between"
          style={{
            paddingLeft: 12,
            paddingRight: rect.x + rect.width - deckRect.x + 8,
            paddingTop: 8,
            paddingBottom: 8,
          }}
        >
          <div className="flex items-baseline gap-2">
            <span
              className="leading-none"
              style={{
                fontFamily: PIXEL_FONT,
                fontSize: 8,
                letterSpacing: "0.18em",
                color,
              }}
            >
              {role}
            </span>
            {showName && (
              <span
                className="min-w-0 flex-1 truncate leading-none"
                style={{
                  fontFamily: PIXEL_FONT,
                  fontSize: 10,
                  color: COLORS.textDim,
                }}
              >
                {name}
              </span>
            )}
          </div>

          <div className="flex items-end gap-2">
            <span
              className="leading-none"
              style={{
                fontFamily: PIXEL_FONT,
                fontSize: 30,
                color: COLORS.text,
                textShadow: TEXT_OUTLINE,
              }}
            >
              {life}
            </span>
            <span
              className="pb-1 leading-none"
              style={{
                fontFamily: PIXEL_FONT,
                fontSize: 8,
                letterSpacing: "0.14em",
                color: COLORS.textFaint,
              }}
            >
              LP
            </span>
          </div>

          {/* Life bar: a flat, hard-edged meter, no gradient. */}
          <div
            className="h-[6px] w-full"
            style={{
              backgroundColor: "rgba(0, 0, 0, 0.55)",
              border: "1px solid rgba(255, 255, 255, 0.12)",
            }}
          >
            <div
              className="h-full"
              style={{
                width: `${lifeRatio * 100}%`,
                backgroundColor: color,
              }}
            />
          </div>

          <div className="flex gap-1.5">
            <Counter label="HAND" value={handCount} />
            <Counter label="GRAVE" value={graveyardCount} />
          </div>
        </div>
      </div>

      <DeckStack rect={deckRect} count={deckCount} color={color} />
    </>
  );
}

/** A small labelled count chip. */
function Counter({ label, value }: { label: string; value: number }) {
  return (
    <span
      className="px-1.5 py-[3px] leading-none"
      style={{
        fontFamily: PIXEL_FONT,
        fontSize: 8,
        letterSpacing: "0.1em",
        color: COLORS.textDim,
        backgroundColor: "rgba(0, 0, 0, 0.45)",
        border: "1px solid rgba(255, 255, 255, 0.1)",
      }}
    >
      {label} {value}
    </span>
  );
}

/**
 * The deck, drawn as a stack of card backs with the remaining count on it.
 *
 * The offset copies are what make it read as a pile rather than a single card;
 * it is also the point draw animations fly out of.
 */
function DeckStack({
  rect,
  count,
  color,
}: {
  rect: Rect;
  count: number;
  color: string;
}) {
  return (
    <div className="absolute" style={rectStyle(rect)}>
      {count > 1 && (
        <img
          src={cardBackUrl()}
          alt=""
          draggable={false}
          className="pixel-art absolute h-full w-full opacity-70"
          style={{ left: 4, top: 4 }}
        />
      )}
      {count > 0 && (
        <img
          src={cardBackUrl()}
          alt=""
          draggable={false}
          className="pixel-art absolute h-full w-full opacity-85"
          style={{ left: 2, top: 2 }}
        />
      )}

      <img
        src={cardBackUrl()}
        alt=""
        draggable={false}
        className="pixel-art absolute inset-0 h-full w-full"
        style={{ opacity: count > 0 ? 1 : 0.25 }}
      />

      <span
        className="absolute left-1/2 -translate-x-1/2 px-1 py-[2px] leading-none"
        style={{
          bottom: -4,
          fontFamily: PIXEL_FONT,
          fontSize: 10,
          color: COLORS.text,
          backgroundColor: "rgba(6, 6, 18, 0.92)",
          border: `1px solid ${color}`,
        }}
      >
        {count}
      </span>
    </div>
  );
}

export interface ActionPanelProps {
  turnCount: number;
  isLocalTurn: boolean;
  isTrapStage: boolean;
  onEndTurn: () => void;
  onSurrender: () => void;
}

/**
 * Turn readout and the two turn-level buttons.
 *
 * @param props - Turn state plus the button callbacks.
 * @returns The controls block.
 */
export function ActionPanel({
  turnCount,
  isLocalTurn,
  isTrapStage,
  onEndTurn,
  onSurrender,
}: ActionPanelProps) {
  const rect = LAYOUT.areas.actions;

  const label = isTrapStage
    ? isLocalTurn
      ? "YOUR TRAPS"
      : "ENEMY TRAPS"
    : isLocalTurn
      ? "YOUR TURN"
      : "OPPONENT TURN";

  const labelColor = isTrapStage
    ? COLORS.gold
    : isLocalTurn
      ? COLORS.positive
      : OPPONENT_COLOR;

  return (
    <div
      className="absolute flex flex-col gap-1.5 px-2.5 py-2"
      style={{ ...rectStyle(rect), ...pixelPanel() }}
    >
      <div className="flex items-center justify-between">
        <span
          className="leading-none"
          style={{
            fontFamily: PIXEL_FONT,
            fontSize: 9,
            letterSpacing: "0.14em",
            color: COLORS.textFaint,
          }}
        >
          TURN {turnCount}
        </span>
        <span
          className="leading-none"
          style={{
            fontFamily: PIXEL_FONT,
            fontSize: 11,
            letterSpacing: "0.08em",
            color: labelColor,
            textShadow: TEXT_OUTLINE,
          }}
        >
          {label}
        </span>
      </div>

      <button
        type="button"
        onClick={onEndTurn}
        disabled={!isLocalTurn}
        className="h-[46px] w-full leading-none transition-transform active:translate-x-[2px] active:translate-y-[2px]"
        style={{
          ...pixelButton("#2f6d43", "#7fe39b", isLocalTurn),
          fontFamily: PIXEL_FONT,
          fontSize: 15,
          letterSpacing: "0.08em",
        }}
      >
        END TURN
      </button>

      <button
        type="button"
        onClick={onSurrender}
        className="h-[26px] w-full leading-none transition-transform active:translate-x-[2px] active:translate-y-[2px]"
        style={{
          ...pixelButton("#5a2130", "#c26b7a"),
          fontFamily: PIXEL_FONT,
          fontSize: 10,
          letterSpacing: "0.14em",
        }}
      >
        SURRENDER
      </button>
    </div>
  );
}
