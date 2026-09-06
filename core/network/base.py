import pygame
from abc import ABC, abstractmethod
from typing import Optional
from ml.environment.environment import GameEnv
from core.data.player import Player
from core.logic.game_engine import GameEngine
from core.gui.input_manager import InputManager
from gui.background.matrix_field import Matrix
from core.gui.render_engine import RenderEngine
from gui.effects.manager import EffectManager
from gui.cache import load_image
from gui.screen.hud import GameHUD, SurrenderOverlay, GameOverOverlay, TrapStageOverlay
from core.config import Config


class GameApp(ABC):
    """
    Base class for game applications, handling common engine and UI setup.

    Attributes:
        screen: The main game screen.
        clock (pygame.time.Clock): Game clock.
        running (bool): Whether the application is running.
        game_started (bool): Whether the game has started.
        dt (float): Delta time.
        should_exit_to_menu (bool): Flag to exit to menu.
        exit_reason (Optional[str]): Reason for exiting.
        game_over (bool): Flag for game over state.
    """

    def __init__(self, screen) -> None:
        """
        Initializes GameApp.

        Args:
            screen: The main game screen.
        """
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.running: bool = True
        self.game_started: bool = True
        self.dt: float = 0
        self.should_exit_to_menu: bool = False
        self.exit_reason: Optional[str] = None
        self.game_over: bool = False

        self._setup_players()
        self._setup_engine()
        self._setup_rendering()
        self._setup_ui()

        self.background = pygame.transform.scale(
            load_image("assets/background.png"), Config.SCREEN_SIZE)

    def _setup_players(self) -> None:
        """Sets up the players for the game."""
        self.player1: Player = Player(player_index=0, name="p1", is_opponent=False)
        self.player2: Player = Player(player_index=1, name="p2", is_opponent=True)

    def _engine_kwargs(self) -> dict:
        """Extra GameEngine arguments for this game mode.

        Offline modes need none. Networked subclasses override this to supply a
        transport plus the authoritative/remote mode, which is why any transport
        they own must be created before ``super().__init__`` runs.

        Returns:
            dict: Keyword arguments forwarded to :class:`GameEngine`.
        """
        return {}

    def _setup_engine(self) -> None:
        """Sets up the game engine and environment."""
        self.game_engine: GameEngine = GameEngine(
            [self.player1, self.player2], **self._engine_kwargs())
        self.env: GameEnv = GameEnv(engine=self.game_engine, render=False)

    def _setup_rendering(self) -> None:
        """Sets up rendering-related objects."""
        self.matrix: Matrix = Matrix(self.screen, self.game_engine.game_state)
        self.render_engine: RenderEngine = RenderEngine(
            matrix=self.matrix,
            screen=self.screen,
            event_logger=self.game_engine.event_logger,
            turn_manager=self.game_engine.turn_manager,
            game_state=self.game_engine.game_state
        )
        self.input_manager: InputManager = InputManager(
            self.matrix,
            self.game_engine,
            self.render_engine
        )

    def _setup_ui(self) -> None:
        """Sets up the user interface elements."""
        self.hud: GameHUD = GameHUD(
            self.game_engine,
            on_end_turn=self.game_engine.end_turn,
            on_surrender=self._on_surrender_requested,
        )
        self.surrender_overlay: SurrenderOverlay = SurrenderOverlay(
            Config.SCREEN_SIZE,
            on_confirm=self._on_surrender_confirmed,
            on_cancel=self._on_surrender_cancelled,
        )
        self.game_over_overlay: GameOverOverlay = GameOverOverlay(
            Config.SCREEN_SIZE,
            on_continue=self._on_return_to_menu,
        )
        self.trap_overlay: TrapStageOverlay = TrapStageOverlay(Config.SCREEN_SIZE)

    def _on_surrender_requested(self) -> None:
        """Handles surrender request."""
        self.surrender_overlay.show()

    def _on_surrender_cancelled(self) -> None:
        """Handles cancellation of surrender request."""
        self.surrender_overlay.hide()

    def _on_surrender_confirmed(self) -> None:
        """Handles confirmation of surrender."""
        local_player: Optional[Player] = self._get_local_player()
        if local_player:
            # Routes through the engine so a networked match emits the
            # concession as an action instead of a silent local mutation.
            self.game_engine.surrender(local_player.id)
            self._check_game_over()
        self.surrender_overlay.hide()

    def _on_return_to_menu(self) -> None:
        """Handles return to menu request."""
        self.should_exit_to_menu = True

    def _get_local_player(self) -> Optional[Player]:
        """
        Returns the local player.

        Returns:
            Optional[Player]: The local player, or None if not found.
        """
        return next(
            (p for p in self.game_engine.game_state.players
             if not p.is_opponent), None
        )

    def step(self, dt: float) -> bool:
        """
        Executes a game step.

        Args:
            dt (float): Delta time.

        Returns:
            bool: Whether the game is still running.
        """
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
        """Handles input events."""
        if self.game_over:
            return self._handle_game_over_events()
        if self.surrender_overlay.visible:
            return self._handle_surrender_overlay_events()
        return self._handle_gameplay_events()

    def _handle_game_over_events(self) -> bool:
        """Handles events during game over screen."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return False
            self.game_over_overlay.handle_event(event)
        return True

    def _handle_surrender_overlay_events(self) -> bool:
        """Handles events during surrender overlay."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                return False
            self.surrender_overlay.handle_event(event)
        return True

    def _handle_gameplay_events(self) -> bool:
        """Handles gameplay-related events."""
        is_local: bool = self.game_engine.is_local_turn()
        self.hud.set_local_turn(is_local)

        # Show trap overlay if it's the opponent's turn to activate traps
        if self.game_engine.turn_manager.is_trap_stage() and not is_local:
            self.trap_overlay.show()
        else:
            self.trap_overlay.hide()

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

    def _check_game_over(self) -> None:
        """Checks for game over state."""
        if self.game_over or not self.game_engine.game_state.is_game_over():
            return
        self.game_over = True
        local_player = self._get_local_player()
        result: str = "VICTORY" if (
            local_player and local_player.life_points > 0) else "DEFEAT"
        self.game_over_overlay.show(result)

    def _draw(self) -> None:
        """Draws all game elements."""
        self.screen.blit(self.background, (0, 0))
        self.matrix.areas["preview_card_table"].draw(self.screen)
        self.matrix.draw()
        self.input_manager.draw(self.screen)
        self.render_engine.draw()
        EffectManager.draw(self.screen)
        self.hud.draw(self.screen)
        self.trap_overlay.draw(self.screen)
        self.surrender_overlay.draw(self.screen)
        self.game_over_overlay.draw(self.screen)
        pygame.display.flip()

    @abstractmethod
    def update(self) -> None:
        """Per-frame game logic — implemented by each game mode."""
        ...
