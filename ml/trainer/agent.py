import numpy as np
import random
from typing import List
import torch
import torch.optim as optim
import torch.nn.functional as F

from ml.storage import ReplayBuffer, ReservoirBuffer
from ml.models import DuelingDQN, AveragePolicy
from ml.trainer.buffer_manager import BufferManager
from ml.utils import update_target


class Agent:
    """
    RL agent with DQN and average policy network.
    """

    def __init__(
            self,
            state_dim: int,
            num_actions: int,
            config
    ):
        self.cfg = config
        self.num_actions = num_actions

        # Core networks
        self.dqn = DuelingDQN(state_dim, num_actions).to(self.cfg.DEVICE)
        self.target_dqn = DuelingDQN(
            state_dim, num_actions).to(self.cfg.DEVICE)
        # Initial sync params to target dqn
        self.update_target_network()

        # Average policy
        self.policy = AveragePolicy(state_dim, num_actions).to(self.cfg.DEVICE)

        # Buffers and optimizers
        self.replay_buffer = ReplayBuffer(self.cfg.BUFFER_SIZE)
        self.reservoir = ReservoirBuffer(self.cfg.BUFFER_SIZE)
        self.rl_optimizer = optim.Adam(self.dqn.parameters(), lr=1e-4)
        self.sl_optimizer = optim.Adam(self.policy.parameters(), lr=1e-4)

        # Buffer manager for temporary state, reward containment till
        # enough samples are met to be flushed into replay and reservoir
        self.buffer_manager = BufferManager(self, self.cfg)

        # Metrics
        self.rl_losses: List[float] = []
        self.sl_losses: List[float] = []

    def select_action(self, state, epsilon: float, best_response: bool = True) -> int:
        """Select action using either DQN or average policy."""
        tensor = torch.FloatTensor(state).to(self.cfg.DEVICE)

        if best_response:
            return self.dqn.act(tensor, epsilon)
        return self.policy.act(tensor)

    def update_networks(self):
        """Update all networks if sufficient data available."""
        if not self._can_update():
            return

        # Normalize the parameters before updating
        torch.nn.utils.clip_grad_norm_(self.policy.parameters(), max_norm=1.0)
        torch.nn.utils.clip_grad_norm_(self.dqn.parameters(), max_norm=1.0)

        rl_loss = self._update_rl_network()
        sl_loss = self._update_sl_network()

        self.rl_losses.append(rl_loss.item())
        self.sl_losses.append(sl_loss.item())

    def _can_update(self) -> bool:
        """Check if buffers have enough samples."""
        min_samples = self.cfg.BATCH_SIZE
        return (
            len(self.replay_buffer) > min_samples and
            len(self.reservoir) > min_samples
        )

    def _update_rl_network(self):
        """Update DQN network."""
        batch = self.replay_buffer.sample(self.cfg.BATCH_SIZE)
        state, action, reward, next_state, done = batch

        # Convert to tensors
        state = torch.FloatTensor(state).to(self.cfg.DEVICE)
        next_state = torch.FloatTensor(next_state).to(self.cfg.DEVICE)
        action = torch.LongTensor(action).to(self.cfg.DEVICE)
        reward = torch.FloatTensor(reward).to(self.cfg.DEVICE)
        done = torch.FloatTensor(done).to(self.cfg.DEVICE)

        # Compute loss
        q_values = self.dqn(state)
        current_q = q_values.gather(1, action.unsqueeze(1)).squeeze(1)

        # Avoid building grad graph for the target network
        with torch.no_grad():
            next_q_values = self.target_dqn(next_state)
            max_next_q = next_q_values.max(1)[0]

        # Additional discount factor
        discount_factor = self.cfg.GAMMA ** self.cfg.MULTI_STEP
        expected_q = reward + discount_factor * max_next_q * (1 - done)

        # Changed MSE loss for Huber loss, avoid huge spikes
        loss = F.smooth_l1_loss(current_q, expected_q)

        # Optimize
        self.rl_optimizer.zero_grad()
        loss.backward()
        self.rl_optimizer.step()

        return loss

    def _update_sl_network(self):
        """Update average policy network."""
        state, action = self.reservoir.sample(self.cfg.BATCH_SIZE)

        state = torch.FloatTensor(state).to(self.cfg.DEVICE)
        action = torch.LongTensor(action).to(self.cfg.DEVICE)

        probs = self.policy(state)
        log_probs = probs.gather(1, action.unsqueeze(1)).log()
        loss = -log_probs.mean()

        self.sl_optimizer.zero_grad()
        loss.backward()
        self.sl_optimizer.step()

        return loss

    def update_target_network(self):
        """Copy weights from DQN to target DQN."""
        update_target(self.dqn, self.target_dqn)

    def select_action_with_mask(
            self,
            state,
            action_mask: np.ndarray,
            epsilon: float,
            best_response: bool = True
    ) -> int:
        """
        Select action with masking.

        Args:
            state: Current state
            action_mask: Boolean array indicating valid actions
            epsilon: Exploration rate
            best_response: Use DQN (True) or policy (False)
        """
        if not np.any(action_mask):
            # No valid actions - should never happen, but fallback
            return 0

        # This assume that batch size will be 1
        tensor = torch.FloatTensor(state).unsqueeze(0).to(self.cfg.DEVICE)
        mask_tensor = torch.FloatTensor(
            action_mask).unsqueeze(0).to(self.cfg.DEVICE)

        if best_response:
            return self._select_with_dqn_masked(tensor, mask_tensor, epsilon)
        else:
            return self._select_with_policy_masked(tensor, mask_tensor)

    def _select_with_dqn_masked(
            self,
            state_tensor: torch.Tensor,
            mask_tensor: torch.Tensor,
            epsilon: float
    ) -> int:
        """DQN selection with masking."""
        q_values = self.dqn(state_tensor)

        # Apply mask (set invalid actions to -inf)
        masked_q = q_values.masked_fill(mask_tensor == 0, float('-inf'))

        assert not torch.isinf(masked_q).all()

        if random.random() < epsilon:
            # Explore: choose randomly from valid actions
            valid_actions = torch.where(mask_tensor[0] == 1)[0]
            return random.choice(valid_actions.tolist())

        # Exploit: choose best valid action
        return masked_q[0].argmax().item()

    def _select_with_policy_masked(
        self,
        state_tensor: torch.Tensor,
        mask_tensor: torch.Tensor
    ) -> int:
        """Policy selection using logit masking BEFORE softmax (Option A)."""
        logits = self.policy.head(self.policy.feature_net(state_tensor))

        # Sanitize logits
        logits = torch.nan_to_num(logits, nan=0.0, posinf=10.0, neginf=-10.0)
        logits = torch.clamp(logits, -10, 10)

        # check for shape mismatches
        assert logits.dim() == 2
        assert logits.shape[-1] == mask_tensor.shape[-1]

        # check for finiteness (corrected assertion)
        assert torch.isfinite(logits).all(), "Logits must be finite"

        # handle edge case: no valid actions
        if mask_tensor.sum().item() == 0:
            return 0

        # mask the logits with -inf
        masked_logits = logits.clone()
        masked_logits = masked_logits.masked_fill(
            mask_tensor == 0, float("-inf"))

        # In case everything is just masked (should be impossible now)
        if torch.isinf(masked_logits).all():
            return 0

        # softmax over valid actions only
        probs = torch.softmax(masked_logits, dim=1)

        # check for finiteness in probabilities (corrected assertion)
        assert torch.isfinite(probs).all(), "Probs must be finite"

        action = torch.multinomial(probs[0], 1).item()
        return action
