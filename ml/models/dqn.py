import random
import torch
import torch.nn as nn
from ml.models.mlp_base import MLPBase


class DQN(nn.Module):
    """Standard DQN"""

    def __init__(self, input_dim, num_actions, hidden_dims=[256, 256]):
        super().__init__()
        self.feature_net = MLPBase(input_dim, hidden_dims)
        self.head = nn.Linear(self.feature_net.output_dim, num_actions)
        self.num_actions = num_actions
        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu")
        nn.init.xavier_uniform_(self.head.weight)
        nn.init.constant_(self.head.bias, 0.0)

    def forward(self, x):
        x = self.feature_net(x)
        return self.head(x)

    def act(self, state, epsilon):
        if random.random() > epsilon:
            state = state.unsqueeze(0).to(self.device)
            with torch.no_grad():
                q_values = self.forward(state)
                action = q_values.argmax(dim=1).item()
        else:
            action = random.randrange(self.num_actions)
        return action
