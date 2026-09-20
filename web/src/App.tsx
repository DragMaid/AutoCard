/**
 * Application shell.
 *
 * Owns the connection lifecycle — lobby, then a room — and wires stage pointer
 * events into the input manager. All gameplay decisions belong to the Python
 * engine; this component only sends intents and draws whatever the resulting
 * patches describe.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { backgroundUrl } from "./game/assets";
import { GameClient } from "./game/gameClient";
import { LAYOUT } from "./game/layout";
import { getCard } from "./game/state";
import {
  COLORS,
  DISPLAY_FONT,
  TEXT_OUTLINE,
  UI_FONT,
  pixelButton,
  pixelPanel,
  pixelWell,
} from "./game/theme";
import type { QueueStatus, RoomStatus } from "./net/actions";
import {
  SocketConnection,
  type ConnectionHandlers,
  type Entry,
  type GameConnection,
} from "./net/client";
import { Board } from "./render/Board";
import { GameOverOverlay, SurrenderOverlay, TrapStageOverlay } from "./render/Hud";
import { WaitingOverlay } from "./render/Waiting";
import { ArrowLayer, CardPreview } from "./render/Overlays";
import { ActionPanel, PlayerPanel } from "./render/Panels";
import { SpriteLayer } from "./render/SpriteLayer";
import { Stage, type StagePointer } from "./render/Stage";
import { useGameLoop } from "./render/useGameLoop";

type Screen = "lobby" | "game";

/** What the lobby is doing. `searching` means a socket is open and queued. */
type LobbyPhase = "idle" | "connecting" | "searching";

const DEFAULT_SERVER =
  (import.meta.env.VITE_GAME_API as string | undefined) ??
  "http://localhost:8080";

/** Room codes the relay generates are five characters of this alphabet. */
const CODE_PATTERN = /[^A-Za-z0-9_-]/g;

