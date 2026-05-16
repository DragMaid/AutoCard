from __future__ import annotations

import numpy as np
import logging
import random
from typing import Any, Dict, List, Optional, Tuple, Callable
from ml.environment.renderer import Renderer
from ml.environment.reward_system import RewardCalculator, RewardConfig, create_enhanced_snapshot
from ml.environment.action_resolvers import TrapStageResolvers
from ml.environment.action_resolvers import NormalResolvers
from core.logic.game_engine import GameEngine
from core.data.player import Player
from core.config import Config as game_config
from ml.config import Config as ml_config
from .action_codec import ActionCodec
from .encoder import encode_state
from . import action_handlers

logger = logging.getLogger(__name__)

Action = Tuple[int, Optional[Dict]]


class GameEnv:
    """Refactored game environment for RL training with enhanced reward system.

    This environment exposes the minimal interface used by training loops:

    - reset() -> tuple[state_p1, state_p2]
    - step(actions) -> (states, rewards, done, info)

    Actions are identified by integer indices corresponding to ActionCodec.
    """
    _action_handlers = {
        "summon": action_handlers.SummonHandler,
        "attack": action_handlers.AttackHandler,
        "cast_spell": action_handlers.CastSpellHandler,
        "set_trap": action_handlers.SetTrapHandler,
        "toggle": action_handlers.ToggleHandler,
        "combine": action_handlers.CombineHandler,
        "activate_trap": action_handlers.ActivateHandler,
        "end_turn": action_handlers.EndTurnHandler,
    }

    def __init__(
        self,
        engine: GameEngine,
        render: bool = False,
        reward_config: Optional[RewardConfig] = None
    ) -> None:
        """Initialize the GameEnv.

        Args:
            engine: The GameEngine instance.
            render: Whether to enable rendering.
            reward_config: Optional configuration for rewards.
        """
        self.render = render
        self.engine = engine
        self.reward_calculator = RewardCalculator(config=reward_config)
        if self.render:
            self.renderer = Renderer(engine=self.engine)

    @property
    def num_actions(self) -> int:
        """Return the number of actions in the action space."""
        return ml_config.NUM_ACTIONS

    @property
    def state_dim(self) -> int:
        """Return the dimension of the state space."""
        dummy = self.engine.game_state.players[0]
        return len(self.get_state(dummy))

    def get_winner(self) -> Optional[int]:
        """Get the index of the winning player, or None if game is not over."""
        for idx, player in enumerate(self.engine.game_state.players):
            if player.life_points <= 0:
                return 1 - idx
        return None

    def reset(self) -> None:
        """Start a new game and return initial states for both players.

        Returns:
            A tuple of (state_player1, state_player2).
        """
        # TODO: fix the reward calculator
        self.reward_calculator.log_episode_summary()
        self.engine.reset()
        self.engine.start_game()

        # Update reward calculator with max stats
        max_stats = game_config.MAX_STATS
        self.reward_calculator.max_stats = max_stats
        self.reward_calculator.reset_episode_tracking()

        if hasattr(self, "renderer"):
            self.renderer.reset()
            # Force Matrix to re-sync with the reset GameState objects (held_cards etc)
            self.renderer.matrix.set_game_state(
                self.engine.game_state, force=True)

    def step(self, action: Optional[Action] = None):
        """Execute a segment for the currently acting player."""
        acting_player = self.get_acting_player()
        use_random = action is None
        reward, _ = self.execute(
            player=acting_player,
            action=action,
            use_random=use_random
        )

        # TODO: calculate the handle turn end
        # Add terminal rewards if game ended
        if self.engine.game_state.is_game_over():
            terminal_rewards = self.reward_calculator.calculate_terminal_reward(
                acting_player, self.get_winner())
            reward += terminal_rewards.total

        next_state = self.get_state(acting_player)
        done = self.engine.game_state.is_game_over()
        return next_state, reward, done

    def get_acting_player(self) -> Optional[Player]:
        """Determine the currently acting player (trapper or current)."""
        tm = self.engine.turn_manager
        if tm.is_trap_stage():
            return tm.get_trapper()
        return tm.get_current_player()

    def execute(
        self,
        player: Player,
        action: Action,
        use_random: bool = False,
        callback: Optional[Callable] = None
    ) -> Tuple[float, bool]:
        """Perform a segment of actions for a single player."""
        if use_random:
            mask, _ = self.get_legal_actions(player.id)
            legal_ids = np.where(mask)[0]
            action_id = random.choice(legal_ids)
        else:
            action_id, _ = action

        action_name, action_params = ActionCodec.decode(action_id)
        before_snapshot = create_enhanced_snapshot(self.engine, player)
        reward, done, _ = self._apply_action(
            player=player,
            action_name=action_name,
            params=action_params,
            before_snapshot=before_snapshot
        )

        if hasattr(self, "renderer") and self.render:
            self.renderer.render()

        if callback:
            callback()

        return reward, done

    def get_card_id_at_slot(self, player_id: str, slot_idx: int) -> Optional[int]:
        """Get the card ID at a player's field slot index (0-9)."""
        gs = self.engine.game_state
        cols = game_config.COLS
        rows_per_player = game_config.ROWS // 2

        row = slot_idx // cols
        col = slot_idx % cols

        if (
            0 <= row < rows_per_player and
            0 <= col < cols and
            gs.field_matrix_ownership[row][col] == player_id
        ):
            return gs.field_matrix[row][col]

        return None

    def get_card_slot_idx(self, player_id: str, card: Any) -> int:
        """Get the 0-9 slot index for a card on the field."""
        gs = self.engine.game_state
        cols = game_config.COLS
        rows_per_player = game_config.ROWS // 2

        for r in range(game_config.ROWS):
            for c in range(game_config.COLS):
                if gs.field_matrix[r][c] == card.id:
                    if gs.field_matrix_ownership[r][c] == player_id:
                        if player_id == self.engine.game_state.players[0].id:
                            return (r - rows_per_player) * cols + c
                        else:
                            return (rows_per_player - 1 - r) * cols + c
        return -1

    def get_legal_actions(self, player: Player) -> Tuple[np.ndarray, Dict[int, Tuple[str, Dict[str, Any]]]]:
        """Return mask for legal actions."""
        mask = np.zeros(ml_config.NUM_ACTIONS, dtype=bool)
        legal_actions = self._get_legal_actions(player)
        for action_id in legal_actions:
            mask[action_id] = True
        return mask, legal_actions

    def _get_legal_actions(self, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Identify which resolvers are allowed based on the game stage."""
        tm = self.engine.turn_manager

        # Use different handlers for different stages
        if tm.is_trap_stage():
            trapper = tm.get_trapper()
            if not trapper or trapper.id != player.id:
                return {}
            allowed_resolver_types = TrapStageResolvers

        else:
            if tm.get_current_player().id != player.id:
                return {}
            allowed_resolver_types = NormalResolvers

        legal_actions: Dict[int, Tuple[str, Dict[str, Any]]] = {}
        for resolver in allowed_resolver_types:
            legal_actions.update(resolver.resolve(self, player))

        return legal_actions

    def _apply_action(
        self,
        player: Player,
        action_name: str,
        params: Optional[Dict],
        before_snapshot: Dict[str, Any]
    ) -> Tuple[float, bool, bool]:
        """Apply action and calculate reward."""
        handler = self._action_handlers[action_name]
        success = handler.perform(self, player, params)
        assert success, params
        # TODO: why not do both snapshots here
        after_snapshot = create_enhanced_snapshot(self.engine, player)
        breakdown = self.reward_calculator.calculate_action_reward(
            action_name, player, params, success, before_snapshot, after_snapshot)
        done = self.engine.game_state.is_game_over()
        return breakdown.total, done, success

    def get_player_index(self, player: Player):
        """Return the index of the player in game state list."""
        return self.engine.game_state.players.index(player)

    def get_state(self, player: Player) -> np.ndarray:
        """Return a flat state vector for a given player"""
        return encode_state(self, player.id)
