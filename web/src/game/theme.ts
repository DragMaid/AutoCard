/**
 * Visual language for the web build.
 *
 * The board art is 16-bit pixel art, so the surrounding chrome is built to
 * match: hard edges, no border radius, two-tone bevels and offset drop shadows
 * instead of blurs and gradients. Everything is expressed as plain style
 * objects because the whole UI is absolutely positioned inside a fixed design
 * stage, where Tailwind's spacing scale has nothing to attach to.
 */

import type { CSSProperties } from "react";

/**
 * Display font for chrome, labels and numbers.
 *
 * `Silkscreen` is loaded from Google Fonts in `index.html`; the monospace
 * fallbacks keep every panel legible (and roughly the same width) offline.
 */
export const PIXEL_FONT =
  '"Silkscreen", "Courier New", ui-monospace, SFMono-Regular, monospace';

/** Reading font, used only where a real sentence has to be legible. */
export const BODY_FONT =
  'system-ui, -apple-system, "Segoe UI", "DejaVu Sans", "Liberation Sans", sans-serif';

/** The palette, sampled from `assets/background.png`. */
export const COLORS = {
  /** Deepest background, behind the starfield. */
  void: "#06060f",
  /** Panel fill; translucent so the starfield reads through it. */
  panel: "rgba(14, 13, 33, 0.88)",
  /** Panel fill for surfaces that must stay opaque. */
  panelSolid: "#0e0d21",
  /** Recessed wells (hand trays, preview plate). */
  well: "rgba(6, 6, 18, 0.72)",
  /** Default panel edge. */
  edge: "#4a4585",
  /** Lit edge, for the top-left bevel. */
  edgeLit: "#8f89e0",
  text: "#e8e5ff",
  textDim: "#9a95c8",
  textFaint: "#6b6799",
  gold: "#ffd447",
  player: "#6d8cff",
  opponent: "#ff6b6b",
  positive: "#5fd97a",
  danger: "#e0475b",
} as const;

/**
 * A raised panel with a two-tone bevel and a hard drop shadow.
 *
 * @param accent - Border colour; the bevel is derived from it.
 * @param depth - Drop-shadow offset in stage pixels; 0 removes the shadow.
 * @returns Styles to spread onto the panel element.
 */
export function pixelPanel(
  accent: string = COLORS.edge,
  depth = 4,
): CSSProperties {
  const shadow = depth > 0 ? `, ${depth}px ${depth}px 0 rgba(0, 0, 0, 0.55)` : "";
  return {
    backgroundColor: COLORS.panel,
    border: `2px solid ${accent}`,
    borderRadius: 0,
    boxShadow:
      `inset 2px 2px 0 rgba(255, 255, 255, 0.14),` +
      ` inset -2px -2px 0 rgba(0, 0, 0, 0.5)${shadow}`,
  };
}

/**
 * A sunken well, used for trays that hold cards.
 *
 * @param accent - Border colour.
 * @returns Styles to spread onto the well element.
 */
export function pixelWell(accent: string = COLORS.edge): CSSProperties {
  return {
    backgroundColor: COLORS.well,
    border: `2px solid ${accent}`,
    borderRadius: 0,
    boxShadow:
      "inset 2px 2px 0 rgba(0, 0, 0, 0.55), inset -2px -2px 0 rgba(255, 255, 255, 0.08)",
  };
}

/**
 * A chunky arcade button.
 *
 * @param fill - Face colour.
 * @param accent - Border colour.
 * @param enabled - A disabled button loses its bevel and drop shadow.
 * @returns Styles to spread onto the button element.
 */
export function pixelButton(
  fill: string,
  accent: string,
  enabled = true,
): CSSProperties {
  if (!enabled) {
    return {
      backgroundColor: "#1a1930",
      border: `2px solid #2e2c4d`,
      borderRadius: 0,
      color: COLORS.textFaint,
      boxShadow: "inset 2px 2px 0 rgba(0, 0, 0, 0.45)",
      cursor: "not-allowed",
    };
  }
  return {
    backgroundColor: fill,
    border: `2px solid ${accent}`,
    borderRadius: 0,
    color: COLORS.text,
    boxShadow:
      "inset 2px 2px 0 rgba(255, 255, 255, 0.22)," +
      " inset -2px -2px 0 rgba(0, 0, 0, 0.45)," +
      " 4px 4px 0 rgba(0, 0, 0, 0.55)",
    cursor: "pointer",
  };
}

/** Uppercase micro-label used above every value in the side rail. */
export function pixelLabel(color: string = COLORS.textDim): CSSProperties {
  return {
    fontFamily: PIXEL_FONT,
    fontSize: 9,
    letterSpacing: "0.14em",
    textTransform: "uppercase",
    color,
  };
}

/**
 * A 1px hard outline around text, replacing the blurred shadows the rest of
 * the web would use. Keeps small pixel type readable over busy art.
 */
export const TEXT_OUTLINE =
  "1px 1px 0 #000, -1px 1px 0 #000, 1px -1px 0 #000, -1px -1px 0 #000";