export default function App() {
  const client = useMemo(() => new GameClient(), []);
  const [screen, setScreen] = useState<Screen>("lobby");
  const [serverUrl, setServerUrl] = useState(DEFAULT_SERVER);
  const [roomCode, setRoomCode] = useState("");
  const [playerName, setPlayerName] = useState("player");
  const [status, setStatus] = useState<string>("idle");
  const [phase, setPhase] = useState<LobbyPhase>("idle");
  const [lobbyError, setLobbyError] = useState<string | null>(null);
  const [queue, setQueue] = useState<QueueStatus | null>(null);
  const [room, setRoom] = useState<RoomStatus | null>(null);
  const [surrendering, setSurrendering] = useState(false);
  const [dismissedGameOver, setDismissedGameOver] = useState(false);

  const connectionRef = useRef<GameConnection | null>(null);
  /** True once a seat has been assigned, so an error means entry failed. */
  const seatedRef = useRef(false);
  const { sprites, hud, error } = useGameLoop(client);

  /** Tears the socket down and returns to the lobby. */
  const leave = useCallback(() => {
    connectionRef.current?.disconnect();
    connectionRef.current = null;
    client.connection = null;
    client.reset();
    seatedRef.current = false;
    setScreen("lobby");
    setPhase("idle");
    setQueue(null);
    setRoom(null);
    setDismissedGameOver(false);
    setSurrendering(false);
  }, [client]);

  const handlers: ConnectionHandlers = useMemo(
    () => ({
      onAssign: (assignment) => {
        client.onAssign(assignment);
        seatedRef.current = true;
        setQueue(null);
        setLobbyError(null);
        setScreen("game");
      },
      onPatch: (patch) => client.onPatch(patch),
      onRoomStatus: (next) => setRoom(next),
      onQueued: (next) => setQueue(next),
      onStatus: (next, detail) =>
        setStatus(detail ? `${next}: ${detail}` : next),
      onError: (message) => {
        client.onError(message);
        setLobbyError(message);

        // An error before a seat arrives means entry failed — a full room, a
        // bad code, an engine that is down — so drop back rather than sit on a
        // socket that will never be dealt into a game.
        if (!seatedRef.current) {
          connectionRef.current?.disconnect();
          connectionRef.current = null;
          client.connection = null;
          setPhase("idle");
          setQueue(null);
        }
      },
    }),
    [client],
  );

  /** Opens a socket and asks the relay for a seat. */
  const enter = useCallback(
    (entry: Entry) => {
      connectionRef.current?.disconnect();
      client.reset();
      seatedRef.current = false;
      setLobbyError(null);
      setRoom(null);
      setPhase(entry.kind === "match" ? "searching" : "connecting");

      const connection = new SocketConnection(
        { url: serverUrl.trim(), entry, playerName: playerName.trim() || "player" },
        handlers,
      );
      connectionRef.current = connection;
      client.connection = connection;
      connection.connect();
    },
    [client, handlers, playerName, serverUrl],
  );

  /** Leaves the quick-match queue without leaving the lobby. */
  const cancelSearch = useCallback(() => {
    connectionRef.current?.cancelMatchmake();
    connectionRef.current?.disconnect();
    connectionRef.current = null;
    client.connection = null;
    setPhase("idle");
    setQueue(null);
  }, [client]);

  // A socket left open by a closing tab keeps its seat until the grace period
  // lapses, which would look to the opponent like a player who never left.
  useEffect(() => () => connectionRef.current?.disconnect(), []);

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
          roomCode={roomCode}
          playerName={playerName}
          phase={phase}
          queue={queue}
          error={lobbyError}
          onServerUrl={setServerUrl}
          onRoomCode={(value) =>
            setRoomCode(value.replace(CODE_PATTERN, "").toUpperCase().slice(0, 24))
          }
          onPlayerName={setPlayerName}
          onQuickMatch={() => enter({ kind: "match" })}
          onCreateRoom={() => enter({ kind: "create" })}
          onPlayAi={() => enter({ kind: "create", mode: "ai" })}
          onJoinRoom={() => enter({ kind: "join", roomId: roomCode.trim() })}
          onCancelSearch={cancelSearch}
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
        <TopBar
          status={status}
          roomId={room?.room_id ?? null}
          mode={room?.mode ?? null}
          error={error}
          onLeave={leave}
        />

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

            <WaitingOverlay
              visible={Boolean(room?.waiting) && !hud.gameOver}
              roomId={room?.room_id ?? ""}
              started={Boolean(room?.started)}
              onLeave={leave}
            />

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
  roomId,
  mode,
  error,
  onLeave,
}: {
  status: string;
  roomId: string | null;
  mode: string | null;
  error: string | null;
  onLeave: () => void;
}) {
  return (
    <header className="flex shrink-0 items-center gap-3 px-5 py-3">
      <span
        className="leading-none"
        style={{
          fontFamily: DISPLAY_FONT,
          fontSize: 13,
          letterSpacing: "0.04em",
          color: COLORS.gold,
          textShadow: TEXT_OUTLINE,
        }}
      >
        AUTOCARD
      </span>

      {roomId && (
        <span
          className="px-2.5 py-1.5 leading-none"
          style={{
            ...pixelWell(`${COLORS.gold}66`),
            fontFamily: UI_FONT,
            fontWeight: 700,
            fontSize: 12,
            letterSpacing: "0.2em",
            color: COLORS.gold,
          }}
        >
          {mode === "ai" ? "VS AI" : roomId}
        </span>
      )}

      <span
        className="px-2.5 py-1.5 leading-none"
        style={{
          ...pixelWell(`${COLORS.edge}88`),
          fontFamily: UI_FONT,
          fontWeight: 500,
          fontSize: 11,
          letterSpacing: "0.06em",
          color: COLORS.textDim,
        }}
      >
        {status}
      </span>

      {error && (
        <span
          className="min-w-0 flex-1 truncate px-2.5 py-1.5 leading-none"
          style={{
            ...pixelWell("#c2455888"),
            fontFamily: UI_FONT,
            fontWeight: 500,
            fontSize: 11,
            color: "#ff9aa6",
          }}
        >
          {error}
        </span>
      )}

      <button
        type="button"
        onClick={onLeave}
        className="ml-auto h-[32px] px-4 leading-none transition-transform active:translate-x-[2px] active:translate-y-[2px]"
        style={{
          ...pixelButton("#2b2a4d", COLORS.edgeLit),
          fontFamily: UI_FONT,
          fontWeight: 700,
          fontSize: 12,
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
  roomCode: string;
  playerName: string;
  phase: LobbyPhase;
  queue: QueueStatus | null;
  error: string | null;
  onServerUrl: (value: string) => void;
  onRoomCode: (value: string) => void;
  onPlayerName: (value: string) => void;
  onQuickMatch: () => void;
  onCreateRoom: () => void;
  onPlayAi: () => void;
  onJoinRoom: () => void;
  onCancelSearch: () => void;
}

/**
 * Entry screen.
 *
 * Four ways in, ordered by how little the player has to decide: be matched with
 * a stranger, open a room and share its code, join a code someone sent, or play
 * the trained agent. The server address is last because it only matters to
 * whoever is running the stack themselves.
 */
function Lobby({
  serverUrl,
  roomCode,
  playerName,
  phase,
  queue,
  error,
  onServerUrl,
  onRoomCode,
  onPlayerName,
  onQuickMatch,
  onCreateRoom,
  onPlayAi,
  onJoinRoom,
  onCancelSearch,
}: LobbyProps) {
  const busy = phase !== "idle";

  return (
    <div className="flex min-h-dvh w-full items-center justify-center p-6">
      <div className="w-full max-w-[460px] px-8 py-9" style={pixelPanel(COLORS.edge, 8)}>
        <h1
          className="leading-none"
          style={{
            fontFamily: DISPLAY_FONT,
            fontSize: 24,
            letterSpacing: "0.02em",
            color: COLORS.gold,
            textShadow: TEXT_OUTLINE,
          }}
        >
          AUTOCARD
        </h1>
        <p
          className="mt-4 leading-relaxed"
          style={{ fontFamily: UI_FONT, fontSize: 13, color: COLORS.textDim }}
        >
          Every rule runs on the server. Pick an opponent.
        </p>

        {error && (
          <div
            className="mt-5 px-3 py-2.5"
            style={{
              ...pixelWell("#c2455888"),
              fontFamily: UI_FONT,
              fontWeight: 500,
              fontSize: 12,
              color: "#ff9aa6",
            }}
          >
            {error}
          </div>
        )}

        <div className="mt-6">
          <Field label="Display name">
            <TextInput value={playerName} onChange={onPlayerName} disabled={busy} />
          </Field>
        </div>

        {phase === "searching" ? (
          <Searching queue={queue} onCancel={onCancelSearch} />
        ) : (
          <div className="mt-6 space-y-3">
            <BigButton
              label="QUICK MATCH"
              hint="Pair me with whoever is waiting"
              fill="#2f6d43"
              accent="#7fe39b"
              disabled={busy}
              onClick={onQuickMatch}
            />

            <div className="flex gap-3">
              <SmallButton
                label="CREATE ROOM"
                fill="#2b2a4d"
                accent={COLORS.edgeLit}
                disabled={busy}
                onClick={onCreateRoom}
              />
              <SmallButton
                label="PLAY VS AI"
                fill="#4a2f6d"
                accent="#b98fe3"
                disabled={busy}
                onClick={onPlayAi}
              />
            </div>

            <Divider label="or join a code" />

            <div className="flex gap-3">
              <div className="min-w-0 flex-1">
                <TextInput
                  value={roomCode}
                  onChange={onRoomCode}
                  onEnter={roomCode.trim() ? onJoinRoom : undefined}
                  placeholder="ABC12"
                  disabled={busy}
                  centered
                />
              </div>
              <button
                type="button"
                onClick={onJoinRoom}
                disabled={busy || !roomCode.trim()}
                className="h-[42px] w-[110px] shrink-0 leading-none transition-transform active:translate-x-[2px] active:translate-y-[2px]"
                style={{
                  ...pixelButton("#2b2a4d", COLORS.edgeLit, !busy && Boolean(roomCode.trim())),
                  fontFamily: UI_FONT,
                  fontWeight: 700,
                  fontSize: 13,
                  letterSpacing: "0.14em",
                }}
              >
                JOIN
              </button>
            </div>
          </div>
        )}

        <details className="mt-7 pt-6" style={{ borderTop: `2px solid ${COLORS.edge}55` }}>
          <summary
            className="cursor-pointer select-none leading-none"
            style={{
              fontFamily: UI_FONT,
              fontWeight: 600,
              fontSize: 11,
              letterSpacing: "0.16em",
              textTransform: "uppercase",
              color: COLORS.textFaint,
            }}
          >
            Server
          </summary>
          <div className="mt-4">
            <TextInput
              value={serverUrl}
              onChange={onServerUrl}
              placeholder="http://localhost:8080"
              disabled={busy}
            />
          </div>
        </details>
      </div>
    </div>
  );
}

/** The quick-match waiting state, shown in place of the entry buttons. */
function Searching({
  queue,
  onCancel,
}: {
  queue: QueueStatus | null;
  onCancel: () => void;
}) {
  return (
    <div className="mt-6 space-y-3">
      <div
        className="flex flex-col items-center gap-2 px-4 py-7"
        style={pixelWell(`${COLORS.edge}aa`)}
      >
        <span
          className="leading-none"
          style={{
            fontFamily: UI_FONT,
            fontWeight: 700,
            fontSize: 17,
            letterSpacing: "0.2em",
            color: COLORS.gold,
          }}
        >
          SEARCHING
          <Ellipsis />
        </span>
        <span
          className="leading-none"
          style={{ fontFamily: UI_FONT, fontSize: 12, color: COLORS.textDim }}
        >
          {queue
            ? `Position ${queue.position} of ${queue.size} waiting`
            : "Joining the queue"}
        </span>
      </div>

      {/* SmallButton grows to fill a row, so it needs one even when alone. */}
      <div className="flex">
        <SmallButton
          label="CANCEL"
          fill="#3a2030"
          accent={COLORS.danger}
          disabled={false}
          onClick={onCancel}
        />
      </div>
    </div>
  );
}

/**
 * Three dots that cycle.
 *
 * Rendered as text rather than a spinner so it inherits the surrounding type
 * and never drifts out of the pixel grid the rest of the chrome sits on.
 */
function Ellipsis() {
  const [count, setCount] = useState(1);

  useEffect(() => {
    const id = setInterval(() => setCount((value) => (value % 3) + 1), 420);
    return () => clearInterval(id);
  }, []);

  // A fixed-width span keeps the label from shifting as the dots change.
  return <span style={{ display: "inline-block", width: "1.6em", textAlign: "left" }}>
    {".".repeat(count)}
  </span>;
}

/** The primary call to action. */
function BigButton({
  label,
  hint,
  fill,
  accent,
  disabled,
  onClick,
}: {
  label: string;
  hint: string;
  fill: string;
  accent: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="w-full px-5 py-4 text-left transition-transform active:translate-x-[2px] active:translate-y-[2px]"
      style={pixelButton(fill, accent, !disabled)}
    >
      <span
        className="block leading-none"
        style={{
          fontFamily: UI_FONT,
          fontWeight: 700,
          fontSize: 17,
          letterSpacing: "0.14em",
        }}
      >
        {label}
      </span>
      <span
        className="mt-2 block leading-none"
        style={{
          fontFamily: UI_FONT,
          fontSize: 12,
          color: disabled ? COLORS.textFaint : "rgba(232, 229, 255, 0.72)",
        }}
      >
        {hint}
      </span>
    </button>
  );
}

/** A secondary action sitting in a row. */
function SmallButton({
  label,
  fill,
  accent,
  disabled,
  onClick,
}: {
  label: string;
  fill: string;
  accent: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="h-[42px] flex-1 leading-none transition-transform active:translate-x-[2px] active:translate-y-[2px]"
      style={{
        ...pixelButton(fill, accent, !disabled),
        fontFamily: UI_FONT,
        fontWeight: 700,
        fontSize: 13,
        letterSpacing: "0.14em",
      }}
    >
      {label}
    </button>
  );
}

/** A labelled rule between two groups of controls. */
function Divider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 pt-2">
      <span className="h-[2px] flex-1" style={{ backgroundColor: `${COLORS.edge}55` }} />
      <span
        className="leading-none"
        style={{
          fontFamily: UI_FONT,
          fontWeight: 600,
          fontSize: 11,
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: COLORS.textFaint,
        }}
      >
        {label}
      </span>
      <span className="h-[2px] flex-1" style={{ backgroundColor: `${COLORS.edge}55` }} />
    </div>
  );
}

/** A framed text input. */
function TextInput({
  value,
  onChange,
  onEnter,
  placeholder,
  disabled,
  centered,
}: {
  value: string;
  onChange: (value: string) => void;
  onEnter?: () => void;
  placeholder?: string;
  disabled?: boolean;
  centered?: boolean;
}) {
  return (
    <input
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === "Enter" && onEnter) onEnter();
      }}
      placeholder={placeholder}
      disabled={disabled}
      // The border comes from `pixelWell` as an inline style, which a Tailwind
      // focus variant cannot override, so focus is shown as an outline.
      className="h-[42px] w-full px-3 outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-[#8f89e0] disabled:opacity-50"
      style={{
        ...pixelWell(`${COLORS.edge}aa`),
        fontFamily: UI_FONT,
        fontWeight: centered ? 700 : 500,
        fontSize: centered ? 17 : 14,
        letterSpacing: centered ? "0.3em" : "0.02em",
        textAlign: centered ? "center" : "left",
        color: COLORS.text,
      }}
    />
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
          fontFamily: UI_FONT,
          fontWeight: 600,
          fontSize: 11,
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
