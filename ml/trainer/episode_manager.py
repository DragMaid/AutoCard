from typing import List, Dict, Any


class EpisodeManager:
    """Tracks episode-level statistics for multiple agents.

    Attributes:
        num_agents (int): Number of agents being tracked.
        wins (List[int]): List of win counts per agent.
        rewards (List[List[float]]): List of lists containing reward histories per agent.
        lengths (List[int]): List of episode lengths.
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
        self.rewards: List[List[float]] = [[] for _ in range(num_agents)]

        # Episode metrics
        self.lengths: List[int] = []
        self.current_episode_rewards: List[float] = [0.0] * num_agents
        self.current_episode_length: int = 0

    def add_reward(self, agent_idx: int, reward: float) -> None:
        """Adds a reward for a specific agent.

        Args:
            agent_idx (int): The index of the agent.
            reward (float): The reward value to add.
        """
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

    def _reset_current_episode(self) -> None:
        """Resets current episode counters."""
        self.current_episode_rewards = [0.0] * self.num_agents
        self.current_episode_length = 0

    def get_statistics(self) -> Dict[str, Any]:
        """Gets current training statistics.

        Returns:
            Dict[str, Any]: A dictionary containing wins, rewards, and episode lengths.
        """
        return {
            "wins": self.wins,
            "rewards": self.rewards,
            "episode_lengths": self.lengths,
        }

    def get_recent_stats(self, window: int = 100) -> Dict[str, Any]:
        """Gets statistics for recent episodes.

        Args:
            window (int, optional): The number of recent episodes to include. Defaults to 100.

        Returns:
            Dict[str, Any]: A dictionary containing recent rewards and recent episode lengths.
        """
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
