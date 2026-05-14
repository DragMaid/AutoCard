import random
import torch
import torch.nn as nn
from ml.models.mlp_base import MLPBase


import random
import torch
import torch.nn as nn
from ml.models.mlp_base import MLPBase
from typing import List


class DuelingDQN(nn.Module):
    """Dueling DQN architecture."""

    def __init__(self, input_dim: int, num_actions: int, hidden_dims: List[int] = [256, 256]):
        """Initializes Dueling DQN.

        Args:
            input_dim: Dimension of input state.
            num_actions: Number of possible actions.
            hidden_dims: List of hidden layer dimensions.
        """
        super().__init__()
        self.feature_net = MLPBase(input_dim, hidden_dims)
        self.num_actions = num_actions

        self.advantage = nn.Linear(self.feature_net.output_dim, num_actions)
        self.value = nn.Linear(self.feature_net.output_dim, 1)

        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu")

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: Input state tensor.

        Returns:
            Q-values for each action.
        """
        # Handle both 1D and 2D inputs
        is_single_state = (x.dim() == 1)
        if is_single_state:
            x = x.unsqueeze(0)  # (state_dim,) -> (1, state_dim)

        x = self.feature_net(x)
        value = self.value(x)
        advantage = self.advantage(x)
        q_values = value + advantage - advantage.mean(dim=1, keepdim=True)

        # Remove batch dimension if input was 1D
        if is_single_state:
            # (1, num_actions) -> (num_actions,)
            q_values = q_values.squeeze(0)

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
