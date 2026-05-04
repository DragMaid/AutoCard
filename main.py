import pygame
import socketio
import gunicorn.app.base
from abc import abstractmethod
from threading import Thread
from multiprocessing import Process, Queue
from ml.environment.environment import GameEnv
from ml.ai_opponent import AIOpponent, HumanVsAIManager
from ml.config import Config
from core.player import Player
from core.handle_game_logic.game_engine import GameEngine
from core.handle_logic_gui.input_manager import InputManager
from gui.gui_info.matrix_field import Matrix
from core.handle_logic_gui.render_engine import RenderEngine
from gui.effects.manager import EffectManager
from gui.cache import load_image
from abc import ABC


# NOTE: pygame code is not thread safe
class GameApp(ABC):
    def __init__(self):
        pygame.init()
        self.config = Config()
        self.screen_size = (1280, 720)
        self.screen = pygame.display.set_mode(self.screen_size)
        self.clock = pygame.time.Clock()
        self.running = True
        self.game_started = True
        self.dt = 0

        self.player1 = Player(0, 'p1')
        self.player2 = Player(1, 'p2', is_opponent=True)

        self.game_engine = GameEngine(
            [self.player1, self.player2], verbose=True, log_to_file=False)

        # TODO: remove this debug call
        self.game_engine.draw_specific_card(self.player1.id, "Maniac War", "spell")
        self.env = GameEnv(engine=self.game_engine, render=False)

        self.field_matrix = Matrix(self.screen, self.game_engine.game_state)
        self.render_engine = RenderEngine(
            self.field_matrix, self.screen, self.game_engine.game_state)
        self.input_manager = InputManager(
            self.field_matrix, self.game_engine, self.render_engine)

        self.background = load_image("assets/background.png")
        self.background = pygame.transform.scale(
            self.background, self.screen_size)

    def handle_events(self):
        current_player = self.game_engine.turn_manager.get_current_player()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

            self.input_manager.handle_event(event)

            if (event.type == pygame.KEYDOWN and
                event.key == pygame.K_SPACE and
                    not current_player.is_opponent):
                self.game_engine.end_turn()

    @abstractmethod
    def update(self):
        ...

    def draw(self):
        self.screen.blit(self.background, self.background.get_rect())
        self.field_matrix.areas["preview_card_table"].draw(self.screen)
        self.field_matrix.draw()
        self.input_manager.draw(self.screen)
        self.render_engine.draw()
        EffectManager.draw(self.screen)
        pygame.display.flip()

    def run(self, callback=None):
        while self.running:
            if callback:
                callback()
            if self.game_started:
                self.handle_events()
                self.update()
                self.draw()
                self.dt = self.clock.tick(60) / 1000
        pygame.quit()


class StandaloneApplication(gunicorn.app.base.BaseApplication):
    def __init__(self, app, options=None, on_worker_init=None):
        self.options = options or {}
        self.application = app
        self.on_worker_init = on_worker_init
        super().__init__()

    def load_config(self):
        for key, value in self.options.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        if self.on_worker_init:
            self.on_worker_init()
        return self.application


class AIGame(GameApp):
    def __init__(self):
        super().__init__()

        self.ai = AIOpponent(
            env=self.env,
            config=self.config,
            checkpoint_path=self.config.CHECKPOINT_PATH,
            agent_id=1,
            device=self.config.DEVICE
        )
        self.ai_manager = HumanVsAIManager(
            game_engine=self.game_engine,
            game_env=self.env,
            ai_opponent=self.ai,
            human_player_idx=0
        )

        self.ai_state = {"running": False}
        self.ai_thread = None

    def update(self):
        current_player = self.game_engine.turn_manager.get_current_player()

        if current_player == self.player2 and not self.ai_state["running"]:
            self.ai_state["running"] = True
            self.ai_thread = Thread(
                target=self.ai_manager.execute_ai_turn,
                kwargs={
                    "on_complete": lambda: self.ai_state.update({"running": False}),
                    "callback": lambda: self.render_engine.align_cards(self.field_matrix)
                }
            )
            self.ai_thread.start()

        self.render_engine.update(
            self.game_engine.game_state,
            self.field_matrix,
            self.game_engine.event_logger
        )
        self.render_engine.animation_mgr.update(self.dt)
        EffectManager.update()

        if self.game_engine.game_state.is_game_over():
            pygame.time.wait(1000)
            self.running = False


