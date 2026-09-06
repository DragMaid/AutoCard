/**
 * Application shell.
 *
 * Owns the connection lifecycle (lobby -> connected room, or the offline demo)
 * and wires stage pointer events into the input manager. All gameplay decisions
 * belong to the Python engine; this component only sends intents and draws
 * whatever the resulting patches describe.
 */

import { useCallback, useMemo, useRef, useState } from "react";

import { backgroundUrl } from "./game/assets";
import { GameClient } from "./game/gameClient";
import { LAYOUT } from "./game/layout";
import { getCard } from "./game/state";
import {
  COLORS,
  PIXEL_FONT,
  TEXT_OUTLINE,
  pixelButton,
  pixelPanel,
  pixelWell,
} from "./game/theme";
import {
  DemoConnection,
  SocketConnection,
  type ConnectionHandlers,
  type GameConnection,
} from "./net/client";
import { Board } from "./render/Board";
import { GameOverOverlay, SurrenderOverlay, TrapStageOverlay } from "./render/Hud";
import { ArrowLayer, CardPreview } from "./render/Overlays";
import { ActionPanel, PlayerPanel } from "./render/Panels";
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
      <Starfield>
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
      </Starfield>
    );
  }

  const state = client.state.gameState;
  const localPlayer = state.players.find((p) => !p.is_opponent);
  const opponent = state.players.find((p) => p.is_opponent);
  const previewCard = getCard(state, hud.previewCardId);

  /** Cards left in a player's deck, or zero before the first sync. */
  const deckCount = (playerId: string | undefined) =>
    playerId
      ? (state.player_info[playerId]?.deck_cards.card_ids.length ?? 0)
      : 0;

  /** Cards in a player's graveyard. */
  const graveCount = (playerId: string | undefined) =>
    playerId
      ? (state.player_info[playerId]?.graveyard_cards.card_ids.length ?? 0)
      : 0;

  return (
    <Starfield>
      <div className="flex h-dvh w-screen flex-col">
        <TopBar status={status} error={error} onLeave={leave} />

        <main className="min-h-0 flex-1 px-5 pb-5">
          <Stage
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={() => client.input.cancel()}
          >
            <Board />

            <PlayerPanel
              rect={LAYOUT.areas.opponentPanel}
              deckRect={LAYOUT.areas.opponentDeck}
              name={hud.opponentName}
              life={hud.opponentLife}
              maxLife={opponent?.max_life_points ?? hud.opponentLife}
              handCount={hud.opponentHandCount}
              graveyardCount={graveCount(opponent?.id)}
              deckCount={deckCount(opponent?.id)}
              isOpponent
              active={!hud.isLocalTurn}
            />

            <CardPreview card={previewCard} />

            <PlayerPanel
              rect={LAYOUT.areas.localPanel}
              deckRect={LAYOUT.areas.myDeck}
              name={hud.localName}
              life={hud.localLife}
              maxLife={localPlayer?.max_life_points ?? hud.localLife}
              handCount={hud.localHandCount}
              graveyardCount={hud.localGraveyard}
              deckCount={deckCount(localPlayer?.id)}
              isOpponent={false}
              active={hud.isLocalTurn}
            />

            <ActionPanel
              turnCount={hud.turnCount}
              isLocalTurn={hud.isLocalTurn}
              isTrapStage={hud.isTrapStage}
              onEndTurn={() => client.connection?.endTurn()}
              onSurrender={() => setSurrendering(true)}
            />

            <SpriteLayer client={client} sprites={sprites} />
            <ArrowLayer
              dragArrow={client.input.dragArrow}
              attackIndicators={client.render.attackIndicators}
              effects={client.render.animations.effects}
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
        </main>
      </div>
    </Starfield>
  );
}

/**
 * The page background: the board's own space art, dimmed behind a vignette.
 *
 * It sits outside the scaled stage so the artwork keeps its native aspect and
 * fills the window no matter what shape the board ends up.
 */
