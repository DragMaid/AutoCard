from __future__ import annotations

from collections import deque
from typing import Any, TYPE_CHECKING
from ml.config import Config as ml_config

if TYPE_CHECKING:
    from ml.trainer.agent import Agent


class BufferManager:
    """Manages temporary storage of transitions for multi-step returns.

    Attributes:
        agent: The agent instance.
        state_deque (deque): Deque of states.
        reward_deque (deque): Deque of rewards.
        action_deque (deque): Deque of actions.
    """

    def __init__(self, agent: Agent) -> None:
        """Initializes the BufferManager.

        Args:
            agent: The Agent instance.
        """
        self.agent = agent

        # Deques for multi-step accumulation
        self.state_deque = deque(maxlen=ml_config.MULTI_STEP)
        self.reward_deque = deque(maxlen=ml_config.MULTI_STEP)
        self.action_deque = deque(maxlen=ml_config.MULTI_STEP)

    def append_transition(
        self,
        state: Any,
        action: int,
        reward: float,
        next_state: Any,
        done: bool
    ) -> None:
        """Adds a transition and pushes to buffers when appropriate.

        Args:
            state (Any): Current state.
            action (int): Action taken.
            reward (float): Reward received.
            next_state (Any): Next state.
            done (bool): Whether the episode is done.
        """
        self.state_deque.append(state)
        self.reward_deque.append(reward)
        self.action_deque.append(action)

        # Push to replay buffer when ready
        if self._should_push_to_replay(done):
            self._push_to_replay_buffer(next_state, done)

    def _should_push_to_replay(self, done: bool) -> bool:
        """Checks if ready to push to replay buffer.

        Args:
            done (bool): Whether the episode is done.

        Returns:
            bool: True if ready, False otherwise.
        """
        return len(self.state_deque) == ml_config.MULTI_STEP or done

    def _push_to_replay_buffer(self, next_state: Any, done: bool) -> None:
        """Pushes multi-step transition to replay buffer.

        Args:
            next_state (Any): Next state.
            done (bool): Whether the episode is done.
        """
        discounted_reward = self._compute_discounted_reward()

        self.agent.replay_buffer.push(
            self.state_deque[0],
            self.action_deque[0],
            discounted_reward,
            next_state,
            float(done)
        )

    def _compute_discounted_reward(self) -> float:
        """Computes discounted sum of rewards in the reward deque.

        Returns:
            float: The computed discounted reward.
        """
        return sum(
            reward * (ml_config.GAMMA ** i)
            for i, reward in enumerate(self.reward_deque)
        )

    def clear(self) -> None:
        """Clears all deques."""
        self.state_deque.clear()
        self.reward_deque.clear()
        self.action_deque.clear()
