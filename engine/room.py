"""One authoritative match: an engine, a mailbox, and an optional AI seat."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from core.data.player import Player
from core.logic.game_engine import EngineMode, GameEngine
from core.network.actions import Intent, IntentType, OpType, Patch, PatchOp
from core.network.patch import diff_state, snapshot
from engine import visibility
from engine.ai import AiDriver
from engine.config import EngineConfig
from engine.transport import AsyncQueueTransport
from ml.environment.environment import GameEnv

logger = logging.getLogger(__name__)

MODE_PVP = "pvp"
MODE_AI = "ai"

#: Intent types that are routine traffic rather than a refused player action.
_QUIET_INTENTS = frozenset({IntentType.REQUEST_SYNC, IntentType.START_GAME})


class Room:
    """A single match, driven by one task so the engine is never re-entered.

    ``GameEngine`` is not thread-safe and not re-entrant, so every intent for a
    room — including the AI's — is funnelled through :attr:`inbox` and applied by
    one worker. That is the whole concurrency design, and it is why the relay may
    forward messages from two sockets without coordinating.

    Attributes:
        room_id: Identifier stamped on every intent and patch.
        mode: Either ``pvp`` or ``ai``.
        engine: The authoritative engine.
        players: Seats in canonical order; index 0 is the canonical board frame.
        ai_seats: Seat indices the agent plays, which no client may claim.
    """

    def __init__(
        self,
        room_id: str,
        mode: str,
        loop: asyncio.AbstractEventLoop,
        config: type[EngineConfig] = EngineConfig,
    ) -> None:
        """Builds a room and starts its worker.

        Args:
            room_id (str): Room identifier shared with the relay.
            mode (str): ``pvp`` for two humans, ``ai`` for one human and the agent.
            loop: Loop the room runs on.
            config: Engine settings, overridable in tests.
        """
        self.room_id = room_id
        self.mode = MODE_AI if mode == MODE_AI else MODE_PVP
        self._config = config
        self._loop = loop

        host = Player(player_index=0, name="host")
        guest = Player(
            player_index=1,
            name="ai" if self.mode == MODE_AI else "guest",
            is_opponent=True,
        )
        self.players: list[Player] = [host, guest]

        self._outbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        # The board as each seat last saw it, which is what that seat's next
        # patch is diffed against. Empty until the first patch is sent.
        self._views: dict[str, dict[str, Any]] = {}

        # Declared before the engine exists: the engine is handed this room's
        # fanout, and the fanout asks which seats are the AI's.
        self.ai_seats: list[int] = [guest.player_index] if self.mode == MODE_AI else []

        self.engine = GameEngine(
            self.players,
            transport=AsyncQueueTransport(self._outbox, loop, self._fanout),
            mode=EngineMode.AUTHORITATIVE,
            room_id=room_id,
            # Anchors the authoritative engine in the host's frame, which is the
            # canonical frame every client mirrors from.
            local_player_id=host.id,
        )
        self.env = GameEnv(engine=self.engine, render=False)

        self._ai: Optional[AiDriver] = None
        if self.mode == MODE_AI:
            self._ai = AiDriver(self.engine, self.env, guest, config)

        self.socket: Any = None
        self.vacated_at: Optional[float] = time.monotonic()
        self.closed = False

        self._worker = loop.create_task(self._run(), name=f"room:{room_id}")
        self._pump = loop.create_task(self._pump_outbox(), name=f"pump:{room_id}")

    # ------------------------------------------------------------------
    # Relay handshake
    # ------------------------------------------------------------------

    def describe(self) -> dict[str, Any]:
        """Builds the ``room_ready`` message the relay needs to seat clients.

        Returns:
            dict: Room id, player ids by seat, AI seats, and the resolved mode.
        """
        return {
            "type": "room_ready",
            "room_id": self.room_id,
            "player_ids": [player.id for player in self.players],
            "ai_seats": list(self.ai_seats),
            "mode": self.mode,
        }

    def attach(self, socket: Any) -> None:
        """Binds the room to a relay socket.

        Args:
            socket: The aiohttp WebSocket response carrying this room's traffic.
        """
        self.socket = socket
        self.vacated_at = None

    def detach(self, socket: Any) -> None:
        """Unbinds a relay socket, starting the room's idle countdown.

        Args:
            socket: The socket that closed. Ignored if a newer one took over.
        """
        if self.socket is socket:
            self.socket = None
            self.vacated_at = time.monotonic()

    @property
    def is_expired(self) -> bool:
        """True once no relay has been attached for longer than the TTL."""
        return (
            self.vacated_at is not None
            and time.monotonic() - self.vacated_at > self._config.ROOM_TTL
        )

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    def submit(self, raw: dict[str, Any]) -> None:
        """Queues one relay message for this room's worker.

        Args:
            raw (dict): The decoded envelope from the relay.
        """
        if not self.closed:
            self.inbox.put_nowait(raw)

    async def _run(self) -> None:
        """Applies queued intents one at a time, then lets the AI respond."""
        try:
            while not self.closed:
                message = await self.inbox.get()
                try:
                    await self._handle(message)
                except Exception:
                    logger.exception("Room %s failed on %s",
                                     self.room_id, message.get("type"))
                finally:
                    # Marks the item done even when handling raised, so anything
                    # waiting on the mailbox to drain cannot hang on a failure.
                    self.inbox.task_done()
        except asyncio.CancelledError:
            raise

    async def _handle(self, message: dict[str, Any]) -> None:
        """Dispatches one relay message.

        Args:
            message (dict): An envelope with a ``type`` field.
        """
        if message.get("type") != "intent":
            return

        raw = message.get("intent") or {}
        try:
            intent = Intent.model_validate(raw)
        except Exception as exc:
            logger.warning("Room %s rejected a malformed intent: %s",
                           self.room_id, exc)
            return

        if intent.room_id and intent.room_id != self.room_id:
            logger.warning("Room %s ignoring intent for %s",
                           self.room_id, intent.room_id)
            return

        # The relay already bound actor_id to the socket's seat; the engine
        # re-validates it anyway, because the relay is defence in depth.
        accepted = self.engine.dispatch(intent)
        if not accepted and intent.type not in _QUIET_INTENTS:
            await self._send({
                "type": "rejected",
                "room_id": self.room_id,
                "actor_id": intent.actor_id,
                "intent_type": intent.type.value,
                "reason": f"{intent.type.value} is not allowed right now",
            })

        await self._play_ai()

    async def _play_ai(self) -> None:
        """Lets the agent act if the turn has become its own."""
        if self._ai is None or not self._ai.is_turn:
            return
        await self._ai.play_turn()

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    @property
    def viewers(self) -> list[Player]:
        """Seats that receive patches: everyone the AI is not playing."""
        return [player for player in self.players
                if player.player_index not in self.ai_seats]

    def _fanout(self, patch: Patch) -> list[dict[str, Any]]:
        """Rewrites one engine patch as a private patch per seat.

        Each seat is diffed against the redacted board it was last shown, so a
        card only reaches it once the rules say that seat may see it, and a card
        that is revealed produces the update that reveals it. The engine's own
        ops are used only to tell a full sync from a delta — never forwarded,
        because they describe the whole board.

        Args:
            patch (Patch): The delta the engine just produced.

        Returns:
            list: One ``{"player_id", "patch"}`` envelope per seat with something
            to say.
        """
        board = snapshot(self.engine)
        resync = any(op.op is OpType.FULL_SYNC for op in patch.ops)
        envelopes: list[dict[str, Any]] = []

        for player in self.viewers:
            view = visibility.redact_snapshot(board, player.id)
            seen = self._views.get(player.id)
            self._views[player.id] = view

            if resync or seen is None:
                # A seat with no history has nothing to diff against: the relay
                # asks for a sync whenever someone sits down, and that is the
                # patch that builds their board from nothing.
                ops = [PatchOp(op=OpType.FULL_SYNC, value=visibility.redact_engine(
                    self.engine.serialize(), player.id))]
            else:
                ops = visibility.repair_reveals(
                    diff_state(seen, view), view["game_state"])

            events = visibility.visible_events(
                patch.events, board["game_state"], player.id)
            if not ops and not events:
                continue

            envelopes.append({
                "player_id": player.id,
                "patch": Patch(
                    room_id=self.room_id,
                    seq=patch.seq,
                    cause=patch.cause,
                    ops=ops,
                    events=events,
                ).model_dump(mode="json"),
            })

        return envelopes

    async def _pump_outbox(self) -> None:
        """Forwards queued patches to the attached relay socket."""
        while not self.closed:
            envelope = await self._outbox.get()
            await self._send({
                "type": "patch",
                "room_id": self.room_id,
                "player_id": envelope.get("player_id"),
                "patch": envelope["patch"],
            })

    async def _send(self, payload: dict[str, Any]) -> None:
        """Writes one message to the relay, dropping it when none is attached.

        A detached room is one whose relay restarted. Its clients will re-join
        and issue ``REQUEST_SYNC``, so a stale backlog would only be noise.

        Args:
            payload (dict): The envelope to write.
        """
        socket = self.socket
        if socket is None or socket.closed:
            return
        try:
            await socket.send_json(payload)
        except (ConnectionResetError, RuntimeError):
            logger.debug("Room %s lost its relay mid-send", self.room_id)
            self.detach(socket)

    async def close(self) -> None:
        """Stops the room's tasks and releases its engine."""
        if self.closed:
            return
        self.closed = True

        for task in (self._worker, self._pump):
            task.cancel()

        await asyncio.gather(self._worker, self._pump, return_exceptions=True)
        logger.info("Room %s closed", self.room_id)
