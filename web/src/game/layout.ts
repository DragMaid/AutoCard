/**
 * Board geometry.
 *
 * The whole UI is laid out once against a fixed 1280x720 design stage and then
 * CSS-scaled to fit the viewport, so every slot, card and panel keeps the same
 * proportions at any window size and the input layer only ever deals in design
 * pixels.
 *
 * The pygame build (`gui/background/matrix_field.py`) derived every rectangle
 * from ratios of the screen size, which left the left margin triple-booked:
 * the deck plate, the life panel, the card preview and the turn HUD all landed
 * on top of each other. This version splits the stage into two explicit
 * columns instead — a side rail and the board — and gives each one a stack of
 * non-overlapping rows with real gutters between them.
 */

import type { Cell } from "../types/game";

/** Design resolution the stage is laid out against. */
export const DESIGN_WIDTH = 1280;
export const DESIGN_HEIGHT = 720;

/** Field dimensions, matching `Config.ROWS` / `Config.COLS`. */
export const ROWS = 4;
export const COLS = 5;

/** Breathing room between the stage frame and its contents. */
export const STAGE_PADDING = 16;

/** Gutter between stacked areas. */
export const GUTTER = 12;

/** Width of the rail holding the player panels, preview and controls. */
export const RAIL_WIDTH = 300;

/** Colours identifying each side of the board. */
export const PLAYER_COLOR = "#6d8cff";
export const OPPONENT_COLOR = "#ff6b6b";

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

/** Every named rectangle on the stage. */
export interface Areas {
  /** Opponent identity, life total and deck, top of the rail. */
  opponentPanel: Rect;
  /** Large card inspector, middle of the rail. */
  previewTable: Rect;
  /** Local identity, life total and deck, lower rail. */
  localPanel: Rect;
  /** Turn readout plus End Turn / Surrender, bottom of the rail. */
  actions: Rect;

  /** Deck stacks, which draw animations fly out of. */
  opponentDeck: Rect;
  myDeck: Rect;

  /** Card trays flanking the grid. */
  opponentHand: Rect;
  myHand: Rect;

  /** The board column as a whole, used for its backing panel. */
  boardColumn: Rect;
}

export interface Layout {
  grid: GridInfo;
  /** Size every card is drawn at on the field and in hand. */
  cardWidth: number;
  cardHeight: number;
  areas: Areas;
}

/** Aspect ratio of the source card art, which is 64x81 for every card. */
export const CARD_ASPECT = 64 / 81;

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
 * The vertical budget is spent top to bottom and has to close exactly:
 * padding, hand tray, gutter, grid, gutter, hand tray, padding. The grid height
 * is whatever is left over, rounded down to a whole number of rows.
 *
 * @param screenWidth - Stage width in design pixels.
 * @param screenHeight - Stage height in design pixels.
 * @returns Every rectangle the renderer needs.
 */
export function buildLayout(
  screenWidth: number = DESIGN_WIDTH,
  screenHeight: number = DESIGN_HEIGHT,
): Layout {
  const pad = STAGE_PADDING;
  const top = pad;
  const bottom = screenHeight - pad;

  // -- columns ------------------------------------------------------------
  const railX = pad;
  const boardX = railX + RAIL_WIDTH + GUTTER + 4;
  const boardWidth = screenWidth - pad - boardX;

  // -- board column rows --------------------------------------------------
  // Chosen so a card at the resulting slot height still clears the tray edges:
  // 4 rows and 2 trays have to share the same 688px of vertical space.
  const handHeight = 108;
  const gridTop = top + handHeight + GUTTER + 4;
  const handTop = bottom - handHeight;
  const gridAvailable = handTop - GUTTER - 4 - gridTop;

  const slotHeight = Math.floor(gridAvailable / ROWS);
  const slotWidth = Math.floor(boardWidth / COLS);
  const gridWidth = slotWidth * COLS;
  const gridHeight = slotHeight * ROWS;

  const grid: GridInfo = {
    originX: boardX + Math.floor((boardWidth - gridWidth) / 2),
    originY: gridTop + Math.floor((gridAvailable - gridHeight) / 2),
    width: gridWidth,
    height: gridHeight,
    slotWidth,
    slotHeight,
  };

  // Cards keep their native 64x81 aspect and sit inside a slot with a margin,
  // so a highlight ring and the row gutter both stay visible.
  const cardHeight = slotHeight - 10;
  const cardWidth = Math.round(cardHeight * CARD_ASPECT);

  // -- rail rows ----------------------------------------------------------
  const panelHeight = 104;
  const actionsHeight = 132;

  const opponentPanel: Rect = {
    x: railX,
    y: top,
    width: RAIL_WIDTH,
    height: panelHeight,
  };
  const actions: Rect = {
    x: railX,
    y: bottom - actionsHeight,
    width: RAIL_WIDTH,
    height: actionsHeight,
  };
  const localPanel: Rect = {
    x: railX,
    y: actions.y - GUTTER - panelHeight,
    width: RAIL_WIDTH,
    height: panelHeight,
  };
  const previewTop = opponentPanel.y + opponentPanel.height + GUTTER;
  const previewTable: Rect = {
    x: railX,
    y: previewTop,
    width: RAIL_WIDTH,
    height: localPanel.y - GUTTER - previewTop,
  };

  /** The deck stack sits in the right-hand third of a player panel. */
  const deckIn = (panel: Rect): Rect => {
    const height = panel.height - 24;
    return {
      x: panel.x + panel.width - 16 - Math.round(height * CARD_ASPECT),
      y: panel.y + 12,
      width: Math.round(height * CARD_ASPECT),
      height,
    };
  };

  return {
    grid,
    cardWidth,
    cardHeight,
    areas: {
      opponentPanel,
      previewTable,
      localPanel,
      actions,
      opponentDeck: deckIn(opponentPanel),
      myDeck: deckIn(localPanel),
      opponentHand: {
        x: grid.originX,
        y: top,
        width: grid.width,
        height: handHeight,
      },
      myHand: {
        x: grid.originX,
        y: handTop,
        width: grid.width,
        height: handHeight,
      },
      boardColumn: {
        x: grid.originX - 4,
        y: top - 4,
        width: grid.width + 8,
        height: bottom - top + 8,
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
 * Computes the top-left of a hand card.
 *
 * Cards are centred in the tray rather than packed against its left edge, and
 * overlap once the hand grows past what fits at full width — the same fan every
 * physical card game ends up with.
 *
 * @param handRect - The hand tray rectangle.
 * @param index - Position of the card within the hand.
 * @param count - How many cards the hand holds.
 * @returns The card's top-left corner in stage space.
 */
export function handSlotPosition(
  handRect: Rect,
  index: number,
  count: number,
): { x: number; y: number } {
  const { cardWidth, cardHeight } = LAYOUT;
  const spacing = 10;
  const usable = handRect.width - 2 * spacing;

  // Step back from the ideal spacing only as far as overflowing forces us to.
  const ideal = cardWidth + spacing;
  const step =
    count > 1 ? Math.min(ideal, (usable - cardWidth) / (count - 1)) : ideal;
  const span = cardWidth + step * Math.max(0, count - 1);

  return {
    x: handRect.x + (handRect.width - span) / 2 + index * step,
    y: handRect.y + (handRect.height - cardHeight) / 2,
  };
}
