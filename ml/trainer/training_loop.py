import torch
import logging
import random
from typing import Any, Tuple
from ml.trainer.agent import Agent
from ml.trainer.episode_manager import EpisodeManager
from ml.utils import epsilon_scheduler, save_model
from ml.config import Config as ml_config
from ml.environment.environment import GameEnv
from core.data.player import Player

logger = logging.getLogger(__name__)


class TrainingLoop:
    """Orchestrates the main training loop for multi-agent RL."""

    def __init__(
        self,
        env: GameEnv,
        agent: Agent,
        episode_manager: EpisodeManager,
    ):
        """Initializes TrainingLoop.

        Args:
            env: Environment.
            agents: List of agents.
            episode_manager: Episode manager.
        """
        self.env = env
        self.agent = agent
        self.episode_manager = episode_manager

        self.epsilon_scheduler = epsilon_scheduler(
            eps_start=ml_config.EPS_START,
            eps_final=ml_config.EPS_FINAL,
            eps_decay=ml_config.EPS_DECAY
        )

    def run(self) -> None:
        """Executes the main training loop."""
        self.env.reset()

        for frame_idx in range(1, ml_config.MAX_FRAMES + 1):
            epsilon = self.epsilon_scheduler(frame_idx)
            acting_player = self.env.get_acting_player()
            state = self.env.get_state(acting_player)
            _, done = self._execute_step(
                player=acting_player,
                state=state,
                epsilon=epsilon
            )

            if frame_idx % ml_config.TRAIN_FREQ == 0:
                if self.agent.can_update_rl():
                    self.agent.update_rl_network()

                if self.agent.can_update_sl():
                    self.agent.update_sl_network()

            if frame_idx % ml_config.UPDATE_TARGET_FREQ == 0:
                self.agent.update_target_network()

            if done or self._episode_too_long():
                logger.info(f"Episode ended at frame {frame_idx}!")
                self.episode_manager.finalize_episode()
                self.agent.buffer_manager.clear()
                self.env.reset()

            if frame_idx % ml_config.EVALUATION_INTERVAL == 0:
                self.save_checkpoint(frame_idx)

    def _execute_step(self, player: Player, state: Any, epsilon: float) -> tuple[Any, bool]:
        """Executes a single training step for all agents.

        Args:
            player: Currently acting player.
            state: Current state.
            epsilon: Exploration probability.

        Returns:
            Next state and completion flag.
        """
        # Decide whether to use the best policy based decision or to explore (random)
        best_response = random.random() >= ml_config.ETA

        # Select actions for all agents
        action_id, q_values = self._select_action(
            player=player,
            state=state,
            epsilon=epsilon,
            best_response=best_response
        )

        # Step environment
        assert action_id is not None
        next_state, reward, done = self.env.step(action_id)

        # Record winner if episode done
        if done:
            self._record_winner()

        # Store transitions for agents
        self.agent.buffer_manager.append_transition(
            state=state,
            action=action_id,
            reward=reward,
            next_state=next_state,
            done=done
        )
        # Store to reservoir if its not best response
        if not best_response:
            self.agent.reservoir.push(state, action_id)

        player_idx = self.env.get_player_index(player)
        self.episode_manager.add_reward(player_idx, reward)
        return next_state, done

    def _select_action(
        self,
        player: Player,
        state: Any,
        epsilon: float,
        best_response: bool
    ) -> Tuple[str, torch.Tensor]:
        """Select action for the given player.

        Args:
            agent: Agent
            state: State
            epsilon: Exploration probability.
            best_response: Best response flag.

        Returns:
            Singular action_id and q values or probability logits
        """
        # TODO: update the get legal action since its being used too sparingly
        mask, _ = self.env.get_legal_actions(player)
        action_id, q_logits = self.agent.select_action_with_mask(
            state=state,
            action_mask=mask,
            epsilon=epsilon,
            best_response=best_response
        )
        return action_id, q_logits

    def _record_winner(self) -> None:
        """Records the winner of the episode."""
        winner = self.env.get_winner()
        if winner is not None:
            self.episode_manager.record_win(winner)

    def _episode_too_long(self) -> bool:
        """Checks if episode has exceeded max length."""
        return (
            self.episode_manager.current_episode_length >=
            ml_config.MAX_ACTIONS_PER_EPISODE
        )

    def save_checkpoint(self, frame_idx: int) -> None:
        """Evaluates current performance and saves models."""
        save_folder = ml_config.CHECKPOINT_PATH.parent
        save_path = save_folder / f"cp_{frame_idx}.pth"
        save_model(self.agent, save_path)
