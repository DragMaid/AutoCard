import torch.nn as nn


class MLPBase(nn.Module):
    """Base MLP network"""

    def __init__(self, input_dim, hidden_dims=[256, 256]):
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

    def forward(self, x):
        return self.features(x)
