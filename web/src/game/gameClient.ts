/**
 * Owns the browser's copy of a match.
 *
 * Holds the single `ClientState`, the render engine, and the input manager, and
 * routes network callbacks into them. Everything mutable lives here rather than
 * in React state so the animation loop can run at frame rate without forcing a
 * re-render; React subscribes for structural changes only.
 */

import { InputManager } from "./inputManager";
import { RenderEngine } from "./renderEngine";
import { emptyClientState, PatchApplier, type ClientState } from "../net/patch";
import type { Assignment, Patch } from "../net/actions";
import type { GameConnection } from "../net/client";

/** Snapshot of everything the HUD displays. */
export interface HudSnapshot {
  connected: boolean;
  turnCount: number;
  isLocalTurn: boolean;
  isTrapStage: boolean;
  gameOver: boolean;
  localName: string;
  localLife: number;
  opponentName: string;
  opponentLife: number;
  localHandCount: number;
  opponentHandCount: number;
  localGraveyard: number;
  previewCardId: string | null;
  hasStarted: boolean;
}

export class GameClient {
  state: ClientState = emptyClientState();
  applier = new PatchApplier(null, false);
  readonly render: RenderEngine;
  readonly input: InputManager;

  connection: GameConnection | null = null;

  /** Seat identity assigned by the server. */
  localPlayerId: string | null = null;
  flip = false;
  hasAssignment = false;

  /** Last error surfaced by the server or the connection. */
  lastError: string | null = null;

  private listeners = new Set<() => void>();
  private structuralVersion = 0;

  constructor() {
    this.render = new RenderEngine((cardId) => {
      this.input.previewCardId = cardId;
    });
    this.input = new InputManager(
      this.render,
      {
        summon: (cardId, cell) => this.connection?.summon(cardId, cell),
        setTrap: (cardId, cell) => this.connection?.setTrap(cardId, cell),
        castSpell: (spellId, targetId) =>
          this.connection?.castSpell(spellId, targetId),
        toggle: (cardId) => this.connection?.toggle(cardId),
        attack: (cardId, targetId, targetIsPlayer) =>
          this.connection?.attack(cardId, targetId, targetIsPlayer),
        upgrade: (cardId, targetId) =>
          this.connection?.upgrade(cardId, targetId),
        toggleTrapActivation: (trapId, activated) =>
          this.connection?.toggleTrapActivation(trapId, activated),
      },
      () => this.state,
    );
  }

  /** Subscribes to structural changes (sprite set, seat, errors). */
  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** Notifies subscribers that the rendered structure changed. */
  private emitChange(): void {
    for (const listener of this.listeners) listener();
  }

  /** Applies a seat assignment and resets the board for the new perspective. */
  onAssign(assignment: Assignment): void {
    this.localPlayerId = assignment.player_id;
    this.flip = Number(assignment.player_index ?? 1) !== 0;
    this.applier = new PatchApplier(this.localPlayerId, this.flip);
    this.hasAssignment = true;
    this.render.reset();
    this.emitChange();
  }

  /** Applies one patch from the authoritative engine. */
  onPatch(patch: Patch): void {
    const hadFullSync = patch.ops.some((op) => op.op === "FULL_SYNC");
    this.applier.apply(this.state, patch);

    if (hadFullSync) {
      // A full sync replaces every card object, so drop stale sprites rather
      // than animating a board that no longer exists.
      this.render.reset();
    }
    this.emitChange();
  }

  /** Records an error for the UI to surface. */
  onError(message: string): void {
    this.lastError = message;
    this.emitChange();
  }

  /** Clears the current error banner. */
  clearError(): void {
    if (this.lastError === null) return;
    this.lastError = null;
    this.emitChange();
  }

  /**
   * Advances one frame.
   *
   * @param dt - Seconds since the previous frame.
   */
  frame(dt: number): void {
    this.render.update(this.state);
    this.render.tick(dt);

    if (this.render.version !== this.structuralVersion) {
      this.structuralVersion = this.render.version;
      this.emitChange();
    }
  }

  /** Builds the HUD snapshot for the current state. */
  hud(): HudSnapshot {
    const { gameState, turn } = this.state;
    const local = gameState.players.find((p) => !p.is_opponent);
    const opponent = gameState.players.find((p) => p.is_opponent);

    const trapStage = turn.is_trap_stage;
    const activeId = trapStage
      ? gameState.players[(turn.current_player_index + 1) % Math.max(1, gameState.players.length)]?.id
      : gameState.players[turn.current_player_index]?.id;

    return {
      connected: this.connection?.status === "connected",
      turnCount: turn.turn_count,
      isLocalTurn: Boolean(local && activeId === local.id),
      isTrapStage: trapStage,
      gameOver: gameState.game_over,
      localName: local?.name ?? "You",
      localLife: local?.life_points ?? 0,
      opponentName: opponent?.name ?? "Opponent",
      opponentLife: opponent?.life_points ?? 0,
      localHandCount: local
        ? (gameState.player_info[local.id]?.held_cards.card_ids.length ?? 0)
        : 0,
      opponentHandCount: opponent
        ? (gameState.player_info[opponent.id]?.held_cards.card_ids.length ?? 0)
        : 0,
      localGraveyard: local
        ? (gameState.player_info[local.id]?.graveyard_cards.card_ids.length ?? 0)
        : 0,
      previewCardId: this.input.previewCardId,
      hasStarted: gameState.players.length > 0,
    };
  }
}
