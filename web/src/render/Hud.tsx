/**
 * Full-stage modal overlays: the trap stage, surrender confirmation and the
 * game-over screen.
 *
 * The turn readout and the End Turn / Surrender buttons used to live here too;
 * they now sit in the side rail (`Panels.tsx`) where they have a rectangle of
 * their own instead of being drawn over the card preview.
 */

import {
  COLORS,
  PIXEL_FONT,
  TEXT_OUTLINE,
  pixelButton,
  pixelPanel,
} from "../game/theme";

/**
 * Stacking order for modals.
 *
 * Card sprites carry their own z-index (up to 1000 while dragging) so they can
 * be layered against each other, which means an unpositioned overlay would be
 * painted *underneath* the board it is supposed to be covering.
 */
const MODAL_Z = 2000;

/** Dimmed overlay shown while the opponent resolves traps. */
export function TrapStageOverlay({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <div
      className="pointer-events-none absolute inset-0 flex items-center justify-center"
      style={{ backgroundColor: "rgba(4, 4, 12, 0.62)", zIndex: MODAL_Z }}
    >
      <div
        className="px-8 py-5"
        style={{ ...pixelPanel(COLORS.gold, 6), backgroundColor: COLORS.panelSolid }}
      >
        <span
          className="leading-none"
          style={{
            fontFamily: PIXEL_FONT,
            fontSize: 24,
            letterSpacing: "0.08em",
            color: COLORS.gold,
            textShadow: TEXT_OUTLINE,
          }}
        >
          OPPONENT RESOLVING TRAPS
        </span>
      </div>
    </div>
  );
}

export interface ConfirmOverlayProps {
  visible: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/** Surrender confirmation dialog. */
export function SurrenderOverlay({
  visible,
  onConfirm,
  onCancel,
}: ConfirmOverlayProps) {
  if (!visible) return null;
  return (
    <div
      className="absolute inset-0 flex items-center justify-center"
      style={{ backgroundColor: "rgba(4, 4, 12, 0.82)", zIndex: MODAL_Z }}
    >
      <div
        className="flex w-[420px] flex-col items-center gap-6 px-8 py-7"
        style={{ ...pixelPanel(COLORS.danger, 6), backgroundColor: COLORS.panelSolid }}
      >
        <span
          className="leading-none"
          style={{
            fontFamily: PIXEL_FONT,
            fontSize: 22,
            letterSpacing: "0.08em",
            color: COLORS.text,
          }}
        >
          SURRENDER?
        </span>
        <p
          className="text-center leading-relaxed"
          style={{
            fontFamily: PIXEL_FONT,
            fontSize: 9,
            color: COLORS.textDim,
          }}
        >
          This ends the match immediately.
        </p>
        <div className="flex gap-4">
          <button
            type="button"
            onClick={onConfirm}
            className="h-[40px] w-[130px] leading-none transition-transform active:translate-x-[2px] active:translate-y-[2px]"
            style={{
              ...pixelButton("#7a2434", "#e0768a"),
              fontFamily: PIXEL_FONT,
              fontSize: 12,
              letterSpacing: "0.12em",
            }}
          >
            SURRENDER
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="h-[40px] w-[130px] leading-none transition-transform active:translate-x-[2px] active:translate-y-[2px]"
            style={{
              ...pixelButton("#2f6d43", "#7fe39b"),
              fontFamily: PIXEL_FONT,
              fontSize: 12,
              letterSpacing: "0.12em",
            }}
          >
            KEEP PLAYING
          </button>
        </div>
      </div>
    </div>
  );
}

export interface GameOverOverlayProps {
  visible: boolean;
  victory: boolean;
  onContinue: () => void;
}

/** Victory / defeat screen. */
export function GameOverOverlay({
  visible,
  victory,
  onContinue,
}: GameOverOverlayProps) {
  if (!visible) return null;

  const color = victory ? COLORS.positive : COLORS.danger;

  return (
    <div
      className="absolute inset-0 flex items-center justify-center"
      style={{ backgroundColor: "rgba(4, 4, 12, 0.86)", zIndex: MODAL_Z }}
    >
      <div
        className="flex w-[480px] flex-col items-center gap-7 px-10 py-9"
        style={{ ...pixelPanel(color, 8), backgroundColor: COLORS.panelSolid }}
      >
        <span
          className="leading-none"
          style={{
            fontFamily: PIXEL_FONT,
            fontSize: 46,
            letterSpacing: "0.1em",
            color,
            textShadow: TEXT_OUTLINE,
          }}
        >
          {victory ? "VICTORY" : "DEFEAT"}
        </span>
        <button
          type="button"
          onClick={onContinue}
          className="h-[46px] w-[220px] leading-none transition-transform active:translate-x-[2px] active:translate-y-[2px]"
          style={{
            ...pixelButton("#2b2a4d", COLORS.edgeLit),
            fontFamily: PIXEL_FONT,
            fontSize: 14,
            letterSpacing: "0.12em",
          }}
        >
          CONTINUE
        </button>
      </div>
    </div>
  );
}