function Starfield({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative min-h-dvh w-full" style={{ backgroundColor: COLORS.void }}>
      <div
        className="pointer-events-none fixed inset-0"
        style={{
          backgroundImage: `url(${backgroundUrl()})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          opacity: 0.55,
        }}
      />
      <div
        className="pointer-events-none fixed inset-0"
        style={{
          background:
            "radial-gradient(ellipse at center, rgba(6,6,15,0.15) 0%, rgba(6,6,15,0.85) 100%)",
        }}
      />
      <div className="relative">{children}</div>
    </div>
  );
}

/** Connection status strip above the stage. */
function TopBar({
  status,
  error,
  onLeave,
}: {
  status: string;
  error: string | null;
  onLeave: () => void;
}) {
  return (
    <header className="flex shrink-0 items-center gap-3 px-5 py-3">
      <span
        className="leading-none"
        style={{
          fontFamily: PIXEL_FONT,
          fontSize: 13,
          letterSpacing: "0.18em",
          color: COLORS.gold,
          textShadow: TEXT_OUTLINE,
        }}
      >
        AUTOCARD
      </span>

      <span
        className="px-2 py-1.5 leading-none"
        style={{
          ...pixelWell(`${COLORS.edge}88`),
          fontFamily: PIXEL_FONT,
          fontSize: 9,
          letterSpacing: "0.1em",
          color: COLORS.textDim,
        }}
      >
        {status}
      </span>

      {error && (
        <span
          className="min-w-0 flex-1 truncate px-2 py-1.5 leading-none"
          style={{
            ...pixelWell("#c2455888"),
            fontFamily: PIXEL_FONT,
            fontSize: 9,
            color: "#ff9aa6",
          }}
        >
          {error}
        </span>
      )}

      <button
        type="button"
        onClick={onLeave}
        className="ml-auto h-[30px] px-4 leading-none transition-transform active:translate-x-[2px] active:translate-y-[2px]"
        style={{
          ...pixelButton("#2b2a4d", COLORS.edgeLit),
          fontFamily: PIXEL_FONT,
          fontSize: 10,
          letterSpacing: "0.14em",
        }}
      >
        LEAVE
      </button>
    </header>
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
    <div className="flex min-h-dvh w-full items-center justify-center p-6">
      <div className="w-full max-w-[440px] px-8 py-8" style={pixelPanel(COLORS.edge, 8)}>
        <h1
          className="leading-none"
          style={{
            fontFamily: PIXEL_FONT,
            fontSize: 26,
            letterSpacing: "0.1em",
            color: COLORS.gold,
            textShadow: TEXT_OUTLINE,
          }}
        >
          AUTOCARD
        </h1>
        <p
          className="mt-3 leading-relaxed"
          style={{
            fontFamily: PIXEL_FONT,
            fontSize: 9,
            color: COLORS.textDim,
          }}
        >
          Join a room on the game API. All rules run on the server.
        </p>

        <div className="mt-7 space-y-4">
          <Field label="Server URL">
            <TextInput
              value={serverUrl}
              onChange={onServerUrl}
              placeholder="http://localhost:8080"
            />
          </Field>

          <Field label="Room ID">
            <TextInput
              value={roomId}
              onChange={onRoomId}
              placeholder="e.g. ABC123"
            />
          </Field>

          <Field label="Display name">
            <TextInput value={playerName} onChange={onPlayerName} />
          </Field>

          <button
            type="button"
            onClick={onConnect}
            className="h-[46px] w-full leading-none transition-transform active:translate-x-[2px] active:translate-y-[2px]"
            style={{
              ...pixelButton("#2f6d43", "#7fe39b"),
              fontFamily: PIXEL_FONT,
              fontSize: 14,
              letterSpacing: "0.1em",
            }}
          >
            JOIN ROOM
          </button>
        </div>

        <div
          className="mt-7 pt-6"
          style={{ borderTop: `2px solid ${COLORS.edge}55` }}
        >
          <p
            className="leading-relaxed"
            style={{
              fontFamily: PIXEL_FONT,
              fontSize: 8,
              color: COLORS.textFaint,
            }}
          >
            No backend yet? Open a captured game state to inspect the board and
            the layout. Actions are recorded but not resolved.
          </p>
          <div className="mt-4 flex gap-3">
            <DemoButton label="DEMO · HOST" onClick={() => onDemo(0)} />
            <DemoButton label="DEMO · GUEST" onClick={() => onDemo(1)} />
          </div>
        </div>
      </div>
    </div>
  );
}

/** A pixel-framed text input. */
function TextInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <input
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      // The border comes from `pixelWell` as an inline style, which a Tailwind
      // focus variant cannot override, so focus is shown as an outline.
      className="w-full px-3 py-2.5 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-[#8f89e0]"
      style={{
        ...pixelWell(`${COLORS.edge}aa`),
        fontFamily: PIXEL_FONT,
        fontSize: 11,
        color: COLORS.text,
      }}
    />
  );
}

/** One of the two offline-demo entry points. */
function DemoButton({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="h-[34px] flex-1 leading-none transition-transform active:translate-x-[2px] active:translate-y-[2px]"
      style={{
        ...pixelButton("#2b2a4d", COLORS.edgeLit),
        fontFamily: PIXEL_FONT,
        fontSize: 9,
        letterSpacing: "0.1em",
      }}
    >
      {label}
    </button>
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
      <span
        className="mb-2 block leading-none"
        style={{
          fontFamily: PIXEL_FONT,
          fontSize: 8,
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: COLORS.textDim,
        }}
      >
        {label}
      </span>
      {children}
    </label>
  );
}
