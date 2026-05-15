import os
import torch
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional

load_dotenv()
BASE_PATH = Path(os.path.dirname(__file__)).parent


class Config:
    """Configuration for the reinforcement learning environment.

    Attributes:
        DEVICE: The computing device (CPU or GPU).
        NUM_ACTIONS: The number of discrete actions.
        MAX_FRAMES: Total training frames.
        BATCH_SIZE: Training batch size.
        BUFFER_SIZE: Replay buffer capacity.
        GAMMA: Discount factor for rewards.
        MULTI_STEP: Number of steps for n-step returns.
        NEGATIVE_REWARD: Whether to allow negative rewards.
        EPS_START: Initial epsilon value for exploration.
        EPS_FINAL: Final epsilon value.
        EPS_DECAY: Number of frames for epsilon decay.
        TRAIN_FREQ: Training frequency in frames.
        UPDATE_TARGET_FREQ: Target network update frequency.
        TAU: Soft update parameter.
        ETA: Epsilon-greedy parameter for self-play.
        EVALUATION_INTERVAL: Interval for evaluation.
        RENDER: Whether to render the game.
        SEED: Random seed for reproducibility.
        CHECKPOINT_PATH: Path to the model checkpoint.
        USER: Database user.
        PASSWORD: Database password.
        DB: Database name.
        HOST: Database host.
        PORT: Database port.
    """
    DEVICE: str = "cuda" if torch.cuda.is_available() else "cpu"

    # Action Space
    NUM_ACTIONS: int = 461

    # Training duration
    MAX_FRAMES: int = 1_000_000
    # NOTE: the higher this is, the more it stutters
    # when training via cpu
    BATCH_SIZE: int = 64
    BUFFER_SIZE: int = 200_000

    # RL Hyperparameters
    GAMMA: float = 0.98
    MULTI_STEP: int = 3
    NEGATIVE_REWARD: bool = True

    # Exploration
    EPS_START: float = 1.0
    EPS_FINAL: float = 0.05
    EPS_DECAY: int = 75_000

    # Update frequency
    TRAIN_FREQ: int = 4
    UPDATE_TARGET_FREQ: int = 2000
    TAU: float = 0.005

    # Self-play / best response
    ETA: float = 0.1

    # Logging & evaluation
    EVALUATION_INTERVAL: int = 10_000
    RENDER: bool = False
    SEED: int = 42

    MAX_ACTIONS_PER_TURN: int = 50

    REWARD_DEBUG: bool = False

    CHECKPOINT_PATH: Path = Path(BASE_PATH, "saves/checkpoint.pth")

    # Database
    EXPERIMENT_NAME = "autocard"
    USER: Optional[str] = os.getenv("POSTGRES_USER")
    PASSWORD: Optional[str] = os.getenv("POSTGRES_PASSWORD")
    DB: Optional[str] = os.getenv("POSTGRES_DB")
    HOST: Optional[str] = os.getenv("POSTGRES_HOST")
    PORT: Optional[str] = os.getenv("POSTGRES_PORT")
