/**
 * Port of `core/gui/input_manager.py`.
 *
 * Translates pointer input in stage space into intents. Every rule the pygame
 * version enforces before sending an action is reproduced here so the UI does
 * not offer moves the server would reject — but the server still re-validates
 * everything, since this layer is only a convenience.
 */

import type { RenderEngine } from "./renderEngine";
import { spriteContains, type Sprite } from "./sprites";
import {
  containsPoint,
  getSlotAtPos,
  LAYOUT,
} from "./layout";
import {
  currentPlayer,
  isLocalTurn,
  iterFieldCardIds,
  localPlayer,
  nextPlayer,
} from "./state";
import type { ClientState } from "../net/patch";
import type { Card, Cell, GameState } from "../types/game";
import { isMonster } from "../types/game";

/** Actions the input layer can request. Implemented by the network client. */
export interface GameActions {
  summon(cardId: string, cell: Cell): void;
  setTrap(cardId: string, cell: Cell): void;
  castSpell(spellId: string, targetId: string | null): void;
  toggle(cardId: string): void;
  attack(cardId: string, targetId: string, targetIsPlayer: boolean): void;
  upgrade(cardId: string, targetId: string): void;
  toggleTrapActivation(trapId: string, activated: boolean): void;
}

/** An in-progress attack/merge arrow. */
export interface DragArrow {
  sourceCardId: string;
  from: { x: number; y: number };
  to: { x: number; y: number };
}

/** Handles pointer interaction over the board. */
export class InputManager {
  /** The hand card currently being dragged, if any. */
  draggingCard: Sprite | null = null;

  /** The attack/merge arrow being dragged, if any. */
  dragArrow: DragArrow | null = null;

  /** Card shown in the preview panel. */
  previewCardId: string | null = null;

  private grabOffset = { x: 0, y: 0 };

  /**
   * @param render - The render engine owning the sprites.
   * @param actions - Sink for the intents this manager produces.
   * @param getState - Accessor for the live client state.
   */
  constructor(
    private render: RenderEngine,
    private actions: GameActions,
    private getState: () => ClientState,
  ) {}

  /**
   * Whether input is currently accepted.
   *
   * Mirrors the guard at the top of `InputManager.handle_event`: while the trap
   * stage belongs to the opponent, the board is read-only.
   */
  private get accepting(): boolean {
    const { gameState, turn } = this.getState();
    if (turn.is_trap_stage && !isLocalTurn(gameState, turn)) return false;
    return true;
  }

  /** Handles a primary-button press at a stage-space point. */
  onPointerDown(x: number, y: number, button: number): void {
    if (!this.accepting) return;

    if (button === 2) {
      this.handleRightClick(x, y);
      return;
    }
    if (button !== 0) return;

    if (this.handleTrapActivation(x, y)) return;

    if (!this.draggingCard) this.tryStartDragCard(x, y);
    if (!this.dragArrow) this.tryStartDragArrow(x, y);
    this.handleClickCard(x, y);
  }

  /** Handles pointer movement at a stage-space point. */
  onPointerMove(x: number, y: number): void {
    if (this.draggingCard) {
      this.draggingCard.x = x + this.grabOffset.x;
      this.draggingCard.y = y + this.grabOffset.y;
    } else if (this.dragArrow) {
      this.dragArrow.to = { x, y };
    }
  }

  /** Handles a primary-button release at a stage-space point. */
  onPointerUp(x: number, y: number): void {
    if (this.draggingCard) {
      this.dropCard(this.draggingCard, x, y);
      this.draggingCard.dragging = false;
      this.draggingCard = null;
      this.render.alignCards(this.getState().gameState);
    }

    if (this.dragArrow) {
      this.finishDragArrow(x, y);
      this.dragArrow = null;
    }
  }

  /** Cancels any in-flight drag, e.g. when the pointer leaves the stage. */
  cancel(): void {
    if (this.draggingCard) {
      this.draggingCard.dragging = false;
      this.draggingCard = null;
      this.render.alignCards(this.getState().gameState);
    }
    this.dragArrow = null;
  }

