import numpy as np
import random
from collections import deque
from typing import Tuple


class ReplayBuffer:
    """Replay buffer for storing and sampling reinforcement learning experiences."""

    def __init__(self, capacity: int) -> None:
        """Initialize the ReplayBuffer.

        Args:
            capacity: The maximum capacity of the buffer.
        """
        self.buffer: deque = deque(maxlen=capacity)

    def __len__(self) -> int:
        """Return the current size of the buffer."""
        return len(self.buffer)

    def push(self, state: np.ndarray, action: int, reward: float, next_state: np.ndarray, done: bool) -> None:
        """Add an experience to the buffer.

        Args:
            state: The current state.
            action: The action taken.
            reward: The reward received.
            next_state: The next state.
            done: Whether the episode is over.
        """
        state = np.expand_dims(state, 0)
        next_state = np.expand_dims(next_state, 0)
        self.buffer.append((state, action, reward, next_state, done))

    def sample(self, batch_size: int) -> Tuple[np.ndarray, Tuple, Tuple, np.ndarray, Tuple]:
        """Sample a batch of experiences from the buffer.

        Args:
            batch_size: The number of experiences to sample.

        Returns:
            A tuple of (states, actions, rewards, next_states, dones).
        """
        items = random.sample(self.buffer, batch_size)
        state, action, reward, next_state, done = zip(*items)
        return np.concatenate(state), action, reward, np.concatenate(next_state), done
