import logging
import math
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from core.data.player import Player
from core.cards.card import CardType
from core.cards.monster_card import CardMode
from core.utils import get_cards_typed
from ml.config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO if Config.REWARD_DEBUG else logging.ERROR)


@dataclass
class RewardConfig:
    """Configuration for reward values in the reinforcement learning agent.

    Attributes:
        deploy_monster: Reward for deploying a monster card.
        deploy_trap: Reward for deploying a trap card.
        attack_destroy: Reward for destroying an opponent's monster.
        survive_attack: Reward for surviving an opponent's attack.
        monster_destroyed: Penalty for losing a monster card.
        use_spell: Reward for using a spell card.
        merge_base: Base reward for merging monsters.
        damage_scale_factor: Scaling factor for damage-based rewards.
        field_advantage_multiplier: Normalized multiplier for field advantage.
        field_advantage_cap: Maximum value for field advantage.
        field_advantage_decay: Decay factor for field advantage smoothing.
        board_control_bonus: Bonus for having more monsters than the opponent.
        no_monsters_penalty: Penalty for having no monsters on the field.
        trap_advantage: Bonus for having a trap advantage.
        skip_turn: Penalty for skipping a turn.
        premature_end_penalty: Penalty for ending turn prematurely.
        invalid_action: Penalty for taking an invalid action.
        valid_action_bonus: Bonus for taking a valid action.
        win: Reward for winning the game.
        lose: Penalty for losing the game.
        direct_attack_bonus: Bonus for performing a direct attack.
        trap_trigger_base: Base reward for triggering a trap.
        trap_trigger_log_scale: Logarithmic scaling for trap trigger rewards.
        max_trap_trigger_reward: Maximum reward for multiple trap triggers.
        spell_combo_bonus: Bonus for spell combos.
        high_level_summon_bonus: Bonus for high-level monster summons.
        bait_block_bonus: Bonus for blocking a trap with bait.
        strength_scale_factor: Scaling factor for strength-based rewards.
        max_step_reward: Maximum allowable reward per step.
        min_step_reward: Minimum allowable reward per step.
    """
    deploy_monster: float = 0.5
    deploy_trap: float = 0.15
    attack_destroy: float = 1.0
    survive_attack: float = 0.2
    monster_destroyed: float = -0.5
    use_spell: float = 0.3
    merge_base: float = 1.0
    damage_scale_factor: float = 0.05
    field_advantage_multiplier: float = 0.5
    field_advantage_cap: float = 0.5
    field_advantage_decay: float = 0.95
    board_control_bonus: float = 0.2
    no_monsters_penalty: float = -0.3
    trap_advantage: float = 0.1
    skip_turn: float = -1.0
    premature_end_penalty: float = -0.3
    invalid_action: float = -0.5
    valid_action_bonus: float = 0.1
    win: float = 2.0
    lose: float = -2.0
    direct_attack_bonus: float = 0.3
    trap_trigger_base: float = 0.5
    trap_trigger_log_scale: float = 1.0
    max_trap_trigger_reward: float = 1.5
    spell_combo_bonus: float = 0.3
    high_level_summon_bonus: float = 0.1
    bait_block_bonus: float = 0.3
    strength_scale_factor: float = 0.1
    max_step_reward: float = 2.0
    min_step_reward: float = -2.0


class RewardPolicy(ABC):
    """Abstract base for composable reward policies."""

    def __init__(self, config: RewardConfig):
        self.config = config

    @abstractmethod
    def calculate(self, context: Dict[str, Any]) -> float:
        """Calculate reward component. Returns 0 if policy doesn't apply."""
        raise NotImplementedError


class TrapActivationPolicy(RewardPolicy):
    """Intelligent trap activation decisions."""

    def calculate(self, context: Dict[str, Any]) -> float:
        """
        Decide whether trap should be activated based on game state.
        """
        trap = context.get("trap")
        if not trap:
            return 0.0

        # TODO: bruh I dont even know how to handle this
        return 0.5


