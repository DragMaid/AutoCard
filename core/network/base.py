import pygame
from abc import ABC, abstractmethod
from ml.environment.environment import GameEnv
from ml.config import Config
from core.player import Player
from core.handle_game_logic.game_engine import GameEngine
from core.handle_logic_gui.input_manager import InputManager
from gui.gui_info.matrix_field import Matrix
from core.handle_logic_gui.render_engine import RenderEngine
from gui.effects.manager import EffectManager
from gui.cache import load_image
from gui.hud import GameHUD, SurrenderOverlay, GameOverOverlay

# TODO: move this to config
SCREEN_SIZE = (1280, 720)


class GameApp(ABC):
    def __init__(self, screen):
        self.config = Config()
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.running = True
        self.game_started = True
        self.dt = 0
        self.should_exit_to_menu = False
        self.exit_reason = None
        self.game_over = False

        self._setup_players()
        self._setup_engine()
        self._setup_rendering()
        self._setup_ui()

        self.background = pygame.transform.scale(
            load_image("assets/background.png"), SCREEN_SIZE
        )

    def _setup_players(self):
        self.player1 = Player(0, "p1")
        self.player2 = Player(1, "p2", is_opponent=True)

    def _setup_engine(self):
        self.game_engine = GameEngine(
            [self.player1, self.player2], verbose=True, log_to_file=False
        )
        self.env = GameEnv(engine=self.game_engine, render=False)

    def _setup_rendering(self):
        self.field_matrix = Matrix(self.screen, self.game_engine.game_state)
        self.render_engine = RenderEngine(
            self.field_matrix, self.screen, self.game_engine.game_state
        )
        self.input_manager = InputManager(
            self.field_matrix, self.game_engine, self.render_engine
        )

    def _setup_ui(self):
        self.hud = GameHUD(
            self.game_engine,
            on_end_turn=self.game_engine.end_turn,
            on_surrender=self._on_surrender_requested,
        )
        self.surrender_overlay = SurrenderOverlay(
            SCREEN_SIZE,
            on_confirm=self._on_surrender_confirmed,
            on_cancel=self._on_surrender_cancelled,
        )
        self.game_over_overlay = GameOverOverlay(
            SCREEN_SIZE,
            on_continue=self._on_return_to_menu,
        )

    def _on_surrender_requested(self):
        self.surrender_overlay.show()

    def _on_surrender_cancelled(self):
        self.surrender_overlay.hide()

    def _on_surrender_confirmed(self):
        local_player = self._get_local_player()
        if local_player:
            local_player.life_points = 0
            self._check_game_over()
        self.surrender_overlay.hide()
        self.game_engine.synchronize()

    def _on_return_to_menu(self):
        self.should_exit_to_menu = True

    def _get_local_player(self):
        return next(
            (p for p in self.game_engine.game_state.players if not p.is_opponent), None
        )

    def _is_local_turn(self) -> bool:
        return not self.game_engine.turn_manager.get_current_player().is_opponent

    # --------------------------------------------------------- main loop

    def step(self, dt) -> bool:
        self.dt = dt
        if not self._handle_events():
            return False
        if self.game_started:
            self.update()
            if not self.game_over:
                self._check_game_over()
            self._draw()
        return self.running

    def _handle_events(self) -> bool:
        if self.game_over:
            return self._handle_game_over_events()
        if self.surrender_overlay.visible:
            return self._handle_surrender_overlay_events()
        return self._handle_gameplay_events()

    def _handle_game_over_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return False
            self.game_over_overlay.handle_event(event)
        return True

    def _handle_surrender_overlay_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return False
            self.surrender_overlay.handle_event(event)
        return True

    def _handle_gameplay_events(self) -> bool:
        is_local = self._is_local_turn()
        self.hud.set_local_turn(is_local)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.should_exit_to_menu = True
                    return False
                if event.key == pygame.K_SPACE and is_local:
                    self.game_engine.end_turn()

            self.input_manager.handle_event(event)
            self.hud.handle_event(event)

        return True

    def _check_game_over(self):
        if self.game_over or not self.game_engine.game_state.is_game_over():
            return
        self.game_over = True
        local_player = self._get_local_player()
        result = "VICTORY" if (local_player and local_player.life_points > 0) else "DEFEAT"
        self.game_over_overlay.show(result)

    def _draw(self):
        self.screen.blit(self.background, (0, 0))
        self.field_matrix.areas["preview_card_table"].draw(self.screen)
        self.field_matrix.draw()
        self.input_manager.draw(self.screen)
        self.render_engine.draw()
        EffectManager.draw(self.screen)
        self.hud.draw(self.screen)
        self.surrender_overlay.draw(self.screen)
        self.game_over_overlay.draw(self.screen)
        pygame.display.flip()

    @abstractmethod
    def update(self):
        """Per-frame game logic — implemented by each game mode."""
        ...