  // -- trap activation ----------------------------------------------------

  /**
   * Toggles a trap's activation when its button is hit.
   *
   * Mirrors `_handle_trap_activation`.
   *
   * @returns True when the press was consumed by a trap button.
   */
  private handleTrapActivation(x: number, y: number): boolean {
    const { gameState } = this.getState();

    for (const trapId of Object.keys(gameState.triggerable_traps)) {
      const sprite = this.render.sprites.get(trapId);
      if (!sprite) continue;

      const card = sprite.card;
      if (card.card_type !== "TRAP" || !card.triggerable || card.is_opponent) {
        continue;
      }

      const rect = this.activateButtonRect(sprite);
      if (!containsPoint(rect, x, y)) continue;

      const activated = !gameState.activated_traps.includes(trapId);
      this.actions.toggleTrapActivation(trapId, activated);
      return true;
    }

    return false;
  }

  /**
   * The ARM button rectangle for a triggerable trap.
   *
   * Must stay in step with the tab `SpriteLayer` draws straddling the card's
   * bottom edge, since that is the only thing the player can aim at.
   */
  activateButtonRect(sprite: Sprite) {
    const height = 18;
    return {
      x: sprite.x - sprite.width / 2,
      y: sprite.y + sprite.height / 2 - height / 2,
      width: sprite.width,
      height,
    };
  }

  // -- dragging a hand card ----------------------------------------------

  /**
   * Picks up the top-most draggable hand card under the pointer.
   *
   * Mirrors `_try_start_drag_card`: only the local player's cards can move, and
   * hands are scanned in reverse so the front-most is grabbed first.
   */
  private tryStartDragCard(x: number, y: number): void {
    const { gameState } = this.getState();

    const candidates = [...this.render.sprites.zones.hand.values()].reverse();
    for (const sprite of candidates) {
      if (sprite.card.is_opponent || !sprite.draggable) continue;
      if (!spriteContains(sprite, x, y)) continue;

      this.draggingCard = sprite;
      sprite.dragging = true;
      this.grabOffset = { x: sprite.x - x, y: sprite.y - y };
      this.previewCardId = sprite.id;
      void gameState;
      return;
    }
  }

  /**
   * Resolves dropping a hand card onto the board.
   *
   * Mirrors `CardGUI.on_drop` and its monster/trap/spell overrides.
   */
  private dropCard(sprite: Sprite, x: number, y: number): void {
    void x;
    void y;
    const { gameState } = this.getState();
    const cell = getSlotAtPos(sprite.x, sprite.y);
    if (!cell) return;

    const card = sprite.card;
    const [row, col] = cell;

    if (card.card_type === "SPELL") {
      // A spell targets whatever occupies the slot; an empty slot is allowed
      // for spells that take no target.
      const targetId = gameState.field_matrix[row]?.[col] ?? null;
      this.actions.castSpell(card.id, targetId);
      return;
    }

    // Monsters and traps must be placed in a slot the owner controls.
    if (gameState.field_matrix_ownership[row]?.[col] !== card.owner_id) return;

    if (card.card_type === "TRAP") this.actions.setTrap(card.id, cell);
    else this.actions.summon(card.id, cell);
  }

  // -- dragging an attack arrow ------------------------------------------

  /**
   * Starts an arrow from an eligible attacker.
   *
   * Mirrors `_try_start_drag_arrow`: the card must be a monster in attack mode,
   * owned by the local player, on that player's turn.
   */
  private tryStartDragArrow(x: number, y: number): void {
    const { gameState, turn } = this.getState();
    const active = currentPlayer(gameState, turn);
    if (!active) return;

    for (const cardId of iterFieldCardIds(gameState)) {
      const card = gameState.entity_lookup[cardId];
      const sprite = this.render.sprites.get(cardId);
      if (!card || !sprite || !spriteContains(sprite, x, y)) continue;

      if (
        isMonster(card) &&
        card.mode === "ATTACK" &&
        card.owner_id === active.id &&
        !card.is_opponent
      ) {
        this.dragArrow = {
          sourceCardId: cardId,
          from: { x: sprite.x, y: sprite.y },
          to: { x: sprite.x, y: sprite.y },
        };
        return;
      }
    }
  }

