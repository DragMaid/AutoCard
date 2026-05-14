import logging
from typing import List

from ml.trainer.agent import Agent
from ml.trainer.mlflow_manager import MLFlowManager
from ml.trainer.episode_manager import EpisodeManager
from ml.trainer.training_loop import TrainingLoop
from ml.utils import (
    set_global_seeds,
    save_model,
    detect_and_load_model,
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
        cfg: Training configuration object.
        num_agents (int): Number of agents participating in the training.
        agents (List[Agent]): List of agent instances.
        episode_manager (EpisodeManager): Manager for handling episode data.
        mlflow_manager (MLFlowManager): Manager for tracking experiments.
    """

    def __init__(self, env, config, num_agents: int = 2) -> None:
        """Initializes the Trainer with environment, configuration, and agent count.

        Args:
            env: The game environment instance.
            config: Training configuration object.
            num_agents (int, optional): Number of agents. Defaults to 2.
        """
        self.env = env
        self.cfg = config
        self.num_agents = num_agents
        self.agents = self._initialize_agents()

        self.episode_manager = EpisodeManager(num_agents)
        self.mlflow_manager = MLFlowManager(config)

        self._load_checkpoints_if_exist()
        logging.info(f"Currently running on device: {self.cfg.DEVICE}")

    def _initialize_agents(self) -> List[Agent]:
        """Creates agent instances with appropriate dimensions.

        Returns:
            List[Agent]: A list of initialized agents.
        """
        return [
            Agent(
                state_dim=self.env.state_dim,
                num_actions=self.env.num_actions,
                config=self.cfg
            )
            for _ in range(self.num_agents)
        ]

    def _load_checkpoints_if_exist(self) -> None:
        """Loads model checkpoints if available."""
        checkpoint_path = self.cfg.CHECKPOINT_PATH
        if not checkpoint_path.exists():
            return

        models = {
            f"agent_{i}": agent.dqn
            for i, agent in enumerate(self.agents)
        }
        policies = {
            f"agent_{i}": agent.policy
            for i, agent in enumerate(self.agents)
        }

        detect_and_load_model(
            logging,
            models=models,
            policies=policies,
            device=self.cfg.DEVICE,
            checkpoint_path=self.cfg.CHECKPOINT_PATH,
        )

    def train(self) -> None:
        """Executes the main training loop."""
        set_global_seeds(self.cfg.SEED)
        self.mlflow_manager.start_run()

        training_loop = TrainingLoop(
            env=self.env,
            agents=self.agents,
            episode_manager=self.episode_manager,
            config=self.cfg
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
                   checkpoint_path=self.cfg.CHECKPOINT_PATH)