class FieldAdvantagePolicy(RewardPolicy):
    """Maintains board position awareness with temporal smoothing."""

    def __init__(self, config: "RewardConfig"):
        super().__init__(config)
        self.prev_advantage = 0.0

    def calculate(self, context: Dict[str, Any]) -> float:
        """
        Calculate normalized field advantage with decay.

        Returns delta advantage (improvement from previous turn).
        """
        snapshot = context.get("snapshot", {})

        my_monsters = snapshot.get("my_monsters", [])
        opp_monsters = snapshot.get("opp_monsters", [])

        # Total stats advantage
        my_total_stats = sum(
            (m.attack if m.mode == CardMode.ATTACK else m.defend)
            for m in my_monsters
        )
        opp_total_stats = sum(
            (m.attack if m.mode == CardMode.ATTACK else m.defend)
            for m in opp_monsters
        )

        # Trap advantage
        my_traps = len([t for t in snapshot.get("my_cards", [])
                       if t.card_type == CardType.TRAP])
        opp_traps = len([t for t in snapshot.get("opp_cards", [])
                        if t.card_type == CardType.TRAP])
        trap_diff = (my_traps - opp_traps) * self.config.trap_advantage

        # Normalize
        total_power = my_total_stats + opp_total_stats + 1e-6
        normalized_advantage = (my_total_stats - opp_total_stats) / total_power
        advantage = normalized_advantage * \
            self.config.field_advantage_multiplier + trap_diff
        advantage = max(min(advantage, self.config.field_advantage_cap),
                        -self.config.field_advantage_cap)

        # Temporal smoothing with decay
        smoothed_prev = self.prev_advantage * self.config.field_advantage_decay
        delta_advantage = advantage - smoothed_prev
        self.prev_advantage = advantage

        return delta_advantage

    def reset(self):
        """Reset temporal tracking for new episode."""
        self.prev_advantage = 0.0


class BoardControlPolicy(RewardPolicy):
    """Rewards board presence and control."""

    def calculate(self, context: Dict[str, Any]) -> float:
        """Rewards maintaining board advantage."""
        snapshot = context.get("snapshot", {})
        my_monster_count = len(snapshot.get("my_monsters", []))
        opp_monster_count = len(snapshot.get("opp_monsters", []))

        if my_monster_count == 0:
            return self.config.no_monsters_penalty
        if my_monster_count > opp_monster_count:
            return self.config.board_control_bonus
        return 0.0


class DamagePolicy(RewardPolicy):
    """Handles damage with logarithmic scaling to reduce variance."""

    def calculate(self, context: Dict[str, Any]) -> float:
        """Calculate logarithmically-scaled damage reward."""
        before = context.get("before", {})
        after = context.get("after", {})

        opp_lp_damage = before.get("opp_lp", 0) - after.get("opp_lp", 0)
        my_lp_damage = before.get("my_lp", 0) - after.get("my_lp", 0)

        reward = 0.0
        if opp_lp_damage > 0:
            reward += math.log(1 + opp_lp_damage) * \
                self.config.damage_scale_factor
        if my_lp_damage > 0:
            reward -= math.log(1 + my_lp_damage) * \
                self.config.damage_scale_factor

        return reward


class StrengthPolicy(RewardPolicy):
    """Rewards deploying or using strong cards."""

    def calculate(self, context: Dict[str, Any]) -> float:
        """Bonus for strong card stats."""
        card = context.get("card")
        if not card:
            return 0.0

        max_stats = context.get("max_stats", 9999)

        attack_bonus = (getattr(card, "attack", 0) / max_stats) * \
            self.config.strength_scale_factor
        defend_bonus = (getattr(card, "defend", 0) / max_stats) * \
            self.config.strength_scale_factor

        return attack_bonus + defend_bonus


