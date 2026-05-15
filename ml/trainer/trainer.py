import logging
from typing import List

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
        self.agents = self._initialize_agents()
        self.mlflow_enabled = mlflow_enabled

        self.episode_manager = EpisodeManager(num_agents)
        self.mlflow_manager = MLFlowManager(enabled=mlflow_enabled)

        logging.info(f"Currently running on device: {ml_config.DEVICE}")

    def _initialize_agents(self) -> List[Agent]:
        """Creates agent instances with appropriate dimensions.

        Returns:
            List[Agent]: A list of initialized agents.
        """
        return [
            Agent(
                state_dim=self.env.state_dim,
                num_actions=self.env.num_actions,
            )
            for _ in range(self.num_agents)
        ]

    def load_checkpoint(self, path: str) -> None:
        """Loads model checkpoints if available."""
        models = {
            f"agent_{i}": agent.dqn
            for i, agent in enumerate(self.agents)
        }
        policies = {
            f"agent_{i}": agent.policy
            for i, agent in enumerate(self.agents)
        }

        load_model(
            logging,
            models=models,
            policies=policies,
            device=ml_config.DEVICE,
            checkpoint_path=path,
        )

    def train(self) -> None:
        """Executes the main training loop."""
        set_global_seeds(ml_config.SEED)
        self.mlflow_manager.start_run()

        training_loop = TrainingLoop(
            env=self.env,
            agents=self.agents,
            episode_manager=self.episode_manager,
            mlflow_enabled=self.mlflow_enabled
        )

        training_loop.run()
        self._save_final_models()

    def _save_final_models(self) -> None:
        """Saves final trained models."""
        models = {
            f"agent_{i}": agent.dqn
            for i, agent in enumerate(self.agents)
        }
        policies = {
            f"agent_{i}": agent.policy
            for i, agent in enumerate(self.agents)
        }

        save_model(logging, models=models, policies=policies,
                   checkpoint_path=ml_config.CHECKPOINT_PATH)
