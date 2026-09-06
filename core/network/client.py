import pygame
import time
import urllib.parse
import socketio
from threading import Thread
from typing import Optional, Any
from gui.effects.manager import EffectManager
from core.config import Config
from core.logic.game_engine import EngineMode
from core.network.actions import Patch
from core.network.patch import PatchApplier
from core.network.transport import (
    EVENT_ASSIGN, EVENT_PATCH, SocketIntentTransport,
)
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

    def __init__(
        self,
        screen: pygame.Surface,
        host: str = Config.DEFAULT_HOST,
        port: int = Config.DEFAULT_PORT,
        password: str = "",
        room_id: str = "local"
    ) -> None:
        """
        Initializes SocketClientGame.

        Args:
            screen: The pygame screen surface.
            host (str): Server host address.
            port (int): Server port.
            password (str): Optional connection password.
            room_id (str): Room to join on the server or relay.
        """
        self._sio: socketio.Client = socketio.Client(
            logger=False, engineio_logger=False, reconnection=False
        )
        self._transport: SocketIntentTransport = SocketIntentTransport(self._sio)
        self.room_id: str = room_id

        super().__init__(screen)

        self.game_started: bool = False
        self.connected: bool = False
        self.connection_error: Optional[str] = None
        self._pending_patches: list[Patch] = []
        self._applier: Optional[PatchApplier] = None
        self._needs_rebuild: bool = False

        self._register_socket_events()

        connect_thread: Thread = Thread(
            target=self._connect, args=(host, port, password), daemon=True
        )
        connect_thread.start()

    def _engine_kwargs(self) -> dict:
        """Runs this engine as a remote client that forwards intents."""
        return {
            "transport": self._transport,
            "mode": EngineMode.REMOTE,
            "room_id": self.room_id,
        }

    def _register_socket_events(self) -> None:
        """Registers event handlers for socket connection."""
        @self._sio.on(EVENT_ASSIGN)
        def on_assign(data: dict) -> None:
            """Records which seat this client plays and how to orient the board."""
            player_id = data.get("player_id")
            self.room_id = data.get("room_id", self.room_id)
            self.game_engine.room_id = self.room_id
            self.game_engine.local_player_id = player_id
            # The guest sits opposite the host, so its board is mirrored: it
            # renders flipped and converts outgoing cells back to server frame.
            self.game_engine.flip = bool(data.get("player_index", 1))
            self._applier = PatchApplier(
                self.game_engine,
                local_player_id=player_id,
                flip=bool(data.get("player_index", 1)),
            )

        @self._sio.on(EVENT_PATCH)
        def on_patch(data: dict) -> None:
            try:
                self._pending_patches.append(Patch.model_validate(data))
            except Exception as e:
                print(f"[Client] Dropped malformed patch: {e}")
                return
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
        self._apply_pending_patches()
        self._tick_rendering()

    def _apply_pending_patches(self) -> None:
        """Applies every patch received since the last frame.

        A full sync replaces the player objects and card collections wholesale,
        so the board layout is rebuilt afterwards to re-bind the hand areas.
        Incremental patches mutate the existing collections in place and only
        need a re-align.
        """
        if not self._pending_patches or self._applier is None:
            return

        for patch in self._pending_patches:
            if any(op.op.value == "FULL_SYNC" for op in patch.ops):
                self._needs_rebuild = True
            self._applier.apply(patch)
        self._pending_patches.clear()

        if self._needs_rebuild:
            self.matrix.set_game_state(self.game_engine.game_state, force=True)
            self._needs_rebuild = False

        self.render_engine.align_cards(self.matrix)

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
