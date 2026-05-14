import numpy as np
import random
import math
from collections import deque
import itertools
from typing import Tuple


class ReservoirBuffer:
    """Reservoir buffer for sampling experiences from a stream."""

    def __init__(self, capacity: int) -> None:
        """Initialize the ReservoirBuffer.

        Args:
            capacity: The maximum capacity of the buffer.
        """
        self.buffer: deque = deque(maxlen=capacity)

    def push(self, state: np.ndarray, action: int) -> None:
        """Add an experience to the buffer.

        Args:
            state: The state.
            action: The action taken.
        """
        state = np.expand_dims(state, 0)
        self.buffer.append((state, action))

    def sample(self, batch_size: int) -> Tuple[np.ndarray, Tuple]:
        """Sample a batch of experiences using efficient reservoir sampling.

        Args:
            batch_size: The number of experiences to sample.

        Returns:
            A tuple of (states, actions).
        """
        n = len(self.buffer)
        reservoir = list(itertools.islice(self.buffer, 0, batch_size))
        threshold = batch_size * 4
        idx = batch_size
        while idx < n and idx <= threshold:
            m = random.randint(0, idx)
            if m < batch_size:
                reservoir[m] = self.buffer[idx]
            idx += 1

        while idx < n:
            p = float(batch_size) / idx
            u = random.random()
            g = math.floor(math.log(u) / math.log(1 - p))
            idx = idx + int(g)
            if idx < n:
                k = random.randint(0, batch_size - 1)
                reservoir[k] = self.buffer[idx]
            idx += 1
        state, action = zip(*random.sample(self.buffer, batch_size))
        return np.concatenate(state), action

    def __len__(self) -> int:
        """Return the current size of the buffer."""
        return len(self.buffer)
