import numpy as np
import random
from typing import Tuple
import torch
import torch.optim as optim
import torch.nn.functional as F

from ml.storage import ReplayBuffer, ReservoirBuffer
from ml.models import DuelingDQN, AveragePolicy
from ml.models.state_encoder import GameStateEncoder
from ml.environment.encoder import get_card_feature_dim, get_player_feature_dim
from ml.trainer.buffer_manager import BufferManager

from core.config import Config as game_config
from ml.config import Config as ml_config


class Agent:
    """RL agent with DQN and average policy network."""

    def __init__(self, state_dim: int, num_actions: int):
        """Initializes Agent.

        Args:
            state_dim: State dimension.
            num_actions: Number of actions.
        """
        self.num_actions = num_actions

        # Initialize GameStateEncoder
        card_dim = get_card_feature_dim()
        # Times 2 since there are 2 players
        player_dim = get_player_feature_dim() * 2
        self.encoder = GameStateEncoder(
            card_dim=card_dim,
            player_dim=player_dim,
            max_hand_cards=game_config.MAX_HAND_CARDS,
            max_board_cards=game_config.ROWS * game_config.COLS
        ).to(ml_config.DEVICE)

        # Core networks
        self.dqn = DuelingDQN(self.encoder, num_actions).to(ml_config.DEVICE)
        self.target_dqn = DuelingDQN(
            self.encoder, num_actions).to(ml_config.DEVICE)
        # Initial sync params to target dqn
        self.update_target_network()

        # Average policy
        self.policy = AveragePolicy(
            self.encoder, num_actions).to(ml_config.DEVICE)

        # TODO: put these things outside instead
        # Buffers and optimizers
        self.replay_buffer = ReplayBuffer(ml_config.BUFFER_SIZE)
        self.reservoir = ReservoirBuffer(ml_config.BUFFER_SIZE)
        self.rl_optimizer = optim.Adam(self.dqn.parameters(), lr=1e-4)
        self.sl_optimizer = optim.Adam(self.policy.parameters(), lr=1e-4)

        # Buffer manager for temporary state, reward containment till
        # enough samples are met to be flushed into replay and reservoir
        self.buffer_manager = BufferManager(self)

    def select_action(self, state: np.ndarray, epsilon: float, best_response: bool = True) -> int:
        """Selects action using either DQN or average policy.

        Args:
            state: Current state.
            epsilon: Exploration probability.
            best_response: Use DQN or average policy.

        Returns:
            Selected action.
        """
        tensor = torch.FloatTensor(state).to(ml_config.DEVICE)

        if best_response:
            return self.dqn.act(tensor, epsilon)
        return self.policy.act(tensor)

    def update_networks(self) -> None:
        """Updates all networks if sufficient data available."""
        if not self._can_update():
            return

        # Normalize the parameters before updating
        torch.nn.utils.clip_grad_norm_(self.policy.parameters(), max_norm=1.0)
        torch.nn.utils.clip_grad_norm_(self.dqn.parameters(), max_norm=1.0)

        self._update_rl_network()
        self._update_sl_network()

    def _can_update(self) -> bool:
        """Checks if buffers have enough samples.

        Returns:
            Boolean indicating if update is possible.
        """
        min_samples = ml_config.BATCH_SIZE
        return (
            len(self.replay_buffer) > min_samples and
            len(self.reservoir) > min_samples
        )

    def _update_rl_network(self) -> torch.Tensor:
        """Updates DQN network.

        Returns:
            Loss tensor.
        """
        # TODO: move the loss calculation somewhere else
        batch = self.replay_buffer.sample(ml_config.BATCH_SIZE)
        state, action, reward, next_state, done = batch

        # Convert to tensors
        state = torch.FloatTensor(state).to(ml_config.DEVICE)
        next_state = torch.FloatTensor(next_state).to(ml_config.DEVICE)
        action = torch.LongTensor(action).to(ml_config.DEVICE)
        reward = torch.FloatTensor(reward).to(ml_config.DEVICE)
        done = torch.FloatTensor(done).to(ml_config.DEVICE)

        # Compute loss
        q_values = self.dqn(state)
        current_q = q_values.gather(1, action.unsqueeze(1)).squeeze(1)

        # Avoid building grad graph for the target network
        with torch.no_grad():
            next_q_values = self.target_dqn(next_state)
            max_next_q = next_q_values.max(1)[0]

        # Additional discount factor
        discount_factor = ml_config.GAMMA ** ml_config.MULTI_STEP
        expected_q = reward + discount_factor * max_next_q * (1 - done)

        # Changed MSE loss for Huber loss, avoid huge spikes
        loss = F.smooth_l1_loss(current_q, expected_q)

        # Optimize
        self.rl_optimizer.zero_grad()
        loss.backward()
        self.rl_optimizer.step()

        return loss

    def _update_sl_network(self) -> torch.Tensor:
        """Updates average policy network.

        Returns:
            Loss tensor.
        """
        state, action = self.reservoir.sample(ml_config.BATCH_SIZE)

        state = torch.FloatTensor(state).to(ml_config.DEVICE)
        action = torch.LongTensor(action).to(ml_config.DEVICE)

        probs = self.policy(state)
        log_probs = probs.gather(1, action.unsqueeze(1)).log()
        loss = -log_probs.mean()

        self.sl_optimizer.zero_grad()
        loss.backward()
        self.sl_optimizer.step()

        return loss

    def update_target_network(self) -> None:
        """Copies weights from DQN to target DQN."""
        self.target_dqn.load_state_dict(self.dqn.state_dict())

    def select_action_with_mask(
            self,
            state: np.ndarray,
            action_mask: np.ndarray,
            epsilon: float,
            best_response: bool = True
    ) -> Tuple[int, torch.Tensor]:
        """Selects action with masking.

        Args:
            state: Current state.
            action_mask: Boolean array indicating valid actions.
            epsilon: Exploration rate.
            best_response: Use DQN (True) or policy (False).

        Returns:
            Selected action and tensor of q-values or logits
        """
        if not np.any(action_mask):
            # No valid actions - should never happen, but fallback
            return 0

        # This assume that batch size will be 1
        tensor = torch.FloatTensor(state).unsqueeze(0).to(ml_config.DEVICE)
        mask_tensor = torch.FloatTensor(
            action_mask).unsqueeze(0).to(ml_config.DEVICE)

        if best_response:
            return self._select_with_dqn_masked(tensor, mask_tensor, epsilon)
        else:
            return self._select_with_policy_masked(tensor, mask_tensor)

    def _select_with_dqn_masked(
            self,
            state_tensor: torch.Tensor,
            mask_tensor: torch.Tensor,
            epsilon: float
    ) -> Tuple[int, torch.Tensor]:
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
        return masked_q[0].argmax().item(), q_values

    def _select_with_policy_masked(
        self,
        state_tensor: torch.Tensor,
        mask_tensor: torch.Tensor
    ) -> Tuple[int, torch.Tensor]:
        """Policy selection using logit masking BEFORE softmax."""
        encoded = self.policy.encoder(state_tensor)
        feat = self.policy.feature_net(encoded)
        logits = self.policy.head(feat)

        # Sanitize logits
        logits = torch.nan_to_num(logits, nan=0.0, posinf=10.0, neginf=-10.0)
        logits = torch.clamp(logits, -10, 10)

        # check for shape mismatches
        assert logits.dim() == 2
        assert logits.shape[-1] == mask_tensor.shape[-1]

        # check for finiteness
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

        # check for finiteness in probabilities
        assert torch.isfinite(probs).all(), "Probs must be finite"

        action = torch.multinomial(probs[0], 1).item()
        return action, probs