  /** Resolves an arrow drop. Mirrors `_finish_drag_arrow`. */
  private finishDragArrow(x: number, y: number): void {
    if (this.resolveArrowOnField(x, y)) return;
    this.resolveArrowOnPlayer(x, y);
  }

  /**
   * Attacks an enemy card, or merges with a friendly one.
   *
   * Mirrors `_try_resolve_arrow_on_field`.
   */
  private resolveArrowOnField(x: number, y: number): boolean {
    const arrow = this.dragArrow;
    if (!arrow) return false;

    const { gameState } = this.getState();
    const attacker = gameState.entity_lookup[arrow.sourceCardId];
    if (!attacker) return false;

    for (const cardId of iterFieldCardIds(gameState)) {
      if (cardId === arrow.sourceCardId) continue;
      const sprite = this.render.sprites.get(cardId);
      if (!sprite || !spriteContains(sprite, x, y)) continue;

      const target = gameState.entity_lookup[cardId];
      if (!target) continue;

      if (target.owner_id !== attacker.owner_id) {
        this.actions.attack(attacker.id, target.id, false);
        return true;
      }

      if (isMonster(target)) {
        this.actions.upgrade(attacker.id, target.id);
        return true;
      }
    }

    return false;
  }

  /**
   * Attacks the opposing player directly.
   *
   * Mirrors `_try_resolve_arrow_on_player`.
   */
  private resolveArrowOnPlayer(x: number, y: number): void {
    const arrow = this.dragArrow;
    if (!arrow) return;

    // Either the opponent's hand tray or their rail panel counts as a direct
    // attack: the panel is where their life total is, so it is the target most
    // players aim at first.
    const onOpponent =
      containsPoint(LAYOUT.areas.opponentHand, x, y) ||
      containsPoint(LAYOUT.areas.opponentPanel, x, y);
    if (!onOpponent) return;

    const { gameState, turn } = this.getState();
    const defender = nextPlayer(gameState, turn);
    if (!defender) return;

    this.actions.attack(arrow.sourceCardId, defender.id, true);
  }

  // -- clicks -------------------------------------------------------------

  /** Toggles a field monster's battle position. Mirrors `_handle_right_click`. */
  private handleRightClick(x: number, y: number): void {
    const { gameState } = this.getState();

    for (const cardId of iterFieldCardIds(gameState)) {
      const sprite = this.render.sprites.get(cardId);
      if (!sprite || !spriteContains(sprite, x, y)) continue;

      const card = gameState.entity_lookup[cardId];
      if (card && isMonster(card)) this.actions.toggle(cardId);
      return;
    }
  }

  /**
   * Sends the clicked card to the preview panel.
   *
   * Mirrors `_handle_click_card` and `CardPreview.set_card`, which refuses to
   * reveal an opponent's face-down card.
   */
  private handleClickCard(x: number, y: number): void {
    const state = this.getState().gameState;

    const pick = (sprites: Iterable<Sprite>): boolean => {
      for (const sprite of sprites) {
        if (!spriteContains(sprite, x, y)) continue;
        if (this.canPreview(sprite.card, state)) this.previewCardId = sprite.id;
        return true;
      }
      return false;
    };

    if (pick(this.render.sprites.zones.matrix.values())) return;
    pick(this.render.sprites.zones.hand.values());
  }

  /** Whether a card may be shown in the preview panel. */
  private canPreview(card: Card, state: GameState): boolean {
    void state;
    if (!card.is_opponent) return true;
    return !card.is_face_down;
  }

  /** Convenience accessor used by the HUD. */
  localPlayerId(): string | null {
    return localPlayer(this.getState().gameState)?.id ?? null;
  }
}
