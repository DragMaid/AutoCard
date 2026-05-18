import logging
from threading import Thread
from typing import Optional
from ml.ai_opponent import AIOpponent, HumanVsAIManager
from gui.effects.manager import EffectManager
from ml.config import Config
from .base import GameApp

logger = logging.getLogger(__name__)


class AIGame(GameApp):
    """
    Game mode for playing against an AI opponent.

    Attributes:
        ai (AIOpponent): The AI opponent instance.
        ai_manager (HumanVsAIManager): Manager for coordinating human vs AI interaction.
    """

    def __init__(self, screen) -> None:
        """
        Initializes AIGame.

        Args:
            screen: The pygame screen surface.
        """
        super().__init__(screen)

        self.ai: AIOpponent = AIOpponent(
            env=self.env,
            checkpoint_path=Config.CHECKPOINT_PATH,
            agent_id=1,
            device=Config.DEVICE
        )
        self.ai_manager: HumanVsAIManager = HumanVsAIManager(
            game_engine=self.game_engine,
            game_env=self.env,
            ai_opponent=self.ai,
            human_player_idx=0,
        )

        self._ai_running: bool = False
        self._ai_thread: Optional[Thread] = None
        self._needs_sync: bool = False

        self.game_engine.start_game()

    def update(self) -> None:
        """
        Updates the game state per frame, including AI execution and rendering.
        """
        self._handle_ai_turn()
        self._sync_gui_if_needed()
        self._tick_rendering()

    def _handle_ai_turn(self) -> None:
        """
        Checks if it's the AI's turn and starts the execution thread if needed.
        """
        if self.ai_manager.is_ai_turn() and not self._ai_running and not self.game_over:
            self._ai_running = True
            self._ai_thread = Thread(
                target=self.ai_manager.execute_turn,
                kwargs={
                    "delay": 0.8,
                    "on_step": self._trigger_sync,
                    "on_complete": self._on_ai_complete,
                },
                daemon=True,
            )
            self._ai_thread.start()
            logger.info("AI turn started.")

    def _trigger_sync(self) -> None:
        """Sets a flag to synchronize the GUI on the next main thread update."""
        self._needs_sync = True

    def _on_ai_complete(self) -> None:
        """Callback for when the AI finishes its turn."""
        self._ai_running = False
        self._trigger_sync()
        logger.info("AI turn completed.")

    def _sync_gui_if_needed(self) -> None:
        """Synchronizes the GUI with the game engine state on the main thread."""
        if self._needs_sync:
            self.matrix.set_game_state(self.game_engine.game_state, force=True)
            self.render_engine.align_cards(self.matrix)
            self._needs_sync = False

    def _tick_rendering(self) -> None:
        """
        Updates rendering-related systems.
        """
        self.render_engine.update()
        self.render_engine.animation_mgr.update(self.dt)
        EffectManager.update()

