from __future__ import annotations

import time
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ml.environment.action_handlers import (
    SummonHandler,
    AttackHandler,
    CastSpellHandler,
    SetTrapHandler,
    ToggleHandler,
    CombineHandler,
    ActionHandler,
)
from ml.environment.action_resolvers import (
    LegalActionResolver,
    SummonResolver,
    AttackResolver,
    CastSpellResolver,
    SetTrapResolver,
    ToggleResolver,
    CombineResolver,
    EndTurnResolver,
)
from ml.environment.utils import (
    ability_to_float,
    card_type_to_int,
)
from ml.environment.renderer import Renderer
from ml.environment.reward_system import (
    RewardCalculator,
    RewardConfig,
    create_enhanced_snapshot
)
from core.handle_game_logic.game_engine import GameEngine
from core.player import Player
import logging

# Constants
CARD_FEATURES = 6
DEFAULT_PARAM_DIM = 2

action_type = List[Tuple[int, Optional[Dict]]]


class GameEnv:
    """Refactored game environment for RL training with enhanced reward system.

    This environment exposes the minimal interface used by training loops:

    - reset() -> tuple[state_p1, state_p2]
    - step(actions) -> (states, rewards, done, info)

    Actions are identified by integer indices corresponding to
    :pyattr:`ACTIONS`.
    """

    ACTIONS: Sequence[str] = (
        "summon",
        "cast_spell",
        "set_trap",
        "toggle",
        "attack",
        "end_turn",
        "combine",
    )

    def __init__(self,
                 engine: GameEngine,
                 render: bool = False,
                 reward_config: Optional[RewardConfig] = None) -> None:
        self.render = render
        self.engine: GameEngine = engine
        self.logger = logging.getLogger("GameEngine")

        # Initialize reward calculator
        self.reward_calculator = RewardCalculator(config=reward_config)

        self._init_handlers_and_resolvers()

        if self.render:
            self.renderer = Renderer(engine=self.engine)

    # -------------------- properties --------------------
    @property
    def param_dim(self) -> int:
        """Maximum number of parameters required for any action."""
        return DEFAULT_PARAM_DIM

    @property
    def num_actions(self) -> int:
        return len(self.ACTIONS)

    @property
    def state_dim(self) -> int:
        if not self.engine:
            return 0
        p1 = self.engine.game_state.players[0]
        return len(self._get_state(p1))

    # -------------------- engine lifecycle --------------------
    def reset(self) -> Tuple[np.ndarray, np.ndarray]:
        """Start a new game and return initial states for both players.

        Returns
        -------
        tuple
            (state_player1, state_player2)
        """
        # Log previous episode summary if exists
        self.reward_calculator.log_episode_summary()
        self.engine.reset()
        self.engine.start_game()

        # Update reward calculator with max stats
        max_stats = float(self.engine.rule_engine.max_stats)
        self.reward_calculator.max_stats = max_stats
        self.reward_calculator.reset_episode_tracking()

        p1, p2 = self.engine.game_state.players
        if hasattr(self, "renderer"):
            self.renderer.reset()

        return self._get_state(p1), self._get_state(p2)

    # -------------------- step loop --------------------

    def step(self, actions: Optional[Dict[str, action_type]] = None):
        """Execute a full round where each player takes multiple actions.

        Parameters
        ----------
        actions
            Optional dict mapping player index as string ("1", "2") to a
            list of (action_idx, params) tuples. If omitted, random legal
            actions are chosen.
        max_actions_per_turn
            Maximum actions a player may take in their turn.
        """
        assert self.engine is not None
        players = self.engine.game_state.players
        rewards: List[float] = [0.0 for _ in players]
        info: Dict[str, Any] = {"player_1_actions": 0, "player_2_actions": 0}

        for idx, player in enumerate(players):
            player_actions = actions.get(str(idx + 1), []) if actions else []

            self.logger.info(f"\n{'─'*60}")
            self.logger.info(f"▶️  {player.name}'s TURN START (Turn {
                             self.engine.turn_manager.turn_count})")
            self.logger.info(f"{'─'*60}")

            # Make sure that it is indeed the player's turn
            if self.engine.turn_manager.get_current_player() != player:
                self.engine.end_turn()

            total_turn_reward, actions_taken, done = self.step_single(
                player, player_actions)

            # End of player's turn
            rewards[idx] = total_turn_reward
            info[f"player_{idx + 1}_actions"] = actions_taken

            self.logger.info(f"{'─'*60}")
            self.logger.info(f"📊 {player.name}'s turn summary: {actions_taken} actions, {
                             total_turn_reward:+.4f} total reward")
            self.logger.info(f"{'─'*60}\n")

            if done:
                break

            # Make sure that the player always end their turn
            if self.engine.turn_manager.get_current_player() == player:
                self.engine.end_turn()

        # Add terminal rewards if game ended
        done = self.engine.game_state.is_game_over()
        if done:
            for idx, player in enumerate(players):
                if player.life_points > 0:
                    terminal_breakdown = self.reward_calculator.calculate_terminal_reward(
                        player, won=True)
                    rewards[idx] += terminal_breakdown.total
                else:
                    terminal_breakdown = self.reward_calculator.calculate_terminal_reward(
                        player, won=False)
                    rewards[idx] += terminal_breakdown.total

        states = tuple(self._get_state(p) for p in players)
        return states, rewards, done, info

    def step_single(self,
                    player,
                    player_actions,
                    max_actions_per_turn: int = 10
                    ):
        total_turn_reward = 0.0
        action_pointer = 0
        actions_taken = 0

        while actions_taken < max_actions_per_turn:

            legal, params = self._get_legal_actions(player)
            if not legal:
                self.logger.info(
                    f"  ℹ️  No legal actions available for {player.name}")
                break

            if action_pointer < len(player_actions):
                action_idx, action_params = player_actions[action_pointer]
                action_pointer += 1
                if action_idx >= len(self.ACTIONS):
                    action_idx = self.ACTIONS.index("end_turn")
            else:
                candidate = random.choice(legal)
                action_idx = self.ACTIONS.index(candidate)
                action_params = self._pick_params_for_action(
                    candidate, params)

            # Take snapshot before action
            before_snapshot = create_enhanced_snapshot(self.engine, player)

            # Perform action via handler
            reward, done, success = self._apply_action(
                player, action_idx, action_params, before_snapshot)

            if hasattr(self, "renderer"):
                self.renderer.render()

            total_turn_reward += reward
            actions_taken += 1

            if done or self.ACTIONS[action_idx] == "end_turn":
                break

        return total_turn_reward, actions_taken, done

    # -------------------- action wiring --------------------
    def _init_handlers_and_resolvers(self) -> None:
        self._action_handlers: Dict[str, ActionHandler] = {
            "summon": SummonHandler(),
            "attack": AttackHandler(),
            "cast_spell": CastSpellHandler(),
            "set_trap": SetTrapHandler(),
            "toggle": ToggleHandler(),
            "combine": CombineHandler(),
            "end_turn": ActionHandler(),
        }

        # resolvers should be ordered (optional)
        self._resolvers: List[LegalActionResolver] = [
            SummonResolver(),
            AttackResolver(),
            CastSpellResolver(),
            SetTrapResolver(),
            ToggleResolver(),
            CombineResolver(),
            EndTurnResolver(),
        ]

    def get_legal_actions(self, player_idx):
        """Return mask and parameters for legal actions."""
        player = self.engine.game_state.players[player_idx]
        legal_actions, params = self._get_legal_actions(player)

        # Create mask
        mask = np.zeros(self.num_actions, dtype=bool)
        for action_name in legal_actions:
            action_idx = self.ACTIONS.index(action_name)
            mask[action_idx] = True

        return mask, params

    def _get_legal_actions(self, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        legal_actions: List[str] = []
        action_params: Dict[str, Any] = {}
        for resolver in self._resolvers:
            names, params = resolver.resolve(self, player)
            for name in names:
                if name not in legal_actions:
                    legal_actions.append(name)
            action_params.update(params)
        return legal_actions, action_params

    @staticmethod
    def _pick_params_for_action(action_name: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Select a safe default parameter set for the chosen action."""
        param_dict = params.get(action_name, {})

        if action_name == "summon":
            monsters = param_dict.get("monsters", [])
            return {"monster": monsters[0]} if monsters else None

        if action_name == "attack":
            attackers = param_dict.get("attackers", [])
            targets = param_dict.get("targets", [])
            if attackers and targets:
                return {"attacker": attackers[0], "target": targets[0]}
            return None

        if action_name == "cast_spell":
            spells = param_dict.get("spells", [])
            targets_dict = param_dict.get("targets", {})
            if spells:
                spell_idx = spells[0]
                targets = targets_dict.get(spell_idx, [])
                return {"spell": spell_idx, "target": targets[0] if targets else None}
            return None

        if action_name == "set_trap":
            traps = param_dict.get("traps", [])
            return {"trap": traps[0]} if traps else None

        if action_name == "toggle":
            toggles = param_dict.get("toggles", [])
            return {"toggle": toggles[0]} if toggles else None

        if action_name == "combine":
            pairs = param_dict.get("pairs", [])
            if pairs:
                return {"pair": pairs[0]}
            return None

        return None

    def _apply_action(
        self,
        player: Player,
        action_idx: int,
        params: Optional[Dict],
        before_snapshot: Dict[str, Any]
    ) -> Tuple[float, bool, bool]:
        """Apply action and calculate reward using the new reward system.

        Returns:
            Tuple of (reward, done, success)
        """
        assert self.engine is not None
        action_name = self.ACTIONS[action_idx]
        handler = self._action_handlers.get(action_name)
        done = False
        success = False

        # Handle no-op or unimplemented actions
        if handler is None or (isinstance(handler, ActionHandler) and type(handler) is ActionHandler):
            if action_name == "end_turn":
                # End turn is always successful
                success = True
            else:
                self.logger.warning(
                    f"⚠️  Action '{action_name}' has no handler")

            after_snapshot = create_enhanced_snapshot(self.engine, player)
            breakdown = self.reward_calculator.calculate_action_reward(
                action_name, player, params, success, before_snapshot, after_snapshot
            )
            return breakdown.total, done, success

        # Perform the action
        try:
            _ = handler.perform(self, player, params)
            success = True
        except Exception as e:
            self.logger.error(
                f"❌ Action '{action_name}' failed with error: {e}")
            success = False

        # Take snapshot after action
        after_snapshot = create_enhanced_snapshot(self.engine, player)

        # Calculate reward using the new reward system
        breakdown = self.reward_calculator.calculate_action_reward(
            action_name, player, params, success, before_snapshot, after_snapshot
        )

        # Check for game over
        if self.engine.game_state.is_game_over():
            done = True

        return breakdown.total, done, success

    # -------------------- state encoding --------------------
    def _get_state(self, player: Player) -> np.ndarray:
        """Return a flat state vector for a given player.

        Layout: [player_features, hand_encoded, board_encoded]
        """
        player_features = self._encode_player_features(player)
        hand_encoded = self._encode_hand(player)
        board_encoded = self._encode_board(player)
        return np.concatenate([player_features, hand_encoded, board_encoded])

    @staticmethod
    def _encode_player_features(player: Player) -> np.ndarray:
        return np.array([player.life_points / player.max_life_points], dtype=np.float32)

    def _encode_hand(self, player: Player) -> np.ndarray:
        gs = self.engine.game_state
        hand_card_ids = gs.player_info[player.id]["held_cards"].cards
        max_hand = self.engine.rule_engine.max_hand_cards
        hand_encoded = np.zeros(max_hand * CARD_FEATURES, dtype=np.float32)
        for i, card_id in enumerate(hand_card_ids[:max_hand]):
            card = gs.get_card_by_id(card_id)
            if not card:
                continue
            base = i * CARD_FEATURES
            hand_encoded[base + 0] = card_type_to_int(card)
            hand_encoded[base + 1] = getattr(card, "atk", 0) / \
                self.reward_calculator.max_stats
            hand_encoded[base + 2] = getattr(card, "defense", 0) / \
                self.reward_calculator.max_stats
            owner_flag = 0  # current player
            hand_encoded[base + 3] = owner_flag
            hand_encoded[base + 4] = ability_to_float(card)
            hand_encoded[base +
                         5] = 1 if card.is_face_down else 0
        return hand_encoded

    def _encode_board(self, player: Player) -> np.ndarray:
        gs = self.engine.game_state
        board = gs.field_matrix
        board_encoded: List[float] = []
        for row in board:
            for card_id in row:
                if card_id:
                    card = gs.get_card_by_id(card_id)
                    owner_flag = 0 if card.owner_id == player.id else 1
                    board_encoded.extend([
                        card_type_to_int(card),
                        getattr(card, "atk", 0) /
                        self.reward_calculator.max_stats,
                        getattr(card, "defense", 0) /
                        self.reward_calculator.max_stats,
                        owner_flag,
                        ability_to_float(card),
                        1 if card.is_face_down else 0,
                    ])
                else:
                    board_encoded.extend([0.0] * CARD_FEATURES)
        return np.array(board_encoded, dtype=np.float32)

    # -------------------- helpers --------------------
    def get_winner(self) -> Optional[int]:
        """Get the index of the winning player, or None if game is not over."""
        for idx, player in enumerate(self.engine.game_state.players):
            if player.life_points <= 0:
                return 1 - idx  # Return the other player's index
        return None

    def get_reward_summary(self) -> Dict[str, Any]:
        """Get summary of rewards for the current episode."""
        return self.reward_calculator.get_episode_summary()

    def step_evaluation(self,
                        player,
                        player_actions,
                        max_actions,
                        callback=None
                        ):
        action_pointer = 0
        actions_taken = 0

        while actions_taken < max_actions:
            legal, params = self._get_legal_actions(player)
            if not legal:
                self.logger.info(
                    f"  ℹ️  No legal actions available for {player.name}")
                break

            if action_pointer < len(player_actions):
                action_idx, action_params = player_actions[action_pointer]
                action_pointer += 1
                if action_idx >= len(self.ACTIONS):
                    action_idx = self.ACTIONS.index("end_turn")
            else:
                candidate = random.choice(legal)
                action_idx = self.ACTIONS.index(candidate)
                action_params = self._pick_params_for_action(
                    candidate, params)

            # Take snapshot before action
            before_snapshot = create_enhanced_snapshot(self.engine, player)

            # Perform action via handler
            reward, done, success = self._apply_action(
                player, action_idx, action_params, before_snapshot)

            actions_taken += 1

            if callback:
                callback()

            if done or self.ACTIONS[action_idx] == "end_turn":
                break

            time.sleep(0.8)
