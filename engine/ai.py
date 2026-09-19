"""Drives the AI seat in a single-player room.

The agent plays through :class:`~ml.environment.environment.GameEnv`, the same
path training uses, so a checkpoint behaves in a live match exactly as it did in
self-play. Because the engine is authoritative, every action the agent takes goes
through ``_transaction`` and emits its own patch — the browser sees the AI play
one move at a time rather than a finished turn.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from core.data.player import Player
from core.logic.game_engine import GameEngine
from engine.config import EngineConfig

if TYPE_CHECKING:  # pragma: no cover - import cost is the whole point
    from ml.ai_opponent import AIOpponent
    from ml.environment.environment import GameEnv

logger = logging.getLogger(__name__)


def build_opponent(env: "GameEnv", agent_id: int, checkpoint: Path,
                   device: str) -> "AIOpponent":
    """Loads the trained agent for one room.

    Torch is imported here rather than at module scope so a server that only
    ever hosts player-versus-player rooms never pays for it.

    Args:
        env (GameEnv): The room's environment, which defines the action space.
        agent_id (int): Which agent in the checkpoint to load.
        checkpoint (Path): Path to the saved weights.
        device (str): Torch device for inference.

    Returns:
        AIOpponent: A ready agent. Falls back to untrained weights when the
        checkpoint is absent, so the stack is playable before a model exists.
    """
    from ml.ai_opponent import AIOpponent

    if not checkpoint.exists():
        logger.warning(
            "No checkpoint at %s; the AI seat will play untrained", checkpoint)

    return AIOpponent(
        env=env,
        checkpoint_path=checkpoint,
        agent_id=agent_id,
        device=device,
    )


class AiDriver:
    """Plays the AI seat whenever the turn belongs to it.

    Attributes:
        engine: The room's authoritative engine.
        env: The environment wrapping that engine.
        player: The player this driver controls.
        opponent: The trained agent, loaded on first use.
    """

    def __init__(
        self,
        engine: GameEngine,
        env: "GameEnv",
        player: Player,
        config: type[EngineConfig] = EngineConfig,
    ) -> None:
        """Initializes the driver without loading any weights yet.

        Args:
            engine (GameEngine): The room's authoritative engine.
            env (GameEnv): Environment built on that engine.
            player (Player): The seat the agent plays.
            config: Engine settings, overridable in tests.
        """
        self.engine = engine
        self.env = env
        self.player = player
        self._config = config
        self.opponent: Optional["AIOpponent"] = None

    @property
    def is_turn(self) -> bool:
        """True when the agent is the acting player and the match is live."""
        if self.engine.game_state.is_game_over():
            return False
        acting = self.env.get_acting_player()
        return acting is not None and acting.id == self.player.id

    def _ensure_loaded(self) -> "AIOpponent":
        """Loads the agent on first use.

        Returns:
            AIOpponent: The loaded agent.
        """
        if self.opponent is None:
            self.opponent = build_opponent(
                env=self.env,
                agent_id=self.player.player_index,
                checkpoint=self._config.CHECKPOINT_PATH,
                device=self._config.AI_DEVICE,
            )
        return self.opponent

    def _step(self) -> bool:
        """Plays one action. Runs on a worker thread; never call concurrently.

        Returns:
            bool: True when an action was played, False when the agent had
            nothing legal left and the turn was handed back.
        """
        mask, _ = self.env.get_legal_actions(self.player)
        if not mask.any():
            # A stage with no legal action would otherwise wedge the match, so
            # give the turn back rather than asking the policy for a move it
            # cannot make.
            logger.info("AI has no legal action; ending its turn")
            self.engine.end_turn()
            return False

        action_id = self._ensure_loaded().get_action(
            self.player, deterministic=True)
        self.env.execute(
            player=self.player, action_id=action_id, use_random=False)
        return True

    async def play_turn(self) -> None:
        """Plays actions until the turn is no longer the agent's.

        Inference is offloaded to a worker thread so torch cannot stall the
        service's event loop, and steps are spaced out so the browser can
        animate each one.
        """
        loop = asyncio.get_running_loop()
        steps = 0

        while self.is_turn and steps < self._config.AI_MAX_STEPS:
            steps += 1
            try:
                played = await loop.run_in_executor(None, self._step)
            except Exception:
                logger.exception("AI step failed; ending the AI turn")
                await loop.run_in_executor(None, self.engine.end_turn)
                return

            if not played:
                return

            if self.is_turn and self._config.AI_DELAY > 0:
                await asyncio.sleep(self._config.AI_DELAY)

        if steps >= self._config.AI_MAX_STEPS:
            logger.warning("AI hit the per-turn step cap; ending its turn")
            await loop.run_in_executor(None, self.engine.end_turn)
