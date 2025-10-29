import logging
from typing import List

from ml.trainer.agent import Agent
from ml.trainer.action_mapper import ActionMapper
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
    """
    Main trainer class coordinating multi-agent RL training.
    """

    def __init__(self, env, config, num_agents: int = 2):
        self.env = env
        self.cfg = config
        self.num_agents = num_agents
        self.agents = self._initialize_agents()

        self.episode_manager = EpisodeManager(num_agents)
        self.mlflow_manager = MLFlowManager(config)
        self.action_mapper = ActionMapper(env)

        self._load_checkpoints_if_exist()
        logging.info(f"Currently running on device: {self.cfg.DEVICE}")

    def _initialize_agents(self) -> List[Agent]:
        """Create agent instances with appropriate dimensions."""
        return [
            Agent(
                state_dim=self.env.state_dim,
                num_actions=self.env.num_actions,
                param_dim=self.env.param_dim,
                config=self.cfg
            )
            for _ in range(self.num_agents)
        ]

    def _load_checkpoints_if_exist(self):
        """Load model checkpoints if available."""
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

    def train(self):
        """Execute the main training loop."""
        set_global_seeds(self.cfg.SEED)
        self.mlflow_manager.start_run()

        training_loop = TrainingLoop(
            env=self.env,
            agents=self.agents,
            action_mapper=self.action_mapper,
            episode_manager=self.episode_manager,
            config=self.cfg
        )

        training_loop.run()
        self._save_final_models()

    def _save_final_models(self):
        """Save final trained models."""
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
