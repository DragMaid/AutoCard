"""
Action mapping from discrete actions and continuous parameters
to environment-specific actions.
"""
from typing import Optional, Tuple, List, Any, Dict
import numpy as np


class ActionMapper:
    """
    Optimized ActionMapper that receives legal_params instead of fetching them.
    """

    def __init__(self, env):
        self.env = env
        self.end_turn_idx = self.env.ACTIONS.index("end_turn")

    def map(
        self,
        player_idx: int,
        action_idx: int,
        cont_params: Optional[np.ndarray] = None,
        legal_params: Optional[Dict] = None
    ) -> Tuple[int, Optional[Dict[str, Any]]]:
        """
        Map discrete action and continuous params to environment action.

        Args:
            player_idx: Index of the player
            action_idx: Discrete action index
            cont_params: Continuous parameters (optional)
            legal_params: Legal action parameters from environment (optional)

        Returns:
            Tuple of (action_index, action_parameters)
        """
        action_name = self.env.ACTIONS[action_idx]

        # Normalize continuous parameters
        if cont_params is None:
            cont_params = np.zeros(self.env.param_dim, dtype=np.float32)
        cont_params = self._normalize_params(cont_params)

        # Get legal params if not provided (fallback for backward compatibility)
        if legal_params is None:
            player = self.env.engine.game_state.players[player_idx]
            _, legal_params = self.env._get_legal_actions(player)

        # Route to specific action handler
        handler = self._get_action_handler(action_name)
        return handler(legal_params, cont_params)

    def _normalize_params(self, params: np.ndarray) -> np.ndarray:
        """Normalize parameters from [-inf, inf] to [0, 1]."""
        return (np.tanh(params) + 1.0) / 2.0

    def _get_action_handler(self, action_name: str):
        """Get the appropriate handler for the action type."""
        handlers = {
            "summon": self._handle_summon,
            "attack": self._handle_attack,
            "cast_spell": self._handle_cast_spell,
            "set_trap": self._handle_set_trap,
            "toggle": self._handle_toggle,
            "combine": self._handle_combine,
        }
        return handlers.get(action_name, self._handle_end_turn)

    def _pick_from_list(self, items: List, scalar: float) -> Optional[Any]:
        """Select item from list using continuous scalar."""
        if not items:
            return None
        idx = min(int(np.floor(scalar * len(items))), len(items) - 1)
        return items[idx]

    # Action handlers (unchanged)
    def _handle_summon(self, params: Dict, cont_params: np.ndarray):
        monsters = params.get("summon", {}).get("monsters", [])
        if not monsters:
            return self.end_turn_idx, None
        monster = self._pick_from_list(monsters, cont_params[0])
        return self.env.ACTIONS.index("summon"), {"monster": int(monster)}

    def _handle_attack(self, params: Dict, cont_params: np.ndarray):
        attack_info = params.get("attack", {})
        attackers = attack_info.get("attackers", [])
        targets = attack_info.get("targets", [])

        if not attackers:
            return self.end_turn_idx, None

        attacker = self._pick_from_list(attackers, cont_params[0])
        target_param = cont_params[1] if len(
            cont_params) > 1 else cont_params[0]
        target = self._pick_from_list(targets, target_param) if targets else 0

        return self.env.ACTIONS.index("attack"), {
            "attacker": int(attacker),
            "target": int(target)
        }

    def _handle_cast_spell(self, params: Dict, cont_params: np.ndarray):
        spell_info = params.get("cast_spell", {})
        spells = spell_info.get("spells", [])
        targets_dict = spell_info.get("targets", {})

        if not spells:
            return self.end_turn_idx, None

        spell_idx = self._pick_from_list(spells, cont_params[0])
        target_list = targets_dict.get(spell_idx, [])
        target_param = cont_params[1] if len(
            cont_params) > 1 else cont_params[0]
        target = self._pick_from_list(
            target_list, target_param) if target_list else None

        return self.env.ACTIONS.index("cast_spell"), {
            "spell": int(spell_idx),
            "target": target
        }

    def _handle_set_trap(self, params: Dict, cont_params: np.ndarray):
        traps = params.get("set_trap", {}).get("traps", [])
        if not traps:
            return self.end_turn_idx, None
        trap = self._pick_from_list(traps, cont_params[0])
        return self.env.ACTIONS.index("set_trap"), {"trap": int(trap)}

    def _handle_toggle(self, params: Dict, cont_params: np.ndarray):
        toggles = params.get("toggle", {}).get("toggles", [])
        if not toggles:
            return self.end_turn_idx, None
        toggle = self._pick_from_list(toggles, cont_params[0])
        return self.env.ACTIONS.index("toggle"), {"toggle": int(toggle)}

    def _handle_combine(self, params: Dict, cont_params: np.ndarray):
        pairs = params.get("combine", {}).get("pairs", [])
        if not pairs:
            return self.end_turn_idx, None
        pair = self._pick_from_list(pairs, cont_params[0])
        return self.env.ACTIONS.index("combine"), {
            "pair": (int(pair[0]), int(pair[1]))
        }

    def _handle_end_turn(self, params: Dict, cont_params: np.ndarray):
        return self.end_turn_idx, None
