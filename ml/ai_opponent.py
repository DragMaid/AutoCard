import torch
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple, Any, Callable
from ml.trainer.agent import Agent
from core.data.player import Player
from ml.environment.environment import GameEnv


logger = logging.getLogger(__name__)


class AIOpponent:
    """Wrapper for a trained AI agent that can play against a human.

    Attributes:
        env (Any): Game environment instance.
        device (str): Device to run inference on.
        agent_id (int): Which agent to load.
        agent (Agent): The trained AI agent.
        actions (Optional[List[int]]): Current list of actions.
        actions_taken (int): Number of actions taken.
        action_pointer (int): Pointer for actions.
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

        # Initialize agent
        self.agent = Agent(
            state_dim=env.state_dim,
            num_actions=env.num_actions,
        )

        # Load trained weights
        self._load_checkpoint(checkpoint_path, agent_id)

        # Set to evaluation mode
        self.agent.dqn.eval()
        if hasattr(self.agent, 'policy') and self.agent.policy is not None:
            self.agent.policy.eval()

        self.actions: Optional[list] = None
        self.actions_taken: int = 0
        self.action_pointer: int = 0

        logger.info(
            "AI Opponent loaded",
            extra={"checkpoint_path": str(checkpoint_path)}
        )

    def _load_checkpoint(self, checkpoint_path: Path, agent_id: int) -> None:
        """Loads model weights from checkpoint.

        Args:
            checkpoint_path (Path): Path to the checkpoint.
            agent_id (int): The index of the agent.
        """
        # Support both directory and file paths
        if checkpoint_path.is_dir():
            # Look for checkpoint.pth in directory
            checkpoint_file = checkpoint_path / "checkpoint.pth"
            if not checkpoint_file.exists():
                raise FileNotFoundError(
                    f"No checkpoint.pth found in {checkpoint_path}")
        else:
            # Assume it's a file path
            checkpoint_file = checkpoint_path / "checkpoint.pth"
            if not checkpoint_file.exists():
                checkpoint_file = checkpoint_path
                if not checkpoint_file.exists():
                    raise FileNotFoundError(
                        f"Checkpoint file not found: {checkpoint_file}")

        # Load the single checkpoint file
        checkpoint = torch.load(checkpoint_file, map_location=self.device)

        # Extract this agent's model
        model_key = f"agent_{agent_id}_model"
        if model_key not in checkpoint:
            raise KeyError(f"Agent {agent_id} model not found in checkpoint. Available keys: {
                           list(checkpoint.keys())}")

        self.agent.dqn.load_state_dict(checkpoint[model_key])
        logger.info(
            "Loaded model state",
            extra={
                "model_key": model_key,
                "checkpoint_file": str(checkpoint_file)
            }
        )

        # Load policy network
        policy_key = f"agent_{agent_id}_policy"
        if policy_key in checkpoint and hasattr(self.agent, 'policy') and self.agent.policy is not None:
            self.agent.policy.load_state_dict(checkpoint[policy_key])
            logger.info(
                "Loaded policy state",
                extra={
                    "policy_key": policy_key,
                    "checkpoint_file": str(checkpoint_file)
                }
            )
        elif hasattr(self.agent, 'policy') and self.agent.policy is not None:
            logger.warning(f"Policy network expected but {
                policy_key} not found in checkpoint")

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
        # Get current state
        state = self.env._get_state(player)

        # Get legal actions
        mask, _ = self.env.get_legal_actions(player_idx)

        # Select action (greedy if deterministic)
        epsilon = 0.0 if deterministic else 0.1
        action_id = self.agent.select_action_with_mask(
            state, mask, epsilon, best_response=True
        )

        logger.info(
            "AI selected action",
            extra={"action_id": int(action_id)}
        )

        return int(action_id), None


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
        ai_action_queue (List[Any]): Queue for AI actions.
        ai_actions_this_turn (int): Number of actions AI has taken this turn.
        max_ai_actions_per_turn (int): Max actions per turn for AI.
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

        self.ai_action_queue: list = []
        self.ai_actions_this_turn: int = 0
        self.max_ai_actions_per_turn: int = 10

        logger.info(
            "Human vs AI initialized",
            extra={
                "human_player": self.human_player.name,
                "ai_player": self.ai_player.name
            }
        )

    def is_ai_turn(self) -> bool:
        """Checks if it's currently the AI's turn.

        Returns:
            bool: True if it's the AI's turn, False otherwise.
        """
        current_player = self.game_engine.turn_manager.get_current_player()
        return current_player == self.ai_player

    def is_human_turn(self) -> bool:
        """Checks if it's currently the human's turn.

        Returns:
            bool: True if it's the human's turn, False otherwise.
        """
        return not self.is_ai_turn()

    def execute_ai_turn(self, on_complete: Optional[Callable] = None, callback: Optional[Callable] = None) -> bool:
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
            logger.info(
                "Game over",
                extra={"phase": "AI turn"}
            )
            return False

        action_id, _ = self.ai_opponent.get_action(
            self.ai_player,
            self.ai_player_idx,
            deterministic=True
        )
        actions = [(action_id, None)]

        self.game_env.step_single(
            self.ai_player, actions, callback=callback)

        if self.game_engine.turn_manager.get_current_player() == self.ai_player:
            self.game_engine.end_turn()

        if on_complete:
            on_complete()
        return True
