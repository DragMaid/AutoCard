from __future__ import annotations

import time
import random
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ml.environment.action_handlers import (
    SummonHandler,
    AttackHandler,
    CastSpellHandler,
    SetTrapHandler,
    ToggleHandler,
    CombineHandler,
    ActivateHandler,
    EndTurnHandler,
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
    TrapActivateResolver,
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
from core.data.player import Player
from ml.config import Config
from core.utils import get_logger
from .action_codec import ActionCodec

# TODO: refactor this shit for god sake
# Constants
CARD_FEATURES = 6

action_type = List[Tuple[int, Optional[Dict]]]


class GameEnv:
    """Refactored game environment for RL training with enhanced reward system.

    This environment exposes the minimal interface used by training loops:

    - reset() -> tuple[state_p1, state_p2]
    - step(actions) -> (states, rewards, done, info)

    Actions are identified by integer indices corresponding to ActionCodec.
    """

    def __init__(
        self,
        engine: GameEngine,
        render: bool = False,
        reward_config: Optional[RewardConfig] = None
    ) -> None:
        self.render = render
        self.engine: GameEngine = engine
        self.logger = get_logger()
        self.reward_calculator = RewardCalculator(config=reward_config)
        self._init_handlers_and_resolvers()
        if self.render:
            self.renderer = Renderer(engine=self.engine)

    @property
    def num_actions(self) -> int:
        return Config.NUM_ACTIONS

    @property
    def state_dim(self) -> int:
        if not self.engine:
            return 0
        p1 = self.engine.game_state.players[0]
        return len(self._get_state(p1))

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
            # Force Matrix to re-sync with the reset GameState objects (held_cards etc)
            self.renderer.field_matrix.set_game_state(
                self.engine.game_state, force=True)

        return self._get_state(p1), self._get_state(p2)

    def step(self, actions: Optional[Dict[str, action_type]] = None):
        """Execute a segment for the currently acting player.
        
        If actions are provided, it executes actions for the acting player from their queue.
        If no actions are provided, it performs a random segment for the acting player.
        """
        assert self.engine is not None
        players = self.engine.game_state.players
        rewards: List[float] = [0.0 for _ in players]
        info: Dict[str, Any] = {
            "player_1_actions": 0,
            "player_2_actions": 0,
            "acting_player_idx": -1
        }

        # Track which actions from the provided lists have been consumed
        action_queues = {k: list(v)
                         for k, v in actions.items()} if actions else {}
        provided_actions = actions is not None

        tm = self.engine.turn_manager
        
        # Determine acting player (trapper or current)
        if tm.is_trap_stage():
            acting_player = tm.get_trapper()
        else:
            acting_player = tm.get_current_player()

        if acting_player is None or self.engine.game_state.is_game_over():
            states = tuple(self._get_state(p) for p in players)
            return states, rewards, self.engine.game_state.is_game_over(), info

        # Find acting player index
        acting_idx = -1
        for i, player in enumerate(self.engine.players):
            if player.id == acting_player.id:
                acting_idx = i
                break
        
        if acting_idx == -1:
            states = tuple(self._get_state(p) for p in players)
            return states, rewards, self.engine.game_state.is_game_over(), info

        info["acting_player_idx"] = acting_idx
        player_id_str = str(acting_idx + 1)

        # Execute a segment for the acting player
        segment_actions_list = action_queues.get(player_id_str, [])
        
        self.logger.info(f"[STAGE] {acting_player.name}'s {'TRAP ' if tm.is_trap_stage() else ''}SEGMENT START (Turn {tm.turn_count})")

        total_turn_reward, actions_taken, consumed_from_list, done = self.step_single(
            acting_player, segment_actions_list, use_random=not provided_actions)

        # Update results
        rewards[acting_idx] += total_turn_reward
        info[f"player_{acting_idx + 1}_actions"] += actions_taken

        self.logger.info(f"{acting_player.name}'s segment summary: {actions_taken} actions, {total_turn_reward:+.4f} segment reward")

        # Handle turn/stage ending if no more actions or forced end
        if not done and not self.engine.game_state.is_game_over():
            # If we are in trap stage and finished our actions, we must resolve traps
            if tm.is_trap_stage() and tm.get_trapper() == acting_player:
                if not segment_actions_list or actions_taken >= 10: # Assuming 10 is max actions per turn
                    before_snap = create_enhanced_snapshot(self.engine, acting_player)
                    num_activated = len(self.engine.game_state.activated_traps)
                    if num_activated > 0:
                        self.reward_calculator.set_trap_triggers(num_activated)
                    self.engine.end_turn()
                    after_snap = create_enhanced_snapshot(self.engine, acting_player)
                    breakdown = self.reward_calculator.calculate_action_reward(
                        "end_turn", acting_player, None, True, before_snap, after_snap
                    )
                    rewards[acting_idx] += breakdown.total

        # Add terminal rewards if game ended
        done = self.engine.game_state.is_game_over()
        if done:
            for idx, player in enumerate(players):
                terminal_breakdown = self.reward_calculator.calculate_terminal_reward(
                    player, won=(player.life_points > 0))
                rewards[idx] += terminal_breakdown.total

        states = tuple(self._get_state(p) for p in players)
        return states, rewards, done, info

    def step_single(self,
                    player,
                    player_actions,
                    max_actions_per_turn: int = 10,
                    use_random: bool = True
                    ):
        total_turn_reward = 0.0
        action_pointer = 0
        actions_taken = 0
        done = False

        while actions_taken < max_actions_per_turn:
            mask, legal_actions = self.get_legal_actions(player.id)
            if not np.any(mask):
                # This player has no legal actions (e.g., interrupted by trap stage)
                break

            if action_pointer < len(player_actions):
                action_id, _ = player_actions[action_pointer]
                action_pointer += 1
            elif use_random:
                # Random legal action selection
                legal_ids = np.where(mask)[0]
                action_id = random.choice(legal_ids)
            else:
                # No more provided actions and random is disabled
                break

            # Use legal_actions if available, otherwise decode
            if action_id in legal_actions:
                action_name, action_params = legal_actions[action_id]
            else:
                action_name, action_params = ActionCodec.decode(action_id)

            # Take snapshot before action
            before_snapshot = create_enhanced_snapshot(self.engine, player)

            # Perform action via handler
            reward, done, success = self._apply_action(
                player, action_name, action_params, before_snapshot)

            if hasattr(self, "renderer"):
                self.renderer.render()

            total_turn_reward += reward
            actions_taken += 1

            if done or action_name == "end_turn":
                break

        return total_turn_reward, actions_taken, action_pointer, done

    # TODO: just move this to the other place
    def _init_handlers_and_resolvers(self) -> None:
        self._action_handlers: Dict[str, ActionHandler] = {
            "summon": SummonHandler(),
            "attack": AttackHandler(),
            "cast_spell": CastSpellHandler(),
            "set_trap": SetTrapHandler(),
            "toggle": ToggleHandler(),
            "combine": CombineHandler(),
            "activate_trap": ActivateHandler(),
            "end_turn": EndTurnHandler(),
        }

        # resolvers should be ordered
        self._resolvers: List[LegalActionResolver] = [
            SummonResolver(),
            AttackResolver(),
            CastSpellResolver(),
            SetTrapResolver(),
            ToggleResolver(),
            CombineResolver(),
            TrapActivateResolver(),
            EndTurnResolver(),
        ]

    def _get_card_slot_idx(self, player_id: str, card: Any) -> int:
        """Get the 0-9 slot index for a card on the field."""
        gs = self.engine.game_state
        for r in range(gs.rows):
            for c in range(gs.cols):
                if gs.field_matrix[r][c] == card.id:
                    if gs.field_matrix_ownership[r][c] == player_id:
                        # Map (r, c) to 0-9 based on player
                        if player_id == self.engine.game_state.players[0].id:
                            return (r - 2) * 5 + c
                        else:
                            return (1 - r) * 5 + c
        return -1

    def _get_card_id_at_slot(self, player_id: str, slot_idx: int) -> Optional[str]:
        """Get the card ID at a specific player slot."""
        gs = self.engine.game_state
        if player_id == self.engine.game_state.players[0].id:
            r = 2 + (slot_idx // 5)
            c = slot_idx % 5
        else:
            r = 1 - (slot_idx // 5)
            c = slot_idx % 5

        if 0 <= r < gs.rows and 0 <= c < gs.cols:
            return gs.field_matrix[r][c]
        return None

    # TODO: refactor this for the love of god
    def get_legal_actions(self, player_id: str | int):
        """Return mask for legal actions."""
        # Convert index to player ID if needed
        if isinstance(player_id, int):
            player = self.engine.game_state.players[player_id]
        else:
            player = self.engine.game_state.players_lookup[player_id]

        mask = np.zeros(Config.NUM_ACTIONS, dtype=bool)

        # Resolve all basic legal actions from resolvers
        legal_actions = self._get_legal_actions(player)

        for action_id in legal_actions:
            mask[action_id] = True

        return mask, legal_actions

    def _get_legal_actions(self, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Identify which resolvers are allowed based on the game stage."""
        tm = self.engine.turn_manager

        if tm.is_trap_stage():
            trapper = tm.get_trapper()
            if not trapper or trapper.id != player.id:
                # Opponent of trapper has NO actions during trap stage
                return {}
            # Trapper can ONLY use TrapActivateResolver or EndTurnResolver
            allowed_resolver_types = (TrapActivateResolver, EndTurnResolver)
        else:
            # Normal turn: acting player can do everything EXCEPT manual trap activation
            if tm.get_current_player().id != player.id:
                return {}
            allowed_resolver_types = (SummonResolver, AttackResolver, CastSpellResolver,
                                      SetTrapResolver, ToggleResolver, CombineResolver,
                                      EndTurnResolver)

        legal_actions: Dict[int, Tuple[str, Dict[str, Any]]] = {}
        for resolver in self._resolvers:
            if isinstance(resolver, allowed_resolver_types):
                legal_actions.update(resolver.resolve(self, player))
        return legal_actions

    def _apply_action(
        self,
        player: Player,
        action_name: str,
        params: Optional[Dict],
        before_snapshot: Dict[str, Any]
    ) -> Tuple[float, bool, bool]:
        """Apply action and calculate reward using the new reward system.

        Returns:
            Tuple of (reward, done, success)
        """
        assert self.engine is not None
        handler = self._action_handlers.get(action_name)
        done = False
        success = False

        # Perform the action
        try:
            success = handler.perform(self, player, params)
        except Exception as e:
            self.logger.error(
                f"Action '{action_name}' failed with error: {e}")
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
        """Normalize the player healthbar"""
        return np.array([player.life_points / player.max_life_points], dtype=np.float32)

    # TODO: re-consider this design later
    # TODO: there's way to many weird constants, fix this
    def _encode_hand(self, player: Player) -> np.ndarray:
        gs = self.engine.game_state
        hand_card_ids = gs.player_info[player.id]["held_cards"].cards
        max_hand = self.engine.rule_engine.max_hand_cards

        # Create a temp placeholder
        # TODO: fix this weird ass hard coded card feature
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
            # TODO: wtf is even this
            owner_flag = 0  # current player
            hand_encoded[base + 3] = owner_flag
            # TODO: rather write this into category separation
            # TODO: rewrite this into vector embeddings
            hand_encoded[base + 4] = ability_to_float(card)
            hand_encoded[base + 5] = 1 if card.is_face_down else 0
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
                        # TODO: same for this thing
                        ability_to_float(card),
                        1 if card.is_face_down else 0,
                    ])
                else:
                    board_encoded.extend([0.0] * CARD_FEATURES)
        return np.array(board_encoded, dtype=np.float32)

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
            mask, legal_actions = self.get_legal_actions(player.id)
            if not np.any(mask):
                break

            if action_pointer < len(player_actions):
                action_id, _ = player_actions[action_pointer]
                action_pointer += 1
            else:
                legal_ids = np.where(mask)[0]
                action_id = random.choice(legal_ids)

            # Use legal_actions if available, otherwise decode
            if action_id in legal_actions:
                action_name, action_params = legal_actions[action_id]
            else:
                action_name, action_params = ActionCodec.decode(action_id)

            # Take snapshot before action
            before_snapshot = create_enhanced_snapshot(self.engine, player)

            # Perform action via handler
            reward, done, success = self._apply_action(
                player, action_name, action_params, before_snapshot)

            actions_taken += 1

            if callback:
                callback()

            if done or action_name == "end_turn":
                break

            time.sleep(0.8)
