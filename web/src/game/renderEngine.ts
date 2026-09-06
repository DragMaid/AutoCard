/**
 * Port of `core/gui/render_engine.py`.
 *
 * Reconciles the sprite set against the game state each frame: cards entering a
 * zone get a sprite plus an entry animation, cards leaving get a death
 * animation, and survivors have their logic card and resting position
 * refreshed. Merge highlighting and the attack-queue arrows are derived here
 * too, so the React layer only has to draw what this engine computed.
 */

import { AnimationManager } from "./animations";
import { EventHandler } from "./eventHandler";
import {
  center,
  getSlotRect,
  handSlotPosition,
  LAYOUT,
  type Rect,
} from "./layout";
import { getMergeableGroups, playersById } from "./state";
import { createSprite, SpriteManager, type Sprite, type Zone } from "./sprites";
import type { ClientState } from "../net/patch";
import type { Card, GameState } from "../types/game";

/** A drawn attack indicator between two points. */
export interface AttackArrow {
  from: { x: number; y: number };
  to: { x: number; y: number };
  color: string;
}

/** Deterministic highlight colours for merge groups. */
const MERGE_COLORS = [
  "rgb(255, 214, 64)",
  "rgb(94, 234, 212)",
  "rgb(244, 114, 182)",
  "rgb(129, 230, 117)",
  "rgb(147, 197, 253)",
  "rgb(253, 164, 96)",
];

/** Reconciles sprites with game state and drives animations. */
export class RenderEngine {
  readonly sprites = new SpriteManager();
  readonly animations = new AnimationManager();
  readonly events: EventHandler;

  /** Arrows drawn for queued attacks awaiting trap resolution. */
  attackIndicators: AttackArrow[] = [];

  /** Stable colour assignment per merge group key. */
  private mergeColors = new Map<string, string>();

  /** Bumped whenever sprites are added or removed, to re-render React. */
  version = 0;

  constructor(onPreviewCard: (cardId: string) => void) {
    this.events = new EventHandler(
      this.sprites,
      this.animations,
      onPreviewCard,
    );
  }

  /** Drops all sprites and animations, used when the board is rebuilt. */
  reset(): void {
    this.sprites.clear();
    this.animations.clear();
    this.mergeColors.clear();
    this.attackIndicators = [];
    this.version += 1;
  }

  /**
   * Runs one reconciliation pass.
   *
   * Mirrors `RenderEngine.update`, in the same order: drain events, sync
   * sprites, refresh merge highlights, start any ready merges, rebuild arrows.
   *
   * @param client - The current client state.
   */
  update(client: ClientState): void {
    const state = client.gameState;

    if (client.pendingEvents.length) {
      const events = client.pendingEvents.splice(0, client.pendingEvents.length);
      this.events.handleEvents(
        events as unknown as Record<string, unknown>[],
        state,
      );
    }

    this.registerCards(state);
    this.handleMerge(state);
    this.events.processPendingMerges();
    this.handleAttackQueue(state);
  }

  /** Syncs both zones against the state. Mirrors `register_cards`. */
  private registerCards(state: GameState): void {
    this.registerHand(state);
    this.registerMatrix(state);
  }

  /**
   * Highlights groups of mergeable monsters.
   *
   * Mirrors `RenderEngine.handle_merge`, keeping a stable colour per group so
   * the highlight does not flicker between frames.
   */
  private handleMerge(state: GameState): void {
    for (const sprite of this.sprites.zones.matrix.values()) {
      sprite.highlight = false;
    }

    const liveKeys = new Set<string>();

    for (const player of state.players) {
      for (const [key, group] of getMergeableGroups(state, player.id)) {
        if (group.length < 2) continue;
        liveKeys.add(key);

        let color = this.mergeColors.get(key);
        if (!color) {
          color = MERGE_COLORS[this.mergeColors.size % MERGE_COLORS.length];
          this.mergeColors.set(key, color);
        }

        for (const card of group) {
          const sprite = this.sprites.get(card.id);
          if (!sprite) continue;
          sprite.highlight = true;
          sprite.highlightColor = color;
        }
      }
    }

    for (const key of [...this.mergeColors.keys()]) {
      if (!liveKeys.has(key)) this.mergeColors.delete(key);
    }
  }

  /** Rebuilds arrows for attacks queued behind a trap. */
  private handleAttackQueue(state: GameState): void {
    this.attackIndicators = [];

    for (const attack of state.attack_queue) {
      const source = this.sprites.get(attack.card_id);
      if (!source) continue;

      let to: { x: number; y: number } | null = null;
      if (attack.target_is_player) {
        const target = state.players.find((p) => p.id === attack.target_id);
        if (target) {
          to = center(
            target.is_opponent
              ? LAYOUT.areas.opponentHand
              : LAYOUT.areas.myHand,
          );
        }
      } else {
        const targetSprite = this.sprites.get(attack.target_id);
        if (targetSprite) to = { x: targetSprite.x, y: targetSprite.y };
      }

      if (to) {
        this.attackIndicators.push({
          from: { x: source.x, y: source.y },
          to,
          color: "rgb(255, 0, 0)",
        });
      }
    }
  }

  /** The hand area belonging to a player. */
  private handRect(isOpponent: boolean): Rect {
    return isOpponent ? LAYOUT.areas.opponentHand : LAYOUT.areas.myHand;
  }

  /** The deck area belonging to a player, where draws animate from. */
  private deckRect(isOpponent: boolean): Rect {
    return isOpponent ? LAYOUT.areas.opponentDeck : LAYOUT.areas.myDeck;
  }

