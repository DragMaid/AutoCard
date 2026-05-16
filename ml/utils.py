from __future__ import annotations

import logging
import torch
import numpy as np
import math
import random
from typing import TYPE_CHECKING, Callable
from pathlib import Path
from ml.config import Config

if TYPE_CHECKING:
    from ml.trainer.agent import Agent

logger = logging.getLogger(__name__)


def epsilon_scheduler(eps_start: float = 1.0, eps_final: float = 0.01, eps_decay: int = 50000) -> Callable[[int], float]:
    """
    Return a function to get epsilon at a given frame index.

    Args:
        eps_start: The initial epsilon value.
        eps_final: The final epsilon value.
        eps_decay: The frame index at which to reach the final epsilon.

    Returns:
        A callable function that returns the epsilon for a given frame index.
    """
    def function(frame_idx: int) -> float:
        return eps_final + (eps_start - eps_final) \
            * math.exp(-1. * frame_idx / eps_decay)
    return function


def set_global_seeds(seed=42):
    """Set seeds for reproducibility."""
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)


def save_model(agent: Agent, path: str = Config.CHECKPOINT_PATH):
    """
    Save all models to a single checkpoint file.

    Args:
        agent: Agent
        path: Path object or string to checkpoint file
    """
    checkpoint_path = Path(path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    # Build checkpoint dict with proper naming
    checkpoint = {}
    checkpoint["dqn"] = agent.dqn.state_dict()
    checkpoint["policy"] = agent.policy.state_dict()

    torch.save(checkpoint, checkpoint_path)
    logger.info(f"Models saved to {checkpoint_path}")


def load_model(agent: Agent, device="cpu", path=Config.CHECKPOINT_PATH):
    """
    Load all models from a single checkpoint file.

    Args:
        agent: Agent
        device: Device to load models to
        checkpoint_path: Path to checkpoint file
    """
    checkpoint_path = Path(path)
    if not checkpoint_path.exists():
        raise ValueError(f"No model found at {checkpoint_path}")

    # Load checkpoint
    checkpoint = torch.load(checkpoint_path, map_location=device)
    agent.dqn.load_state_dict(checkpoint["dqn"])
    agent.policy.load_state_dict(checkpoint["policy"])
    logger.info(f"Models loaded from {checkpoint_path}")