class SummonPolicy(RewardPolicy):
    """Reward for deploying monsters and traps."""

    def calculate(self, context: Dict[str, Any]) -> float:
        """Calculate summon reward."""
        before = context.get("before", {})
        after = context.get("after", {})
        card = context.get("card")
        max_stats = context.get("max_stats", 9999)

        reward = 0.0

        # Check if monster was summoned
        if len(after.get("my_monsters", [])) > len(before.get("my_monsters", [])):
            reward += self.config.deploy_monster

            # Strength bonus
            strength_bonus = (card.attack / max_stats) * \
                self.config.strength_scale_factor
            reward += strength_bonus

            # High-level bonus
            if hasattr(card, "star") and card.star >= 2:
                reward += self.config.high_level_summon_bonus

        # Trap deployment
        elif len(after.get("my_traps", [])) > len(before.get("my_traps", [])):
            reward += self.config.deploy_trap

        return reward


class AttackPolicy(RewardPolicy):
    """Reward for attacking with damage and destruction bonuses."""

    def __init__(self, config: "RewardConfig"):
        super().__init__(config)
        self.damage_policy = DamagePolicy(config)
        self.strength_policy = StrengthPolicy(config)

    def calculate(self, context: Dict[str, Any]) -> float:
        """Calculate attack reward with damage and destruction."""
        before = context.get("before", {})
        after = context.get("after", {})
        max_stats = context.get("max_stats", 9999)

        reward = 0.0

        # Damage component
        damage_reward = self.damage_policy.calculate(context)
        reward += damage_reward

        # Monster destruction
        opp_destroyed = [m for m in before.get("opp_monsters", [])
                         if m not in after.get("opp_monsters", [])]
        my_destroyed = [m for m in before.get("my_monsters", [])
                        if m not in after.get("my_monsters", [])]

        if opp_destroyed:
            reward += self.config.attack_destroy * len(opp_destroyed)
            for m in opp_destroyed:
                strength = (m.attack / max_stats) * \
                    self.config.strength_scale_factor
                reward += strength

        if my_destroyed:
            reward += self.config.monster_destroyed * len(my_destroyed)

        # Direct attack bonus
        if (len(before.get("opp_monsters", [])) == 0 and
                len(after.get("opp_monsters", [])) == 0):
            reward += self.config.direct_attack_bonus
        elif not opp_destroyed and before.get("opp_lp") == after.get("opp_lp"):
            reward += self.config.survive_attack

        return reward


class SpellPolicy(RewardPolicy):
    """Reward for casting spells with combo detection."""

    def calculate(self, context: Dict[str, Any]) -> float:
        """Calculate spell reward with buffs and combos."""
        before = context.get("before", {})
        after = context.get("after", {})
        reward = 0.0

        # Base spell reward
        reward += self.config.use_spell

        # Detect spell combos (buffed monsters)
        try:
            buffed_count = 0
            for i, before_mon in enumerate(before.get("my_monsters", [])):
                if i < len(after.get("my_monsters", [])):
                    after_mon = after.get("my_monsters", [])[i]
                    if (getattr(after_mon, "attack", 0) > getattr(before_mon, "attack", 0) or
                            getattr(after_mon, "defend", 0) > getattr(before_mon, "defend", 0)):
                        buffed_count += 1

            if buffed_count >= 1:
                reward += self.config.spell_combo_bonus * buffed_count
        except (IndexError, AttributeError):
            pass

        # Trap destruction (only if not already triggered)
        traps_rewarded = context.get("traps_rewarded", set())
        before_traps = [c for c in before.get("opp_cards", [])
                        if c.card_type == CardType.TRAP]
        after_traps = [c for c in after.get("opp_cards", [])
                       if c.card_type == CardType.TRAP]

        destroyed_traps = [t for t in before_traps
                           if t not in after_traps and id(t) not in traps_rewarded]

        if destroyed_traps:
            reward += self.config.bait_block_bonus * len(destroyed_traps)

        return reward


