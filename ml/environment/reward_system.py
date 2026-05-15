import logging
import math
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from core.data.player import Player
from core.cards.card import CardType
from core.cards.monster_card import CardMode
from core.utils import get_cards_typed
from ml.confg import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO if Config.REWARD_DEBUG else logging.ERROR)

# TODO: do reconsider this for a bit


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
    """Centralized reward calculation with comprehensive logging."""

    def __init__(self, config: Optional[RewardConfig] = None, max_stats: float = 9999.0):
        self.config = config or RewardConfig()
        self.max_stats = max_stats

        # Track rewards per episode for analysis
        self.episode_rewards: Dict[str, List[float]] = {}

        # Temporal tracking for advantage smoothing
        self.prev_field_advantage: float = 0.0
        self.turns_skipped: int = 0

        # Trap trigger tracking
        self.traps_triggered_this_step: int = 0
        # Track to prevent double-counting
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
        self.prev_field_advantage = 0.0
        self.turns_skipped = 0
        self.traps_triggered_this_step = 0
        self.traps_rewarded_this_step = set()

    def set_trap_triggers(self, num_triggers: int, trap_ids: Optional[List[int]] = None):
        """Set the number of traps triggered this step for reward calculation.

        Args:
            num_triggers: Number of traps triggered
            trap_ids: Optional list of trap object IDs to prevent double-counting
        """
        self.traps_triggered_this_step = num_triggers

        # Track trap IDs to prevent double-counting with spell destruction
        if trap_ids:
            self.traps_rewarded_this_step.update(trap_ids)

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
        """Calculate reward for a specific action with detailed breakdown."""
        breakdown = RewardBreakdown(action_type=action_name)

        # Valid action exploration bonus
        if success:
            breakdown.add("valid_action", self.config.valid_action_bonus)
        else:
            breakdown.add("invalid_action", self.config.invalid_action)
            breakdown.clamp(self.config.min_step_reward,
                            self.config.max_step_reward)
            self._log_reward(player, breakdown)
            return breakdown

        # Dispatch to specific action reward calculators
        if action_name == "summon":
            self._calculate_summon_reward(
                breakdown, player, params, before_snapshot, after_snapshot)
        elif action_name == "attack":
            self._calculate_attack_reward(
                breakdown, player, params, before_snapshot, after_snapshot)
        elif action_name == "cast_spell":
            self._calculate_spell_reward(
                breakdown, player, params, before_snapshot, after_snapshot)
        elif action_name == "set_trap":
            self._calculate_trap_reward(breakdown, player, params)
        elif action_name == "toggle":
            self._calculate_toggle_reward(
                breakdown, player, params, before_snapshot, after_snapshot)
        elif action_name == "combine":
            self._calculate_combine_reward(
                breakdown, player, params, before_snapshot, after_snapshot)
        elif action_name == "end_turn":
            # Clear trap tracking at end of turn
            self.traps_rewarded_this_step.clear()

            # Check if player did nothing this turn
            if self._is_passive_turn(before_snapshot, after_snapshot):
                self.turns_skipped += 1
                breakdown.add("skip_turn_penalty", self.config.skip_turn)
                breakdown.add("repeated_skip_penalty", -
                              0.05 * self.turns_skipped)
            else:
                self.turns_skipped = 0

            # Penalty for ending turn prematurely when valid moves exist
            if has_valid_moves and not self._is_passive_turn(before_snapshot, after_snapshot):
                breakdown.add("premature_end_penalty",
                              self.config.premature_end_penalty)

        # Add trap trigger rewards if any traps were triggered
        if self.traps_triggered_this_step > 0:
            trap_reward = self._calculate_trap_trigger_reward(
                self.traps_triggered_this_step)
            breakdown.add("trap_trigger", trap_reward)
            self.traps_triggered_this_step = 0  # Reset for next step

        # Add normalized field advantage reward with temporal smoothing
        field_reward = self._calculate_field_advantage(player, after_snapshot)
        if field_reward != 0:
            breakdown.add("field_advantage", field_reward)

        # Board control bonus
        board_bonus = self._calculate_board_control(player, after_snapshot)
        if board_bonus != 0:
            breakdown.add("board_control", board_bonus)

        # Clamp to prevent extreme rewards (BEFORE logging)
        breakdown.clamp(self.config.min_step_reward,
                        self.config.max_step_reward)

        self._log_reward(player, breakdown)
        self.episode_rewards["action_rewards"].append(breakdown.total)
        return breakdown

    def _calculate_trap_trigger_reward(self, num_triggers: int) -> float:
        """Calculate reward for trap triggers with adjustable logarithmic scaling.

        Args:
            num_triggers: Number of traps triggered this step

        Returns:
            Scaled reward, capped at max_trap_trigger_reward

        Note:
            trap_trigger_log_scale controls curve steepness:
            - 1.0 = standard log scaling (default)
            - 0.5 = gentler curve (reduces spike for 3-4 traps)
            - 2.0 = steeper curve (rewards multiple traps more)
        """
        if num_triggers <= 0:
            return 0.0

        # Adjustable logarithmic scaling to reduce spikes
        # log1p(x^scale) creates a tunable curve
        scaled_triggers = num_triggers ** self.config.trap_trigger_log_scale
        reward = self.config.trap_trigger_base * math.log1p(scaled_triggers)

        # Cap the maximum trap trigger reward
        reward = min(reward, self.config.max_trap_trigger_reward)

        return reward

    def _calculate_summon_reward(
        self,
        breakdown: RewardBreakdown,
        player: Player,
        params: Optional[Dict],
        before: Dict[str, Any],
        after: Dict[str, Any]
    ):
        """Calculate reward for summoning a monster or trap."""
        # Check if a monster was actually summoned
        if len(after["my_monsters"]) > len(before["my_monsters"]):
            new_monster = [m for m in after["my_monsters"]
                           if m not in before["my_monsters"]]
            if new_monster:
                monster = new_monster[0]
                base_reward = self.config.deploy_monster
                breakdown.add("deploy_monster", base_reward)

                # Bonus for summoning stronger monsters (scaled)
                strength_bonus = (monster.attack / self.max_stats) * \
                    self.config.strength_scale_factor
                breakdown.add("strength_bonus", strength_bonus)

                # High-level monster bonus (2+ stars)
                if hasattr(monster, 'star') and monster.star >= 2:
                    breakdown.add("high_level_summon",
                                  self.config.high_level_summon_bonus)

    def _calculate_attack_reward(
        self,
        breakdown: RewardBreakdown,
        player: Player,
        params: Optional[Dict],
        before: Dict[str, Any],
        after: Dict[str, Any]
    ):
        """Calculate reward for attacking with logarithmic damage scaling."""
        opp_lp_damage = before["opp_lp"] - after["opp_lp"]
        my_lp_damage = before["my_lp"] - after["my_lp"]

        # Logarithmic damage dealt reward
        if opp_lp_damage > 0:
            damage_reward = math.log(1 + opp_lp_damage) * \
                self.config.damage_scale_factor
            breakdown.add("damage_dealt", damage_reward)

            # Direct attack bonus (no opponent monsters)
            if len(before["opp_monsters"]) == 0 and len(after["opp_monsters"]) == 0:
                breakdown.add("direct_attack_bonus",
                              self.config.direct_attack_bonus)

        # Logarithmic damage taken penalty
        if my_lp_damage > 0:
            damage_penalty = -math.log(1 + my_lp_damage) * \
                self.config.damage_scale_factor
            breakdown.add("damage_taken", damage_penalty)

        # Monsters destroyed/lost
        opp_monsters_destroyed = [
            m for m in before["opp_monsters"] if m not in after["opp_monsters"]]
        my_monsters_destroyed = [
            m for m in before["my_monsters"] if m not in after["my_monsters"]]

        if opp_monsters_destroyed:
            destroy_reward = self.config.attack_destroy * \
                len(opp_monsters_destroyed)
            breakdown.add("attack_destroy", destroy_reward)

            # Bonus based on destroyed monster strength
            for m in opp_monsters_destroyed:
                stat = m.attack if m.mode == CardMode.ATTACK else m.defend
                strength_bonus = (stat / self.max_stats) * \
                    self.config.strength_scale_factor
                breakdown.add("destroy_strength_bonus", strength_bonus)

        if my_monsters_destroyed:
            loss_penalty = self.config.monster_destroyed * \
                len(my_monsters_destroyed)
            breakdown.add("monster_destroyed", loss_penalty)

        # Attack survived without consequences
        elif opp_lp_damage == 0 and my_lp_damage == 0 and not opp_monsters_destroyed:
            breakdown.add("survive_attack", self.config.survive_attack)

    def _calculate_spell_reward(
        self,
        breakdown: RewardBreakdown,
        player: Player,
        params: Optional[Dict],
        before: Dict[str, Any],
        after: Dict[str, Any]
    ):
        """Calculate reward for casting a spell.

        Note: Prevents double-counting trap destruction with trap trigger rewards.
        """
        breakdown.add("use_spell", self.config.use_spell)

        # Detect buffed monsters (spell combo)
        try:
            cards_changed = []
            for i, before_mon in enumerate(before.get("my_monsters", [])):
                if i < len(after.get("my_monsters", [])):
                    after_mon = after.get("my_monsters", [])[i]
                    if getattr(after_mon, "attack", 0) > getattr(before_mon, "attack", 0) or \
                       getattr(after_mon, "defend", 0) > getattr(before_mon, "defend", 0):
                        cards_changed.append(after_mon)

            if len(cards_changed) >= 1:
                breakdown.add("spell_combo",
                              self.config.spell_combo_bonus * len(cards_changed))
        except (IndexError, AttributeError):
            pass  # Ignore if monster lists don't align

        # Check for trap destruction (only reward if not already triggered)
        before_traps = [c for c in before.get("opp_cards", [])
                        if c.card_type == CardType.TRAP]
        after_traps = [c for c in after.get("opp_cards", [])
                       if c.card_type == CardType.TRAP]

        # Find destroyed traps
        destroyed_traps = [t for t in before_traps if t not in after_traps]

        # Only reward if these traps weren't already rewarded via trigger
        newly_destroyed = [t for t in destroyed_traps
                           if id(t) not in self.traps_rewarded_this_step]

        if newly_destroyed:
            breakdown.add("trap_destroyed_bonus",
                          self.config.bait_block_bonus * len(newly_destroyed))
            # Mark these traps as rewarded
            for trap in newly_destroyed:
                self.traps_rewarded_this_step.add(id(trap))

    def _calculate_trap_reward(
        self,
        breakdown: RewardBreakdown,
        player: Player,
        params: Optional[Dict],
    ):
        """Calculate reward for setting a trap (planning incentive)."""
        breakdown.add("deploy_trap", self.config.deploy_trap)

    def _calculate_toggle_reward(
        self,
        breakdown: RewardBreakdown,
        player: Player,
        params: Optional[Dict],
        before: Dict[str, Any],
        after: Dict[str, Any],
    ):
        """Calculate reward for toggling a monster's position."""
        if params and "toggle" in params:
            toggle_idx = params["toggle"]
            if toggle_idx < len(after["my_monsters"]):
                am = after["my_monsters"][toggle_idx]
                # Reward optimal positioning
                if (am.mode == CardMode.ATTACK and am.attack > am.defend) \
                        or (am.mode == CardMode.DEFEND and am.attack < am.defend):
                    breakdown.add("optimal_toggle", 0.2)
                elif (am.mode == CardMode.DEFEND and am.attack > am.defend):
                    breakdown.add("suboptimal_toggle", -0.5)

    def _calculate_combine_reward(
        self,
        breakdown: RewardBreakdown,
        player: Player,
        params: Optional[Dict],
        before: Dict[str, Any],
        after: Dict[str, Any]
    ):
        """Calculate reward for combining monsters."""
        before_monsters = before["my_monsters"]
        after_monsters = after["my_monsters"]

        new_monsters = [m for m in after_monsters if m not in before_monsters]
        if new_monsters:
            new_monster = new_monsters[0]
            level = getattr(new_monster, "star", 1)

            # Logarithmic reward based on level
            merge_reward = self.config.merge_base * math.log(level + 1)
            breakdown.add("merge_combine", merge_reward)

            # Strength bonus for powerful merged monster
            strength_bonus = (new_monster.attack / self.max_stats) * 0.1
            breakdown.add("merge_strength_bonus", strength_bonus)

    def _calculate_field_advantage(self, player: Player, snapshot: Dict[str, Any]) -> float:
        """Calculate normalized field advantage with temporal smoothing and decay.

        Returns:
            Delta advantage (improvement from previous turn), with smoothed transitions

        Note:
            - Positive delta = improving position (rewarded)
            - Negative delta = declining position (penalized, but smoothed)
            - Decay factor prevents over-reaction to single-turn swings
        """
        my_total_stats = sum(
            (m.attack if m.mode == CardMode.ATTACK else m.defend)
            for m in snapshot["my_monsters"]
        )

        opp_total_stats = sum(
            (m.attack if m.mode == CardMode.ATTACK else m.defend)
            for m in snapshot["opp_monsters"]
        )

        # Trap advantage
        my_traps = len([t for t in snapshot["my_cards"]
                       if t.card_type == CardType.TRAP])
        opp_traps = len([t for t in snapshot["opp_cards"]
                        if t.card_type == CardType.TRAP])
        trap_diff = (my_traps - opp_traps) * self.config.trap_advantage

        # Normalize by total power to get relative advantage
        total_power = my_total_stats + opp_total_stats + 1e-6  # Avoid division by zero
        normalized_advantage = (my_total_stats - opp_total_stats) / total_power

        # Apply multiplier
        advantage = normalized_advantage * \
            self.config.field_advantage_multiplier + trap_diff

        # Cap the advantage to prevent runaway scaling
        advantage = max(min(advantage, self.config.field_advantage_cap),
                        -self.config.field_advantage_cap)

        # Apply decay to previous advantage for smoothing
        # This prevents sudden swings from being over-penalized
        smoothed_prev = self.prev_field_advantage * self.config.field_advantage_decay

        # Temporal smoothing - reward improvement from smoothed baseline
        delta_advantage = advantage - smoothed_prev

        # Update tracking (use actual advantage, not smoothed)
        self.prev_field_advantage = advantage

        return delta_advantage

    def _calculate_board_control(self, player: Player, snapshot: Dict[str, Any]) -> float:
        """Reward maintaining board presence."""
        my_monster_count = len(snapshot["my_monsters"])
        opp_monster_count = len(snapshot["opp_monsters"])

        # Penalty for having no monsters
        if my_monster_count == 0:
            return self.config.no_monsters_penalty

        # Bonus for maintaining board advantage
        if my_monster_count > opp_monster_count:
            return self.config.board_control_bonus

        return 0.0

    def _is_passive_turn(self, before: Dict[str, Any], after: Dict[str, Any]) -> bool:
        """Check if the player did nothing significant this turn."""
        my_monsters_changed = len(before["my_monsters"]) != len(
            after["my_monsters"])
        opp_monsters_changed = len(before["opp_monsters"]) != len(
            after["opp_monsters"])
        lp_changed = before["opp_lp"] != after["opp_lp"]
        hand_changed = len(before.get("my_cards", [])) != len(
            after.get("my_cards", []))

        return not (my_monsters_changed or opp_monsters_changed or lp_changed or hand_changed)

    def calculate_terminal_reward(self, player: Player, won: bool,
                                  final_snapshot: Optional[Dict[str, Any]] = None) -> RewardBreakdown:
        """Calculate reward for game end with optional LP ratio bonus."""
        breakdown = RewardBreakdown(action_type="terminal")

        if won:
            breakdown.add("victory", self.config.win)

            # Optional: LP ratio bonus
            if final_snapshot and final_snapshot.get("my_lp") and final_snapshot.get("opp_lp"):
                lp_ratio = final_snapshot["my_lp"] / \
                    max(final_snapshot["opp_lp"], 1)
                lp_bonus = min(lp_ratio * 0.2, 0.5)  # Cap at 0.5
                breakdown.add("lp_ratio_bonus", lp_bonus)
        else:
            breakdown.add("defeat", self.config.lose)

        # Clamp terminal reward BEFORE logging
        breakdown.clamp(self.config.min_step_reward,
                        self.config.max_step_reward)

        self._log_reward(player, breakdown, terminal=True)
        self.episode_rewards["terminal_rewards"].append(breakdown.total)
        return breakdown

    def _log_reward(self, player: Player, breakdown: RewardBreakdown, terminal: bool = False):
        """Log reward details."""
        if terminal:
            logger.debug(f"ERMINAL REWARD for {player.name}")
            logger.debug(f"{breakdown.get_summary()}")
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
