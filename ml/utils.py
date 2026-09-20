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


def epsilon_scheduler(eps_start: float, eps_final: float, eps_decay: int) -> Callable[[int], float]:
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
    checkpoint["encoder"] = agent.encoder.state_dict()

    torch.save(checkpoint, checkpoint_path)
    logger.info(f"Models saved to {checkpoint_path}")


def load_model(agent: Agent, device="cpu", path=Config.CHECKPOINT_PATH,
               agent_id: int = 0):
    """
    Load all models from a single checkpoint file.

    Two layouts are accepted. The current one, written by save_model, holds one
    set of weights under "dqn"/"policy"/"encoder". Self-play runs before that
    saved both seats in one file, as "agent_<n>_model" and "agent_<n>_policy",
    with the encoder's weights nested inside each network under "feature_net.".
    Published checkpoints are still in that older shape, so it is read rather
    than rejected.

    Args:
        agent: Agent
        device: Device to load models to
        path: Path to checkpoint file
        agent_id: Which seat to load, for the per-seat layout only

    Raises:
        ValueError: If the file is missing, or holds neither layout.
    """
    checkpoint_path = Path(path)
    if not checkpoint_path.exists():
        raise ValueError(f"No model found at {checkpoint_path}")

    # Load checkpoint
    checkpoint = torch.load(checkpoint_path, map_location=device)

    if "dqn" in checkpoint:
        agent.dqn.load_state_dict(checkpoint["dqn"])
        agent.policy.load_state_dict(checkpoint["policy"])
        # Last, and deliberately so: dqn and policy each carry a copy of the
        # encoder's parameters, and this is the one the agent should end up with.
        agent.encoder.load_state_dict(checkpoint["encoder"])
    elif f"agent_{agent_id}_model" in checkpoint:
        # The dqn goes last here for the same reason: the encoder is a shared
        # module, and inference reads it through the dqn.
        agent.policy.load_state_dict(checkpoint[f"agent_{agent_id}_policy"])
        agent.dqn.load_state_dict(checkpoint[f"agent_{agent_id}_model"])
    else:
        raise ValueError(
            f"Unrecognized checkpoint at {checkpoint_path}: expected 'dqn' or "
            f"'agent_{agent_id}_model', found {sorted(checkpoint)}"
        )

    logger.info(f"Models loaded from {checkpoint_path}")


def safe_mask(mask: torch.Tensor) -> torch.Tensor:
    """
    Ensures every sequence has at least one valid token.

    Args:
        mask: Bool tensor of shape (B, T)
              True = valid token, False = invalid

    Returns:
        mask with guarantee that each row has >= 1 True
    """

    # find rows where everything is invalid
    empty_rows = mask.any(dim=1)

    # if no empty rows, return original (no copy needed)
    if not empty_rows.any():
        return mask

    # clone only when needed
    safe = mask.clone()

    # force token 0 to be valid for empty rows
    safe[empty_rows, 0] = False

    return safe
