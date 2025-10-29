import os
import torch
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
BASE_PATH = Path(os.path.dirname(__file__)).parent


class Config:
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

    # Training duration
    MAX_FRAMES = 1_000_000        # total frames to train
    BATCH_SIZE = 64               # samples per update
    BUFFER_SIZE = 200_000         # bigger buffer for more diverse experience

    # RL Hyperparameters
    GAMMA = 0.98                  # slightly lower discount for noisy rewards
    MULTI_STEP = 3                # 3-step returns
    NEGATIVE_REWARD = True

    # Exploration
    EPS_START = 1.0
    EPS_FINAL = 0.05              # allow a bit more exploration at the end
    EPS_DECAY = 75_000            # slower decay → explore longer

    # Update frequency
    TRAIN_FREQ = 4                # train every 4 frames
    UPDATE_TARGET_FREQ = 2000     # update target every 1000 frames
    TAU = 0.005                   # soft target update

    # Self-play / best response
    ETA = 0.1                     # 10% of the time use non-best response

    # Logging & evaluation
    EVALUATION_INTERVAL = 1000    # log every 1000 frames
    RENDER = False                 # turn on only for debugging
    SEED = 42                      # reproducibility

    CHECKPOINT_PATH = Path(BASE_PATH, "ml/saves/checkpoint.pth")
    RUNS_PATH = Path(BASE_PATH, "mlruns")

    # Database
    USER = os.getenv("POSTGRES_USER")
    PASSWORD = os.getenv("POSTGRES_PASSWORD")
    DB = os.getenv("POSTGRES_DB")
    HOST = os.getenv("POSTGRES_HOST")
    PORT = os.getenv("POSTGRES_PORT")
