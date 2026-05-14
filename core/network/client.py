import time
import urllib.parse
import socketio
from threading import Thread
from typing import Optional, Any
from gui.effects.manager import EffectManager
from .base import GameApp
from .utils import resolve_to_localhost_if_self


class SocketClientGame(GameApp):
    """
    Game mode for client-side socket connections.

    Attributes:
        game_started (bool): Whether the game has started.
        connected (bool): Whether the client is connected.
        connection_error (Optional[str]): Connection error message, if any.
    """

    def __init__(self, screen, host: str = "localhost", port: int = 5555, password: str = "") -> None:
        """
        Initializes SocketClientGame.

        Args:
            screen: The pygame screen surface.
            host (str): Server host address.
            port (int): Server port.
            password (str): Optional connection password.
        """
        super().__init__(screen)

        self.game_started: bool = False
        self.connected: bool = False
        self.connection_error: Optional[str] = None
        self._pending_data: Optional[dict] = None

        self._sio: socketio.Client = socketio.Client(
            logger=False, engineio_logger=False, reconnection=False
        )
        self.game_engine.socket_io = self._sio
        self._register_socket_events()

        connect_thread: Thread = Thread(
            target=self._connect, args=(host, port, password), daemon=True
        )
        connect_thread.start()

    def _register_socket_events(self) -> None:
        """Registers event handlers for socket connection."""
        @self._sio.on("synchronize")
        def on_synchronize(data: dict) -> None:
            self._pending_data = data
            self.game_started = True

        @self._sio.event
        def connect() -> None:
            print("[Client] Connected to server")
            self.connected = True

        @self._sio.on("connect_error")
        def on_connect_error(data: Any) -> None:
            print(f"[Client] Connection error: {data}")
            self.connection_error = str(data)

        @self._sio.event
        def disconnect() -> None:
            print("[Client] Disconnected from server")
            if not self.game_over:
                self.exit_reason = "Disconnected from server"
                self.running = False

    def _connect(self, host: str, port: int, password: str) -> None:
        """Connects to the server."""
        time.sleep(0.5)  # brief delay so a freshly-started server is ready
        host = resolve_to_localhost_if_self(host)
        url: str = f"http://{host}:{port}"
        if password:
            url += f"?password={urllib.parse.quote(password)}"
        try:
            self._sio.connect(url, wait_timeout=10)
        except Exception as e:
            self.connection_error = str(e)

    def update(self) -> None:
        """Updates game state."""
        self._apply_pending_sync()
        self._tick_rendering()

    def _apply_pending_sync(self) -> None:
        """Applies pending game state synchronization."""
        if self._pending_data is None:
            return
        self.game_engine.deserialize(self._pending_data)

        # Fix perspective: client is index 1, server is index 0
        for player in self.game_engine.game_state.players:
            player.is_opponent = (player.player_index == 0)

        # Update all cards to match the new perspective
        for card in self.game_engine.game_state.entity_lookup.values():
            owner = self.game_engine.game_state.players_lookup.get(card.owner_id)
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
        try:
            self._sio.disconnect()
        except Exception:
            raise
