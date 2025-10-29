import torch
import torch.nn as nn
from ml.models.mlp_base import MLPBase


class GaussianPolicy(nn.Module):
    """
    Gaussian policy that outputs a continuous parameter vector.
    Returns: (sampled_params, log_prob, deterministic_params)
    """

    def __init__(self, state_dim, param_dim, hidden_dims=[256, 256], param_bound=1.0):
        super().__init__()
        self.net = MLPBase(state_dim, hidden_dims)
        self.mean = nn.Linear(self.net.output_dim, param_dim)
        self.log_std = nn.Linear(self.net.output_dim, param_dim)
        self.param_dim = param_dim
        self.param_bound = param_bound
        # initialize log_std small negative
        nn.init.constant_(self.log_std.bias, -3.0)

    def forward(self, state):
        x = self.net(state)
        mean = self.mean(x)
        log_std = self.log_std(x).clamp(-20, 2)
        std = log_std.exp()
        return mean, std

    def sample(self, state):
        """
        state: (B, state_dim) or (1, state_dim)
        returns:
           params_t (B, param_dim)  - sampled and tanh-squashed
           log_prob (B, 1)
           deterministic (B, param_dim)
        """
        mean, std = self.forward(state)
        normal = torch.distributions.Normal(mean, std)
        x_t = normal.rsample()  # reparam trick
        y_t = torch.tanh(x_t) * self.param_bound
        # log prob correction for tanh (from SAC repo)
        log_prob = normal.log_prob(x_t)
        # sum over param dims
        log_prob = log_prob.sum(dim=1, keepdim=True)
        # correction
        log_prob = log_prob - \
            torch.log(1 - torch.tanh(x_t).pow(2) +
                      1e-6).sum(dim=1, keepdim=True)
        deterministic = torch.tanh(mean) * self.param_bound
        return y_t, log_prob, deterministic
