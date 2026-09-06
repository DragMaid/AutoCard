/**
 * Application shell.
 *
 * Owns the connection lifecycle (lobby -> connected room, or the offline demo)
 * and wires stage pointer events into the input manager. All gameplay decisions
 * belong to the Python engine; this component only sends intents and draws
 * whatever the resulting patches describe.
 */

import { useCallback, useMemo, useRef, useState } from "react";

import { GameClient } from "./game/gameClient";
import { getCard } from "./game/state";
import {
  DemoConnection,
  SocketConnection,
  type ConnectionHandlers,
  type GameConnection,
} from "./net/client";
import { Board } from "./render/Board";
import { Hud, GameOverOverlay, SurrenderOverlay, TrapStageOverlay } from "./render/Hud";
import { ArrowLayer, CardPreview } from "./render/Overlays";
import { SpriteLayer } from "./render/SpriteLayer";
import { Stage, type StagePointer } from "./render/Stage";
import { useGameLoop } from "./render/useGameLoop";
import type { SerializedEngine } from "./types/game";
import demoSnapshot from "./demo/snapshot.json";

type Screen = "lobby" | "game";

const DEFAULT_SERVER =
  (import.meta.env.VITE_GAME_API as string | undefined) ??
  "http://localhost:8080";

export default function App() {
  const client = useMemo(() => new GameClient(), []);
  const [screen, setScreen] = useState<Screen>("lobby");
  const [serverUrl, setServerUrl] = useState(DEFAULT_SERVER);
  const [roomId, setRoomId] = useState("");
  const [playerName, setPlayerName] = useState("player");
  const [status, setStatus] = useState<string>("idle");
  const [surrendering, setSurrendering] = useState(false);
  const [dismissedGameOver, setDismissedGameOver] = useState(false);

  const connectionRef = useRef<GameConnection | null>(null);
  const { sprites, hud, error } = useGameLoop(client);

  const handlers: ConnectionHandlers = useMemo(
    () => ({
      onAssign: (assignment) => client.onAssign(assignment),
      onPatch: (patch) => client.onPatch(patch),
      onStatus: (next, detail) => setStatus(detail ? `${next}: ${detail}` : next),
      onError: (message) => client.onError(message),
    }),
    [client],
  );

  /** Opens a live room on the Java relay. */
  const connect = useCallback(() => {
    const connection = new SocketConnection(
      { url: serverUrl, roomId: roomId.trim() || "lobby", playerName },
      handlers,
    );
    connectionRef.current = connection;
    client.connection = connection;
    connection.connect();
    setScreen("game");
  }, [client, handlers, playerName, roomId, serverUrl]);

  /** Opens the captured snapshot with no backend attached. */
  const openDemo = useCallback(
    (seatIndex: number) => {
      const connection = new DemoConnection(
        demoSnapshot as unknown as SerializedEngine,
        handlers,
        seatIndex,
      );
      connectionRef.current = connection;
      client.connection = connection;
      connection.connect();
      setScreen("game");
    },
    [client, handlers],
  );

  const leave = useCallback(() => {
    connectionRef.current?.disconnect();
    connectionRef.current = null;
    client.connection = null;
    setScreen("lobby");
    setDismissedGameOver(false);
  }, [client]);

  const onPointerDown = useCallback(
    (pointer: StagePointer) => {
      client.clearError();
      client.input.onPointerDown(pointer.x, pointer.y, pointer.button);
    },
    [client],
  );

  const onPointerMove = useCallback(
    (pointer: StagePointer) => client.input.onPointerMove(pointer.x, pointer.y),
    [client],
  );

  const onPointerUp = useCallback(
    (pointer: StagePointer) => client.input.onPointerUp(pointer.x, pointer.y),
    [client],
  );

  if (screen === "lobby") {
    return (
      <Lobby
        serverUrl={serverUrl}
        roomId={roomId}
        playerName={playerName}
        onServerUrl={setServerUrl}
        onRoomId={setRoomId}
        onPlayerName={setPlayerName}
        onConnect={connect}
        onDemo={openDemo}
      />
    );
  }

  const state = client.state.gameState;
  const localPlayer = state.players.find((p) => !p.is_opponent);
  const opponent = state.players.find((p) => p.is_opponent);
  const previewCard = getCard(state, hud.previewCardId);

  return (
    <div className="relative h-dvh w-screen bg-black">
      <Stage
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={() => client.input.cancel()}
      >
        <Board
          localName={hud.localName}
          localLife={hud.localLife}
          opponentName={hud.opponentName}
          opponentLife={hud.opponentLife}
          localDeckCount={
            localPlayer
              ? (state.player_info[localPlayer.id]?.deck_cards.card_ids.length ?? 0)
              : 0
          }
          opponentDeckCount={
            opponent
              ? (state.player_info[opponent.id]?.deck_cards.card_ids.length ?? 0)
              : 0
          }
        />

        <CardPreview card={previewCard} />
        <SpriteLayer client={client} sprites={sprites} />
        <ArrowLayer
          dragArrow={client.input.dragArrow}
          attackIndicators={client.render.attackIndicators}
          effects={client.render.animations.effects}
        />

        <Hud
          hud={hud}
          onEndTurn={() => client.connection?.endTurn()}
          onSurrender={() => setSurrendering(true)}
        />

        <TrapStageOverlay visible={hud.isTrapStage && !hud.isLocalTurn} />

        <SurrenderOverlay
          visible={surrendering}
          onConfirm={() => {
            client.connection?.surrender();
            setSurrendering(false);
          }}
          onCancel={() => setSurrendering(false)}
        />

        <GameOverOverlay
          visible={hud.gameOver && !dismissedGameOver}
          victory={hud.localLife > 0}
          onContinue={() => {
            setDismissedGameOver(true);
            leave();
          }}
        />
      </Stage>

      <StatusBar status={status} error={error} onLeave={leave} />
    </div>
  );
}

