import time
import urllib.parse
import socketio
from threading import Thread
from gui.effects.manager import EffectManager
from .base import GameApp
from .utils import resolve_to_localhost_if_self


class SocketClientGame(GameApp):
    def __init__(self, screen, host="localhost", port=5555, password=""):
        super().__init__(screen)

        self.game_started = False
        self.connected = False
        self.connection_error = None
        self._pending_data = None

        self._sio = socketio.Client(
            logger=False, engineio_logger=False, reconnection=False
        )
        self.game_engine.socket_io = self._sio
        self._register_socket_events()

        connect_thread = Thread(
            target=self._connect, args=(host, port, password), daemon=True
        )
        connect_thread.start()

    def _register_socket_events(self):
        @self._sio.on("synchronize")
        def on_synchronize(data):
            self._pending_data = data
            self.game_started = True

        @self._sio.event
        def connect():
            print("[Client] Connected to server")
            self.connected = True

        @self._sio.on("connect_error")
        def on_connect_error(data):
            print(f"[Client] Connection error: {data}")
            self.connection_error = str(data)

        @self._sio.event
        def disconnect():
            print("[Client] Disconnected from server")
            if not self.game_over:
                self.exit_reason = "Disconnected from server"
                self.running = False

    def _connect(self, host: str, port: int, password: str):
        time.sleep(0.5)  # brief delay so a freshly-started server is ready
        host = resolve_to_localhost_if_self(host)
        url = f"http://{host}:{port}"
        if password:
            url += f"?password={urllib.parse.quote(password)}"
        try:
            self._sio.connect(url, wait_timeout=10)
        except Exception as e:
            self.connection_error = str(e)

    def update(self):
        self._apply_pending_sync()
        self._tick_rendering()

    def _apply_pending_sync(self):
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

    def _tick_rendering(self):
        self.render_engine.update()
        self.render_engine.animation_mgr.update(self.dt)
        EffectManager.update()

    def cleanup(self):
        try:
            self._sio.disconnect()
        except Exception:
            raise
