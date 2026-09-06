/**
 * TypeScript mirror of `core/network/actions.py`.
 *
 * Intents travel browser -> Java relay -> Python engine and carry nothing but
 * IDs. Patches travel back and describe single-field mutations of the game
 * state. Keep this file in lockstep with the Python module: the two are one
 * protocol.
 */

import type { Cell, GameEvent, SerializedEngine } from "../types/game";

export const PROTOCOL_VERSION = 1;

/** Socket.IO event names shared with the Python server and the Java relay. */
export const EVENT_INTENT = "action";
export const EVENT_PATCH = "patch";
export const EVENT_ASSIGN = "assign";
export const EVENT_JOIN = "join";
export const EVENT_ERROR = "game_error";

export type IntentType =
  | "START_GAME"
  | "DRAW"
  | "SUMMON"
  | "SET_TRAP"
  | "CAST_SPELL"
  | "TOGGLE"
  | "ATTACK"
  | "UPGRADE"
  | "TOGGLE_TRAP_ACTIVATION"
  | "END_TURN"
  | "SURRENDER"
  | "REQUEST_SYNC";

export type OpType =
  | "CARD_UPSERT"
  | "CARD_UPDATE"
  | "CARD_REMOVE"
  | "ZONE_ADD"
  | "ZONE_REMOVE"
  | "FIELD_SET"
  | "PLAYER_UPDATE"
  | "PLAYER_INFO_UPDATE"
  | "TURN_UPDATE"
  | "TRIGGERABLE_TRAPS_SET"
  | "ACTIVATED_TRAPS_SET"
  | "ATTACK_QUEUE_SET"
  | "EFFECTS_SET"
  | "GAME_OVER_SET"
  | "FULL_SYNC";

export type Zone = "hand" | "graveyard" | "deck";

/** Payload of an intent. Every value is an identifier or a plain scalar. */
export interface IntentPayload {
  card_id?: string;
  target_id?: string | null;
  cell?: [number, number] | null;
  target_is_player?: boolean;
  activated?: boolean;
}

export interface Intent {
  version: number;
  room_id: string;
  actor_id: string;
  type: IntentType;
  payload: IntentPayload;
  seq: number;
}

export interface PatchOp {
  op: OpType;
  card_id?: string | null;
  card?: Record<string, unknown> | null;
  fields?: Record<string, unknown> | null;
  player_id?: string | null;
  zone?: Zone | null;
  row?: number | null;
  col?: number | null;
  value?: unknown;
}

export interface Patch {
  version: number;
  room_id: string;
  seq: number;
  cause: string | null;
  ops: PatchOp[];
  events: GameEvent[];
}

/** Seat assignment handed to a client when it joins a room. */
export interface Assignment {
  room_id: string;
  player_id: string;
  player_index: number;
  opponent_id?: string;
}

/**
 * Builds an intent, dropping undefined payload entries.
 *
 * Mirrors `make_intent` in Python, which strips `None` values so the JSON stays
 * minimal and the server sees only the fields an action actually needs.
 *
 * @param roomId - Room the intent targets.
 * @param actorId - Player performing the action.
 * @param type - Which action is requested.
 * @param seq - Client-side monotonic counter.
 * @param payload - ID-only arguments.
 * @returns The intent ready to emit.
 */
export function makeIntent(
  roomId: string,
  actorId: string,
  type: IntentType,
  seq: number,
  payload: IntentPayload = {},
): Intent {
  const clean: IntentPayload = {};
  for (const [key, value] of Object.entries(payload)) {
    if (value !== undefined && value !== null) {
      (clean as Record<string, unknown>)[key] = value;
    }
  }
  return {
    version: PROTOCOL_VERSION,
    room_id: roomId,
    actor_id: actorId,
    type,
    payload: clean,
    seq,
  };
}

/** A patch op carrying a complete engine snapshot. */
export function isFullSync(op: PatchOp): boolean {
  return op.op === "FULL_SYNC";
}

/** Extracts the engine snapshot from a FULL_SYNC op. */
export function fullSyncValue(op: PatchOp): SerializedEngine {
  return op.value as SerializedEngine;
}

/** Type guard for a well-formed cell coming off the wire. */
export function asCell(value: unknown): Cell | null {
  if (!Array.isArray(value) || value.length < 2) return null;
  return [Number(value[0]), Number(value[1])];
}
