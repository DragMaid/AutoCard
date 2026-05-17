import numpy as np
from collections import deque


class BatchStorage:
    """
    Storage for actors to support multi-step learning and efficient priority calculation.
    Saving Q values with experiences enablealculation
    without re-calculating Q-values for each state.
    """

    def __init__(self, n_steps, gamma=0.99):
        self.state_deque = deque(maxlen=n_steps)
        self.action_deque = deque(maxlen=n_steps)
        self.reward_deque = deque(maxlen=n_steps)
        self.q_values_deque = deque(maxlen=n_steps)
        self.states = []
        self.actions = []
        self.rewards = []
        self.next_states = []
        self.dones = []
        self.q_values = []
        self.next_q_values = []

        self.n_steps = n_steps
        self.gamma = gamma

    def add(self, state, reward, action, done, q_values):
        if len(self.state_deque) == self.n_steps or done:
            t0_state = self.state_deque[0]
            t0_reward = self.multi_step_reward(*self.reward_deque, reward)
            t0_action = self.action_deque[0]
            t0_q_values = self.q_values_deque[0]
            tp_n_state = state
            tp_n_q_values = q_values
            done = np.float32(done)
            self.states.append(t0_state)
            self.actions.append(t0_action)
            self.rewards.append(t0_reward)
            self.next_states.append(tp_n_state)
            self.dones.append(done)
            self.q_values.append(t0_q_values)
            self.next_q_values.append(tp_n_q_values)

        if done:
            self.state_deque.clear()
            self.reward_deque.clear()
            self.action_deque.clear()
        else:
            self.state_deque.append(state)
            self.reward_deque.append(reward)
            self.action_deque.append(action)
            self.q_values_deque.append(q_values)

    def reset(self):
        self.states = []
        self.actions = []
        self.rewards = []
        self.next_states = []
        self.dones = []
        self.q_values = []
        self.next_q_values = []

    # TODO: I think you should
    def compute_priorities(self):
        # TODO: Should I seperate this method from BatchStorage class?
        actions = np.array(self.actions)
        rewards = np.array(self.rewards)
        dones = np.array(self.dones)
        q_values = np.stack(self.q_values)
        next_q_values = np.stack(self.next_q_values)

        q_a_values = q_values[(range(len(q_values)), actions)]
        next_q_a_values = next_q_values.max(1)
        expected_q_a_values = rewards + \
            (self.gamma ** self.n_steps) * next_q_a_values * (1 - dones)
        td_error = expected_q_a_values - q_a_values
        prios = np.abs(td_error) + 1e-6
        return prios

    def make_batch(self):
        prios = self.compute_priorities()
        batch = [self.states, self.actions,
                 self.rewards, self.next_states, self.dones]
        return batch, prios

    def multi_step_reward(self, *rewards):
        ret = 0.
        for idx, reward in enumerate(rewards):
            ret += reward * (self.gamma ** idx)
        return ret

    def __len__(self):
        return len(self.states)
