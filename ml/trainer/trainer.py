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
    load_model
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
        mlflow (MLFlowManager): Manager for tracking experiments.
    """

    def __init__(self, env: GameEnv, device: str, mlflow_enabled: bool = False) -> None:
        """Initializes the Trainer with environment, configuration, and agent count.

        Args:
            env: The game environment instance.
            mlflow_enabled (bool): whether to use mlflow or not
        """
        self.env = env
        self.agent = Agent(num_actions=self.env.num_actions, device=device)

        self.episode_manager = EpisodeManager(2)
        self.mlflow = MLFlowManager(enabled=mlflow_enabled)

        logging.info(f"Currently running on device: {ml_config.DEVICE}")

    def train(self) -> None:
        """Executes the main training loop."""
        set_global_seeds(ml_config.SEED)
        self.mlflow.start_run()

        training_loop = TrainingLoop(
            env=self.env,
            agent=self.agent,
            episode_manager=self.episode_manager,
            mlflow=self.mlflow
        )

        training_loop.run()
        save_model(self.agent)

    def load_checkpoint(self, device: str, path: str):
        """Load the agent checkpoint."""
        load_model(self.agent, device, path)
