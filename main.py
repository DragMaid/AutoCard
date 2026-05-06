import pygame
import socketio
import socket
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
from gui.cache import load_image, get_font
from abc import ABC
from gui.matchmaking import MatchmakingScreen, ScreenState
from gui.ui_components import Button


class GameApp(ABC):
    def __init__(self, screen):
        self.config = Config()
        self.screen_size = (1280, 720)
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.running = True
        self.game_started = True
        self.dt = 0
        self.should_exit_to_menu = False
        self.exit_reason = None
        self.game_over = False
        self.winner_text = ""

        self.player1 = Player(0, 'p1')
        self.player2 = Player(1, 'p2', is_opponent=True)

        self.game_engine = GameEngine(
            [self.player1, self.player2], verbose=True, log_to_file=False)

        self.env = GameEnv(engine=self.game_engine, render=False)

        self.field_matrix = Matrix(self.screen, self.game_engine.game_state)
        self.render_engine = RenderEngine(
            self.field_matrix, self.screen, self.game_engine.game_state)
        self.input_manager = InputManager(
            self.field_matrix, self.game_engine, self.render_engine)

        self.background = load_image("assets/background.png")
        self.background = pygame.transform.scale(
            self.background, self.screen_size)

        self.continue_button = Button(
            pygame.Rect(540, 400, 200, 50),
            "Continue",
            callback=self.return_to_menu
        )

    def return_to_menu(self):
        self.should_exit_to_menu = True

    def handle_events(self):
        if self.game_over:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    return False
                self.continue_button.handle_event(event)
            return True

        current_player = self.game_engine.turn_manager.get_current_player()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return False

            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.should_exit_to_menu = True
                return False

            self.input_manager.handle_event(event)

            if (event.type == pygame.KEYDOWN and
                event.key == pygame.K_SPACE and
                    not current_player.is_opponent):
                self.game_engine.end_turn()
        return True

    @abstractmethod
    def update(self):
        ...

    def check_game_over(self):
        if not self.game_over and self.game_engine.game_state.is_game_over():
            self.game_over = True
            # Find local player in game_state.players (is_opponent=False)
            local_player = next(
                (p for p in self.game_engine.game_state.players if not p.is_opponent), None)
            if local_player and local_player.life_points > 0:
                self.winner_text = "VICTORY"
            else:
                self.winner_text = "DEFEAT"

    def draw(self):
        self.screen.blit(self.background, self.background.get_rect())
        self.field_matrix.areas["preview_card_table"].draw(self.screen)
        self.field_matrix.draw()
        self.input_manager.draw(self.screen)
        self.render_engine.draw()
        EffectManager.draw(self.screen)

        if self.game_over:
            self.draw_game_over_overlay()

        pygame.display.flip()

    def draw_game_over_overlay(self):
        overlay = pygame.Surface(self.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        font = get_font(72)
        color = (50, 250, 50) if self.winner_text == "VICTORY" else (250, 50, 50)
        text_surf = font.render(self.winner_text, True, color)
        text_rect = text_surf.get_rect(center=(self.screen_size[0]//2, 300))
        self.screen.blit(text_surf, text_rect)

        self.continue_button.draw(self.screen)

    def step(self, dt):
        self.dt = dt
        if not self.handle_events():
            return False
        if self.game_started:
            self.update()
            if not self.game_over:
                self.check_game_over()
            self.draw()
        return self.running


class AIGame(GameApp):
    def __init__(self, screen):
        super().__init__(screen)

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

        self.game_started = True
        self.game_engine.start_game()

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


class SocketClientGame(GameApp):
    def __init__(self, screen, host="localhost", port=5000, password=""):
        super().__init__(screen)
        print(f"Connecting to http://{host}:{port}...")
        self.sio = socketio.Client(logger=True, engineio_logger=True, reconnection=False)
        self.game_engine.socket_io = self.sio
        self.pending_data = None
        self.connected = False
        self.connection_error = None
        self.game_started = False

        @self.sio.on("synchronize")
        def on_synchronize(data):
            print("Received initial synchronization data")
            self.pending_data = data
            self.game_started = True

        @self.sio.event
        def disconnect():
            print("Disconnected from server")
            if not self.game_over:
                self.exit_reason = "Disconnected from server"
                self.running = False

        @self.sio.event
        def connect():
            print("Socket.IO connection established")
            self.connected = True

        @self.sio.on("connect_error")
        def on_connect_error(data):
            print(f"Socket.IO connection error: {data}")
            self.connection_error = str(data)

        self.connect_thread = Thread(
            target=self._connect, args=(host, port, password), daemon=True)
        self.connect_thread.start()

    def _connect(self, host, port, password):
        try:
            # Added a slight delay to ensure server is ready if we just started it locally
            import time
            time.sleep(0.5)

            # If the host is this machine, use localhost to avoid NAT loopback or firewall issues
            # that might prevent connecting to our own public/LAN IP.
            if host not in ["localhost", "127.0.0.1"]:
                try:
                    hostname = socket.gethostname()
                    local_ips = [socket.gethostbyname(hostname)]
                    try:
                        _, _, ip_list = socket.gethostbyname_ex(hostname)
                        local_ips.extend(ip_list)
                    except:
                        pass
                    if host in local_ips:
                        print(f"Redirecting local host {host} to localhost")
                        host = "localhost"
                except:
                    pass

            url = f"http://{host}:{port}"
            # Add password to query string if provided
            if password:
                import urllib.parse
                url += f"?password={urllib.parse.quote(password)}"
            print(f"Attempting to connect to {url}")
            self.sio.connect(url, wait_timeout=10)
        except Exception as e:
            print(f"Connection thread exception: {e}")
            self.connection_error = str(e)

    def update(self):
        if self.pending_data:
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

    def cleanup(self):
        try:
            self.sio.disconnect()
        except:
            pass


class SocketServerGame(GameApp):
    def __init__(self, screen, host='0.0.0.0', port=5000, room_name="AutoCard Room", password=""):
        super().__init__(screen)
        self.pending_data = None
        self.game_started = False
        self.connected_clients = 0
        self.password = password

        self._sub_queue = Queue()
        self._out_queue = Queue()

        from core.network.discovery import DiscoveryServer
        self.discovery_server = DiscoveryServer(
            port, room_name=room_name, password_protected=bool(password))
        self.discovery_server.start()

        self.server_process = Process(
            target=self._run_server, args=(host, port, password))
        self.server_process.start()

    def _handle_sub_queue(self):
        while not self._sub_queue.empty():
            msg = self._sub_queue.get()
            key, value = list(msg.items())[0]
            if key == "connected":
                self.connected_clients += 1
                self.game_engine.start_game()
                self.game_engine.draw_specific_card(self.player1.id, "Silent Witch", "monster")
                self.game_started = True
                self.game_engine.synchronize = self.emit_synchronize
                self.game_engine.synchronize()
            elif key == "disconnected":
                self.connected_clients -= 1
                if self.game_started and not self.game_over:
                    self.exit_reason = "Client disconnected"
                    self.running = False
            elif key == "synchronize":
                self.pending_data = value

    def _run_server(self, host, port, password):
        from werkzeug.serving import run_simple

        sio = socketio.Server(cors_allowed_origins='*', async_mode='threading')
        app = socketio.WSGIApp(sio)

        def emit_bridge():
            while True:
                try:
                    item = self._out_queue.get()
                    if item is None:
                        break
                    event, data = item
                    sio.emit(event, data)
                except Exception:
                    pass

        bridge_thread = Thread(target=emit_bridge, daemon=True)
        bridge_thread.start()

        @sio.on("synchronize")
        def on_synchronize(sid, data):
            self._sub_queue.put({"synchronize": data})

        @sio.event
        def connect(sid, environ):
            if password:
                client_pass = None
                # Extract auth data from query parameters or headers
                if 'HTTP_AUTHORIZATION' in environ:
                    client_pass = environ.get(
                        'HTTP_AUTHORIZATION', '').replace('Bearer ', '')
                elif 'QUERY_STRING' in environ:
                    import urllib.parse
                    query = urllib.parse.parse_qs(environ['QUERY_STRING'])
                    client_pass = query.get('password', [None])[0]

                if client_pass != password:
                    print(f"Invalid password from {sid}")
                    return False  # Reject connection

            print(f"SID {sid} connected")
            self._sub_queue.put({"connected": {}})
            return True

        @sio.event
        def disconnect(sid):
            self._sub_queue.put({"disconnected": {}})

        print(f"Server listening on {host}:{port} (werkzeug threading)")
        run_simple(host, port, app, threaded=True, use_reloader=False)

    def emit_synchronize(self):
        game_data = self.game_engine.serialize()
        self._out_queue.put(("synchronize", game_data))

    def update(self):
        self._handle_sub_queue()
        if self.pending_data:
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

    def cleanup(self):
        print("Stopping SocketServerGame...")
        try:
            if self.discovery_server:
                self.discovery_server.stop()
            if self.server_process:
                self.server_process.terminate()
                self.server_process.join(timeout=2)
                if self.server_process.is_alive():
                    print("Force killing server process...")
                    self.server_process.kill()
            self._out_queue.put(None)
        except Exception as e:
            print(f"Error during SocketServerGame cleanup: {e}")


class MainApplication:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((1280, 720))
        self.clock = pygame.time.Clock()
        self.matchmaker = MatchmakingScreen(self.screen)
        self.game_app = None
        self.running = True

    def run(self):
        while self.running:
            dt = self.clock.tick(60) / 1000.0

            # Check for user cancellation in matchmaking UI
            if self.matchmaker.state == ScreenState.MENU and self.game_app:
                print("Matchmaking cancelled or returned to menu, cleaning up game...")
                self._cleanup_game()
                self.matchmaker.result = None

            # If we have an active game and it's actually started, let it take over
            if self.game_app and self.game_app.game_started and self.matchmaker.state == ScreenState.START_GAME:
                if not self.game_app.step(dt) or self.game_app.should_exit_to_menu:
                    reason = getattr(self.game_app, 'exit_reason', None)
                    self._cleanup_game()
                    self.matchmaker.set_state(ScreenState.MENU)
                    if reason:
                        self.matchmaker._show_error(reason)
            else:
                # In matchmaking (includes MENU, HOST, JOIN, and WAITING states)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    self.matchmaker.handle_event(event)

                self.matchmaker.update(dt)
                self.matchmaker.draw(self.screen)

                if self.matchmaker.state == ScreenState.WAITING:
                    if self.game_app is None:
                        self._create_game_app(self.matchmaker.result)

                    if self.game_app:
                        if isinstance(self.game_app, SocketServerGame):
                            self.game_app._handle_sub_queue()
                            if self.game_app.game_started:
                                self.matchmaker.set_state(
                                    ScreenState.START_GAME)
                        elif isinstance(self.game_app, SocketClientGame):
                            if self.game_app.connection_error:
                                self.matchmaker._show_error(
                                    f"Failed: {self.game_app.connection_error}")
                                self._cleanup_game()
                                self.matchmaker.set_state(ScreenState.JOIN)
                            elif self.game_app.connected and self.game_app.game_started:
                                self.matchmaker.set_state(
                                    ScreenState.START_GAME)

                elif self.matchmaker.state == ScreenState.START_GAME:
                    # Double check we have a game app
                    if not self.game_app:
                        self._create_game_app(self.matchmaker.result)

                elif self.matchmaker.state == ScreenState.EXIT:
                    self.running = False

        self._cleanup_game()
        pygame.quit()

    def _cleanup_game(self):
        if self.game_app:
            print("Cleaning up game resources...")
            try:
                if hasattr(self.game_app, 'cleanup'):
                    self.game_app.cleanup()
            except Exception as e:
                print(f"Error during cleanup: {e}")
            finally:
                self.game_app = None

    def _create_game_app(self, result):
        if not result:
            return
        mode = result[0]
        try:
            if mode == "SERVER":
                self.game_app = SocketServerGame(
                    self.screen, port=result[1], password=result[2], room_name=result[3])
            elif mode == "CLIENT":
                self.game_app = SocketClientGame(
                    self.screen, host=result[1], port=result[2], password=result[3])
            elif mode == "AI":
                self.game_app = AIGame(self.screen)
        except Exception as e:
            print(f"Failed to create game app: {e}")
            self.matchmaker._show_error(str(e))
            self.matchmaker.set_state(ScreenState.MENU)

    def _start_game(self, result):
        if not self.game_app:
            self._create_game_app(result)


if __name__ == "__main__":
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("--client", action="store_true")
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--ai", action="store_true")
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    if not (args.client or args.server or args.ai):
        app = MainApplication()
        app.run()
    else:
        pygame.init()
        screen = pygame.display.set_mode((1280, 720))
        if args.client:
            app = SocketClientGame(screen, host=args.host, port=args.port)
        elif args.server:
            app = SocketServerGame(screen, host=args.host, port=args.port)
        elif args.ai:
            app = AIGame(screen)

        running = True
        clock = pygame.time.Clock()
        while running:
            dt = clock.tick(60) / 1000.0
            running = app.step(dt)
        pygame.quit()


# TODO: weird interaction when attacking with a trap card triggered
# TODO: add a end turn button instead of the usual space key
# TODO: add an option for the game to be hosted instead of local socket
# TODO: some time its not anybody turn
# TODO: the draw card spell should only be used in correct turn
