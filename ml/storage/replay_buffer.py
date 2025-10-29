import numpy as np
import random

from collections import deque


class ReplayBuffer(object):
    def __init__(self, capacity, store_action_params=False):
        self.buffer = deque(maxlen=capacity)
        self.store_action_params = store_action_params

    def __len__(self):
        return len(self.buffer)

    # If storing action params:
    def push(self, state, action, reward, next_state, done, action_params=None):
        state = np.expand_dims(state, 0)
        next_state = np.expand_dims(next_state, 0)
        if self.store_action_params:
            # store action params as array (1D)
            self.buffer.append(
                (state, action, action_params, reward, next_state, done))
        else:
            self.buffer.append((state, action, reward, next_state, done))

    def sample(self, batch_size):
        items = random.sample(self.buffer, batch_size)
        if self.store_action_params:
            state, action, action_params, reward, next_state, done = zip(
                *items)
            return np.concatenate(state), action, np.concatenate(action_params), reward, np.concatenate(next_state), done
        else:
            state, action, reward, next_state, done = zip(*items)
            return np.concatenate(state), action, reward, np.concatenate(next_state), done
