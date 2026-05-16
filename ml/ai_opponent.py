import logging
from pathlib import Path
from typing import Optional, Dict, Tuple, Any, Callable
from ml.trainer.agent import Agent
from core.data.player import Player
from ml.environment.environment import GameEnv
from ml.utils import load_model


logger = logging.getLogger(__name__)


class AIOpponent:
    """Wrapper for a trained AI agent that can play against a human.

    Attributes:
        env (Any): Game environment instance.
        device (str): Device to run inference on.
        agent_id (int): Which agent to load.
        agent (Agent): The trained AI agent.
        actions (Optional[List[int]]): Current list of actions.
    """

    def __init__(
        self,
        env: GameEnv,
        checkpoint_path: Path,
        agent_id: int = 0,
        device: str = "cpu"
    ) -> None:
        """Initializes AIOpponent from a trained checkpoint.

        Args:
            env (Any): GameEnv instance.
            checkpoint_path (Path): Path to saved model checkpoint.
            agent_id (int, optional): Which agent to load. Defaults to 0.
            device (str, optional): Device to run inference on. Defaults to "cpu".
        """
        self.env = env
        self.device = device
        self.agent_id = agent_id

        self.agent = Agent(
            state_dim=env.state_dim,
            num_actions=env.num_actions,
        )
        load_model(self.agent, path=checkpoint_path)

        self.agent.dqn.eval()
        self.agent.policy.eval()

    def get_action(
        self,
        player: Player,
        player_idx: int,
        deterministic: bool = True
    ) -> Tuple[int, Optional[Dict]]:
        """Gets an action from the AI for the given game state.

        Args:
            player (Player): The Player object.
            player_idx (int): Index of the player (0 or 1).
            deterministic (bool, optional): If True, always pick best action (no exploration). Defaults to True.

        Returns:
            Tuple[int, Optional[Dict]]: Tuple of (action_id, None) ready for env.step().
        """
        state = self.env.get_state(player)
        mask, _ = self.env.get_legal_actions(player_idx)

        # Select action (greedy if deterministic)
        epsilon = 0.0 if deterministic else 0.1
        action_id = self.agent.select_action_with_mask(
            state, mask, epsilon, best_response=True
        )
        return int(action_id)


class HumanVsAIManager:
    """Manages a game between human and AI, handling turn logic.

    Attributes:
        game_engine (Any): GameEngine instance.
        game_env (Any): GameEnv instance.
        ai_opponent (AIOpponent): AIOpponent instance.
        human_player_idx (int): Which player is human.
        ai_player_idx (int): Which player is AI.
        human_player (Player): Human player object.
        ai_player (Player): AI player object.
    """

    def __init__(
        self,
        game_engine: Any,
        game_env: Any,
        ai_opponent: AIOpponent,
        human_player_idx: int = 0
    ) -> None:
        """Initializes the manager.

        Args:
            game_engine (Any): GameEngine instance.
            game_env (Any): GameEnv instance.
            ai_opponent (AIOpponent): AIOpponent instance.
            human_player_idx (int, optional): Which player is human. Defaults to 0.
        """
        self.game_engine = game_engine
        self.game_env = game_env
        self.ai_opponent = ai_opponent
        self.human_player_idx = human_player_idx
        self.ai_player_idx = 1 - human_player_idx
        self.human_player = game_engine.game_state.players[human_player_idx]
        self.ai_player = game_engine.game_state.players[self.ai_player_idx]

    def execute(self, on_complete: Optional[Callable] = None, callback: Optional[Callable] = None) -> bool:
        """Executes the AI's complete turn.

        Args:
            on_complete (Optional[Callable], optional): Callback on completion. Defaults to None.
            callback (Optional[Callable], optional): Callback during step. Defaults to None.

        Returns:
            bool: True if turn completed, False if game over.
        """
        if not self.is_ai_turn():
            logger.warning(
                "Invalid turn call",
                extra={"reason": "Called execute_ai_turn but it's not AI's turn!"}
            )
            return True

        if self.game_engine.game_state.is_game_over():
            return False

        action_id, _ = self.ai_opponent.get_action(
            self.ai_player,
            self.ai_player_idx,
            deterministic=True
        )

        self.game_env.execute(
            player=self.ai_player,
            action_id=action_id,
            use_random=False,
            callback=callback
        )

        if on_complete:
            on_complete()

        return True
