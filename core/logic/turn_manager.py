from typing import Optional
from pydantic import BaseModel
from core.data.game_state import GameState
from core.data.effects import EffectTracker
from core.data.player import Player


class TurnManagerState(BaseModel):
    current_player_index: int = 0
    _is_trap_stage: bool = False
    turn_count: int = 1


class TurnManager:
    """
    Manages turn-based logic, including player switching, turn tracking, and phase states.
    """

    def __init__(self, game_state: GameState, effect_tracker: EffectTracker):
        """
        Initializes the TurnManager.

        Args:
            game_state (GameState): The current game state object.
            effect_tracker (EffectTracker): Tracker for active game effects.
        """
        self.game_state = game_state
        self.effect_tracker = effect_tracker
        self.turn_state = TurnManagerState()

    def serialize(self) -> dict:
        return self.turn_state.model_dump()

    def deserialize(self, serialized: dict) -> None:
        self.turn_state = TurnManagerState.model_validate(serialized)

    def get_trapper(self) -> Optional[Player]:
        """
        Returns the player currently authorized to trigger traps, if in trap stage.

        Returns:
            Player: The trapping player, or None if not in trap stage.
        """
        if not self.is_trap_stage():
            return None
        return self.get_next_player()

    def get_current_player(self) -> Player:
        """
        Returns the player whose turn it currently is.

        Returns:
            Player: The current player object.
        """
        return self.game_state.players[self.turn_state.current_player_index]

    def get_next_player(self) -> Player:
        """
        Returns the player who will be active after the current turn ends.

        Returns:
            Player: The next player object.
        """
        return self.game_state.players[self.get_next_player_index()]

    def get_next_player_index(self) -> int:
        """
        Calculates the index of the next player.

        Returns:
            int: The index of the next player in the game state's players list.
        """
        return (self.turn_state.current_player_index + 1) % len(self.game_state.players)

    def is_trap_stage(self) -> bool:
        """
        Checks if the game is currently in the trap stage.

        Returns:
            bool: True if in trap stage, False otherwise.
        """
        return self.turn_state._is_trap_stage

    def toggle_trap_stage(self, state: Optional[bool] = None) -> None:
        """
        Toggles the trap stage state.

        Args:
            state (bool, optional): Force set the trap stage state.
        """
        self.turn_state._is_trap_stage = state if state is not None else not self.turn_state._is_trap_stage

    def end_turn(self) -> None:
        """
        Finalizes the current turn, resets turn-based player flags, updates effects,
        and increments the turn count.
        """
        current_player = self.get_current_player()
        self.game_state.player_info[current_player.id]["has_summoned_monster"] = False
        self.game_state.player_info[current_player.id]["has_summoned_trap"] = False
        self.game_state.player_info[current_player.id]["has_toggled"] = False
        self.current_player_index = self.get_next_player_index()
        self.turn_count += 1
        self.effect_tracker.update_round(self.game_state)

    def get_phase_count(self) -> int:
        """
        Calculates how many full cycles of turns have passed.

        Returns:
            int: The number of completed turn cycles.
        """
        return self.turn_count // len(self.game_state.players)

    def reset(self) -> None:
        """
        Resets the turn management to the initial state (turn 1, player 0).
        """
        self.turn_state = TurnManagerState()