class TogglePolicy(RewardPolicy):
    """Reward for optimal position toggling."""

    def calculate(self, context: Dict[str, Any]) -> float:
        """Calculate toggle reward."""
        after = context.get("after", {})
        toggle_idx = context.get("toggle_idx")

        if toggle_idx is None:
            return 0.0

        monsters = after.get("my_monsters", [])
        if toggle_idx >= len(monsters):
            return 0.0

        monster = monsters[toggle_idx]
        reward = 0.0

        # Optimal positioning
        if ((monster.mode == CardMode.ATTACK and monster.attack > monster.defend) or
                (monster.mode == CardMode.DEFEND and monster.defend > monster.attack)):
            reward += 0.2
        elif monster.mode == CardMode.DEFEND and monster.attack > monster.defend:
            reward -= 0.5

        return reward


class CombinePolicy(RewardPolicy):
    """Reward for merging/combining monsters."""

    def calculate(self, context: Dict[str, Any]) -> float:
        """Calculate merge reward."""
        before = context.get("before", {})
        after = context.get("after", {})
        max_stats = context.get("max_stats", 9999)

        reward = 0.0

        new_monsters = [m for m in after.get("my_monsters", [])
                        if m not in before.get("my_monsters", [])]

        if new_monsters:
            new_monster = new_monsters[0]
            level = getattr(new_monster, "star", 1)

            # Logarithmic merge reward
            merge_reward = self.config.merge_base * math.log(level + 1)
            reward += merge_reward

            # Strength bonus for merged monster
            strength = (new_monster.attack / max_stats) * 0.1
            reward += strength

        return reward


class EndTurnPolicy(RewardPolicy):
    """Penalties and bonuses for turn management."""

    def __init__(self, config: "RewardConfig"):
        super().__init__(config)
        self.turns_skipped = 0

    def calculate(self, context: Dict[str, Any]) -> float:
        """Calculate end turn penalties/bonuses."""
        before = context.get("before", {})
        after = context.get("after", {})
        has_valid_moves = context.get("has_valid_moves", False)

        reward = 0.0

        # Check if turn was passive
        is_passive = self._is_passive_turn(before, after)

        if is_passive:
            self.turns_skipped += 1
            reward += self.config.skip_turn
            reward -= 0.05 * self.turns_skipped  # Cumulative penalty
        else:
            self.turns_skipped = 0

            # Penalize premature end if moves available
            if has_valid_moves:
                reward += self.config.premature_end_penalty

        return reward

    def _is_passive_turn(self, before: Dict, after: Dict) -> bool:
        """Check if turn did nothing significant."""
        return (len(before["my_monsters"]) == len(after["my_monsters"]) and
                len(before["opp_monsters"]) == len(after["opp_monsters"]) and
                before["opp_lp"] == after["opp_lp"] and
                len(before.get("my_cards", [])) == len(after.get("my_cards", [])))

    def reset(self):
        """Reset for new episode."""
        self.turns_skipped = 0


@dataclass
class RewardBreakdown:
    """Detailed breakdown of rewards for logging."""
    total: float = 0.0
    components: Dict[str, float] = field(default_factory=dict)
    action_type: str = ""

    def add(self, component_name: str, value: float):
        """Add a reward component."""
        if value != 0:
            self.components[component_name] = value
            self.total += value

    def clamp(self, min_val: float, max_val: float):
        """Clamp total reward to prevent extreme values."""
        if self.total > max_val:
            self.components["_clamped_excess"] = self.total - max_val
            self.total = max_val
        elif self.total < min_val:
            self.components["_clamped_deficit"] = self.total - min_val
            self.total = min_val

    def get_summary(self) -> str:
        """Get a formatted summary of the reward."""
        if not self.components:
            return f"Total: {self.total:.4f}"

        parts = [f"{name}={val:+.4f}" for name, val in self.components.items()]
        return f"Total: {self.total:+.4f} ({', '.join(parts)})"


