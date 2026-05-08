from multiprocessing import Process, Queue
from core.network.discovery import DiscoveryServer
from gui.effects.manager import EffectManager
from .base import GameApp
from .utils import run_socketio_server


class SocketServerGame(GameApp):
    def __init__(self, screen, host="0.0.0.0", port=5000,
                 room_name="AutoCard Room", password=""):
        super().__init__(screen)

        self.game_started = False
        self.connected_clients = 0
        self._pending_data = None
        self._password = password

        self._sub_queue: Queue = Queue()   # server → main process
        self._out_queue: Queue = Queue()   # main process → server

        self._discovery = DiscoveryServer(
            port, room_name=room_name, password_protected=bool(password)
        )
        self._discovery.start()

        self._server_process = Process(
            target=run_socketio_server,
            args=(host, port, password, self._sub_queue, self._out_queue),
            daemon=True,
        )
        self._server_process.start()

    def update(self):
        self._drain_sub_queue()
        self._apply_pending_sync()
        self._tick_rendering()

    def _drain_sub_queue(self):
        while not self._sub_queue.empty():
            msg = self._sub_queue.get()
            key, value = next(iter(msg.items()))

            if key == "connected":
                # TODO: remove the debug function after
                from core.handle_game_logic.utils import draw_specific_card
                self.connected_clients += 1
                self.game_engine.start_game()

                # draw_specific_card(self.game_engine, self.player1.id, "Weaken Summon", "trap")
                draw_specific_card(self.game_engine, self.player1.id, "Crippling Curse", "trap")

                self.game_started = True
                self.game_engine.synchronize = self._emit_sync
                self.game_engine.synchronize()

            elif key == "disconnected":
                self.connected_clients -= 1
                if self.game_started and not self.game_over:
                    self.exit_reason = "Client disconnected"
                    self.running = False

            elif key == "synchronize":
                self._pending_data = value

    def _apply_pending_sync(self):
        if self._pending_data is None:
            return
        self.game_engine.deserialize(self._pending_data)
        self.field_matrix.set_game_state(
            self.game_engine.game_state, force=True)
        self.render_engine.align_cards(self.field_matrix)
        self._pending_data = None

    def _emit_sync(self):
        self._out_queue.put(("synchronize", self.game_engine.serialize()))

    def _tick_rendering(self):
        self.render_engine.update()
        self.render_engine.animation_mgr.update(self.dt)
        EffectManager.update()

    def cleanup(self):
        print("Stopping SocketServerGame…")
        try:
            self._discovery.stop()
        except Exception as e:
            print(f"Discovery stop error: {e}")
        try:
            self._server_process.terminate()
            self._server_process.join(timeout=2)
            if self._server_process.is_alive():
                print("Force-killing server process…")
                self._server_process.kill()
        except Exception as e:
            print(f"Server process stop error: {e}")
        self._out_queue.put(None)  # signal bridge thread to exit
