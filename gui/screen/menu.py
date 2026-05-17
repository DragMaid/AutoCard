import pygame
from gui.screen.matchmaking import MatchmakingScreen, ScreenState
from core.network.server import SocketServerGame
from core.network.client import SocketClientGame
from core.network.ai import AIGame
from core.config import Config


class GameApp:
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode(Config.SCREEN_SIZE)
        self.clock = pygame.time.Clock()
        self.matchmaker = MatchmakingScreen(self.screen)
        self.game_app = None
        self.running = True

    def run(self) -> None:
        while self.running:
            dt = self.clock.tick(Config.FPS) / 1000.0
            self._tick(dt)

        self._cleanup_game()
        pygame.quit()

    def _tick(self, dt: float) -> None:
        state = self.matchmaker.state

        # User navigated back to the menu while a game existed → clean it up
        if state == ScreenState.MENU and self.game_app:
            self._cleanup_game()

        if state == ScreenState.EXIT:
            self.running = False
            return

        if self._game_is_running():
            self._tick_game(dt)
        else:
            self._tick_matchmaking(dt)

    def _game_is_running(self) -> bool:
        return (
            self.game_app is not None
            and self.game_app.game_started
            and self.matchmaker.state == ScreenState.START_GAME
        )

    def _tick_game(self, dt: float) -> None:
        keep_running = self.game_app.step(dt)
        if not keep_running or self.game_app.should_exit_to_menu:
            reason = getattr(self.game_app, "exit_reason", None)
            self._cleanup_game()
            self.matchmaker.set_state(ScreenState.MENU)
            if reason:
                self.matchmaker.show_error(reason)

    def _tick_matchmaking(self, dt: float) -> None:
        self._handle_matchmaking_events()
        self.matchmaker.update(dt)
        self.matchmaker.draw(self.screen)

        state = self.matchmaker.state
        if state == ScreenState.WAITING:
            self._poll_waiting()
        elif state == ScreenState.START_GAME and self.game_app is None:
            self._create_game_app(self.matchmaker.result)

    def _handle_matchmaking_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            self.matchmaker.handle_event(event)

    def _poll_waiting(self) -> None:
        """Check connection / lobby state and advance to START_GAME when ready."""
        if self.game_app is None:
            self._create_game_app(self.matchmaker.result)

        if self.game_app is None:
            return

        if isinstance(self.game_app, SocketServerGame):
            self.game_app.drain_sub_queue()
            if self.game_app.game_started:
                self.matchmaker.set_state(ScreenState.START_GAME)

        elif isinstance(self.game_app, SocketClientGame):
            if self.game_app.connection_error:
                self.matchmaker.show_error(
                    f"Failed: {self.game_app.connection_error}")
                self._cleanup_game()
                self.matchmaker.set_state(ScreenState.JOIN)
            elif self.game_app.connected and self.game_app.game_started:
                self.matchmaker.set_state(ScreenState.START_GAME)

    def _create_game_app(self, result: tuple) -> None:
        if not result:
            return
        mode = result[0]
        try:
            if mode == "SERVER":
                self.game_app = SocketServerGame(
                    self.screen, port=result[1], password=result[2], room_name=result[3]
                )
            elif mode == "CLIENT":
                self.game_app = SocketClientGame(
                    self.screen, host=result[1], port=result[2], password=result[3]
                )
            elif mode == "AI":
                self.game_app = AIGame(self.screen)
        except Exception as e:
            print(f"Failed to create game: {e}")
            self.matchmaker.set_state(ScreenState.MENU)
            self.matchmaker.show_error(str(e))

    def _cleanup_game(self):
        if self.game_app is None:
            return
        print("Cleaning up game resources…")
        try:
            if hasattr(self.game_app, "cleanup"):
                self.game_app.cleanup()
        except Exception as e:
            print(f"Cleanup error: {e}")
        finally:
            self.game_app = None


def run_headless_game(args):
    """Bypass matchmaking for direct CLI launches."""
    pygame.init()
    screen = pygame.display.set_mode(Config.SCREEN_SIZE)
    clock = pygame.time.Clock()

    if args.client:
        app = SocketClientGame(screen, host=args.host, port=args.port)
    elif args.server:
        app = SocketServerGame(screen)
    else:  # --ai
        app = AIGame(screen)

    running = True
    while running:
        dt = clock.tick(Config.FPS) / 1000.0
        running = app.step(dt)

    if hasattr(app, "cleanup"):
        app.cleanup()
    pygame.quit()