/** Connection status strip pinned outside the scaled stage. */
function StatusBar({
  status,
  error,
  onLeave,
}: {
  status: string;
  error: string | null;
  onLeave: () => void;
}) {
  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-3 p-3">
      <span className="pointer-events-auto rounded bg-black/70 px-2.5 py-1 text-xs text-slate-300">
        {status}
      </span>

      {error && (
        <span className="pointer-events-auto max-w-md rounded bg-red-950/90 px-3 py-1.5 text-xs text-red-200 ring-1 ring-red-500/40">
          {error}
        </span>
      )}

      <button
        type="button"
        onClick={onLeave}
        className="pointer-events-auto rounded bg-slate-800/90 px-3 py-1 text-xs text-slate-200 hover:bg-slate-700"
      >
        Leave
      </button>
    </div>
  );
}

interface LobbyProps {
  serverUrl: string;
  roomId: string;
  playerName: string;
  onServerUrl: (value: string) => void;
  onRoomId: (value: string) => void;
  onPlayerName: (value: string) => void;
  onConnect: () => void;
  onDemo: (seatIndex: number) => void;
}

/** Room entry screen. */
function Lobby({
  serverUrl,
  roomId,
  playerName,
  onServerUrl,
  onRoomId,
  onPlayerName,
  onConnect,
  onDemo,
}: LobbyProps) {
  return (
    <div className="flex h-dvh w-screen items-center justify-center bg-slate-950 p-6">
      <div className="w-full max-w-md rounded-2xl bg-slate-900 p-7 ring-1 ring-slate-800">
        <h1 className="text-2xl font-semibold text-slate-100">AutoCard</h1>
        <p className="mt-1 text-sm text-slate-400">
          Join a room on the game API. All rules run on the server.
        </p>

        <div className="mt-6 space-y-4">
          <Field label="Server URL">
            <input
              value={serverUrl}
              onChange={(event) => onServerUrl(event.target.value)}
              placeholder="http://localhost:8080"
              className="w-full rounded-lg bg-slate-800 px-3 py-2 text-sm text-slate-100 outline-none ring-1 ring-slate-700 focus:ring-sky-500"
            />
          </Field>

          <Field label="Room ID">
            <input
              value={roomId}
              onChange={(event) => onRoomId(event.target.value)}
              placeholder="e.g. ABC123"
              className="w-full rounded-lg bg-slate-800 px-3 py-2 text-sm text-slate-100 outline-none ring-1 ring-slate-700 focus:ring-sky-500"
            />
          </Field>

          <Field label="Display name">
            <input
              value={playerName}
              onChange={(event) => onPlayerName(event.target.value)}
              className="w-full rounded-lg bg-slate-800 px-3 py-2 text-sm text-slate-100 outline-none ring-1 ring-slate-700 focus:ring-sky-500"
            />
          </Field>

          <button
            type="button"
            onClick={onConnect}
            className="w-full rounded-lg bg-sky-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-sky-500"
          >
            Join room
          </button>
        </div>

        <div className="mt-7 border-t border-slate-800 pt-5">
          <p className="text-xs text-slate-500">
            No backend yet? Open a captured game state to inspect the board and
            the layout. Actions are recorded but not resolved.
          </p>
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={() => onDemo(0)}
              className="flex-1 rounded-lg bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700"
            >
              Demo · host seat
            </button>
            <button
              type="button"
              onClick={() => onDemo(1)}
              className="flex-1 rounded-lg bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700"
            >
              Demo · guest seat
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-slate-400">
        {label}
      </span>
      {children}
    </label>
  );
}
