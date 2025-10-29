"""
Agent module handling RL and IL components.
"""
import numpy as np
import random
from typing import List
import logging
import torch
import torch.optim as optim
import torch.nn.functional as F

from ml.storage import ReplayBuffer, ReservoirBuffer
from ml.models import DuelingDQN, PDQN, AveragePolicy
from ml.trainer.buffer_manager import BufferManager
from ml.utils import update_target


class Agent:
    """
    RL agent with DQN, policy network, and optional PDQN.
    """

    def __init__(
            self,
            state_dim: int,
            num_actions: int,
            param_dim: int,
            config,
            use_pdqn: bool = True
    ):
        self.cfg = config
        self.use_pdqn = use_pdqn
        self.num_actions = num_actions

        # Core networks
        self.dqn = DuelingDQN(state_dim, num_actions).to(self.cfg.DEVICE)
        self.target_dqn = DuelingDQN(
            state_dim, num_actions).to(self.cfg.DEVICE)
        update_target(self.dqn, self.target_dqn)

        # Average policy
        self.policy = AveragePolicy(state_dim, num_actions).to(self.cfg.DEVICE)

        # PDQN components
        if use_pdqn:
            self._initialize_pdqn(state_dim, num_actions, param_dim)

        # Buffers and optimizers
        self.replay_buffer = ReplayBuffer(self.cfg.BUFFER_SIZE)
        self.reservoir = ReservoirBuffer(self.cfg.BUFFER_SIZE)
        self.rl_optimizer = optim.Adam(self.dqn.parameters(), lr=1e-4)
        self.sl_optimizer = optim.Adam(self.policy.parameters(), lr=1e-4)

        self.buffer_manager = BufferManager(
            self,
            self.cfg,
            param_dim if use_pdqn else 0
        )

        # Metrics
        self.rl_losses: List[float] = []
        self.sl_losses: List[float] = []

    def _initialize_pdqn(
            self,
            state_dim: int,
            num_actions: int,
            param_dim: int
    ):
        """Initialize PDQN components."""
        self.pdqn = PDQN(state_dim, num_actions, param_dim).to(self.cfg.DEVICE)
        self.param_buffer = ReplayBuffer(self.cfg.BUFFER_SIZE)

        self.pdqn_critic_opt = optim.Adam(
            self.pdqn.critic.parameters(),
            lr=1e-4
        )
        self.pdqn_actor_opt = optim.Adam(
            self.pdqn.actor.parameters(),
            lr=1e-4
        )
        self.pdqn_alpha_opt = optim.Adam(
            [self.pdqn.log_alpha],
            lr=1e-4
        )

    def select_action(
            self,
            state,
            epsilon: float,
            best_response: bool = True
    ) -> int:
        """Select action using either DQN or average policy."""
        tensor = torch.FloatTensor(state).to(self.cfg.DEVICE)

        if best_response:
            return self.dqn.act(tensor, epsilon)
        return self.policy.act(tensor)

    def select_continuous_params(self, state):
        """Select continuous parameters using PDQN actor."""
        if not self.use_pdqn:
            return None

        state_tensor = torch.FloatTensor(
            state).unsqueeze(0).to(self.cfg.DEVICE)

        with torch.no_grad():
            cont_params, _, _ = self.pdqn.actor.sample(state_tensor)

        return cont_params.squeeze(0).cpu().numpy()

    def update_networks(self):
        """Update all networks if sufficient data available."""
        if not self._can_update():
            return

        torch.nn.utils.clip_grad_norm_(self.policy.parameters(), max_norm=1.0)
        torch.nn.utils.clip_grad_norm_(self.dqn.parameters(), max_norm=1.0)

        if self.use_pdqn and hasattr(self, "pqdn"):
            torch.nn.utils.clip_grad_norm_(
                self.pqdn.parameters(), max_norm=1.0)

        self._check_and_reset_weights(self.policy, "policy")
        self._check_and_reset_weights(self.dqn, "dqn")

        if self.use_pdqn and hasattr(self, "pqdn"):
            self._check_and_reset_weights(self.pdqn.actor, "pdqn.actor")
            self._check_and_reset_weights(self.pdqn.critic, "pdqn.critic")

        rl_loss = self._update_rl_network()
        sl_loss = self._update_sl_network()

        self.rl_losses.append(rl_loss.item())
        self.sl_losses.append(sl_loss.item())

        if self.use_pdqn:
            self._update_pdqn_network()

    @staticmethod
    def _check_and_reset_weights(model, model_name="model"):
        for name, param in model.named_parameters():
            if not torch.isfinite(param).all():
                logging.warning(f"⚠️ NaN detected in {model_name}.{
                                name}, resetting weights.")
                if param.ndim >= 2:
                    torch.nn.init.xavier_uniform_(param)
                else:
                    torch.nn.init.zeros_(param)

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
        next_q_values = self.target_dqn(next_state)

        current_q = q_values.gather(1, action.unsqueeze(1)).squeeze(1)
        max_next_q = next_q_values.max(1)[0]

        discount_factor = self.cfg.GAMMA ** self.cfg.MULTI_STEP
        expected_q = reward + discount_factor * max_next_q * (1 - done)

        loss = F.smooth_l1_loss(current_q, expected_q.detach())

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

    def _update_pdqn_network(self):
        """Update PDQN networks."""
        self.pdqn.update(
            self.param_buffer,
            critic_optimizer=self.pdqn_critic_opt,
            actor_optimizer=self.pdqn_actor_opt,
            alpha_optimizer=self.pdqn_alpha_opt,
            batch_size=self.cfg.BATCH_SIZE,
            gamma=self.cfg.GAMMA,
            tau=self.cfg.TAU
        )

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

        tensor = torch.FloatTensor(state).unsqueeze(0).to(self.cfg.DEVICE)
        mask_tensor = torch.FloatTensor(
            action_mask).unsqueeze(0).to(self.cfg.DEVICE)

        if best_response:
            return self._select_with_dqn_masked(
                tensor, mask_tensor, epsilon
            )
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

        if random.random() < epsilon:
            # Explore: choose randomly from valid actions
            valid_actions = torch.where(mask_tensor[0] == 1)[0]
            return random.choice(valid_actions.tolist())
        else:
            # Exploit: choose best valid action
            return masked_q[0].argmax().item()

    def _select_with_policy_masked(self, state_tensor: torch.Tensor, mask_tensor: torch.Tensor) -> int:
        """Policy selection with masking and detailed debug logging."""
        try:
            # Step 1: Forward pass
            probs = self.policy(state_tensor)

            # --- DEBUG LOGS ---
            # logging.info(f"Policy output shape: {probs.shape}, dtype: {probs.dtype}")
            # logging.info(f"Mask shape: {mask_tensor.shape}, dtype: {mask_tensor.dtype}")
            # logging.info(f"Mask sum (valid actions): {mask_tensor.sum().item()}")

            # Step 2: Validate shapes
            if probs.dim() != 2:
                logging.error(f"Unexpected policy output shape: {probs.shape}")
                return 0
            if probs.shape[-1] != mask_tensor.shape[-1]:
                logging.error(f"Shape mismatch: probs {
                              probs.shape} vs mask {mask_tensor.shape}")
                return 0

            # Step 3: Check for invalid values
            if not torch.isfinite(probs).all():
                logging.error(
                    f"Non-finite values in policy output: min={probs.min().item()}, max={probs.max().item()}")
                return 0

            # Step 4: Apply masking
            masked_probs = probs[0] * mask_tensor[0]
            prob_sum = masked_probs.sum().item()
            # logging.info(f"Sum of masked probs: {prob_sum:.6f}")

            # Step 5: Handle invalid / degenerate cases
            if mask_tensor.sum().item() == 0:
                logging.warning(
                    "Mask tensor has no valid actions! Falling back to random action.")
                return random.randint(0, probs.shape[-1] - 1)

            if prob_sum < 1e-8:
                valid_actions = torch.where(mask_tensor[0] == 1)[0]
                logging.warning(
                    "All masked probabilities are near zero. Using uniform over valid actions.")
                return random.choice(valid_actions.cpu().tolist())

            # Step 6: Normalize and sample
            masked_probs = masked_probs / prob_sum
            masked_probs = torch.clamp(masked_probs, min=1e-10)
            masked_probs = masked_probs / masked_probs.sum()

            # --- DEBUG LOGS ---
            # logging.info(f"Final prob dist: min={masked_probs.min().item():.6f}, max={masked_probs.max().item():.6f}, sum={masked_probs.sum().item():.6f}")

            action = torch.multinomial(masked_probs, 1).item()
            # logging.info(f"Selected action: {action}")
            return action

        except Exception as e:
            logging.exception(f"Exception in _select_with_policy_masked: {e}")
            return 0
