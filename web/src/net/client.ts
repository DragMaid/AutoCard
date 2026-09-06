/**
 * Socket.IO client for the room relay.
 *
 * The browser speaks only two messages: it emits ID-only intents and receives
 * patches. All rules live in the Python engine behind the Java API, so this
 * module deliberately contains no game logic beyond translating grid cells out
 * of the local (possibly mirrored) frame and into the server's frame.
 */

import { io, type Socket } from "socket.io-client";

import { COLS, ROWS } from "../game/layout";
import type { GameActions } from "../game/inputManager";
import type { Cell, SerializedEngine } from "../types/game";
import {
  EVENT_ASSIGN,
  EVENT_ERROR,
  EVENT_INTENT,
  EVENT_JOIN,
  EVENT_PATCH,
  makeIntent,
  type Assignment,
  type Intent,
  type IntentPayload,
  type IntentType,
  type Patch,
} from "./actions";

export type ConnectionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "error"
  | "closed";

/** Callbacks a connection raises as the match progresses. */
export interface ConnectionHandlers {
  onAssign(assignment: Assignment): void;
  onPatch(patch: Patch): void;
  onStatus(status: ConnectionStatus, detail?: string): void;
  onError(message: string): void;
}

/** Everything the UI can ask the server to do. */
export interface GameConnection extends GameActions {
  endTurn(): void;
  surrender(): void;
  requestSync(): void;
  startGame(): void;
  disconnect(): void;
  readonly status: ConnectionStatus;
}

/** Options for opening a room connection. */
export interface ConnectOptions {
  /** Base URL of the Java API, e.g. `https://api.example.com`. */
  url: string;
  /** Room to join. */
  roomId: string;
  /** Optional bearer token forwarded in the Socket.IO auth payload. */
  token?: string;
  /** Optional display name sent with the join request. */
  playerName?: string;
}

/**
 * A live connection to a room served by the Java relay.
 *
 * @remarks
 * The seat assignment decides whether the board is mirrored, which in turn
 * decides how outgoing cells are translated. Until `assign` arrives the
 * connection assumes the un-mirrored host seat.
 */
export class SocketConnection implements GameConnection {
  private socket: Socket | null = null;
  private seq = 0;

  /** Seat identity, populated by the server's `assign` message. */
  roomId: string;
  actorId = "";
  flip = false;

  status: ConnectionStatus = "idle";

  constructor(
    private options: ConnectOptions,
    private handlers: ConnectionHandlers,
  ) {
    this.roomId = options.roomId;
  }

  /** Opens the socket and joins the room. */
  connect(): void {
    this.setStatus("connecting");

    this.socket = io(this.options.url, {
      transports: ["websocket"],
      auth: this.options.token ? { token: this.options.token } : undefined,
      reconnection: true,
      reconnectionAttempts: 5,
    });

    this.socket.on("connect", () => {
      this.setStatus("connected");
      this.socket?.emit(EVENT_JOIN, {
        room_id: this.roomId,
        player_name: this.options.playerName ?? "player",
      });
    });

    this.socket.on(EVENT_ASSIGN, (data: Assignment) => {
      this.roomId = data.room_id ?? this.roomId;
      this.actorId = data.player_id;
      // Seat 0 is the authoritative frame; any other seat renders mirrored.
      this.flip = Number(data.player_index ?? 1) !== 0;
      this.handlers.onAssign(data);
    });

    this.socket.on(EVENT_PATCH, (data: Patch) => {
      if (data.room_id && data.room_id !== this.roomId) return;
      this.handlers.onPatch(data);
    });

    this.socket.on(EVENT_ERROR, (data: { message?: string } | string) => {
      this.handlers.onError(
        typeof data === "string" ? data : (data?.message ?? "Server error"),
      );
    });

    this.socket.on("connect_error", (error: Error) => {
      this.setStatus("error", error.message);
    });

    this.socket.on("disconnect", (reason: string) => {
      this.setStatus("closed", reason);
    });
  }

  /** Closes the socket. */
  disconnect(): void {
    this.socket?.disconnect();
    this.socket = null;
    this.setStatus("closed");
  }

  private setStatus(status: ConnectionStatus, detail?: string): void {
    this.status = status;
    this.handlers.onStatus(status, detail);
  }

  /**
   * Converts a cell from this seat's frame into the server's frame.
   *
   * Mirrors `GameEngine._canonical_cell`. A mirrored seat renders row 0 where
   * the server keeps the last row, so the slot the player dropped onto is not
   * the slot the engine knows by that name.
   */
  private canonicalCell(cell: Cell): Cell {
    if (!this.flip) return cell;
    return [ROWS - 1 - cell[0], COLS - 1 - cell[1]];
  }