class SocketClientGame(GameApp):
    def __init__(self, host="localhost", port=5000):
        super().__init__()
        self.sio = socketio.Client()
        self.game_engine.socket_io = self.sio
        self.pending_data = None

        @self.sio.on("synchronize")
        def on_synchronize(data):
            print("Recieved new sync state")
            # Store data to be applied when animations are clear
            self.pending_data = data

        @self.sio.event
        def disconnect(sid):
            self.running = False

        try:
            self.sio.connect(f"http://{host}:{port}")
        except Exception as e:
            print(f"Connection failed: {e}")

    def update(self):
        # if self.pending_data and not self.render_engine.animation_mgr.is_running():
        if self.pending_data:
            self.game_engine.deserialize(self.pending_data)
            print("Pending data synchronized")

            self.field_matrix.set_game_state(
                self.game_engine.game_state, force=True)

            self.render_engine.align_cards(self.field_matrix)
            self.pending_data = None

        self.render_engine.update(
            self.game_engine.game_state,
            self.field_matrix,
            self.game_engine.event_logger
        )
        self.render_engine.animation_mgr.update(self.dt)
        EffectManager.update()

    def run(self):
        try:
            super().run()
        finally:
            self.sio.disconnect()


class SocketServerGame(GameApp):
    def __init__(self, host='localhost', port=5000):
        super().__init__()
        self.pending_data = None
        self.game_started = False

        self._sub_queue = Queue()
        self._out_queue = Queue()

        self.server_process = Process(
            target=self._run_server, args=(host, port))
        self.server_process.start()

    def _handle_sub_queue(self):
        while not self._sub_queue.empty():
            key, value = list(self._sub_queue.get().items())[0]
            if key == "connected":
                self.game_engine.start_game()
                self.game_started = True
                self.game_engine.synchronize = self.emit_synchronize
                self.game_engine.synchronize()
            elif key == "disconnected":
                self.running = False
                exit(0)
            elif key == "synchronize":
                print("Sync request processed")
                self.pending_data = value
            else:
                raise

    def _run_server(self, host, port):
        sio = socketio.Server(cors_allowed_origins='*', async_mode='threading')
        app = socketio.WSGIApp(sio)

        def start_bridge():
            bridge_thread = Thread(target=emit_bridge, daemon=True)
            bridge_thread.start()

        def emit_bridge():
            """Listens to the queue and emits to actual connected clients."""
            print("Bridge thread started in worker process")
            while True:
                try:
                    # This blocks until the main process sends data
                    item = self._out_queue.get()
                    print(f"Bridge received item from queue: {
                          item[0] if isinstance(item, tuple) else item}")
                    event, data = item
                    if event:
                        print(f"Bridge emitting event: {event}")
                        # Check connected clients
                        clients = list(
                            sio.manager.rooms['/'].keys()) if '/' in sio.manager.rooms else []
                        print(f"Connected clients in '/': {clients}")
                        sio.emit(event, data)
                        print(f"Bridge emit call finished for {event}")
                except Exception as e:
                    print(f"Bridge Error: {e}")
                    print(f"Sample row: {data}")

        @sio.on("synchronize")
        def on_synchronize(sid, data):
            print("Sync request recieved")
            self._sub_queue.put({"synchronize": data})

        @sio.event
        def connect(sid, environ, auth):
            print(f"SID {sid} jointed the game")
            self._sub_queue.put({"connected": {}})

        @sio.event
        def disconnect(sid, environ):
            self._sub_queue.put({"disconnected": {}})

        options = {
            'bind': f'{host}:{port}',
            'workers': 1,
            'threads': 4,
            'worker_class': 'sync',
        }
        StandaloneApplication(app, options, on_worker_init=start_bridge).run()

    def emit_synchronize(self):
        print("Synchronization signal sent")
        game_data = self.game_engine.serialize()
        self._out_queue.put(("synchronize", game_data))

    def run(self):
        super().run(callback=self._handle_sub_queue)

    def update(self):
        if self.pending_data:
            print("Sync successful")
            self.game_engine.deserialize(self.pending_data)
            self.field_matrix.set_game_state(
                self.game_engine.game_state, force=True)
            self.render_engine.align_cards(self.field_matrix)
            self.pending_data = None

        self.render_engine.update(
            self.game_engine.game_state,
            self.field_matrix,
            self.game_engine.event_logger
        )
        self.render_engine.animation_mgr.update(self.dt)
        EffectManager.update()


if __name__ == "__main__":
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("--client", action="store_true")
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--ai", action="store_true")
    args = parser.parse_args()

    app = None
    if args.client:
        app = SocketClientGame()

    if args.server:
        app = SocketServerGame()

    if args.ai:
        app = AIGame()

    app.run()
