/**
 * TypeScript mirror of `core/network/patch.py` (the applier half).
 *
 * The browser never computes a diff — only the authoritative Python engine does
 * that. This module applies the resulting ops to the single local `GameState`
 * and reproduces the two view-only rules the Python applier uses:
 *
 * 1. A guest renders the board rotated 180 degrees, so incoming cells are
 *    mirrored on the way in.
 * 2. `is_opponent` / `is_face_down` are never trusted from the wire; they are
 *    recomputed from who the local player is.
 */

import { ROWS, COLS } from "../game/layout";
import type {
  AttackEntry,
  Card,
  Cell,
  Effect,
  GameEvent,
  GameState,
  Player,
  PlayerInfo,
  SerializedEngine,
  TrapContext,
  TurnManagerState,
} from "../types/game";
import type { Patch, PatchOp, Zone } from "./actions";

const ZONE_FIELDS: Record<Zone, keyof PlayerInfo> = {
  hand: "held_cards",
  graveyard: "graveyard_cards",
  deck: "deck_cards",
};

/** The complete client-side view of a match. */
export interface ClientState {
  gameState: GameState;
  turn: TurnManagerState;
  effects: Effect[];
  /** Events produced by the last applied patch, consumed by the event handler. */
  pendingEvents: GameEvent[];
  /** Last server sequence number applied, used to detect gaps. */
  seq: number;
}

/** Builds an empty state for before the first sync arrives. */
export function emptyClientState(): ClientState {
  return {
    gameState: {
      players: [],
      game_over: false,
      player_info: {},
      entity_lookup: {},
      field_matrix: Array.from({ length: ROWS }, () =>
        Array.from({ length: COLS }, () => null),
      ),
      field_matrix_ownership: Array.from({ length: ROWS }, () =>
        Array.from({ length: COLS }, () => ""),
      ),
      triggerable_traps: {},
      activated_traps: [],
      attack_queue: [],
    },
    turn: { current_player_index: 0, is_trap_stage: false, turn_count: 1 },
    effects: [],
    pendingEvents: [],
    seq: 0,
  };
}

/** Deep-clones a serialized payload so applied state never aliases the wire. */
function clone<T>(value: T): T {
  return structuredClone(value);
}

/**
 * Applies patches to a local state, translating into the viewer's frame.
 *
 * @remarks
 * Instances are cheap; recreate one whenever the seat assignment changes.
 */
export class PatchApplier {
  /**
   * @param localPlayerId - The player this browser controls.
   * @param flip - True when this seat renders the board rotated 180 degrees.
   */
  constructor(
    public localPlayerId: string | null,
    public flip: boolean,
  ) {}

  /** Maps a canonical cell into the viewer's frame. */
  private cell(row: number, col: number): Cell {
    if (!this.flip) return [row, col];
    return [ROWS - 1 - row, COLS - 1 - col];
  }

  /** Maps a serialized `pos_in_matrix` into the viewer's frame. */
  private pos(value: unknown): Cell | null {
    if (!Array.isArray(value) || value.length < 2) return null;
    return this.cell(Number(value[0]), Number(value[1]));
  }

  /** Rotates a 2D matrix 180 degrees, matching `_deserialize_2d_matrix`. */
  private rotate<T>(matrix: T[][]): T[][] {
    return matrix.map((row) => [...row].reverse()).reverse();
  }

  /**
   * Applies every op in a patch, then refreshes derived view flags.
   *
   * @param state - The state to mutate. Returned for convenient chaining.
   * @param patch - The patch received from the authoritative engine.
   * @returns The same state object, mutated in place.
   */
  apply(state: ClientState, patch: Patch): ClientState {
    for (const op of patch.ops) {
      try {
        this.applyOp(state, op);
      } catch (error) {
        console.error("Failed to apply patch op", op.op, error);
      }
    }

    if (patch.events?.length) {
      state.pendingEvents.push(...patch.events);
    }
    state.seq = patch.seq ?? state.seq;

    this.normalize(state);
    return state;
  }