class RewardCalculator:
    """Policy-based reward calculation with modular, composable components."""

    def __init__(self, config: Optional[RewardConfig] = None, max_stats: float = 9999.0):
        self.config = config or RewardConfig()
        self.max_stats = max_stats

        # Initialize policies
        self.trap_activation = TrapActivationPolicy(self.config)
        self.field_advantage = FieldAdvantagePolicy(self.config)
        self.board_control = BoardControlPolicy(self.config)
        self.damage = DamagePolicy(self.config)

        # Action policies
        self.summon = SummonPolicy(self.config)
        self.attack = AttackPolicy(self.config)
        self.spell = SpellPolicy(self.config)
        self.toggle = TogglePolicy(self.config)
        self.combine = CombinePolicy(self.config)
        self.end_turn = EndTurnPolicy(self.config)
        self.activate_trap = TrapActivationPolicy(self.config)

        # Episode tracking
        self.episode_rewards: Dict[str, List[float]] = {}
        self.traps_rewarded_this_step: set = set()

        self.reset_episode_tracking()

    def reset_episode_tracking(self):
        """Reset episode-level reward tracking."""
        self.episode_rewards = {
            "total": [],
            "action_rewards": [],
            "damage_rewards": [],
            "field_rewards": [],
            "terminal_rewards": [],
        }
        self.field_advantage.reset()
        self.end_turn.reset()
        self.traps_rewarded_this_step.clear()

    def calculate_action_reward(
        self,
        action_name: str,
        player: Player,
        params: Optional[Dict],
        success: bool,
        before_snapshot: Dict[str, Any],
        after_snapshot: Dict[str, Any],
        has_valid_moves: bool = False
    ) -> RewardBreakdown:
        """Calculate reward for a specific action using policy composition."""
        breakdown = RewardBreakdown(action_type=action_name)

        # Valid action exploration bonus
        if not success:
            breakdown.add("invalid_action", self.config.invalid_action)
            breakdown.clamp(self.config.min_step_reward,
                            self.config.max_step_reward)
            self._log_reward(player, breakdown)
            return breakdown

        breakdown.add("valid_action", self.config.valid_action_bonus)

        # Build common context
        common_context = {
            "before": before_snapshot,
            "after": after_snapshot,
            "snapshot": after_snapshot,
            "max_stats": self.max_stats,
            "traps_rewarded": self.traps_rewarded_this_step,
            "player": player,
        }

        # Dispatch to action-specific policies
        if action_name == "summon":
            reward = self._apply_policy(self.summon, common_context, {
                                        "card": self._get_new_monster(before_snapshot, after_snapshot)})
            breakdown.add("summon", reward)

        elif action_name == "attack":
            reward = self._apply_policy(self.attack, common_context, {})
            breakdown.add("attack", reward)

        elif action_name == "cast_spell":
            reward = self._apply_policy(self.spell, common_context, {})
            breakdown.add("spell", reward)

        elif action_name == "set_trap":
            breakdown.add("deploy_trap", self.config.deploy_trap)

        elif action_name == "toggle":
            reward = self._apply_policy(self.toggle, common_context, {
                                        "toggle_idx": params.get("toggle") if params else None})
            breakdown.add("toggle", reward)

        elif action_name == "combine":
            reward = self._apply_policy(self.combine, common_context, {})
            breakdown.add("combine", reward)

        elif action_name == "activate_trap":
            reward = self._apply_policy(self.activate_trap, common_context, {})
            breakdown.add("activate_trap", reward)

        elif action_name == "end_turn":
            common_context["has_valid_moves"] = has_valid_moves
            reward = self._apply_policy(self.end_turn, common_context, {})
            breakdown.add("end_turn", reward)
            self.traps_rewarded_this_step.clear()

        # Apply board-level policies (always)
        field_reward = self._apply_policy(
            self.field_advantage, common_context, {})
        if field_reward != 0:
            breakdown.add("field_advantage", field_reward)

        board_reward = self._apply_policy(
            self.board_control, common_context, {})
        if board_reward != 0:
            breakdown.add("board_control", board_reward)

        # Clamp to safe range
        breakdown.clamp(self.config.min_step_reward,
                        self.config.max_step_reward)

        self._log_reward(player, breakdown)
        self.episode_rewards["action_rewards"].append(breakdown.total)
        return breakdown

    def _apply_policy(self, policy: RewardPolicy, common_context: Dict[str, Any],
                      extra_context: Dict[str, Any]) -> float:
        """Apply a policy with merged context."""
        context = {**common_context, **extra_context}
        return policy.calculate(context)

    def _get_new_monster(self, before: Dict, after: Dict):
        """Extract newly summoned monster."""
        new_monsters = [m for m in after.get("my_monsters", [])
                        if m not in before.get("my_monsters", [])]
        return new_monsters[0] if new_monsters else None

    def calculate_terminal_reward(self, player: Player, won: bool,
                                  final_snapshot: Optional[Dict[str, Any]] = None) -> RewardBreakdown:
        """Calculate reward for game end with optional LP ratio bonus."""
        breakdown = RewardBreakdown(action_type="terminal")

        if won:
            breakdown.add("victory", self.config.win)
            if final_snapshot and final_snapshot.get("my_lp") and final_snapshot.get("opp_lp"):
                lp_ratio = final_snapshot["my_lp"] / \
                    max(final_snapshot["opp_lp"], 1)
                lp_bonus = min(lp_ratio * 0.2, 0.5)
                breakdown.add("lp_ratio_bonus", lp_bonus)
        else:
            breakdown.add("defeat", self.config.lose)

        breakdown.clamp(self.config.min_step_reward,
                        self.config.max_step_reward)
        self._log_reward(player, breakdown, terminal=True)
        self.episode_rewards["terminal_rewards"].append(breakdown.total)
        return breakdown

    def _log_reward(self, player: Player, breakdown: RewardBreakdown, terminal: bool = False):
        """Log reward details."""
        if terminal:
            logger.debug(f"TERMINAL REWARD for {player.name}: {
                         breakdown.get_summary()}")
        elif breakdown.total != 0:
            logger.debug(f"REWARD ({breakdown.action_type}): {
                         breakdown.get_summary()}")

    def get_episode_summary(self) -> Dict[str, Any]:
        """Get summary statistics for the episode."""
        summary = {}
        for key, rewards in self.episode_rewards.items():
            if rewards:
                summary[key] = {
                    "total": sum(rewards),
                    "mean": sum(rewards) / len(rewards),
                    "min": min(rewards),
                    "max": max(rewards),
                    "count": len(rewards),
                }
        return summary

    def log_episode_summary(self):
        """Log episode reward summary."""
        summary = self.get_episode_summary()
        logger.debug("EPISODE REWARD SUMMARY")
        for category, stats in summary.items():
            logger.debug(f"\n{category.upper()}:")
            logger.debug(f"Total: {stats['total']:+.4f}")
            logger.debug(f"Mean:  {stats['mean']:+.4f}")
            logger.debug(f"Range: [{stats['min']:+.4f}, {stats['max']:+.4f}]")
            logger.debug(f"Count: {stats['count']}")


def create_enhanced_snapshot(engine, player: Player) -> Dict[str, Any]:
    """Create an enhanced snapshot with all necessary information for reward calculation."""
    gs = engine.game_state
    opp_id = gs.get_opponent_id(player.id)
    opp = gs.players_lookup[opp_id]

    return {
        "my_lp": player.life_points,
        "opp_lp": opp.life_points,
        "my_monsters": list(get_cards_typed(gs, player.id, CardType.MONSTER)),
        "opp_monsters": list(get_cards_typed(gs, opp_id, CardType.MONSTER)),
        "my_cards": list(gs.get_player_field_cards(player.id)),
        "opp_cards": list(gs.get_player_field_cards(opp_id)),
        "my_hand_size": len(gs.player_info[player.id].held_cards.card_ids),
        "opp_hand_size": len(gs.player_info[opp_id].held_cards.card_ids),
        "triggerable_traps": list(gs.triggerable_traps.keys()),
        "activated_traps": list(gs.activated_traps),
    }
