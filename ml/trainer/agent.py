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


# TODO: Would have been better if I did another level of abstraction
# one only for action selection while the other is used for training

class Agent:
    """RL agent with DQN and average policy network."""

    def __init__(self, num_actions: int):
        """Initializes Agent. """
        self._init_encoder()

        # Core networks
        self.dqn = DuelingDQN(
            self.encoder, num_actions).to(ml_config.DEVICE)
        self.target_dqn = DuelingDQN(
            self.encoder, num_actions).to(ml_config.DEVICE)
        # Initial sync params to target dqn
        self.update_target_network()

        # Average policy
        self.policy = AveragePolicy(
            self.encoder, num_actions).to(ml_config.DEVICE)

        # Buffers and optimizers
        self.replay_buffer = ReplayBuffer(ml_config.BUFFER_SIZE)
        self.reservoir = ReservoirBuffer(ml_config.BUFFER_SIZE)
        self.rl_optimizer = optim.Adam(self.dqn.parameters(), lr=1e-4)
        self.sl_optimizer = optim.Adam(self.policy.parameters(), lr=1e-4)

        # Buffer manager for temporary state, reward containment till
        # enough samples are met to be flushed into replay and reservoir
        self.buffer_manager = BufferManager(self)

    def _init_encoder(self):
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

    def update_rl_network(self) -> torch.Tensor:
        """Updates DQN network.

        Returns:
            Loss tensor.
        """
        batch = self.replay_buffer.sample(ml_config.BATCH_SIZE)
        state, action, reward, next_state, done = batch

        # Convert to tensors
        state = torch.FloatTensor(state).to(ml_config.DEVICE)
        next_state = torch.FloatTensor(next_state).to(ml_config.DEVICE)
        action = torch.LongTensor(action).to(ml_config.DEVICE)
        reward = torch.FloatTensor(reward).to(ml_config.DEVICE)
        done = torch.FloatTensor(done).to(ml_config.DEVICE)

        torch.nn.utils.clip_grad_norm_(self.dqn.parameters(), max_norm=1.0)
        # Compute loss
        q_values = self.dqn(state)
        next_q_values = self.dqn(next_state)

        current_q = q_values.gather(1, action.unsqueeze(1)).squeeze(1)
        next_actions = next_q_values.nax(1)[1].unsqueeze(1)

        # Avoid building grad graph for the target network
        with torch.no_grad():
            target_next_q_values = self.target_dqn(next_state)
            next_q_a_values = target_next_q_values.gather(
                1, next_actions).squeeze(1)

        # Additional discount factor
        discount_factor = ml_config.GAMMA ** ml_config.MULTI_STEP
        expected_q = reward + discount_factor * next_q_a_values * (1 - done)

        # Changed MSE loss for Huber loss, avoid huge spikes
        loss = F.smooth_l1_loss(current_q, expected_q)

        td_error = torch.abs(expected_q.detach() - current_q)
        prios = (td_error + 1e-6).data.cpu().numpy()

        # Optimize
        self.rl_optimizer.zero_grad()
        loss.backward()
        self.rl_optimizer.step()

        return loss, prios

    def can_update_sl(self):
        return len(self.reservoir) >= ml_config.BATCH_SIZE

    def can_update_rl(self):
        return len(self.replay_buffer) >= ml_config.BATCH_SIZE

    def update_sl_network(self) -> torch.Tensor:
        """Updates average policy network.

        Returns:
            Loss tensor.
        """
        state, action = self.reservoir.sample(ml_config.BATCH_SIZE)

        state = torch.FloatTensor(state).to(ml_config.DEVICE)
        action = torch.LongTensor(action).to(ml_config.DEVICE)

        torch.nn.utils.clip_grad_norm_(self.policy.parameters(), max_norm=1.0)
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
        assert np.any(action_mask)

        # This assume that batch size will be 1
        tensor = torch.FloatTensor(state).unsqueeze(0).to(ml_config.DEVICE)
        mask_tensor = torch.FloatTensor(
            action_mask).unsqueeze(0).to(ml_config.DEVICE)
        q_values = self.dqn(tensor)

        if best_response:
            return self._select_with_dqn_masked(q_values, tensor, mask_tensor, epsilon), q_values
        else:
            return self._select_with_policy_masked(tensor, mask_tensor), q_values

    def _select_with_dqn_masked(
            self,
            q_values: torch.Tensor,
            state_tensor: torch.Tensor,
            mask_tensor: torch.Tensor,
            epsilon: float
    ) -> Tuple[int, torch.Tensor]:
        """DQN selection with masking."""
        # Apply mask (set invalid actions to -inf)
        masked_q = q_values.masked_fill(mask_tensor == 0, float('-inf'))

        assert not torch.isinf(masked_q).all()

        if random.random() < epsilon:
            # Explore: choose randomly from valid actions
            valid_actions = torch.where(mask_tensor[0] == 1)[0]
            # Still returning q_values here to assign priorities
            # NOTE: im not sure if this is correct since the q vals
            # here did not drive the action, but waiting for episolon
            # to drop eventually until real dqn acts are chosen
            # is also not a very smart idea
            return random.choice(valid_actions.tolist())

        # Exploit: choose best valid action
        return masked_q[0].argmax().item()

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
        assert not mask_tensor.sum().item() == 0

        # mask the logits with -inf
        masked_logits = logits.clone()
        masked_logits = masked_logits.masked_fill(
            mask_tensor == 0, float("-inf"))

        # In case everything is just masked (should be impossible now)
        assert not torch.isinf(masked_logits).all()

        # softmax over valid actions only
        probs = torch.softmax(masked_logits, dim=1)

        # check for finiteness in probabilities
        assert torch.isfinite(probs).all(), "Probs must be finite"

        action = torch.multinomial(probs[0], 1).item()
        return action
