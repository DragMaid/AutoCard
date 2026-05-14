import torch
import torch.nn as nn
from ml.models.mlp_base import MLPBase
from typing import List


from ml.models.state_encoder import GameStateEncoder

class AveragePolicy(nn.Module):
    """Policy network for NFSP with Attention-based state encoding."""

    def __init__(self, encoder: GameStateEncoder, num_actions: int, hidden_dims: List[int] = [256, 256]):
        """Initializes AveragePolicy.

        Args:
            encoder: GameStateEncoder instance.
            num_actions: Number of actions.
            hidden_dims: List of hidden layer dimensions.
        """
        super().__init__()
        self.encoder = encoder
        self.feature_net = MLPBase(encoder.output_dim, hidden_dims)
        self.num_actions = num_actions
        self.head = nn.Linear(self.feature_net.output_dim, num_actions)
        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu")

        # Xavier initialization
        nn.init.xavier_uniform_(self.head.weight)
        nn.init.constant_(self.head.bias, 0.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: Input tensor (flat).

        Returns:
            Action probabilities.
        """
        # Encode state
        x = self.encoder(x)
        
        # Feature extraction
        x = self.feature_net(x)

        # Compute logits
        logits = self.head(x)

        # Sanitize values before softmax
        logits = torch.nan_to_num(logits, nan=0.0, posinf=10.0, neginf=-10.0)
        logits = torch.clamp(logits, -10, 10)

        # Use numerically safe softmax (log-sum-exp trick)
        return self.stable_softmax(logits, dim=1)

    def act(self, state: torch.Tensor) -> int:
        """Selects action.

        Args:
            state: State tensor.

        Returns:
            Action index.
        """
        state = state.unsqueeze(0).to(self.device)
        with torch.no_grad():
            probs = self.forward(state)
            action = probs.multinomial(1).item()
        return action

    @staticmethod
    def stable_softmax(logits: torch.Tensor, dim: int = -1) -> torch.Tensor:
        """Computes numerically stable softmax.

        Args:
            logits: Logits.
            dim: Dimension.

        Returns:
            Probabilities.
        """
        z = logits - logits.max(dim=dim, keepdim=True).values
        numerator = torch.exp(z)
        denominator = numerator.sum(dim=dim, keepdim=True)
        return numerator / denominator