  /** Emits one intent to the relay. */
  private send(type: IntentType, payload: IntentPayload = {}): void {
    if (!this.socket?.connected) {
      this.handlers.onError("Not connected to the game server");
      return;
    }
    this.seq += 1;
    const intent: Intent = makeIntent(
      this.roomId,
      this.actorId,
      type,
      this.seq,
      payload,
    );
    this.socket.emit(EVENT_INTENT, intent);
  }

  summon(cardId: string, cell: Cell): void {
    this.send("SUMMON", { card_id: cardId, cell: this.canonicalCell(cell) });
  }

  setTrap(cardId: string, cell: Cell): void {
    this.send("SET_TRAP", { card_id: cardId, cell: this.canonicalCell(cell) });
  }

  castSpell(spellId: string, targetId: string | null): void {
    this.send("CAST_SPELL", { card_id: spellId, target_id: targetId });
  }

  toggle(cardId: string): void {
    this.send("TOGGLE", { card_id: cardId });
  }

  attack(cardId: string, targetId: string, targetIsPlayer: boolean): void {
    this.send("ATTACK", {
      card_id: cardId,
      target_id: targetId,
      target_is_player: targetIsPlayer,
    });
  }

  upgrade(cardId: string, targetId: string): void {
    this.send("UPGRADE", { card_id: cardId, target_id: targetId });
  }

  toggleTrapActivation(trapId: string, activated: boolean): void {
    this.send("TOGGLE_TRAP_ACTIVATION", { card_id: trapId, activated });
  }

  endTurn(): void {
    this.send("END_TURN");
  }

  surrender(): void {
    this.send("SURRENDER");
  }

  requestSync(): void {
    this.send("REQUEST_SYNC");
  }

  startGame(): void {
    this.send("START_GAME");
  }
}

/**
 * An offline connection that replays a captured engine snapshot.
 *
 * Used to develop and demo the interface with no backend running. Because all
 * rules live server-side, this mode is view-only: intents are logged and
 * surfaced to the UI rather than resolved.
 */
export class DemoConnection implements GameConnection {
  status: ConnectionStatus = "idle";

  /** Intents the UI attempted, most recent last. */
  readonly attempted: Intent[] = [];

  private seq = 0;

  constructor(
    private snapshot: SerializedEngine,
    private handlers: ConnectionHandlers,
    /** Which seat to view the captured board from. */
    private seatIndex = 0,
  ) {}

  /** Emits the snapshot as a single full-sync patch. */
  connect(): void {
    this.status = "connected";
    this.handlers.onStatus("connected", "demo");

    const player = this.snapshot.game_state.players[this.seatIndex];
    this.handlers.onAssign({
      room_id: "demo",
      player_id: player?.id ?? "",
      player_index: this.seatIndex,
    });

    this.handlers.onPatch({
      version: 1,
      room_id: "demo",
      seq: 1,
      cause: "FULL_SYNC",
      ops: [{ op: "FULL_SYNC", value: this.snapshot }],
      events: [],
    });
  }

  disconnect(): void {
    this.status = "closed";
    this.handlers.onStatus("closed");
  }

  private record(type: IntentType, payload: IntentPayload = {}): void {
    this.seq += 1;
    const player = this.snapshot.game_state.players[this.seatIndex];
    this.attempted.push(
      makeIntent("demo", player?.id ?? "", type, this.seq, payload),
    );
    this.handlers.onError(
      `Demo mode: ${type} was not sent. Connect a backend to play.`,
    );
  }

  summon(cardId: string, cell: Cell): void {
    this.record("SUMMON", { card_id: cardId, cell });
  }
  setTrap(cardId: string, cell: Cell): void {
    this.record("SET_TRAP", { card_id: cardId, cell });
  }
  castSpell(spellId: string, targetId: string | null): void {
    this.record("CAST_SPELL", { card_id: spellId, target_id: targetId });
  }
  toggle(cardId: string): void {
    this.record("TOGGLE", { card_id: cardId });
  }
  attack(cardId: string, targetId: string, targetIsPlayer: boolean): void {
    this.record("ATTACK", {
      card_id: cardId,
      target_id: targetId,
      target_is_player: targetIsPlayer,
    });
  }
  upgrade(cardId: string, targetId: string): void {
    this.record("UPGRADE", { card_id: cardId, target_id: targetId });
  }
  toggleTrapActivation(trapId: string, activated: boolean): void {
    this.record("TOGGLE_TRAP_ACTIVATION", { card_id: trapId, activated });
  }
  endTurn(): void {
    this.record("END_TURN");
  }
  surrender(): void {
    this.record("SURRENDER");
  }
  requestSync(): void {
    this.record("REQUEST_SYNC");
  }
  startGame(): void {
    this.record("START_GAME");
  }
}