  /**
   * Syncs hand sprites and lays them out left to right.
   *
   * Mirrors `register_hand` plus `HandUI.align`.
   */
  private registerHand(state: GameState): void {
    const desired: Card[] = [];
    const positions = new Map<string, { x: number; y: number }>();
    const byId = playersById(state);

    for (const player of state.players) {
      const rect = this.handRect(player.is_opponent);
      const heldIds = state.player_info[player.id]?.held_cards.card_ids ?? [];

      heldIds.forEach((cardId, index) => {
        const card = state.entity_lookup[cardId];
        if (!card) return;
        desired.push(card);

        const topLeft = handSlotPosition(rect, index);
        positions.set(cardId, {
          x: topLeft.x + LAYOUT.cardWidth / 2,
          y: topLeft.y + LAYOUT.cardHeight / 2,
        });
      });
    }

    this.syncSprites({
      desired,
      zone: "hand",
      create: (card) => {
        const owner = byId.get(card.owner_id);
        const isOpponent = Boolean(owner?.is_opponent);
        const at = positions.get(card.id) ?? { x: 0, y: 0 };
        return createSprite(
          card,
          "hand",
          at.x,
          at.y,
          LAYOUT.cardWidth,
          LAYOUT.cardHeight,
          isOpponent,
        );
      },
      onAdd: (sprite) => {
        const deck = center(this.deckRect(sprite.card.is_opponent));
        this.animations.createDrawAnimation(sprite, [deck.x, deck.y]);
      },
      place: (sprite) => {
        const at = positions.get(sprite.id);
        if (!at) return;
        sprite.homeX = at.x;
        sprite.homeY = at.y;
        // Leave a dragged or animating card where it is; snap the rest home.
        if (!sprite.dragging && !this.animations.isAnimating(sprite)) {
          sprite.x = at.x;
          sprite.y = at.y;
        }
      },
    });
  }

  /**
   * Syncs field sprites and pins them to their slots.
   *
   * Mirrors `register_matrix`.
   */
  private registerMatrix(state: GameState): void {
    const desired: Card[] = [];
    const byId = playersById(state);

    for (const row of state.field_matrix) {
      for (const cardId of row) {
        if (!cardId) continue;
        const card = state.entity_lookup[cardId];
        if (card) desired.push(card);
      }
    }

    const slotCenter = (card: Card) => {
      const pos = card.pos_in_matrix;
      if (!pos) return null;
      const rect = getSlotRect(pos[0], pos[1]);
      return rect ? center(rect) : null;
    };

    this.syncSprites({
      desired,
      zone: "matrix",
      create: (card) => {
        const owner = byId.get(card.owner_id);
        const at = slotCenter(card) ?? { x: 0, y: 0 };
        const sprite = createSprite(
          card,
          "matrix",
          at.x,
          at.y,
          LAYOUT.cardWidth,
          LAYOUT.cardHeight,
          Boolean(owner?.is_opponent),
        );
        sprite.draggable = false;
        if ("mode" in card && card.mode === "DEFEND") sprite.angle = 90;
        return sprite;
      },
      onAdd: (sprite) => this.animations.createPlaceAnimation(sprite),
      place: (sprite) => {
        const at = slotCenter(sprite.card);
        if (!at) return;
        sprite.homeX = at.x;
        sprite.homeY = at.y;
        if (!this.animations.isAnimating(sprite)) {
          sprite.x = at.x;
          sprite.y = at.y;
        }
      },
    });
  }

  /**
   * Reconciles one zone's sprites against the cards that belong in it.
   *
   * Mirrors `RenderEngine.sync_sprites`, including its rule that cards leaving
   * as part of a pending merge are not given a death animation.
   */
  private syncSprites(options: {
    desired: Card[];
    zone: Zone;
    create: (card: Card) => Sprite;
    onAdd?: (sprite: Sprite) => void;
    place?: (sprite: Sprite) => void;
  }): void {
    const { desired, zone, create, onAdd, place } = options;
    const existing = this.sprites.zones[zone];
    const desiredIds = new Set(desired.map((card) => card.id));

    let changed = false;

    for (const cardId of [...existing.keys()]) {
      if (desiredIds.has(cardId)) continue;
      if (this.events.isPendingMerge(cardId)) continue;
      if (!this.animations.isAnimating(existing.get(cardId)!, "DeathAnimation")) {
        this.animations.createDeathAnimation(cardId, zone, this.sprites);
        changed = true;
      }
    }

    for (const card of desired) {
      const current = existing.get(card.id);

      if (!current) {
        const sprite = create(card);
        this.sprites.add(sprite, zone);
        place?.(sprite);
        onAdd?.(sprite);
        changed = true;
        continue;
      }

      current.card = card;
      place?.(current);

      // Keep rotation in sync with battle position unless a toggle is playing.
      if (
        "mode" in card &&
        !this.animations.isAnimating(current, "ToggleRotateAnimation") &&
        !this.animations.isAnimating(current, "AttackAnimation")
      ) {
        current.angle = card.mode === "DEFEND" ? 90 : 0;
      }
    }

    if (changed) this.version += 1;
  }

  /** Re-runs hand layout, mirroring `RenderEngine.align_cards`. */
  alignCards(state: GameState): void {
    this.registerHand(state);
  }

  /**
   * Advances animations.
   *
   * @param dt - Seconds since the previous frame.
   */
  tick(dt: number): void {
    const before = this.sprites.all().length;
    this.animations.update(dt);
    if (this.sprites.all().length !== before) this.version += 1;
  }
}
