"""
Episode statistics and metrics management.
"""
from typing import List


class EpisodeManager:
    """
    Tracks episode-level statistics for multiple agents.
    """

    def __init__(self, num_agents: int):
        self.num_agents = num_agents

        # Per-agent metrics
        self.wins = [0] * num_agents
        self.rewards = [[] for _ in range(num_agents)]

        # Episode metrics
        self.lengths: List[int] = []
        self.current_episode_rewards = [0] * num_agents
        self.current_episode_length = 0

    def add_reward(self, agent_idx: int, reward: float):
        """Add reward for specific agent."""
        self.current_episode_rewards[agent_idx] += reward
        self.current_episode_length += 1

    def record_win(self, winner_idx: int):
        """Record a win for the specified agent."""
        if 0 <= winner_idx < self.num_agents:
            self.wins[winner_idx] += 1

    def finalize_episode(self):
        """
        Finalize current episode and store statistics.
        Returns normalized rewards per agent.
        """
        if self.current_episode_length == 0:
            return

        # Store length
        self.lengths.append(self.current_episode_length)

        # Normalize and store rewards
        for agent_idx in range(self.num_agents):
            normalized_reward = (
                self.current_episode_rewards[agent_idx] /
                self.current_episode_length
            )
            self.rewards[agent_idx].append(normalized_reward)

        # Reset for next episode
        self._reset_current_episode()

    def _reset_current_episode(self):
        """Reset current episode counters."""
        self.current_episode_rewards = [0] * self.num_agents
        self.current_episode_length = 0

    def get_statistics(self) -> dict:
        """Get current training statistics."""
        return {
            "wins": self.wins,
            "rewards": self.rewards,
            "episode_lengths": self.lengths,
        }

    def get_recent_stats(self, window: int = 100) -> dict:
        """Get statistics for recent episodes."""
        recent_rewards = [
            rewards[-window:] if len(rewards) >= window else rewards
            for rewards in self.rewards
        ]
        recent_lengths = (
            self.lengths[-window:]
            if len(self.lengths) >= window
            else self.lengths
        )

        return {
            "recent_rewards": recent_rewards,
            "recent_lengths": recent_lengths,
        }
