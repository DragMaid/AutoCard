class TurnManager:
    def __init__(self, game_state, effect_tracker):
        self.game_state = game_state
        self.effect_tracker = effect_tracker
        self.current_player_index = 0
        self._is_trap_stage = False
        self.turn_count = 1

    def serialize(self):
        return {
            "current_player_index": self.current_player_index,
            "turn_count": self.turn_count
        }

    def deserialize(self, content):
        self.current_player_index = content["current_player_index"]
        self.turn_count = content["turn_count"]

    def get_current_player(self):
        return self.game_state.players[self.current_player_index]

    def get_next_player(self):
        return self.game_state.players[self.get_next_player_index()]

    def get_next_player_index(self):
        return (self.current_player_index + 1) % len(self.game_state.players)

    def is_trap_stage(self):
        return self._is_trap_stage

    def toggle_trap_stage(self, state=None):
        self._is_trap_stage = state if state else not self._is_trap_stage

    def end_turn(self):
        current_player = self.get_current_player()
        self.game_state.player_info[current_player.id]["has_summoned_monster"] = False
        self.game_state.player_info[current_player.id]["has_summoned_trap"] = False
        self.game_state.player_info[current_player.id]["has_toggled"] = False
        self.current_player_index = self.get_next_player_index()
        self.turn_count += 1
        self.effect_tracker.update_round(self.game_state)

    def get_phase_count(self):
        return self.turn_count // len(self.game_state.players)

    def reset(self):
        self.turn_count = 1
        self.current_player_index = 0