  /** Dispatches one op to its handler. */
  private applyOp(state: ClientState, op: PatchOp): void {
    const gs = state.gameState;

    switch (op.op) {
      case "FULL_SYNC":
        this.applyFullSync(state, op.value as SerializedEngine);
        break;

      case "CARD_UPSERT": {
        if (!op.card_id || !op.card) break;
        const card = clone(op.card) as unknown as Card;
        card.pos_in_matrix = this.pos(card.pos_in_matrix);
        gs.entity_lookup[op.card_id] = card;
        break;
      }

      case "CARD_UPDATE": {
        const card = op.card_id ? gs.entity_lookup[op.card_id] : undefined;
        if (!card) break;
        for (const [key, value] of Object.entries(op.fields ?? {})) {
          if (key === "id" || key === "card_type") continue;
          if (key === "pos_in_matrix") {
            card.pos_in_matrix = this.pos(value);
            continue;
          }
          (card as unknown as Record<string, unknown>)[key] = clone(value);
        }
        break;
      }

      case "CARD_REMOVE":
        if (op.card_id) delete gs.entity_lookup[op.card_id];
        break;

      case "ZONE_ADD": {
        const collection = this.collection(gs, op.player_id, op.zone);
        if (collection && op.card_id && !collection.includes(op.card_id)) {
          collection.push(op.card_id);
        }
        break;
      }

      case "ZONE_REMOVE": {
        const collection = this.collection(gs, op.player_id, op.zone);
        if (!collection || !op.card_id) break;
        const index = collection.indexOf(op.card_id);
        if (index >= 0) collection.splice(index, 1);
        break;
      }

      case "FIELD_SET": {
        if (op.row == null || op.col == null) break;
        const [row, col] = this.cell(op.row, op.col);
        gs.field_matrix[row][col] = op.card_id ?? null;
        break;
      }

      case "PLAYER_UPDATE": {
        const player = gs.players.find((p) => p.id === op.player_id);
        if (!player) break;
        for (const [key, value] of Object.entries(op.fields ?? {})) {
          if (key === "id" || key === "is_opponent") continue;
          (player as unknown as Record<string, unknown>)[key] = clone(value);
        }
        break;
      }

      case "PLAYER_INFO_UPDATE": {
        const info = op.player_id ? gs.player_info[op.player_id] : undefined;
        if (!info) break;
        const zoneFields = Object.values(ZONE_FIELDS) as string[];
        for (const [key, value] of Object.entries(op.fields ?? {})) {
          if (zoneFields.includes(key)) {
            (info[key as keyof PlayerInfo] as unknown as { card_ids: string[] })
              .card_ids = clone(value) as string[];
          } else {
            (info as unknown as Record<string, unknown>)[key] = clone(value);
          }
        }
        break;
      }

      case "TURN_UPDATE":
        Object.assign(state.turn, clone(op.fields ?? {}));
        break;

      case "TRIGGERABLE_TRAPS_SET":
        gs.triggerable_traps = clone(
          (op.value ?? {}) as Record<string, TrapContext>,
        );
        break;

      case "ACTIVATED_TRAPS_SET":
        gs.activated_traps = clone((op.value ?? []) as string[]);
        break;

      case "ATTACK_QUEUE_SET":
        gs.attack_queue = clone((op.value ?? []) as AttackEntry[]);
        break;

      case "EFFECTS_SET":
        state.effects = clone((op.value ?? []) as Effect[]);
        break;

      case "GAME_OVER_SET":
        gs.game_over = Boolean(op.value);
        break;
    }
  }

  /**
   * Replaces the whole local state from a server snapshot.
   *
   * Reproduces `GameState.deserialize`: for a mirrored seat both the field
   * matrix and the ownership matrix are rotated 180 degrees, and every card's
   * position is recomputed from its new slot.
   */
  private applyFullSync(state: ClientState, snapshot: SerializedEngine): void {
    const source = clone(snapshot);
    const gs = source.game_state;

    if (this.flip) {
      gs.field_matrix = this.rotate(gs.field_matrix);
      gs.field_matrix_ownership = this.rotate(gs.field_matrix_ownership);
    }

    for (let row = 0; row < gs.field_matrix.length; row += 1) {
      for (let col = 0; col < gs.field_matrix[row].length; col += 1) {
        const cardId = gs.field_matrix[row][col];
        const card = cardId ? gs.entity_lookup[cardId] : undefined;
        if (card) card.pos_in_matrix = [row, col];
      }
    }

    state.gameState = gs;
    state.turn = source.turn_manager;
    state.effects = source.effect_tracker ?? [];
    if (source.event_logger?.length) {
      state.pendingEvents.push(...source.event_logger);
    }
  }

  /** Looks up a player's card-id list for a zone. */
  private collection(
    gs: GameState,
    playerId: string | null | undefined,
    zone: Zone | null | undefined,
  ): string[] | null {
    if (!playerId || !zone) return null;
    const info = gs.player_info[playerId];
    if (!info) return null;
    const field = ZONE_FIELDS[zone];
    return (info[field] as unknown as { card_ids: string[] }).card_ids;
  }

  /**
   * Recomputes the per-viewer flags that are never sent over the wire.
   *
   * Matches `_deserialize_card` on the Python side so both clients agree on
   * what is hidden.
   */
  normalize(state: ClientState): void {
    if (!this.localPlayerId) return;
    const gs = state.gameState;

    for (const player of gs.players) {
      player.is_opponent = player.id !== this.localPlayerId;
    }

    const byId = new Map<string, Player>(gs.players.map((p) => [p.id, p]));
    for (const card of Object.values(gs.entity_lookup)) {
      const owner = byId.get(card.owner_id);
      card.is_opponent = Boolean(owner?.is_opponent);

      if (card.is_opponent) {
        card.is_face_down =
          card.card_type === "TRAP" || card.pos_in_matrix === null;
      } else {
        card.is_face_down =
          card.card_type === "TRAP" && card.pos_in_matrix !== null;
      }
    }
  }
}
