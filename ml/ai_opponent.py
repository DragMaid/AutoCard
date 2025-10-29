import torch
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple
from ml.trainer.agent import Agent
from ml.trainer.action_mapper import ActionMapper
from core.player import Player


class AIOpponent:
    """
    Wrapper for a trained AI agent that can play against a human.
    """

    def __init__(
        self,
        env,
        config,
        checkpoint_path: Path,
        agent_id: int = 0,
        device: str = "cpu"
    ):
        """
        Initialize AI opponent from a trained checkpoint.

        Args:
            env: GameEnv instance
            config: Training config
            checkpoint_path: Path to saved model checkpoint
            agent_id: Which agent to load (0 or 1)
            device: Device to run inference on
        """
        self.env = env
        self.config = config
        self.device = device
        self.agent_id = agent_id
        self.logger = logging.getLogger("AIOpponent")

        # Initialize agent
        self.agent = Agent(
            state_dim=env.state_dim,
            num_actions=env.num_actions,
            param_dim=env.param_dim,
            config=config
        )

        # Initialize action mapper
        self.action_mapper = ActionMapper(env)

        # Load trained weights
        self._load_checkpoint(checkpoint_path, agent_id)

        # Set to evaluation mode
        self.agent.dqn.eval()
        if hasattr(self.agent, 'policy') and self.agent.policy is not None:
            self.agent.policy.eval()

        self.actions = None
        self.actions_taken = 0
        self.action_pointer = 0

        self.logger.info(f"AI Opponent loaded from {checkpoint_path}")

    def _load_checkpoint(self, checkpoint_path: Path, agent_id: int):
        """Load model weights from checkpoint."""
        # Support both directory and file paths
        if checkpoint_path.is_dir():
            # Look for checkpoint.pth in directory
            checkpoint_file = checkpoint_path / "checkpoint.pth"
            if not checkpoint_file.exists():
                raise FileNotFoundError(
                    f"No checkpoint.pth found in {checkpoint_path}")
        else:
            # Assume it's a file path
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
        self.logger.info(f"Loaded {model_key} from {checkpoint_file}")

        # Load policy network if using PDQN
        policy_key = f"agent_{agent_id}_policy"
        if policy_key in checkpoint and hasattr(self.agent, 'policy') and self.agent.policy is not None:
            self.agent.policy.load_state_dict(checkpoint[policy_key])
            self.logger.info(f"Loaded {policy_key} from {checkpoint_file}")
        elif hasattr(self.agent, 'policy') and self.agent.policy is not None:
            self.logger.warning(f"Policy network expected but {
                                policy_key} not found in checkpoint")

    def get_action(
        self,
        player: Player,
        player_idx: int,
        deterministic: bool = True
    ) -> Tuple[int, Optional[Dict]]:
        """
        Get an action from the AI for the given game state.

        Args:
            player: The Player object
            player_idx: Index of the player (0 or 1)
            deterministic: If True, always pick best action (no exploration)

        Returns:
            Tuple of (action_idx, param_dict) ready for env.step()
        """
        # Get current state
        state = self.env._get_state(player)

        # Get legal actions
        mask, legal_params = self.env.get_legal_actions(player_idx)

        # Select action (greedy if deterministic)
        epsilon = 0.0 if deterministic else 0.1
        discrete_action = self.agent.select_action_with_mask(
            state, mask, epsilon, best_response=True
        )

        with torch.no_grad():
            cont_params = self.agent.select_continuous_params(state)

        # Map to environment action
        action_idx, param_dict = self.action_mapper.map(
            player_idx,
            discrete_action,
            cont_params,
            legal_params
        )

        self.logger.info(
            f"AI selected: {self.env.ACTIONS[action_idx]} with params {param_dict}")

        return int(action_idx), param_dict


class HumanVsAIManager:
    """
    Manages a game between human and AI, handling turn logic.
    """

    def __init__(
        self,
        game_engine,
        game_env,
        ai_opponent: AIOpponent,
        human_player_idx: int = 0
    ):
        """
        Initialize the manager.

        Args:
            game_engine: GameEngine instance
            game_env: GameEnv instance
            ai_opponent: AIOpponent instance
            human_player_idx: Which player is human (0 or 1)
        """
        self.game_engine = game_engine
        self.game_env = game_env
        self.ai_opponent = ai_opponent
        self.human_player_idx = human_player_idx
        self.ai_player_idx = 1 - human_player_idx

        self.logger = logging.getLogger("HumanVsAI")

        self.human_player = game_engine.game_state.players[human_player_idx]
        self.ai_player = game_engine.game_state.players[self.ai_player_idx]

        self.ai_action_queue = []
        self.ai_actions_this_turn = 0
        self.max_ai_actions_per_turn = 10

        self.logger.info(f"Human vs AI initialized: Human={
                         self.human_player.name}, AI={self.ai_player.name}")

    def is_ai_turn(self) -> bool:
        """Check if it's currently the AI's turn."""
        current_player = self.game_engine.turn_manager.get_current_player()
        return current_player == self.ai_player

    def is_human_turn(self) -> bool:
        """Check if it's currently the human's turn."""
        return not self.is_ai_turn()

    def execute_ai_turn(self, on_complete=None, callback=None):
        """
        Execute the AI's complete turn.
        Returns True if turn completed, False if game over.
        """
        if not self.is_ai_turn():
            self.logger.warning(
                "Called execute_ai_turn but it's not AI's turn!")
            return True

        if self.game_engine.game_state.is_game_over():
            self.logger.info("Game over during AI turn")
            return False

        action_idx, param_dict = self.ai_opponent.get_action(
            self.ai_player,
            self.ai_player_idx,
            deterministic=True
        )
        actions = [(action_idx, param_dict)]

        self.game_env.step_evaluation(self.ai_player, actions, 10, callback)

        if self.game_engine.turn_manager.get_current_player() == self.ai_player:
            self.game_engine.end_turn()

        if on_complete:
            on_complete()
