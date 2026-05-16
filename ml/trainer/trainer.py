import logging

from ml.config import Config as ml_config
from ml.environment.environment import GameEnv
from ml.trainer.agent import Agent
from ml.trainer.mlflow_manager import MLFlowManager
from ml.trainer.episode_manager import EpisodeManager
from ml.trainer.training_loop import TrainingLoop
from ml.utils import (
    set_global_seeds,
    save_model,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)


class Trainer:
    """Main trainer class coordinating multi-agent RL training.

    Attributes:
        env: The game environment.
        num_agents (int): Number of agents participating in the training.
        agents (List[Agent]): List of agent instances.
        episode_manager (EpisodeManager): Manager for handling episode data.
        mlflow_manager (MLFlowManager): Manager for tracking experiments.
    """

    def __init__(self, env: GameEnv, num_agents: int = 2, mlflow_enabled: bool = False) -> None:
        """Initializes the Trainer with environment, configuration, and agent count.

        Args:
            env: The game environment instance.
            num_agents (int, optional): Number of agents. Defaults to 2.
            mlflow_enabled (bool): whether to use mlflow or not
        """
        self.env = env
        self.num_agents = num_agents
        self.agent = Agent(
            state_dim=self.env.state_dim,
            num_actions=self.env.num_actions,
        )
        self.mlflow_enabled = mlflow_enabled

        self.episode_manager = EpisodeManager(num_agents)
        self.mlflow_manager = MLFlowManager(enabled=mlflow_enabled)

        logging.info(f"Currently running on device: {ml_config.DEVICE}")

    def train(self) -> None:
        """Executes the main training loop."""
        set_global_seeds(ml_config.SEED)
        self.mlflow_manager.start_run()

        training_loop = TrainingLoop(
            env=self.env,
            agent=self.agent,
            episode_manager=self.episode_manager,
        )

        training_loop.run()
        save_model(self.agent)
