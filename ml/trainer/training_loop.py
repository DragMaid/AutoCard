import time
import random
import logging
from typing import List, Dict

from ml.trainer.agent import Agent
from ml.trainer.action_mapper import ActionMapper
from ml.trainer.episode_manager import EpisodeManager
from ml.utils import epsilon_scheduler, log_training_metrics, save_model


class TrainingLoop:
    """
    Orchestrates the main training loop for multi-agent RL.
    """

    MAX_STEPS_PER_EPISODE = 1000

    def __init__(
        self,
        env,
        agents: List[Agent],
        action_mapper: ActionMapper,
        episode_manager: EpisodeManager,
        config
    ):
        self.env = env
        self.agents = agents
        self.action_mapper = action_mapper
        self.episode_manager = episode_manager
        self.cfg = config

        self.epsilon_scheduler = epsilon_scheduler(
            self.cfg.EPS_START,
            self.cfg.EPS_FINAL,
            self.cfg.EPS_DECAY
        )

    def run(self):
        """Execute the main training loop."""
        states = list(self.env.reset())
        start_time = time.time()

        for frame_idx in range(1, self.cfg.MAX_FRAMES + 1):
            epsilon = self.epsilon_scheduler(frame_idx)

            # Execute single step
            states, done = self._execute_step(states, epsilon)

            # Update networks
            self._update_all_agents()

            # Periodic target network updates
            if frame_idx % self.cfg.UPDATE_TARGET_FREQ == 0:
                self._update_target_networks()

            # Handle episode completion
            if done or self._episode_too_long():
                self._handle_episode_end(done)
                states = list(self.env.reset())

            # Periodic evaluation and checkpointing
            if frame_idx % self.cfg.EVALUATION_INTERVAL == 0:
                self._evaluate_and_save(
                    frame_idx, duration=time.time()-start_time)
                start_time = time.time()

    def _execute_step(self, states: List, epsilon: float):
        """Execute a single training step for all agents."""
        best_response = random.random() >= self.cfg.ETA

        # Select actions for all agents
        actions, selected_params = self._select_all_actions(
            self.agents, states, epsilon, best_response)

        # Step environment
        next_states, rewards, done, info = self.env.step(actions)

        # Record winner if episode done
        if done:
            self._record_winner()

        # Store transitions for all agents
        self._store_transitions(
            states,
            actions,
            rewards,
            next_states,
            done,
            best_response,
            selected_params
        )

        return next_states, done

    def _select_all_actions(
        self,
        agents: List[Agent],
        states: List,
        epsilon: float,
        best_response: bool
    ) -> Dict:
        """Select actions for all agents."""
        env_actions = {}
        selected_params = {}

        for agent_idx, (agent, state) in enumerate(zip(agents, states)):
            # Get current action mask from environment
            mask, legal_params = self.env.get_legal_actions(agent_idx)

            # Select discrete action
            discrete_action = agent.select_action_with_mask(
                state,
                mask,
                epsilon,
                best_response
            )

            # Select continuous parameters if using PDQN
            cont_params = agent.select_continuous_params(state)
            selected_params[agent_idx] = cont_params

            # Map to environment action
            action_idx, param_dict = self.action_mapper.map(
                agent_idx,
                discrete_action,
                cont_params,
                legal_params
            )

            # Store for environment (1-indexed players)
            player_id = str(agent_idx + 1)
            env_actions[player_id] = [(int(action_idx), param_dict)]

        return env_actions, selected_params

    def _store_transitions(
        self,
        states: List,
        actions: Dict,
        rewards: List,
        next_states: List,
        done: bool,
        best_response: bool,
        selected_params: List,
    ):
        """Store transitions in agent buffers."""
        for agent_idx, agent in enumerate(self.agents):
            # Extract action info for this agent
            player_id = str(agent_idx + 1)
            action_idx, _ = actions[player_id][0]

            # Get continuous params if PDQN
            cont_params = selected_params.get(agent_idx)

            # Add to buffer manager
            agent.buffer_manager.append_transition(
                states[agent_idx],
                action_idx,
                rewards[agent_idx],
                next_states[agent_idx],
                done,
                cont_params
            )

            # Add to reservoir if not best response
            if not best_response:
                agent.reservoir.push(states[agent_idx], action_idx)

            # Track episode reward
            self.episode_manager.add_reward(agent_idx, rewards[agent_idx])

    def _record_winner(self):
        """Record the winner of the episode."""
        winner = self.env.get_winner()
        if winner >= 0:
            self.episode_manager.record_win(winner)

    def _update_all_agents(self):
        """Update networks for all agents."""
        for agent in self.agents:
            agent.update_networks()

    def _update_target_networks(self):
        """Update target networks for all agents."""
        for agent in self.agents:
            agent.update_target_network()

    def _episode_too_long(self) -> bool:
        """Check if episode has exceeded max length."""
        return (
            self.episode_manager.current_episode_length >=
            self.MAX_STEPS_PER_EPISODE
        )

    def _handle_episode_end(self, done: bool):
        """Handle end of episode cleanup."""
        self.episode_manager.finalize_episode()

        # Clear agent buffer managers
        for agent in self.agents:
            agent.buffer_manager.clear()

    def _evaluate_and_save(self, frame_idx: int, duration):
        """Evaluate current performance and save models."""
        stats = self.episode_manager.get_statistics()

        # Log metrics
        log_training_metrics(
            frame_idx,
            self.cfg.MAX_FRAMES,
            stats["rewards"],
            stats["episode_lengths"],
            [agent.rl_losses for agent in self.agents],
            [agent.sl_losses for agent in self.agents],
            stats["wins"],
            self.cfg.UPDATE_TARGET_FREQ,
            duration,
            logging
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

        save_model(logging, models=models, policies=policies,
                   checkpoint_path=self.cfg.CHECKPOINT_PATH)
