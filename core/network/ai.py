from threading import Thread
from typing import Optional
from ml.ai_opponent import AIOpponent, HumanVsAIManager
from gui.effects.manager import EffectManager
from ml.config import Config
from .base import GameApp


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
        )
        self.ai_manager: HumanVsAIManager = HumanVsAIManager(
            game_engine=self.game_engine,
            game_env=self.env,
            ai_opponent=self.ai,
            human_player_idx=0,
        )

        self._ai_running: bool = False
        self._ai_thread: Optional[Thread] = None

        self.game_engine.start_game()

    def update(self) -> None:
        """
        Updates the game state per frame, including AI execution.
        """
        self._maybe_start_ai_turn()
        self._tick_rendering()

    def _maybe_start_ai_turn(self) -> None:
        """
        Checks if it's the AI's turn and triggers the execution if not already running.
        """
        def force_align():
            self.matrix.set_game_state(
                self.game_engine.game_state, force=True)
            self.render_engine.align_cards(self.matrix)

        current = self.game_engine.turn_manager.get_current_player()
        if current == self.player2 and not self._ai_running:
            self._ai_running = True
            self._ai_thread = Thread(
                target=self.ai_manager.execute_ai_turn,
                kwargs={
                    "on_complete": lambda: setattr(self, "_ai_running", False),
                    "callback": lambda: force_align(),
                },
                daemon=True,
            )
            self._ai_thread.start()

    def _tick_rendering(self) -> None:
        """
        Updates rendering-related systems.
        """
        self.render_engine.update()
        self.render_engine.animation_mgr.update(self.dt)
        EffectManager.update()
