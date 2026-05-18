import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class EpisodeManager:
    """Tracks episode-level statistics for multiple agents.

    Attributes:
        num_agents (int): Number of agents being tracked.
        wins (List[int]): List of win counts per agent.
        total_episodes (int): Total number of completed episodes.
        current_episode_rewards (List[float]): Rewards for the current episode per agent.
        current_episode_length (int): Length of the current episode.
    """

    def __init__(self, num_agents: int) -> None:
        """Initializes the EpisodeManager with the number of agents.

        Args:
            num_agents (int): The number of agents.
        """
        self.num_agents = num_agents

        # Per-agent metrics
        self.wins: List[int] = [0] * num_agents
        self.total_episodes: int = 0

        # Current episode metrics
        self.current_episode_rewards: List[float] = [0.0] * num_agents
        self.current_episode_length: int = 0

    def add_reward(self, agent_idx: int, reward: float) -> None:
        """Adds a reward for a specific agent.

        Args:
            agent_idx (int): The index of the agent.
            reward (float): The reward value to add.
        """
        if 0 <= agent_idx < self.num_agents:
            self.current_episode_rewards[agent_idx] += reward
        self.current_episode_length += 1

    def record_win(self, winner_idx: int) -> None:
        """Records a win for the specified agent.

        Args:
            winner_idx (int): The index of the winning agent.
        """
        if 0 <= winner_idx < self.num_agents:
            self.wins[winner_idx] += 1

    def finalize_episode(self) -> None:
        """Finalizes current episode and stores statistics."""
        if self.current_episode_length == 0:
            return

        self.total_episodes += 1

        # Display statistics
        self._display_stats()

        # Reset for next episode
        self._reset_current_episode()

    def _display_stats(self) -> None:
        """Logs current episode statistics and win rates."""
        stats_msg = (
            f"Episode {self.total_episodes} finished | "
            f"Length: {self.current_episode_length} | "
        )

        agent_stats = []
        for i in range(self.num_agents):
            win_rate = (self.wins[i] / self.total_episodes) * 100
            total_reward = self.current_episode_rewards[i]
            agent_stats.append(
                f"P{i+1} Win Rate: {win_rate:.1f}% | "
                f"P{i+1} Reward: {total_reward:.2f}"
            )

        logger.info(stats_msg + " | ".join(agent_stats))

    def _reset_current_episode(self) -> None:
        """Resets current episode counters."""
        self.current_episode_rewards = [0.0] * self.num_agents
        self.current_episode_length = 0

    def get_statistics(self) -> Dict[str, Any]:
        """Gets current training statistics.

        Returns:
            Dict[str, Any]: A dictionary containing wins and total episodes.
        """
        return {
            "wins": self.wins,
            "total_episodes": self.total_episodes,
        }
