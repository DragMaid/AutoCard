import pygame
from core.handle_logic_gui.render_engine import RenderEngine
from gui.gui_info.matrix_field import Matrix
from gui.effects.manager import EffectManager
from gui.cache import load_image


class Renderer:
    """
    Renderer class for the game environment.
    Supports dynamic engine updates and integration with RenderThread.
    """

    def __init__(self, engine=None, delay=0.0, screen_size=(1280, 720), train_mode=True):
        # Pygame setup
        pygame.init()
        self.screen_size = screen_size
        self.screen = pygame.display.set_mode(self.screen_size)
        self.clock = pygame.time.Clock()
        self.dt = 0

        self.engine = engine
        self.train_mode = train_mode
        self.render_delay = delay

        # Background
        image_path = "assets/background.png"
        self.background = load_image(image_path)
        self.background = pygame.transform.scale(
            self.background, self.screen_size)

        # Initialize field_matrix and render_engine if engine is provided
        if self.engine is not None:
            self._init_render_objects()

    def reset(self):
        self.render_engine.reset()

    def _init_render_objects(self):
        """Initialize or update field_matrix and render_engine for the current engine."""
        self.field_matrix = Matrix(self.screen, self.engine.game_state)
        self.render_engine = RenderEngine(
            self.field_matrix, self.screen, train_mode=self.train_mode
        )

    def render(self, components=[]):
        """Draw the current game state to the screen."""
        if self.engine is None:
            return

        # Background
        self.screen.blit(self.background, (0, 0))

        # Draw field and preview areas
        if hasattr(self, "field_matrix"):
            if "preview_card_table" in self.field_matrix.areas:
                self.field_matrix.areas["preview_card_table"].draw(self.screen)
            self.field_matrix.draw()

        # Draw animations via render_engine
        if hasattr(self, "render_engine"):
            self.render_engine.update(
                self.engine.game_state,
                self.field_matrix,
                self.engine.event_logger
            )
            self.render_engine.animation_mgr.update(self.dt)
            self.render_engine.draw()

        # Draw global effects
        EffectManager.update()
        EffectManager.draw(self.screen)

        for component in components:
            component.draw(self.screen)

        pygame.display.flip()
        pygame.event.pump()

        self.tick(fps=0 if self.train_mode else 60)

    def tick(self, fps=60):
        """Advance the clock; should be called once per loop."""
        self.dt = self.clock.tick(fps) / 1000.0
