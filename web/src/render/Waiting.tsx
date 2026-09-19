/**
 * The overlay shown while a room still has an empty seat.
 *
 * A seat can be empty for two very different reasons, and the screen says which
 * one it is. Before the match starts, the room is useless until its code
 * reaches someone, so the code is the whole point: set large, spaced, and one
 * click from the clipboard. Once the match has started an empty seat means the
 * opponent dropped, where the code is meaningless — they are already in the
 * room and the relay is holding their seat for them.
 */

import { useCallback, useEffect, useState } from "react";

import {
  COLORS,
  TEXT_OUTLINE,
  UI_FONT,
  pixelButton,
  pixelPanel,
  pixelWell,
} from "../game/theme";

/**
 * Stacking order for modals.
 *
 * Card sprites carry their own z-index (up to 1000 while dragging), so an
 * unpositioned overlay would be painted underneath the board it covers.
 */
const MODAL_Z = 2000;

export interface WaitingOverlayProps {
  visible: boolean;
  /** Room code to share. */
  roomId: string;
  /** True once both seats have been filled at least once. */
  started: boolean;
  /** Abandon the room and go back to the lobby. */
  onLeave: () => void;
}

/** "Waiting for an opponent", with the code to hand out. */
export function WaitingOverlay({
  visible,
  roomId,
  started,
  onLeave,
}: WaitingOverlayProps) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const id = setTimeout(() => setCopied(false), 1600);
    return () => clearTimeout(id);
  }, [copied]);

  const copy = useCallback(() => {
    // `navigator.clipboard` is undefined outside a secure context, which
    // includes a plain-http dev server on anything but localhost.
    navigator.clipboard
      ?.writeText(roomId)
      .then(() => setCopied(true))
      .catch(() => setCopied(false));
  }, [roomId]);

  if (!visible) return null;
  if (started) return <OpponentLeftOverlay onLeave={onLeave} />;

  return (
    <div
      className="absolute inset-0 flex items-center justify-center"
      style={{ backgroundColor: "rgba(4, 4, 12, 0.86)", zIndex: MODAL_Z }}
    >
      <div
        className="flex w-[460px] flex-col items-center gap-6 px-9 py-9"
        style={{ ...pixelPanel(COLORS.gold, 6), backgroundColor: COLORS.panelSolid }}
      >
        <span
          className="leading-none"
          style={{
            fontFamily: UI_FONT,
            fontWeight: 700,
            fontSize: 20,
            letterSpacing: "0.16em",
            color: COLORS.gold,
            textShadow: TEXT_OUTLINE,
          }}
        >
          WAITING FOR OPPONENT
        </span>

        <span
          className="text-center leading-relaxed"
          style={{ fontFamily: UI_FONT, fontSize: 13, color: COLORS.textDim }}
        >
          Send this code to whoever you want to play. The match starts the
          moment they join.
        </span>

        <div className="w-full px-5 py-5 text-center" style={pixelWell(`${COLORS.gold}66`)}>
          <span
            className="leading-none"
            style={{
              fontFamily: UI_FONT,
              fontWeight: 700,
              fontSize: 40,
              letterSpacing: "0.34em",
              // The tracking is applied on the right of every glyph, which
              // would otherwise push the code visibly off-centre.
              paddingLeft: "0.34em",
              color: COLORS.text,
              textShadow: TEXT_OUTLINE,
            }}
          >
            {roomId}
          </span>
        </div>

        <div className="flex w-full gap-3">
          <button
            type="button"
            onClick={copy}
            className="h-[44px] flex-1 leading-none transition-transform active:translate-x-[2px] active:translate-y-[2px]"
            style={{
              ...pixelButton(copied ? "#2f6d43" : "#2b2a4d", copied ? "#7fe39b" : COLORS.edgeLit),
              fontFamily: UI_FONT,
              fontWeight: 700,
              fontSize: 13,
              letterSpacing: "0.14em",
            }}
          >
            {copied ? "COPIED" : "COPY CODE"}
          </button>

          <button
            type="button"
            onClick={onLeave}
            className="h-[44px] flex-1 leading-none transition-transform active:translate-x-[2px] active:translate-y-[2px]"
            style={{
              ...pixelButton("#3a2030", COLORS.danger),
              fontFamily: UI_FONT,
              fontWeight: 700,
              fontSize: 13,
              letterSpacing: "0.14em",
            }}
          >
            CANCEL
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Shown when the other seat empties after the match has begun.
 *
 * Deliberately not the share-code screen: the opponent already has the room,
 * the relay is holding their seat through its grace period, and handing the
 * code out again would invite a third person to a table that is full. The only
 * choice offered is to give the match up, and it says so rather than being
 * labelled "cancel" — quitting a game in progress should not read like backing
 * out of a queue.
 */
function OpponentLeftOverlay({ onLeave }: { onLeave: () => void }) {
  return (
    <div
      className="absolute inset-0 flex items-center justify-center"
      style={{ backgroundColor: "rgba(4, 4, 12, 0.82)", zIndex: MODAL_Z }}
    >
      <div
        className="flex w-[440px] flex-col items-center gap-6 px-9 py-8"
        style={{ ...pixelPanel(COLORS.edge, 6), backgroundColor: COLORS.panelSolid }}
      >
        <span
          className="leading-none"
          style={{
            fontFamily: UI_FONT,
            fontWeight: 700,
            fontSize: 19,
            letterSpacing: "0.16em",
            color: COLORS.text,
            textShadow: TEXT_OUTLINE,
          }}
        >
          OPPONENT DISCONNECTED
        </span>

        <span
          className="text-center leading-relaxed"
          style={{ fontFamily: UI_FONT, fontSize: 13, color: COLORS.textDim }}
        >
          Their seat is being held. The board picks up where it left off if they
          come back.
        </span>

        <div className="flex">
          <button
            type="button"
            onClick={onLeave}
            className="h-[44px] w-[200px] leading-none transition-transform active:translate-x-[2px] active:translate-y-[2px]"
            style={{
              ...pixelButton("#3a2030", COLORS.danger),
              fontFamily: UI_FONT,
              fontWeight: 700,
              fontSize: 13,
              letterSpacing: "0.14em",
            }}
          >
            LEAVE MATCH
          </button>
        </div>
      </div>
    </div>
  );
}
