/**
 * Sprite model, ported from `gui/sprites/`.
 *
 * A sprite pairs a logic card with the transient visual state the animation
 * layer mutates each frame (position, rotation, squash, alpha). Positions are
 * kept as centers, matching pygame's `rect.center`, so the ported animation math
 * carries over unchanged.
 *
 * Unlike the pygame build, opponent cards are not drawn upside down: their
 * names and stats have to stay readable, and the owner is already obvious from
 * the tile colour and the card's outline.
 */

import type { Card } from "../types/game";

export type Zone = "hand" | "matrix";

/** A renderable card instance. */
export interface Sprite {
  /** Card id; also the sprite's identity across frames. */
  id: string;
  zone: Zone;
  /** The logic card, refreshed from game state every update. */
  card: Card;

  /** Center position in stage space. */
  x: number;
  y: number;
  width: number;
  height: number;

  /** Where the sprite rests when no animation is running. */
  homeX: number;
  homeY: number;

  /** Transient animation state, mirroring `CardGUI`'s attributes. */
  angle: number;
  scaleX: number;
  scaleY: number;
  alpha: number;
  offsetY: number;

  /** Merge-group highlight, driven by `RenderEngine.handleMerge`. */
  highlight: boolean;
  highlightColor: string;

  /** True while the player is dragging this card. */
  dragging: boolean;
  /** Cleared once a card has been committed to the field. */
  draggable: boolean;
  /** Overrides the logic card's face-down flag during a reveal animation. */
  faceDownOverride: boolean | null;

  /** Outer node (position + opacity), bound by React for the render loop. */
  el: HTMLDivElement | null;
  /**
   * Inner node carrying rotation and squash.
   *
   * Kept separate from `el` because pygame draws the stat line, merge highlight
   * and trap button in screen space around the card's bounding box — they must
   * not spin with a monster switched to defence position.
   */
  faceEl: HTMLDivElement | null;
}

/**
 * Creates a sprite at rest.
 *
 * @param card - The logic card to represent.
 * @param zone - Which collection the sprite belongs to.
 * @param x - Center x in stage space.
 * @param y - Center y in stage space.
 * @param width - Rendered width.
 * @param height - Rendered height.
 * @returns The new sprite.
 */
export function createSprite(
  card: Card,
  zone: Zone,
  x: number,
  y: number,
  width: number,
  height: number,
): Sprite {
  return {
    id: card.id,
    zone,
    card,
    x,
    y,
    width,
    height,
    homeX: x,
    homeY: y,
    angle: 0,
    scaleX: 1,
    scaleY: 1,
    alpha: 1,
    offsetY: 0,
    highlight: false,
    highlightColor: "rgb(255, 255, 0)",
    dragging: false,
    draggable: true,
    faceDownOverride: null,
    el: null,
    faceEl: null,
  };
}

/** Returns whether a point in stage space lies over a sprite. */
export function spriteContains(sprite: Sprite, x: number, y: number): boolean {
  const halfW = sprite.width / 2;
  const halfH = sprite.height / 2;
  return (
    x >= sprite.x - halfW &&
    x <= sprite.x + halfW &&
    y >= sprite.y - halfH &&
    y <= sprite.y + halfH
  );
}

/**
 * Tracks sprites by zone, ported from `gui/sprites/sprite_manager.py`.
 *
 * Lookups are global across zones, while add/remove are zone-scoped, so a card
 * moving from hand to field is two operations rather than a mutation.
 */
export class SpriteManager {
  readonly zones: Record<Zone, Map<string, Sprite>> = {
    hand: new Map(),
    matrix: new Map(),
  };

  private readonly index = new Map<string, Sprite>();

  /** Registers a sprite in a zone. */
  add(sprite: Sprite, zone: Zone): void {
    sprite.zone = zone;
    this.zones[zone].set(sprite.id, sprite);
    this.index.set(sprite.id, sprite);
  }

  /** Removes a sprite from one zone, or from every zone when none is given. */
  remove(cardId: string, zone?: Zone): void {
    const targets: Zone[] = zone ? [zone] : (["hand", "matrix"] as Zone[]);
    for (const name of targets) this.zones[name].delete(cardId);

    const stillPresent = (["hand", "matrix"] as Zone[]).some((name) =>
      this.zones[name].has(cardId),
    );
    if (!stillPresent) this.index.delete(cardId);
  }

  /** Global sprite lookup across every zone. */
  get(cardId: string): Sprite | undefined {
    return this.index.get(cardId);
  }

  /** Every sprite currently registered, in no particular order. */
  all(): Sprite[] {
    return [...this.index.values()];
  }

  /** Drops every sprite. */
  clear(): void {
    this.zones.hand.clear();
    this.zones.matrix.clear();
    this.index.clear();
  }
}

/**
 * Decides whether a sprite renders face down.
 *
 * Mirrors the per-zone rules in `register_hand` / `register_matrix` plus
 * `TrapCardGUI.update`: hand cards are hidden for the opponent, field traps are
 * hidden for everyone until their owner may activate them, and an in-flight
 * reveal animation overrides both.
 *
 * @param sprite - The sprite being drawn.
 * @returns True when the card back should be shown.
 */
export function isSpriteFaceDown(sprite: Sprite): boolean {
  if (sprite.faceDownOverride !== null) return sprite.faceDownOverride;

  const card = sprite.card;
  if (sprite.zone === "hand") return card.is_opponent;

  if (card.card_type === "TRAP") {
    if (card.triggerable && !card.is_opponent) return false;
    return !card.is_triggered;
  }

  return false;
}
