import torch
import torch.nn as nn
from ml.models.dqn import DQN
from ml.models.mlp_base import MLPBase


class AveragePolicy(DQN):
    """Policy network for NFSP (stochastic, NaN-safe version)."""

    def __init__(self, input_dim, num_actions, hidden_dims=[256, 256]):
        super().__init__(input_dim, num_actions)
        self.feature_net = MLPBase(input_dim, hidden_dims)
        self.num_actions = num_actions
        self.head = nn.Linear(self.feature_net.output_dim, num_actions)
        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu")

        # Xavier initialization (prevents huge logits early)
        nn.init.xavier_uniform_(self.head.weight)
        nn.init.constant_(self.head.bias, 0.0)

    def forward(self, x):
        x = self.feature_net(x)

        # Compute logits
        logits = self.head(x)

        # Sanitize values before softmax
        logits = torch.nan_to_num(logits, nan=0.0, posinf=10.0, neginf=-10.0)
        logits = torch.clamp(logits, -10, 10)

        # Use numerically safe softmax (log-sum-exp trick)
        return self.stable_softmax(logits, dim=1)

    def act(self, state):
        state = state.unsqueeze(0).to(self.device)
        with torch.no_grad():
            probs = self.forward(state)
            action = probs.multinomial(1).item()
        return action

    @staticmethod
    def stable_softmax(logits, dim=-1):
        z = logits - logits.max(dim=dim, keepdim=True).values
        numerator = torch.exp(z)
        denominator = numerator.sum(dim=dim, keepdim=True)
        return numerator / denominator
