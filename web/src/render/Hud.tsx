/**
 * HUD and modal overlays, ported from `gui/screen/hud.py`.
 *
 * Keeps the original geometry: a turn panel pinned to the lower-left with the
 * End Turn and Surrender buttons beneath it, and full-screen overlays for the
 * trap stage, surrender confirmation and game over.
 */

import { DESIGN_HEIGHT } from "../game/layout";
import { CARD_FONT_FAMILY } from "../game/text";
import type { HudSnapshot } from "../game/gameClient";

export interface HudProps {
  hud: HudSnapshot;
  onEndTurn: () => void;
  onSurrender: () => void;
}

/**
 * The turn panel and action buttons.
 *
 * @param props - HUD values plus button callbacks.
 * @returns The HUD layer.
 */
export function Hud({ hud, onEndTurn, onSurrender }: HudProps) {
  const label = hud.isTrapStage
    ? hud.isLocalTurn
      ? "Your Trap"
      : "Enemy Trap"
    : hud.isLocalTurn
      ? "Your Turn"
      : "Opponent Turn";

  const labelColor = hud.isTrapStage
    ? "rgb(255, 200, 0)"
    : hud.isLocalTurn
      ? "rgb(100, 255, 100)"
      : "rgb(255, 100, 100)";

  return (
    <div
      className="absolute"
      style={{
        left: 10,
        top: DESIGN_HEIGHT - 235,
        width: 160,
        fontFamily: CARD_FONT_FAMILY,
      }}
    >
      <div
        className="flex flex-col items-center gap-2 rounded-[10px] px-3 py-4"
        style={{
          backgroundColor: "rgba(20, 20, 30, 0.78)",
          border: "2px solid rgb(100, 100, 150)",
          height: 125,
        }}
      >
        <span className="text-[19px] text-[rgb(220,220,255)]">
          Turn: {hud.turnCount}
        </span>
        <span className="text-[19px] font-semibold" style={{ color: labelColor }}>
          {label}
        </span>
        <span className="text-[13px] text-slate-400">
          Hand {hud.localHandCount} · Grave {hud.localGraveyard}
        </span>
      </div>

      <button
        type="button"
        onClick={onSurrender}
        className="mt-2 h-10 w-[150px] rounded border-2 border-slate-300/70 text-[16px] font-semibold text-white transition-colors"
        style={{ backgroundColor: "rgb(80, 30, 30)" }}
      >
        Surrender
      </button>

      <button
        type="button"
        onClick={onEndTurn}
        disabled={!hud.isLocalTurn}
        className="mt-2 h-[50px] w-[150px] rounded border-2 text-[22px] font-semibold transition-colors disabled:cursor-not-allowed"
        style={
          hud.isLocalTurn
            ? {
                backgroundColor: "rgb(50, 100, 50)",
                borderColor: "rgb(200, 200, 200)",
                color: "white",
              }
            : {
                backgroundColor: "rgb(30, 30, 30)",
                borderColor: "rgb(60, 60, 60)",
                color: "rgb(100, 100, 100)",
              }
        }
      >
        End Turn
      </button>
    </div>
  );
}

/** Dimmed overlay shown while the opponent resolves traps. */
export function TrapStageOverlay({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <div
      className="pointer-events-none absolute inset-0 flex items-center justify-center"
      style={{ backgroundColor: "rgba(0,0,0,0.47)" }}
    >
      <span
        className="text-[48px] font-semibold text-white"
        style={{ fontFamily: CARD_FONT_FAMILY }}
      >
        Opponent Resolving Traps...
      </span>
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
      className="absolute inset-0 flex flex-col items-center justify-center gap-8"
      style={{
        backgroundColor: "rgba(0,0,0,0.78)",
        fontFamily: CARD_FONT_FAMILY,
      }}
    >
      <span className="text-[36px] font-semibold text-white">Surrender?</span>
      <div className="flex gap-5">
        <button
          type="button"
          onClick={onConfirm}
          className="h-10 w-[100px] rounded border-2 border-slate-300/70 text-white"
          style={{ backgroundColor: "rgb(120, 30, 30)" }}
        >
          Yes
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="h-10 w-[100px] rounded border-2 border-slate-300/70 text-white"
          style={{ backgroundColor: "rgb(30, 100, 30)" }}
        >
          No
        </button>
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
  return (
    <div
      className="absolute inset-0 flex flex-col items-center justify-center gap-10"
      style={{
        backgroundColor: "rgba(0,0,0,0.7)",
        fontFamily: CARD_FONT_FAMILY,
      }}
    >
      <span
        className="text-[72px] font-bold"
        style={{ color: victory ? "rgb(50,250,50)" : "rgb(250,50,50)" }}
      >
        {victory ? "VICTORY" : "DEFEAT"}
      </span>
      <button
        type="button"
        onClick={onContinue}
        className="h-[50px] w-[200px] rounded border-2 border-slate-300/70 text-[22px] text-white"
        style={{ backgroundColor: "rgb(50, 50, 50)" }}
      >
        Continue
      </button>
    </div>
  );
}
