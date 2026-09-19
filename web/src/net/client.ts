/**
 * Socket.IO client for the room relay.
 *
 * The browser speaks only two gameplay messages: it emits ID-only intents and
 * receives patches. All rules live in the Python engine behind the C# relay, so
 * this module deliberately contains no game logic beyond translating grid cells
 * out of the local (possibly mirrored) frame and into the server's frame.
 *
 * Everything else here is lobby traffic: how you got into a room, and how full
 * that room is.
 */

import { io, type Socket } from "socket.io-client";

import { COLS, ROWS } from "../game/layout";
import type { GameActions } from "../game/inputManager";
import type { Cell } from "../types/game";
import {
  EVENT_ASSIGN,
  EVENT_CANCEL_MATCHMAKE,
  EVENT_CREATE_ROOM,
  EVENT_ERROR,
  EVENT_INTENT,
  EVENT_JOIN,
  EVENT_MATCHMAKE,
  EVENT_PATCH,
  EVENT_QUEUED,
  EVENT_ROOM_STATUS,
  makeIntent,
  type Assignment,
  type Intent,
  type IntentPayload,
  type IntentType,
  type Patch,
  type QueueStatus,
  type RoomStatus,
} from "./actions";

export type ConnectionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "error"
  | "closed";

/**
 * How a client wants to get into a room.
 *
 * The relay decides the room in every case but `join`: `create` gets a freshly
 * generated code to share, and `match` waits to be paired with a stranger.
 */
export type Entry =
  | { kind: "join"; roomId: string }
  | { kind: "create"; mode?: "pvp" | "ai" }
  | { kind: "match" };

/** Callbacks a connection raises as the match progresses. */
export interface ConnectionHandlers {
  onAssign(assignment: Assignment): void;
  onPatch(patch: Patch): void;
  onRoomStatus(status: RoomStatus): void;
  onQueued(status: QueueStatus): void;
  onStatus(status: ConnectionStatus, detail?: string): void;
  onError(message: string): void;
}

/** Everything the UI can ask the server to do. */
export interface GameConnection extends GameActions {
  endTurn(): void;
  surrender(): void;
  requestSync(): void;
  startGame(): void;
  cancelMatchmake(): void;
  disconnect(): void;
  readonly status: ConnectionStatus;
}

/** Options for opening a room connection. */
export interface ConnectOptions {
  /** Base URL of the relay, e.g. `https://api.example.com`. */
  url: string;
  /** How to get into a room. */
  entry: Entry;
  /** Optional bearer token forwarded in the Socket.IO auth payload. */
  token?: string;
  /** Optional display name sent with the entry request. */
  playerName?: string;
}

/**
 * A live connection to a room served by the C# relay.
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
  roomId = "";
  actorId = "";
  flip = false;

  status: ConnectionStatus = "idle";

  constructor(
    private options: ConnectOptions,
    private handlers: ConnectionHandlers,
  ) {
    if (options.entry.kind === "join") {
      this.roomId = options.entry.roomId;
    }
  }

  /** Opens the socket and enters a room. */
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
      this.enter();
    });

    this.socket.on(EVENT_ASSIGN, (data: Assignment) => {
      this.roomId = data.room_id ?? this.roomId;
      this.actorId = data.player_id;
      // Seat 0 is the authoritative frame; any other seat renders mirrored.
      this.flip = Number(data.player_index ?? 1) !== 0;
      this.handlers.onAssign(data);
    });

    this.socket.on(EVENT_ROOM_STATUS, (data: RoomStatus) => {
      this.handlers.onRoomStatus(data);
    });

    this.socket.on(EVENT_QUEUED, (data: QueueStatus) => {
      this.handlers.onQueued(data);
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

  /**
   * Asks the relay for a seat.
   *
   * Once a seat has been assigned this always rejoins that room by id, because
   * socket.io reconnects by re-running `connect`: repeating the original entry
   * would open a *second* room for someone who was only briefly offline. The
   * relay holds the seat for its grace period and hands the board back.
   */
  private enter(): void {
    if (this.actorId) {
      this.socket?.emit(EVENT_JOIN, {
        room_id: this.roomId,
        player_name: this.options.playerName ?? "player",
        player_id: this.actorId,
      });
      return;
    }

    const { entry } = this.options;
    const playerName = this.options.playerName ?? "player";

    switch (entry.kind) {
      case "join":
        this.socket?.emit(EVENT_JOIN, {
          room_id: entry.roomId,
          player_name: playerName,
        });
        return;
      case "create":
        this.socket?.emit(EVENT_CREATE_ROOM, {
          player_name: playerName,
          mode: entry.mode ?? "pvp",
        });
        return;
      case "match":
        this.socket?.emit(EVENT_MATCHMAKE, { player_name: playerName });
        return;
    }
  }

  /** Withdraws from the quick-match queue without closing the socket. */
  cancelMatchmake(): void {
    this.socket?.emit(EVENT_CANCEL_MATCHMAKE, {});
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
