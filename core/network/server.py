import logging
from multiprocessing import Process, Queue
from typing import Optional
from core.network.discovery import DiscoveryServer
from gui.effects.manager import EffectManager
from .base import GameApp
from .utils import run_socketio_server

logger = logging.getLogger(__name__)


class SocketIOWrapper:
    """
    Bridges the GameEngine's socket_io interface to the server's output queue.
    """

    def __init__(self, out_queue: Queue) -> None:
        self.out_queue: Queue = out_queue

    def emit(self, event: str, data: dict) -> None:
        """Emits an event to the client."""
        self.out_queue.put((event, data))


class SocketServerGame(GameApp):
    """
    Game mode for server-side socket hosting.

    Attributes:
        game_started (bool): Whether the game has started.
        connected_clients (int): Number of connected clients.
    """

    def __init__(self, screen, host: str = "0.0.0.0", port: int = 5555,
                 room_name: str = "AutoCard Room", password: str = "") -> None:
        """
        Initializes SocketServerGame.

        Args:
            screen: The pygame screen surface.
            host (str): Server host address.
            port (int): Server port.
            room_name (str): Name of the room.
            password (str): Optional connection password.
        """
        super().__init__(screen)

        self.game_started: bool = False
        self.connected_clients: int = 0
        self._pending_data: Optional[dict] = None
        self._password: str = password

        self._sub_queue: Queue = Queue()   # server → main process
        self._out_queue: Queue = Queue()   # main process → server

        self.game_engine.socket_io = SocketIOWrapper(self._out_queue)

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

    def update(self) -> None:
        """Updates game state."""
        self.drain_sub_queue()
        self._apply_pending_sync()
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

            elif key == "disconnected":
                print(f"[Server Main] Client disconnected. Total: {
                      self.connected_clients - 1}")
                self.connected_clients -= 1
                if self.game_started and not self.game_over:
                    self.exit_reason = "Client disconnected"
                    self.running = False

            elif key == "synchronize":
                self._pending_data = value

    def _apply_pending_sync(self) -> None:
        """Applies pending game state synchronization."""
        if self._pending_data is None:
            return
        self.game_engine.deserialize(self._pending_data)

        # Ensure server perspective: server is index 0, client is index 1
        for player in self.game_engine.game_state.players:
            player.is_opponent = (player.player_index == 1)

        # Update all cards to match the perspective
        for card in self.game_engine.game_state.entity_lookup.values():
            owner = self.game_engine.game_state.players_lookup.get(
                card.owner_id)
            if owner:
                card.is_opponent = owner.is_opponent

        self.matrix.set_game_state(
            self.game_engine.game_state, force=True)
        self.render_engine.align_cards(self.matrix)
        self._pending_data = None

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
