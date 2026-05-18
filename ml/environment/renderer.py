import pygame
from typing import Optional, Tuple, List, Any
from core.config import Config
from core.gui.render_engine import RenderEngine
from gui.background.matrix_field import Matrix
from gui.effects.manager import EffectManager
from gui.cache import load_image


class Renderer:
    """Renderer class for the game environment.

    Supports dynamic engine updates and integration with RenderThread.

    Attributes:
        screen_size: A tuple representing the screen dimensions (width, height).
        engine: The GameEngine instance to render.
        train_mode: Boolean indicating if the environment is in training mode.
    """

    def __init__(
        self,
        engine: Optional[Any] = None,
        screen_size: Tuple[int, int] = Config.SCREEN_SIZE,
        train_mode: bool = True,
    ) -> None:
        """Initialize the Renderer.

        Args:
            engine: The GameEngine instance.
            screen_size: Screen dimensions.
            train_mode: Whether to run in training mode.
        """
        # Pygame setup
        pygame.init()
        self.screen_size = screen_size
        self.screen = pygame.display.set_mode(self.screen_size)
        self.clock = pygame.time.Clock()
        self.dt: float = 0.0

        self.engine = engine
        self.train_mode = train_mode

        # Background
        image_path = "assets/background.png"
        self.background = load_image(image_path)
        self.background = pygame.transform.scale(
            self.background, self.screen_size)

        # Initialize matrix and render_engine if engine is provided
        if self.engine is not None:
            self._init_render_objects()

    def reset(self) -> None:
        """Reset the render engine."""
        self.render_engine.reset()

    def _init_render_objects(self) -> None:
        """Initialize or update matrix and render_engine for the current engine."""
        self.matrix = Matrix(self.screen, self.engine.game_state)
        self.render_engine = RenderEngine(
            matrix=self.matrix,
            screen=self.screen,
            game_state=self.engine.game_state,
            event_logger=self.engine.event_logger,
            turn_manager=self.engine.turn_manager,
            train_mode=self.train_mode,
        )

    def render(self, components: Optional[List[Any]] = None) -> None:
        """Draw the current game state to the screen.

        Args:
            components: Optional list of additional components to draw.
        """
        if self.engine is None:
            return
        if components is None:
            components = []

        # Background
        self.screen.blit(self.background, (0, 0))

        # Draw field and preview areas
        if hasattr(self, "matrix"):
            if "preview_card_table" in self.matrix.areas:
                self.matrix.areas["preview_card_table"].draw(self.screen)
            self.matrix.draw()

        # Draw animations via render_engine
        if hasattr(self, "render_engine"):
            self.render_engine.update()
            self.render_engine.animation_mgr.update(self.dt)
            self.render_engine.draw()

        # Draw global effects
        EffectManager.update()
        EffectManager.draw(self.screen)

        for component in components:
            component.draw(self.screen)

        pygame.display.flip()
        pygame.event.pump()

        self.tick(fps=0 if self.train_mode else Config.FPS)

    def tick(self, fps: int = 60) -> None:
        """Advance the clock; should be called once per loop.

        Args:
            fps: Frames per second to cap at.
        """
        self.dt = self.clock.tick(fps) / 1000.0
