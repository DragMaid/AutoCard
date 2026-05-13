from threading import Thread
from ml.ai_opponent import AIOpponent, HumanVsAIManager
from gui.effects.manager import EffectManager
from .base import GameApp


class AIGame(GameApp):
    def __init__(self, screen):
        super().__init__(screen)

        self.ai = AIOpponent(
            env=self.env,
            config=self.config,
            checkpoint_path=self.config.CHECKPOINT_PATH,
            agent_id=1,
            device=self.config.DEVICE,
        )
        self.ai_manager = HumanVsAIManager(
            game_engine=self.game_engine,
            game_env=self.env,
            ai_opponent=self.ai,
            human_player_idx=0,
        )

        self._ai_running = False
        self._ai_thread = None

        self.game_engine.start_game()

    def update(self):
        self._maybe_start_ai_turn()
        self._tick_rendering()

    def _maybe_start_ai_turn(self):
        current = self.game_engine.turn_manager.get_current_player()
        if current == self.player2 and not self._ai_running:
            self._ai_running = True
            self._ai_thread = Thread(
                target=self.ai_manager.execute_ai_turn,
                kwargs={
                    "on_complete": lambda: setattr(self, "_ai_running", False),
                    "callback": lambda: self.render_engine.align_cards(self.matrix),
                },
                daemon=True,
            )
            self._ai_thread.start()

    def _tick_rendering(self):
        self.render_engine.update()
        self.render_engine.animation_mgr.update(self.dt)
        EffectManager.update()
