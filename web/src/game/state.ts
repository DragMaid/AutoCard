/**
 * Read-only selectors over the game state.
 *
 * These are ports of the query methods on `core.data.game_state.GameState` and
 * `core.logic.turn_manager.TurnManager`. The browser never mutates state through
 * this module — only patches from the authoritative engine do that.
 */

import { COLS, ROWS } from "./layout";
import type {
  Card,
  GameState,
  MonsterCard,
  Player,
  TurnManagerState,
} from "../types/game";
import { isMonster } from "../types/game";

/** Looks up a card by id. Mirrors `GameState.get_card_by_id`. */
export function getCard(state: GameState, cardId: string | null | undefined): Card | null {
  if (!cardId) return null;
  return state.entity_lookup[cardId] ?? null;
}

/** Indexes players by id. Mirrors `GameState.players_lookup`. */
export function playersById(state: GameState): Map<string, Player> {
  return new Map(state.players.map((player) => [player.id, player]));
}

/** The player this client controls, i.e. the one drawn along the bottom. */
export function localPlayer(state: GameState): Player | null {
  return state.players.find((player) => !player.is_opponent) ?? null;
}

/** The opposing player. */
export function opponentPlayer(state: GameState): Player | null {
  return state.players.find((player) => player.is_opponent) ?? null;
}

/** Yields every non-empty card id on the field, row major. */
export function* iterFieldCardIds(state: GameState): Generator<string> {
  for (const row of state.field_matrix) {
    for (const cardId of row) {
      if (cardId) yield cardId;
    }
  }
}

/** Cards a player controls on the field. Mirrors `get_player_field_cards`. */
export function getPlayerFieldCards(
  state: GameState,
  playerId: string,
): Card[] {
  const cards: Card[] = [];
  for (let row = 0; row < ROWS; row += 1) {
    for (let col = 0; col < COLS; col += 1) {
      const cardId = state.field_matrix[row]?.[col];
      if (!cardId) continue;
      if (state.field_matrix_ownership[row]?.[col] !== playerId) continue;
      const card = state.entity_lookup[cardId];
      if (card) cards.push(card);
    }
  }
  return cards;
}

/** Card ids held by a player. Mirrors `get_player_held_card_ids`. */
export function getHeldCardIds(state: GameState, playerId: string): string[] {
  return state.player_info[playerId]?.held_cards.card_ids ?? [];
}

/** The opposing player's id. Mirrors `get_opponent_id`. */
export function getOpponentId(
  state: GameState,
  playerId: string,
): string | null {
  for (const id of Object.keys(state.player_info)) {
    if (id !== playerId) return id;
  }
  return null;
}

/**
 * Groups a player's field monsters by type and star level.
 *
 * Mirrors `GameState.get_mergeable_groups`; the renderer highlights any group
 * with two or more members as a merge candidate.
 *
 * @param state - Current game state.
 * @param playerId - The player whose board to inspect.
 * @returns A map from `"playerId|type|star"` to the matching monsters.
 */
export function getMergeableGroups(
  state: GameState,
  playerId: string,
): Map<string, MonsterCard[]> {
  const groups = new Map<string, MonsterCard[]>();
  for (const card of getPlayerFieldCards(state, playerId)) {
    if (!isMonster(card)) continue;
    const key = `${playerId}|${card.monster_type}|${card.star}`;
    const bucket = groups.get(key);
    if (bucket) bucket.push(card);
    else groups.set(key, [card]);
  }
  return groups;
}

/** The player whose turn it is. Mirrors `TurnManager.get_current_player`. */
export function currentPlayer(
  state: GameState,
  turn: TurnManagerState,
): Player | null {
  return state.players[turn.current_player_index] ?? null;
}

/** The player who acts next. Mirrors `TurnManager.get_next_player`. */
export function nextPlayer(
  state: GameState,
  turn: TurnManagerState,
): Player | null {
  if (!state.players.length) return null;
  const index = (turn.current_player_index + 1) % state.players.length;
  return state.players[index] ?? null;
}

/**
 * The player allowed to activate traps, if the trap stage is open.
 *
 * Mirrors `TurnManager.get_trapper`.
 */
export function trapper(
  state: GameState,
  turn: TurnManagerState,
): Player | null {
  if (!turn.is_trap_stage) return null;
  return nextPlayer(state, turn);
}

/**
 * Whether the local player may act right now.
 *
 * Mirrors `core.logic.utils.is_local_turn`: during the trap stage control
 * belongs to the trapper, otherwise to the current player.
 */
export function isLocalTurn(
  state: GameState,
  turn: TurnManagerState,
): boolean {
  const local = localPlayer(state);
  if (!local) return false;

  const activeTrapper = trapper(state, turn);
  if (activeTrapper) return activeTrapper.id === local.id;

  return currentPlayer(state, turn)?.id === local.id;
}
