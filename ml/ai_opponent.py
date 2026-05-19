import logging
import time
from pathlib import Path
from typing import Optional, Callable
from ml.trainer.agent import Agent
from core.data.player import Player
from ml.environment.environment import GameEnv
from core.logic.game_engine import GameEngine
from ml.utils import load_model


logger = logging.getLogger(__name__)


class AIOpponent:
    """Wrapper for a trained AI agent that can play against a human.

    Attributes:
        env (GameEnv): Game environment instance.
        device (str): Device to run inference on.
        agent_id (int): Which agent to load.
        agent (Agent): The trained AI agent.
    """

    def __init__(
        self,
        env: GameEnv,
        checkpoint_path: Optional[Path] = None,
        agent_id: int = 0,
        device: str = "cpu"
    ) -> None:
        """Initializes AIOpponent.

        Args:
            env (GameEnv): GameEnv instance.
            checkpoint_path (Optional[Path]): Path to saved model checkpoint. 
                If None, uses an untrained agent.
            agent_id (int, optional): Which agent to load. Defaults to 0.
            device (str, optional): Device to run inference on. Defaults to "cpu".
        """
        self.env = env
        self.device = device
        self.agent_id = agent_id

        self.agent = Agent(num_actions=env.num_actions, device="cpu")

        if checkpoint_path and checkpoint_path.exists():
            load_model(self.agent, path=checkpoint_path)
            logger.info(f"Loaded AI checkpoint from {checkpoint_path}")
        else:
            logger.warning(
                "No valid checkpoint found for AI; using untrained agent.")

        self.agent.dqn.to(device)
        self.agent.dqn.eval()
        self.agent.policy.eval()

    def get_action(
        self,
        player: Player,
        deterministic: bool = True
    ) -> int:
        """Gets an action from the AI for the given game state.

        Args:
            player (Player): The Player object.
            deterministic (bool, optional): If True, always pick best action (no exploration). Defaults to True.

        Returns:
            int: The selected action ID.
        """
        state = self.env.get_state(player)
        mask, _ = self.env.get_legal_actions(player)

        # Select action (greedy if deterministic)
        epsilon = 0.0 if deterministic else 0.1
        action_id, _ = self.agent.select_action_with_mask(
            state, mask, epsilon, best_response=True
        )
        return int(action_id)


class HumanVsAIManager:
    """Manages a game between human and AI, handling turn logic.

    Attributes:
        game_engine (GameEngine): GameEngine instance.
        game_env (GameEnv): GameEnv instance.
        ai_opponent (AIOpponent): AIOpponent instance.
        human_player_idx (int): Which player is human.
        ai_player_idx (int): Which player is AI.
    """

    def __init__(
        self,
        game_engine: GameEngine,
        game_env: GameEnv,
        ai_opponent: AIOpponent,
        human_player_idx: int = 0
    ) -> None:
        """Initializes the manager.

        Args:
            game_engine (GameEngine): GameEngine instance.
            game_env (GameEnv): GameEnv instance.
            ai_opponent (AIOpponent): AIOpponent instance.
            human_player_idx (int, optional): Which player is human. Defaults to 0.
        """
        self.game_engine = game_engine
        self.game_env = game_env
        self.ai_opponent = ai_opponent
        self.human_player_idx = human_player_idx
        self.ai_player_idx = 1 - human_player_idx

    @property
    def ai_player(self) -> Player:
        return self.game_engine.game_state.players[self.ai_player_idx]

    @property
    def human_player(self) -> Player:
        return self.game_engine.game_state.players[self.human_player_idx]

    def is_ai_turn(self) -> bool:
        """Checks if it is currently the AI's turn (either active or trapper)."""
        acting_player = self.game_env.get_acting_player()
        if not acting_player:
            return False
        return acting_player.id == self.ai_player.id

    def execute_step(self, callback: Optional[Callable] = None) -> bool:
        """Executes a single action for the AI.

        Args:
            callback (Optional[Callable]): Callback called after the action is executed.

        Returns:
            bool: True if an action was executed, False otherwise.
        """
        if not self.is_ai_turn() or self.game_engine.game_state.is_game_over():
            return False

        action_id = self.ai_opponent.get_action(
            self.ai_player,
            deterministic=True
        )

        self.game_env.execute(
            player=self.ai_player,
            action_id=action_id,
            use_random=False,
            callback=callback
        )
        return True

    def execute_turn(
        self,
        delay: float = 0.5,
        on_step: Optional[Callable] = None,
        on_complete: Optional[Callable] = None
    ) -> None:
        """Executes the AI's actions until its turn ends.

        Args:
            delay (float): Time to wait between actions in seconds.
            on_step (Optional[Callable]): Callback called after each action.
            on_complete (Optional[Callable]): Callback called when the turn ends.
        """
        while self.is_ai_turn() and not self.game_engine.game_state.is_game_over():
            success = self.execute_step(callback=on_step)
            if not success:
                break
            if delay > 0:
                time.sleep(delay)

        if on_complete:
            on_complete()
