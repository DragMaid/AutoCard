import pygame
import logging
from multiprocessing import Process, Queue
from typing import Optional
from core.network.discovery import DiscoveryServer
from core.network.actions import Intent
from core.network.transport import QueueTransport
from core.logic.game_engine import EngineMode
from gui.effects.manager import EffectManager
from core.config import Config
from .base import GameApp
from .utils import run_socketio_server

logger = logging.getLogger(__name__)


class SocketServerGame(GameApp):
    """
    Game mode for server-side socket hosting.

    Attributes:
        game_started (bool): Whether the game has started.
        connected_clients (int): Number of connected clients.
    """

    def __init__(
        self,
        screen: pygame.Surface,
        host: str = Config.DEFAULT_HOST,
        port: int = Config.DEFAULT_PORT,
        room_name: str = "AutoCard Room",
        password: str = "",
        room_id: str = "local"
    ) -> None:
        """
        Initializes SocketServerGame.

        Args:
            screen: The pygame screen surface.
            host (str): Server host address.
            port (int): Server port.
            room_name (str): Human-readable name advertised by discovery.
            password (str): Optional connection password.
            room_id (str): Identifier stamped on every intent and patch. A
                direct LAN host only serves one room, but a public relay uses
                this to fan messages out to the right match.
        """
        self._sub_queue: Queue = Queue()   # server → main process
        self._out_queue: Queue = Queue()   # main process → server
        self._transport: QueueTransport = QueueTransport(self._out_queue)
        self.room_id: str = room_id

        super().__init__(screen)

        self.game_started: bool = False
        self.connected_clients: int = 0
        self._password: str = password

        self._discovery: DiscoveryServer = DiscoveryServer(
            port, room_name=room_name, password_protected=bool(password)
        )
        self._discovery.start()

        self._server_process: Process = Process(
            target=run_socketio_server,
            args=(host, port, password, self._sub_queue, self._out_queue),
            daemon=True,
        )
        self._server_process.start()

    def _engine_kwargs(self) -> dict:
        """Runs this engine as the room's source of truth."""
        return {
            "transport": self._transport,
            "mode": EngineMode.AUTHORITATIVE,
            "room_id": self.room_id,
            "local_player_id": self.player1.id,
        }

    def update(self) -> None:
        """Updates game state."""
        self.drain_sub_queue()
        self._tick_rendering()

    def drain_sub_queue(self) -> None:
        """Drains the sub queue for messages from the server process."""
        while not self._sub_queue.empty():
            msg = self._sub_queue.get()
            key, value = next(iter(msg.items()))

            if key == "connected":
                print(f"[Server Main] Client connected. Total: {
                      self.connected_clients + 1}")
                self.connected_clients += 1
                self.game_engine.start_game()
                from core.logic.utils import draw_specific_card
                from core.cards.card import CardType
                draw_specific_card(
                    self.game_engine, self.player1.id, "Mirror Strike", CardType.TRAP)
                self.game_started = True

                # Tell the guest which seat it holds, then hand it the board.
                self._transport.send_assignment({
                    "room_id": self.room_id,
                    "player_id": self.player2.id,
                    "player_index": self.player2.player_index,
                    "opponent_id": self.player1.id,
                })
                self.game_engine.send_full_sync()

            elif key == "disconnected":
                print(f"[Server Main] Client disconnected. Total: {
                      self.connected_clients - 1}")
                self.connected_clients -= 1
                if self.game_started and not self.game_over:
                    self.exit_reason = "Client disconnected"
                    self.running = False

            elif key == "intent":
                self._dispatch_intent(value)

    def _dispatch_intent(self, data: dict) -> None:
        """Validates and applies one client intent on the authoritative engine.

        Applying the intent emits a patch through the transport automatically,
        so there is nothing to broadcast here.

        Args:
            data (dict): A serialized :class:`~core.network.actions.Intent`.
        """
        try:
            intent = Intent.model_validate(data)
        except Exception as e:
            logger.error(f"Rejected malformed intent: {e}")
            return

        if intent.room_id and intent.room_id != self.room_id:
            logger.warning(
                f"Ignoring intent for room {intent.room_id}")
            return

        if not self.game_engine.dispatch(intent):
            logger.info(f"Intent {intent.type} rejected")

        self.render_engine.align_cards(self.matrix)

    def _tick_rendering(self) -> None:
        """Updates rendering systems."""
        self.render_engine.update()
        self.render_engine.animation_mgr.update(self.dt)
        EffectManager.update()

    def cleanup(self) -> None:
        """Cleans up resources."""
        logger.info("Stopping SocketServerGame…")
        try:
            self._discovery.stop()
        except Exception as e:
            logger.error(f"Discovery stop error: {e}")
        try:
            self._server_process.terminate()
            self._server_process.join(timeout=2)
            if self._server_process.is_alive():
                logger.info("Force-killing server process…")
                self._server_process.kill()
        except Exception as e:
            logger.error(f"Server process stop error: {e}")
        self._out_queue.put(None)  # signal bridge thread to exit
