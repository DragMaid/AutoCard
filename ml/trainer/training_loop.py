import time
import random
import logging
from typing import List, Dict, Any

from ml.trainer.agent import Agent
from ml.trainer.episode_manager import EpisodeManager
from ml.utils import epsilon_scheduler, log_training_metrics, save_model

from ml.config import Config as ml_config
from ml.environment.environment import GameEnv


class TrainingLoop:
    """Orchestrates the main training loop for multi-agent RL."""

    def __init__(
        self,
        env: GameEnv,
        agents: List[Agent],
        episode_manager: EpisodeManager,
        mlflow_enabled: bool = False
    ):
        """Initializes TrainingLoop.

        Args:
            env: Environment.
            agents: List of agents.
            episode_manager: Episode manager.
        """
        self.env = env
        self.agents = agents
        self.episode_manager = episode_manager
        self.mlflow_enabled = mlflow_enabled

        self.epsilon_scheduler = epsilon_scheduler(
            ml_config.EPS_START,
            ml_config.EPS_FINAL,
            ml_config.EPS_DECAY
        )

    def run(self) -> None:
        """Executes the main training loop."""
        states = list(self.env.reset())
        start_time = time.time()

        for frame_idx in range(1, ml_config.MAX_FRAMES + 1):
            epsilon = self.epsilon_scheduler(frame_idx)

            # Execute single step
            states, done = self._execute_step(states, epsilon)

            # NOTE: the training process will eventually slow down
            # due to the replay buffer and reservoir filling up
            # Update networks
            if frame_idx % ml_config.TRAIN_FREQ == 0:
                self._update_all_agents()

            # Periodic target network updates
            if frame_idx % ml_config.UPDATE_TARGET_FREQ == 0:
                self._update_target_networks()

            # Handle episode completion
            if done or self._episode_too_long():
                self._handle_episode_end(done)
                states = list(self.env.reset())

            # Periodic evaluation and checkpointing
            if frame_idx % ml_config.EVALUATION_INTERVAL == 0:
                elapsed = time.time()-start_time
                self._evaluate_and_save(frame_idx, duration=elapsed)
                start_time = time.time()

    def _execute_step(self, states: List[Any], epsilon: float) -> tuple[List[Any], bool]:
        """Executes a single training step for all agents.

        Args:
            states: Current states.
            epsilon: Exploration probability.

        Returns:
            Next states and completion flag.
        """
        # Decide whether to use the best policy based decision or to explore (random)
        best_response = random.random() >= ml_config.ETA

        # Select actions for all agents
        env_actions, _ = self._select_all_actions(
            self.agents, states, epsilon, best_response)

        # Step environment
        next_states, rewards, done, info = self.env.step(env_actions)

        # Record winner if episode done
        if done:
            self._record_winner()

        # Store transitions for agents
        self._store_transitions(
            states,
            env_actions,
            rewards,
            next_states,
            done,
            best_response,
            acting_idx=info.get("acting_player_idx", -1)
        )

        return next_states, done

    def _select_all_actions(
        self,
        agents: List[Agent],
        states: List[Any],
        epsilon: float,
        best_response: bool
    ) -> Dict[str, List[tuple[int, None]]]:
        """Selects actions for all agents.

        Args:
            agents: List of agents.
            states: List of states.
            epsilon: Exploration probability.
            best_response: Best response flag.

        Returns:
            Dictionary of actions.
        """
        env_actions = {}

        # States here has batch size >= 1 but we will be processing each independently
        for agent_idx, (agent, state) in enumerate(zip(agents, states)):
            # Get current action mask from environment
            mask, _ = self.env.get_legal_actions(agent_idx)

            # Select discrete action ID
            action_id = agent.select_action_with_mask(
                state,
                mask,
                epsilon,
                best_response
            )

            # Store for environment (1-indexed players)
            player_id = str(agent_idx + 1)
            env_actions[player_id] = [(int(action_id), None)]

        return env_actions

    def _store_transitions(
        self,
        states: List[Any],
        actions: Dict[str, Any],
        rewards: List[float],
        next_states: List[Any],
        done: bool,
        best_response: bool,
        acting_idx: int = -1
    ) -> None:
        """Stores transitions in agent buffers."""
        for agent_idx, agent in enumerate(self.agents):
            # Only store transition if this agent was acting OR if the episode is done
            if agent_idx != acting_idx and not done:
                continue

            # Extract action info for this agent
            player_id = str(agent_idx + 1)
            action_id, _ = actions[player_id][0]

            # Add to buffer manager
            agent.buffer_manager.append_transition(
                states[agent_idx],
                action_id,
                rewards[agent_idx],
                next_states[agent_idx],
                done
            )

            # Add to reservoir if not best response (only for acting agent)
            if not best_response and agent_idx == acting_idx:
                agent.reservoir.push(states[agent_idx], action_id)

            # Track episode reward
            self.episode_manager.add_reward(agent_idx, rewards[agent_idx])

    def _record_winner(self) -> None:
        """Records the winner of the episode."""
        winner = self.env.get_winner()
        if winner >= 0:
            self.episode_manager.record_win(winner)

    def _update_all_agents(self) -> None:
        """Updates networks for all agents."""
        for agent in self.agents:
            agent.update_networks()

    def _update_target_networks(self) -> None:
        """Updates target networks for all agents."""
        for agent in self.agents:
            agent.update_target_network()

    def _episode_too_long(self) -> bool:
        """Checks if episode has exceeded max length."""
        return (
            self.episode_manager.current_episode_length >=
            ml_config.MAX_ACTIONS_PER_TURN
        )

    def _handle_episode_end(self, done: bool) -> None:
        """Handles end of episode cleanup."""
        self.episode_manager.finalize_episode()

        # Clear agent buffer managers
        for agent in self.agents:
            agent.buffer_manager.clear()

    def _evaluate_and_save(self, frame_idx: int, duration: float) -> None:
        """Evaluates current performance and saves models."""
        stats = self.episode_manager.get_statistics()

        # Log metrics
        log_training_metrics(
            frame_idx,
            ml_config.MAX_FRAMES,
            stats["rewards"],
            stats["episode_lengths"],
            [agent.rl_losses for agent in self.agents],
            [agent.sl_losses for agent in self.agents],
            stats["wins"],
            ml_config.UPDATE_TARGET_FREQ,
            duration,
            logging,
            self.mlflow_enabled
        )

        # Save models
        models = {
            f"agent_{i}": agent.dqn
            for i, agent in enumerate(self.agents)
        }
        policies = {
            f"agent_{i}": agent.policy
            for i, agent in enumerate(self.agents)
        }

        save_folder = ml_config.CHECKPOINT_PATH.parent
        save_path = save_folder / f"cp_{frame_idx}.pth"
        save_model(logging, models=models, policies=policies,
                   checkpoint_path=save_path)
