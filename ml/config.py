import os
import torch
from dotenv import load_dotenv
from pathlib import Path
from typing import Optional

load_dotenv()
BASE_PATH = Path(os.path.dirname(__file__)).parent


class Config:
    """
    Configuration for the reinforcement learning environment.
    """

    DEVICE: str = "cuda" if torch.cuda.is_available() else "cpu"

    # Action Space
    NUM_ACTIONS: int = 461

    # TODO: reconsider a better duration for 3 hours of training
    # Training duration
    MAX_FRAMES: int = 1_000_000
    # NOTE: the higher this is, the more it stutters
    # when training via cpu
    BATCH_SIZE: int = 64
    BUFFER_SIZE: int = 2_000_000

    # RL Hyperparameters
    BETA: int = 0.4
    ALPHA: int = 0.6
    GAMMA: float = 0.98
    MULTI_STEP: int = 3
    NEGATIVE_REWARD: bool = True
    LR: float = 1e-4

    # Exploration
    EPS_START: float = 1.0
    EPS_FINAL: float = 0.05
    EPS_DECAY: int = 75_000

    # Update frequency
    TRAIN_INTERVAL: int = 4
    UPDATE_TARGET_INTERVAL: int = 4000

    # Self-play / best response
    ETA: float = 0.1
    MAX_NORM: float = 1.0

    # Logging & evaluation
    SEED: int = 42
    RENDER: bool = False
    REWARD_DEBUG: bool = False
    SAVE_INTERVAL: int = 5000
    MAX_ACTIONS_PER_EPISODE: int = 300
    CHECKPOINT_PATH: Path = Path(BASE_PATH, "saves/checkpoint.pth")

    # Distributed client
    QUEUE_SIZE: int = 16
    EMIT_DATA_INTERVAL: int = 50
    PUSH_PARAM_INTERVAL: int = 400
    EMIT_METRICS_INTERVAL: int = 50
    SAMPLE_THRESHOLD: int = 10_000
    LOG_FOLDER: Path = Path(BASE_PATH, "logs")

    # Proxy server location
    ACTOR_TTL: int = 10
    SERVER_PORT: int = 5000
    SERVER_QUEUE_SIZE: int = 100
    SERVER_URL: str = os.getenv("SERVER_URL", "http://localhost:5000")
    AUTH_CODE: str = os.getenv("AUTH_CODE", "1234")

    # Database for MLFlow (Optional)
    EXPERIMENT_NAME: str = "autocard"
    USER: Optional[str] = os.getenv("POSTGRES_USER")
    PASSWORD: Optional[str] = os.getenv("POSTGRES_PASSWORD")
    DB: Optional[str] = os.getenv("POSTGRES_DB")
    HOST: Optional[str] = os.getenv("POSTGRES_HOST")
    PORT: Optional[str] = os.getenv("POSTGRES_PORT")
