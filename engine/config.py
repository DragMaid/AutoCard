"""Settings for the engine service, read from the environment."""

from __future__ import annotations

import os
from pathlib import Path

from ml.config import Config as MlConfig


class EngineConfig:
    """Runtime settings for :mod:`engine.service`.

    Attributes:
        HOST: Interface the WebSocket server binds to.
        PORT: Port the relay connects to.
        ROOM_TTL: Seconds a room survives after its relay socket drops. The
            relay reconnects on restart and resumes the same match, so this is
            deliberately longer than a redeploy takes.
        AI_DELAY: Seconds between consecutive AI actions, so a human can follow
            what the opponent did instead of seeing a turn resolve instantly.
        AI_MAX_STEPS: Safety valve on one AI turn, in case a policy loops.
        AI_DEVICE: Torch device used for inference.
        CHECKPOINT_PATH: Trained weights. A missing file falls back to an
            untrained agent, so the stack runs end to end before a model exists.
    """

    HOST: str = os.getenv("AUTOCARD_ENGINE_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("AUTOCARD_ENGINE_PORT", "9000"))
    ROOM_TTL: float = float(os.getenv("AUTOCARD_ROOM_TTL", "300"))

    AI_DELAY: float = float(os.getenv("AUTOCARD_AI_DELAY", "0.8"))
    AI_MAX_STEPS: int = int(os.getenv("AUTOCARD_AI_MAX_STEPS", "64"))
    AI_DEVICE: str = os.getenv("AUTOCARD_AI_DEVICE", MlConfig.DEVICE)

    CHECKPOINT_PATH: Path = Path(
        os.getenv("AUTOCARD_CHECKPOINT", str(MlConfig.CHECKPOINT_PATH))
    )
