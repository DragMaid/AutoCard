import torch
import torch.nn as nn
from typing import List


class MLPBase(nn.Module):
    """Base MLP network."""

    def __init__(self, input_dim: int, hidden_dims: List[int] = [256, 256]):
        """Initializes MLP base.

        Args:
            input_dim: Input dimension.
            hidden_dims: List of hidden layer dimensions.
        """
        super().__init__()
        layers = []
        last_dim = input_dim
        for h in hidden_dims:
            layers.append(nn.Linear(last_dim, h))
            layers.append(nn.ReLU())
            layers.append(nn.LayerNorm(h))
            last_dim = h
        self.features = nn.Sequential(*layers)
        self.output_dim = last_dim  # for Dueling heads or Policy

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass.

        Args:
            x: Input tensor.

        Returns:
            Output tensor.
        """
        return self.features(x)
