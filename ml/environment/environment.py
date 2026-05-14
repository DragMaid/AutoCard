from __future__ import annotations

import numpy as np
import logging
import random
from typing import Any, Dict, List, Optional, Tuple
from ml.environment.renderer import Renderer
from ml.environment.reward_system import RewardCalculator, RewardConfig, create_enhanced_snapshot
from ml.environment.action_resolvers import TrapStageResolvers
from ml.environment.action_resolvers import NormalResolvers
from core.logic.game_engine import GameEngine
from core.data.player import Player
from core.config import config
from ml.config import Config as MLConfig
from .action_codec import ActionCodec
from .encoder import encode_state
from . import action_handlers

logger = logging.getLogger(__name__)

action_type = List[Tuple[int, Optional[Dict]]]


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
        self.engine: GameEngine = engine
        self.reward_calculator = RewardCalculator(config=reward_config)
        if self.render:
            self.renderer = Renderer(engine=self.engine)

    @property
    def num_actions(self) -> int:
        """Return the number of actions in the action space."""
        return MLConfig.NUM_ACTIONS

    @property
    def state_dim(self) -> int:
        """Return the dimension of the state space."""
        if not self.engine:
            return 0
        p1 = self.engine.game_state.players[0]
        return len(self._get_state(p1))

    def get_winner(self) -> Optional[int]:
        """Get the index of the winning player, or None if game is not over."""
        for idx, player in enumerate(self.engine.game_state.players):
            if player.life_points <= 0:
                return 1 - idx
        return None

    def reset(self) -> Tuple[np.ndarray, np.ndarray]:
        """Start a new game and return initial states for both players.

        Returns:
            A tuple of (state_player1, state_player2).
        """
        self.reward_calculator.log_episode_summary()
        self.engine.reset()
        self.engine.start_game()

        # Update reward calculator with max stats
        max_stats = config.MAX_STATS
        self.reward_calculator.max_stats = max_stats
        self.reward_calculator.reset_episode_tracking()

        if hasattr(self, "renderer"):
            self.renderer.reset()
            # Force Matrix to re-sync with the reset GameState objects (held_cards etc)
            self.renderer.matrix.set_game_state(
                self.engine.game_state, force=True)

        p1, p2 = self.engine.game_state.players
        return self._get_state(p1), self._get_state(p2)

    def step(self, actions: Optional[Dict[str, action_type]] = None):
        """Execute a segment for the currently acting player."""
        assert self.engine is not None

        players = self.engine.game_state.players
        rewards: List[float] = [0.0 for _ in players]
        info: Dict[str, Any] = {
            "player_1_actions": 0,
            "player_2_actions": 0,
            "acting_player_idx": -1
        }

        acting_player = self._get_acting_player()
        if acting_player is None or self.engine.game_state.is_game_over():
            return self._step_result(players, rewards, info)

        acting_idx = self._get_player_index(acting_player)
        if acting_idx == -1:
            return self._step_result(players, rewards, info)

        info["acting_player_idx"] = acting_idx

        # Execute a segment for the acting player
        action_queues = {k: list(v)
                         for k, v in actions.items()} if actions else {}
        segment_actions_list = action_queues.get(str(acting_idx + 1), [])

        total_turn_reward, actions_taken, _, _ = self.step_single(
            acting_player, segment_actions_list, use_random=actions is None
        )

        rewards[acting_idx] += total_turn_reward
        info[f"player_{acting_idx + 1}_actions"] += actions_taken

        # Handle turn/stage ending
        rewards[acting_idx] += self._handle_turn_end(
            acting_player, actions_taken, segment_actions_list
        )

        # Add terminal rewards if game ended
        if self.engine.game_state.is_game_over():
            terminal_rewards = self._get_terminal_rewards(players)
            for i, r in enumerate(terminal_rewards):
                rewards[i] += r

        return self._step_result(players, rewards, info)

    def _get_acting_player(self) -> Optional[Player]:
        """Determine the currently acting player (trapper or current)."""
        tm = self.engine.turn_manager
        if tm.is_trap_stage():
            return tm.get_trapper()
        return tm.get_current_player()

    def _get_player_index(self, player: Player) -> int:
        """Find the index of a player in the engine's player list."""
        for i, p in enumerate(self.engine.game_state.players):
            if p.id == player.id:
                return i
        return -1

    def _handle_turn_end(
        self,
        player: Player,
        actions_taken: int,
        remaining_actions: List[Any]
    ) -> float:
        """End turn/stage if necessary and return associated reward."""
        if self.engine.game_state.is_game_over():
            return 0.0

        tm = self.engine.turn_manager
        if tm.is_trap_stage() and tm.get_trapper() == player:
            if not remaining_actions or actions_taken >= MLConfig.MAX_ACTIONS_PER_TURN:
                before_snap = create_enhanced_snapshot(self.engine, player)
                num_activated = len(self.engine.game_state.activated_traps)
                if num_activated > 0:
                    self.reward_calculator.set_trap_triggers(num_activated)

                self.engine.end_turn()

                after_snap = create_enhanced_snapshot(self.engine, player)
                breakdown = self.reward_calculator.calculate_action_reward(
                    "end_turn", player, None, True, before_snap, after_snap
                )
                return breakdown.total
        return 0.0

    def _get_terminal_rewards(self, players: List[Player]) -> List[float]:
        """Calculate rewards for the end of the game."""
        rewards = []
        for player in players:
            terminal_breakdown = self.reward_calculator.calculate_terminal_reward(
                player, won=(player.life_points > 0)
            )
            rewards.append(terminal_breakdown.total)
        return rewards

    def _step_result(
        self,
        players: List[Player],
        rewards: List[float],
        info: Dict[str, Any]
    ) -> Tuple[Tuple[np.ndarray, ...], List[float], bool, Dict[str, Any]]:
        """Package the results of a step."""
        states = tuple(self._get_state(p) for p in players)
        done = self.engine.game_state.is_game_over()
        return states, rewards, done, info

    def step_single(
        self,
        player: Player,
        player_actions: List[Tuple[int, Optional[Dict]]],
        max_actions: Optional[int] = None,
        use_random: bool = True
    ) -> Tuple[float, int, int, bool]:
        """Perform a segment of actions for a single player."""
        if max_actions is None:
            max_actions = MLConfig.MAX_ACTIONS_PER_TURN

        total_turn_reward = 0.0
        action_pointer = 0
        actions_taken = 0
        done = False

        while actions_taken < max_actions:
            mask, legal_actions = self.get_legal_actions(player.id)
            if not np.any(mask):
                break

            if action_pointer < len(player_actions):
                action_id, _ = player_actions[action_pointer]
                action_pointer += 1
            elif use_random:
                legal_ids = np.where(mask)[0]
                action_id = random.choice(legal_ids)
            else:
                break

            if action_id in legal_actions:
                action_name, action_params = legal_actions[action_id]
            else:
                action_name, action_params = ActionCodec.decode(action_id)

            before_snapshot = create_enhanced_snapshot(self.engine, player)
            reward, done, _ = self._apply_action(
                player, action_name, action_params, before_snapshot)

            if hasattr(self, "renderer") and self.render:
                self.renderer.render()

            total_turn_reward += reward
            actions_taken += 1

            if done or action_name == "end_turn":
                break

        return total_turn_reward, actions_taken, action_pointer, done

    def get_card_slot_idx(self, player_id: str, card: Any) -> int:
        """Get the 0-9 slot index for a card on the field."""
        gs = self.engine.game_state
        cols = config.COLS
        rows_per_player = config.ROWS // 2

        for r in range(config.ROWS):
            for c in range(config.COLS):
                if gs.field_matrix[r][c] == card.id:
                    if gs.field_matrix_ownership[r][c] == player_id:
                        if player_id == self.engine.game_state.players[0].id:
                            return (r - rows_per_player) * cols + c
                        else:
                            return (rows_per_player - 1 - r) * cols + c
        return -1

    def get_legal_actions(self, player_id: str | int) -> Tuple[np.ndarray, Dict[int, Tuple[str, Dict[str, Any]]]]:
        """Return mask for legal actions."""
        if isinstance(player_id, int):
            player = self.engine.game_state.players[player_id]
        else:
            player = self.engine.game_state.players_lookup[player_id]

        mask = np.zeros(MLConfig.NUM_ACTIONS, dtype=bool)
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
        after_snapshot = create_enhanced_snapshot(self.engine, player)
        breakdown = self.reward_calculator.calculate_action_reward(
            action_name, player, params, success, before_snapshot, after_snapshot)
        done = self.engine.game_state.is_game_over()
        return breakdown.total, done, success

    def _get_state(self, player: Player) -> np.ndarray:
        """Return a flat state vector for a given player."""
        return encode_state(self, player.id)
