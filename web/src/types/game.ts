/**
 * TypeScript mirror of the Python game state serialization format.
 *
 * Every shape here matches what `GameState.serialize()` / `GameEngine.serialize()`
 * emit on the Python side (pydantic `model_dump(mode="json")`), so a payload can
 * travel Python -> Java relay -> browser without any field renaming.
 */

export type CardType = "MONSTER" | "SPELL" | "TRAP";
export type CardMode = "ATTACK" | "DEFEND";

export type MonsterType =
  | "SCHOLAR"
  | "CONQUEROR"
  | "FOREST_MONSTER"
  | "DEMON"
  | "FOREST_GUARD";

export type SpellAbility =
  | "BUFF_ATTACK"
  | "BUFF_DEFEND"
  | "DESTROY_TRAP"
  | "EXTRA_SUMMON"
  | "DRAW_CARD";

export type TrapAbility =
  | "REFLECT_ATTACK"
  | "DODGE_ATTACK"
  | "DEBUFF_ATTACK"
  | "DEBUFF_DEFEND";

export type ActivateCondition = "TOGGLE" | "ATTACK" | "SUMMON";

/** A grid position serialized as `[row, col]`. */
export type Cell = [number, number];

/** Fields shared by every card, matching `core.cards.card.Card`. */
export interface BaseCard {
  id: string;
  name: string;
  description: string;
  card_type: CardType;
  owner_id: string;
  image_path: string | null;
  is_placed: boolean;
  is_face_down: boolean;
  is_opponent: boolean;
  pos_in_matrix: Cell | null;
}

export interface MonsterCard extends BaseCard {
  card_type: "MONSTER";
  monster_type: MonsterType;
  attack: number;
  defend: number;
  star: number;
  mode: CardMode;
  has_attacked: boolean;
}

export interface SpellCard extends BaseCard {
  card_type: "SPELL";
  abilities: SpellAbility[];
  effectiveness: number[] | null;
  duration: number[] | null;
}

export interface TrapCard extends BaseCard {
  card_type: "TRAP";
  abilities: TrapAbility[];
  activation: ActivateCondition;
  effectiveness: number[] | null;
  duration: number[] | null;
  is_triggered: boolean;
  triggerable: boolean;
}

export type Card = MonsterCard | SpellCard | TrapCard;

export const isMonster = (card: Card): card is MonsterCard =>
  card.card_type === "MONSTER";
export const isTrap = (card: Card): card is TrapCard =>
  card.card_type === "TRAP";
export const isSpell = (card: Card): card is SpellCard =>
  card.card_type === "SPELL";

export interface Player {
  id: string;
  player_index: number;
  name: string;
  life_points: number;
  original_life_points: number;
  max_life_points: number;
  is_opponent: boolean;
}

/** Mirrors `gui.background.hand.CollectionInfo`. */
export interface CollectionInfo {
  card_ids: string[];
  player_id: string;
}

export interface PlayerInfo {
  has_summoned_trap: boolean;
  has_summoned_monster: boolean;
  has_toggled: boolean;
  held_cards: CollectionInfo;
  graveyard_cards: CollectionInfo;
  deck_cards: CollectionInfo;
  active_traps: string[];
}

export interface TrapContext {
  target_id: string;
}

export interface AttackEntry {
  attacker_id: string;
  defender_id: string;
  card_id: string;
  target_id: string;
  target_is_player: boolean;
}

export interface GameState {
  players: Player[];
  game_over: boolean;
  player_info: Record<string, PlayerInfo>;
  entity_lookup: Record<string, Card>;
  field_matrix: (string | null)[][];
  field_matrix_ownership: string[][];
  triggerable_traps: Record<string, TrapContext>;
  activated_traps: string[];
  attack_queue: AttackEntry[];
}

export interface Effect {
  effect_type: "BUFF" | "DEBUFF";
  stat: string;
  target_id: string;
  value: number;
  duration: number;
  remaining: number;
}

export interface TurnManagerState {
  current_player_index: number;
  is_trap_stage: boolean;
  turn_count: number;
}

/** Mirrors `GameEngine.serialize()`. */
export interface SerializedEngine {
  game_state: GameState;
  effect_tracker: Effect[];
  event_logger: GameEvent[];
  turn_manager: TurnManagerState;
}

// --- Animation events (core.data.events) ---------------------------------

export interface AttackEvent {
  card_id: string;
  target_id: string;
  target_is_player: boolean;
}
export interface TrapTriggerEvent {
  card_id: string;
  target_id: string;
}
export interface TrapTriggerableEvent {
  card_id: string;
}
export interface ToggleEvent {
  card_id: string;
  mode: string;
}
export interface SpellActiveEvent {
  spell_id: string;
  target_id: string | null;
}
export interface MergeEvent {
  card_id: string;
  target_id: string;
  result_card_id: string;
}

/**
 * The event union is discriminated structurally, exactly as pydantic's
 * `GameEventAdapter` does: there is no explicit `type` tag on the wire.
 */
export type GameEvent =
  | AttackEvent
  | TrapTriggerEvent
  | TrapTriggerableEvent
  | ToggleEvent
  | SpellActiveEvent
  | MergeEvent;

/** Narrows a raw event object to the concrete variant it represents. */
export type EventKind =
  | "ATTACK"
  | "TRAP_TRIGGER"
  | "TRAP_TRIGGERABLE"
  | "TOGGLE"
  | "SPELL_ACTIVE"
  | "MERGE"
  | "UNKNOWN";

/**
 * Identifies which event variant a serialized payload is.
 *
 * The Python side relies on pydantic's smart union, which picks the first model
 * whose required fields are all present. The order below reproduces that.
 *
 * @param event - A serialized event from `event_logger`.
 * @returns The event's discriminated kind.
 */
export function eventKind(event: Record<string, unknown>): EventKind {
  if ("spell_id" in event) return "SPELL_ACTIVE";
  if ("result_card_id" in event) return "MERGE";
  if ("target_is_player" in event) return "ATTACK";
  if ("mode" in event) return "TOGGLE";
  if ("target_id" in event) return "TRAP_TRIGGER";
  if ("card_id" in event) return "TRAP_TRIGGERABLE";
  return "UNKNOWN";
}
