import random
import torch
from typing import List
import torch.nn as nn
from ml.models.mlp_base import MLPBase
from ml.models.state_encoder import GameStateEncoder
from ml.config import Config


class DuelingDQN(nn.Module):
    """Dueling DQN architecture with Attention-based state encoding."""

    def __init__(self, encoder: GameStateEncoder, num_actions: int, hidden_dims: List[int] = [256, 256]):
        """Initializes Dueling DQN.

        Args:
            encoder: GameStateEncoder instance.
            num_actions: Number of possible actions.
            hidden_dims: List of hidden layer dimensions.
        """
        super().__init__()
        self.encoder = encoder
        self.feature_net = MLPBase(encoder.output_dim, hidden_dims)
        self.num_actions = num_actions

        self.advantage = nn.Linear(self.feature_net.output_dim, num_actions)
        self.value = nn.Linear(self.feature_net.output_dim, 1)

        self.device = Config.DEVICE

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: Input state tensor (flat).

        Returns:
            Q-values for each action.
        """
        # Encode state using the attention-based encoder
        # GameStateEncoder handles 1D/2D inputs automatically
        x = self.encoder(x)

        # Pass through feature network
        x = self.feature_net(x)

        value = self.value(x)
        advantage = self.advantage(x)
        q_values = value + advantage - advantage.mean(dim=1, keepdim=True)

        return q_values

    def act(self, state: torch.Tensor, epsilon: float) -> int:
        """Selects action.

        Args:
            state: Current state.
            epsilon: Exploration probability.

        Returns:
            Selected action index.
        """
        if random.random() > epsilon:
            state = state.unsqueeze(0).to(self.device)
            with torch.no_grad():
                q_values = self.forward(state)
                action = q_values.argmax(dim=1).item()
        else:
            action = random.randrange(self.num_actions)
        return action
