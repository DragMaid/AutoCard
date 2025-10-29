import torch
import random
import numpy as np
import torch.nn as nn
import torch.nn.functional as F
from ml.models.mlp_base import MLPBase
from ml.models.gaussian_policy import GaussianPolicy
from ml.utils import hard_update


class DuelingParamCritic(nn.Module):
    """
    Dueling critic that takes concatenated (state, action_params) and outputs Q-values
    for each discrete action (num_actions).
    """

    def __init__(self, state_dim, param_dim, num_actions, hidden_dims=[256, 256]):
        super().__init__()
        input_dim = state_dim + param_dim
        self.feature_net = MLPBase(input_dim, hidden_dims)
        self.advantage = nn.Linear(self.feature_net.output_dim, num_actions)
        self.value = nn.Linear(self.feature_net.output_dim, 1)
        self.num_actions = num_actions

        nn.init.xavier_uniform_(self.advantage.weight)
        nn.init.constant_(self.advantage.bias, 0.0)

        nn.init.xavier_uniform_(self.value.weight)
        nn.init.constant_(self.value.bias, 0.0)

    def forward(self, state, action_params):
        """
        state: (B, state_dim)
        action_params: (B, param_dim)
        returns: q_values (B, num_actions)
        """
        x = torch.cat([state, action_params], dim=1)
        f = self.feature_net(x)
        adv = self.advantage(f)               # (B, num_actions)
        val = self.value(f)                   # (B, 1)
        q = val + adv - adv.mean(dim=1, keepdim=True)
        return q


class PDQN(nn.Module):
    """
    Pure model: actor + dueling critic + critic target + log_alpha param.
    No optimizers or update logic here.
    """

    def __init__(
        self,
        state_dim,
        num_actions,
        param_dim,
        actor_hidden=[256, 256],
        critic_hidden=[256, 256],
        param_bound=1.0,
        initial_alpha=0.2,
    ):
        super().__init__()
        self.state_dim = state_dim
        self.num_actions = num_actions
        self.param_dim = param_dim
        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu")

        self.actor = GaussianPolicy(
            state_dim, param_dim, actor_hidden, param_bound).to(self.device)

        self.critic = DuelingParamCritic(
            state_dim, param_dim, num_actions, critic_hidden).to(self.device)
        self.critic_target = DuelingParamCritic(
            state_dim, param_dim, num_actions, critic_hidden).to(self.device)
        hard_update(self.critic_target, self.critic)

        # log alpha as a parameter for stability (SAC style)
        # store log_alpha; user can create optimizer for pdqn.log_alpha
        self.log_alpha = nn.Parameter(torch.tensor(
            np.log(initial_alpha), dtype=torch.float32, device=self.device))
        # target entropy: negative of number of discrete actions (heuristic)
        self.target_entropy = -float(num_actions)

    @property
    def alpha(self):
        return self.log_alpha.exp()

    def select_action(self, state, epsilon=0.0, train=True):
        """
        state: numpy array or torch tensor (state_dim,)
        returns: discrete action (int), action_params (numpy array)
        """
        if isinstance(state, np.ndarray):
            state_t = torch.FloatTensor(state).to(self.device).unsqueeze(0)
        else:
            state_t = state.to(self.device).unsqueeze(0)

        with torch.no_grad():
            params, _, _ = self.actor.sample(state_t)  # (1, param_dim)
            q_values = self.critic(state_t, params)    # (1, num_actions)
            q_np = q_values.detach().cpu().numpy().squeeze(0)

        if train and random.random() < epsilon:
            discrete = np.random.randint(self.num_actions)
        else:
            discrete = int(np.argmax(q_np))

        return discrete, params.squeeze(0).detach().cpu().numpy()

    def update(
        self,
        param_buffer,
        critic_optimizer=None,
        actor_optimizer=None,
        alpha_optimizer=None,
        batch_size=64,
        gamma=0.99,
        tau=0.005
    ):
        """
        Update PDQN actor and critic from the parameter buffer.
        """
        if len(param_buffer) < batch_size:
            return  # not enough samples

        # Sample a batch
        state, action_params, reward, next_state, done = param_buffer.sample(
            batch_size)
        action_params = np.array(action_params, dtype=np.float32)
        state = torch.FloatTensor(state).to(self.device)
        next_state = torch.FloatTensor(next_state).to(self.device)
        action_params = torch.FloatTensor(action_params).to(self.device)
        reward = torch.FloatTensor(reward).to(self.device)
        done = torch.FloatTensor(done).to(self.device)

        # -------------------
        # Critic update
        # -------------------
        with torch.no_grad():
            next_params, next_log_prob, _ = self.actor.sample(next_state)
            next_q = self.critic_target(next_state, next_params)
            next_q_max = next_q.max(1)[0]
            target_q = reward + gamma * (1 - done) * next_q_max

        current_q = self.critic(state, action_params)
        q_loss = F.mse_loss(current_q.max(1)[0], target_q)

        if critic_optimizer is not None:
            critic_optimizer.zero_grad()
            q_loss.backward()
            critic_optimizer.step()

        # -------------------
        # Actor update
        # -------------------
        sampled_params, log_prob, _ = self.actor.sample(state)
        q_val = self.critic(state, sampled_params)
        actor_loss = (-q_val.max(1)[0] + self.alpha * log_prob).mean()

        if actor_optimizer is not None:
            actor_optimizer.zero_grad()
            actor_loss.backward()
            actor_optimizer.step()

        # -------------------
        # Alpha update (optional)
        # -------------------
        if alpha_optimizer is not None:
            alpha_loss = -(self.log_alpha * (log_prob +
                           self.target_entropy).detach()).mean()
            alpha_optimizer.zero_grad()
            alpha_loss.backward()
            alpha_optimizer.step()

        # -------------------
        # Soft update target
        # -------------------
        for target_param, param in zip(self.critic_target.parameters(), self.critic.parameters()):
            target_param.data.copy_(
                tau * param.data + (1 - tau) * target_param.data)
