"""
Buffer management for multi-step transitions.
"""
from collections import deque
from typing import Optional
import numpy as np

from ml.utils import flatten_action_params


class BufferManager:
    """
    Manages temporary storage of transitions for multi-step returns.
    """

    def __init__(self, agent, config, param_dim: int):
        self.agent = agent
        self.param_dim = param_dim
        self.cfg = config

        # Deques for multi-step accumulation
        self.state_deque = deque(maxlen=self.cfg.MULTI_STEP)
        self.reward_deque = deque(maxlen=self.cfg.MULTI_STEP)
        self.action_deque = deque(maxlen=self.cfg.MULTI_STEP)

    def append_transition(
        self,
        state,
        action: int,
        reward: float,
        next_state,
        done: bool,
        param_vec: Optional[np.ndarray] = None
    ):
        """
        Add transition and push to buffers when appropriate.

        Args:
            state: Current state
            action: Action taken
            reward: Reward received
            next_state: Next state
            done: Whether episode is done
            param_vec: Continuous action parameters (optional)
        """
        self.state_deque.append(state)
        self.reward_deque.append(reward)
        self.action_deque.append(action)

        # Push to replay buffer when ready
        if self._should_push_to_replay(done):
            self._push_to_replay_buffer(next_state, done)

        # Push to param buffer if using PDQN
        if param_vec is not None:
            self._push_to_param_buffer(
                state,
                param_vec,
                reward,
                next_state,
                done
            )

    def _should_push_to_replay(self, done: bool) -> bool:
        """Check if ready to push to replay buffer."""
        return len(self.state_deque) == self.cfg.MULTI_STEP or done

    def _push_to_replay_buffer(self, next_state, done: bool):
        """Push multi-step transition to replay buffer."""
        discounted_reward = self._compute_discounted_reward()

        self.agent.replay_buffer.push(
            self.state_deque[0],
            self.action_deque[0],
            discounted_reward,
            next_state,
            float(done)
        )

    def _compute_discounted_reward(self) -> float:
        """Compute discounted sum of rewards in deque."""
        return sum(
            reward * (self.cfg.GAMMA ** i)
            for i, reward in enumerate(self.reward_deque)
        )

    def _push_to_param_buffer(
        self,
        state,
        param_vec: np.ndarray,
        reward: float,
        next_state,
        done: bool
    ):
        """Push continuous parameter transition to param buffer."""
        param_vec_flat = flatten_action_params(
            np.array(param_vec),
            self.param_dim
        )

        self.agent.param_buffer.push(
            state,
            param_vec_flat,
            reward,
            next_state,
            float(done)
        )

    def clear(self):
        """Clear all deques."""
        self.state_deque.clear()
        self.reward_deque.clear()
        self.action_deque.clear()
