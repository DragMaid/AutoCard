/**
 * Port of the pygame board geometry.
 *
 * `gui/background/matrix_field.py` computes every rectangle from the screen size
 * and the ratios in `GameAreaConfig`. The whole UI is laid out once here against
 * a fixed 1280x720 design stage, then CSS-scaled to whatever the viewport is, so
 * the React build matches the desktop build slot for slot at any resolution.
 *
 * Integer arithmetic mirrors Python exactly: `int(...)` is `Math.trunc` and `//`
 * is `Math.floor`.
 */

import type { Cell } from "../types/game";

/** Design resolution, matching `Config.SCREEN_SIZE`. */
export const DESIGN_WIDTH = 1280;
export const DESIGN_HEIGHT = 720;

/** Field dimensions, matching `Config.ROWS` / `Config.COLS`. */
export const ROWS = 4;
export const COLS = 5;

/** Ratios and spacing from `GameAreaConfig`. */
export const LEFT_RATIO = 0.25;
export const RIGHT_RATIO = 0.01;
export const TOP_RATIO = 0.18;
export const BOTTOM_RATIO = 0.18;
export const AREA_PADDING = 10;
export const AREA_BORDER_WIDTH = 2;

/** Colors from `GameAreaConfig`, as CSS strings. */
export const PLAYER_COLOR = "rgb(100, 100, 255)";
export const OPPONENT_COLOR = "rgb(255, 100, 100)";
export const CARD_COLOR = "rgb(255, 215, 0)";

export interface Rect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface GridInfo {
  originX: number;
  originY: number;
  width: number;
  height: number;
  slotWidth: number;
  slotHeight: number;
}

export interface Layout {
  grid: GridInfo;
  /** Size a card is drawn at on the field and in hand: half a slot wide. */
  cardWidth: number;
  cardHeight: number;
  areas: {
    opponentDeck: Rect;
    opponentLp: Rect;
    opponentHand: Rect;
    myDeck: Rect;
    myLp: Rect;
    myHand: Rect;
    previewTable: Rect;
  };
}

/** Centers a rectangle's midpoint. */
export function center(rect: Rect): { x: number; y: number } {
  return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
}

/** Tests whether a stage-space point falls inside a rectangle. */
export function containsPoint(rect: Rect, x: number, y: number): boolean {
  return (
    x >= rect.x &&
    x < rect.x + rect.width &&
    y >= rect.y &&
    y < rect.y + rect.height
  );
}

/**
 * Builds the full board layout for the design stage.
 *
 * Reproduces `Matrix._calculate_margins`, `_calculate_grid_dimensions`,
 * `_calculate_area_dimensions` and `_create_game_areas`.
 *
 * @param screenWidth - Stage width in design pixels.
 * @param screenHeight - Stage height in design pixels.
 * @returns Every rectangle the renderer needs.
 */
export function buildLayout(
  screenWidth: number = DESIGN_WIDTH,
  screenHeight: number = DESIGN_HEIGHT,
): Layout {
  const margins = {
    left: Math.trunc(screenWidth * LEFT_RATIO),
    right: Math.trunc(screenWidth * RIGHT_RATIO),
    top: Math.trunc(screenHeight * TOP_RATIO),
    bottom: Math.trunc(screenHeight * BOTTOM_RATIO),
  };

  const availWidth = screenWidth - (margins.left + margins.right);
  const availHeight = screenHeight - (margins.top + margins.bottom);

  const slotWidth = Math.floor(availWidth / COLS);
  const slotHeight = Math.floor(availHeight / ROWS);
  const gridWidth = COLS * slotWidth;
  const gridHeight = ROWS * slotHeight;

  const grid: GridInfo = {
    originX: margins.left + Math.floor((availWidth - gridWidth) / 2),
    originY: margins.top + Math.floor((availHeight - gridHeight) / 2),
    width: gridWidth,
    height: gridHeight,
    slotWidth,
    slotHeight,
  };

  const padding = AREA_PADDING;
  const deckWidth = Math.max(0, margins.left - 2 * padding);
  const topHeight = margins.top - 2 * padding;
  const bottomHeight = margins.bottom - 2 * padding;

  return {
    grid,
    cardWidth: slotWidth / 2,
    cardHeight: slotHeight,
    areas: {
      opponentDeck: {
        x: padding,
        y: padding,
        width: deckWidth / 2,
        height: topHeight,
      },
      opponentLp: {
        x: deckWidth / 1.8,
        y: padding,
        width: deckWidth / 2,
        height: topHeight,
      },
      opponentHand: {
        x: grid.originX,
        y: padding,
        width: grid.width,
        height: margins.top - 2 * padding,
      },
      myDeck: {
        x: padding,
        y: screenHeight - margins.bottom + padding,
        width: deckWidth / 2,
        height: bottomHeight,
      },
      myLp: {
        x: padding * 16.5,
        y: screenHeight - margins.bottom + padding,
        width: deckWidth / 2,
        height: bottomHeight,
      },
      myHand: {
        x: grid.originX,
        y: screenHeight - margins.bottom + padding,
        width: grid.width,
        height: bottomHeight,
      },
      previewTable: {
        x: padding * 4 - 25,
        y: padding * 13,
        width: grid.width / 3.5 + 25,
        height: grid.height,
      },
    },
  };
}

/** The single layout instance every module shares. */
export const LAYOUT = buildLayout();

/**
 * Returns the rectangle of one field slot.
 *
 * @param row - Row index in render coordinates.
 * @param col - Column index in render coordinates.
 * @returns The slot rectangle, or null when out of bounds.
 */
export function getSlotRect(row: number, col: number): Rect | null {
  if (row < 0 || row >= ROWS || col < 0 || col >= COLS) return null;
  const { grid } = LAYOUT;
  return {
    x: grid.originX + col * grid.slotWidth,
    y: grid.originY + row * grid.slotHeight,
    width: grid.slotWidth,
    height: grid.slotHeight,
  };
}

/**
 * Finds the field slot under a stage-space point.
 *
 * @param x - Stage x coordinate.
 * @param y - Stage y coordinate.
 * @returns The `[row, col]` cell, or null when the point is off the grid.
 */
export function getSlotAtPos(x: number, y: number): Cell | null {
  const { grid } = LAYOUT;
  if (
    x < grid.originX ||
    x >= grid.originX + grid.width ||
    y < grid.originY ||
    y >= grid.originY + grid.height
  ) {
    return null;
  }
  return [
    Math.floor((y - grid.originY) / grid.slotHeight),
    Math.floor((x - grid.originX) / grid.slotWidth),
  ];
}

/**
 * Computes the top-left of a hand card, matching `HandUI.align`.
 *
 * Cards are packed left to right at one card width each, from the hand area's
 * top-left corner.
 *
 * @param handRect - The hand area rectangle.
 * @param index - Position of the card within the hand.
 * @returns The card's top-left corner in stage space.
 */
export function handSlotPosition(
  handRect: Rect,
  index: number,
): { x: number; y: number } {
  return {
    x: handRect.x + index * LAYOUT.cardWidth,
    y: handRect.y,
  };
}
