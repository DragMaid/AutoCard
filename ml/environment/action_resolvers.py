from __future__ import annotations

from typing import Tuple, List, Dict, Any, TYPE_CHECKING, Optional
from core.cards.spell_card import SpellAbility
from core.utils import get_cards_typed
from core.data.player import Player
from core.cards.card import CardType
from core.cards.monster_card import CardMode
from .action_codec import ActionCodec

if TYPE_CHECKING:
    from ml.environment .environment import GameEnv


class LegalActionResolver:
    """Abstract base class for resolving legal actions in the environment."""

    def resolve(env: GameEnv, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Resolve legal actions for a given player.

        Args:
            env: The game environment.
            player: The player to resolve actions for.

        Returns:
            A dictionary mapping action IDs to (action_name, action_parameters).
        """
        raise NotImplementedError


class TrapActivateResolver(LegalActionResolver):
    """Resolver for activating triggerable traps."""

    def resolve(env: GameEnv, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Resolve triggerable traps based on the current state."""
        gs = env.engine.game_state
        results = {}

        for trap_id in gs.triggerable_traps.keys():
            card = gs.get_card_by_id(trap_id)
            if card.owner_id == player.id and card.id not in gs.activated_traps:
                slot = env.get_card_slot_idx(player.id, card)
                action_id = ActionCodec.encode("activate_trap", trap=slot)
                results[action_id] = (
                    "activate_trap", {"card_id": trap_id, "slot": slot})

        return results


class SummonResolver(LegalActionResolver):
    """Resolver for summoning monsters."""

    def resolve(env: GameEnv, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Resolve summonable monsters from hand slots."""
        gs = env.engine.game_state
        card_ids = gs.player_info[player.id].held_cards.card_ids

        results = {}
        empty_count = len(gs.get_empty_slots(player.id))
        if gs.player_info[player.id].has_summoned_monster or \
                empty_count <= 0:
            return {}

        for i, cid in enumerate(card_ids):
            card = gs.get_card_by_id(cid)
            if card and card.card_type == CardType.MONSTER:
                action_id = ActionCodec.encode("summon", monster=i)
                results[action_id] = (
                    "summon", {"card_id": cid, "hand_idx": i})

        return results


class AttackResolver(LegalActionResolver):
    """Resolver for attacking with monsters."""

    def resolve(env: GameEnv, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Resolve monsters in field slots that can attack."""
        gs = env.engine.game_state
        tm = env.engine.turn_manager
        opp_id = gs.get_opponent_id(player.id)

        # Get attackers that are in attack mode and haven't attacked yet
        my_attackers = [c for c in gs.get_player_field_cards(player.id)
                        if c.card_type == CardType.MONSTER
                        and c.mode == CardMode.ATTACK
                        and not c.has_attacked]

        if not my_attackers or tm.turn_state.turn_count <= 1:
            return {}

        opp_monsters = get_cards_typed(gs, opp_id, CardType.MONSTER)
        results = {}

        for attacker in my_attackers:
            attacker_slot = env.get_card_slot_idx(player.id, attacker)

            if not opp_monsters:
                # Direct attack is target 10
                action_id = ActionCodec.encode(
                    "attack", attacker=attacker_slot, target=10)
                results[action_id] = ("attack", {
                    "attacker_id": attacker.id,
                    "target_id": opp_id,
                    "target_is_player": True
                })
            else:
                for target in opp_monsters:
                    target_slot = env.get_card_slot_idx(opp_id, target)
                    action_id = ActionCodec.encode(
                        "attack", attacker=attacker_slot, target=target_slot)
                    results[action_id] = ("attack", {
                        "attacker_id": attacker.id,
                        "target_id": target.id,
                        "target_is_player": False
                    })
        return results


class CastSpellResolver(LegalActionResolver):
    """Resolver for casting spells."""

    def resolve(env: GameEnv, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Resolve castable spells and their target field slots."""
        gs = env.engine.game_state
        card_ids = gs.player_info[player.id].held_cards.card_ids
        opp_id = gs.get_opponent_id(player.id)

        results = {}
        for i, cid in enumerate(card_ids):
            card = gs.get_card_by_id(cid)
            if not card or card.card_type != CardType.SPELL:
                continue

            # NOTE: this is assuming ability will act well together, bad design but good for now
            ability = card.abilities[0]
            valid_targets: List[Tuple[int, Optional[str], bool]] = []

            if ability in (SpellAbility.BUFF_ATTACK, SpellAbility.BUFF_DEFEND):
                my_monsters = get_cards_typed(gs, player.id, CardType.MONSTER)
                for m in my_monsters:
                    s = env.get_card_slot_idx(player.id, m)
                    valid_targets.append((1 + s, m.id, False))

            elif ability == SpellAbility.DESTROY_TRAP:
                opp_traps = get_cards_typed(gs, opp_id, CardType.TRAP)
                for t in opp_traps:
                    s = env.get_card_slot_idx(opp_id, t)
                    valid_targets.append((11 + s, t.id, False))
            else:
                valid_targets.append((0, None, False))

            for target_val, target_id, is_player in valid_targets:
                action_id = ActionCodec.encode(
                    "cast_spell", spell=i, target=target_val)
                results[action_id] = ("cast_spell", {
                    "card_id": cid,
                    "target_id": target_id,
                    "hand_idx": i,
                    "target_val": target_val
                })

        return results


class SetTrapResolver(LegalActionResolver):
    """Resolver for setting traps."""

    def resolve(env: GameEnv, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Resolve settable traps from hand slots."""
        gs = env.engine.game_state
        card_ids = gs.player_info[player.id].held_cards.card_ids

        empty_cnt = len(gs.get_empty_slots(player.id))
        if gs.player_info[player.id].has_summoned_trap or empty_cnt <= 0:
            return {}

        results = {}
        for i, cid in enumerate(card_ids):
            card = gs.get_card_by_id(cid)
            if card and card.card_type == CardType.TRAP:
                action_id = ActionCodec.encode("set_trap", trap=i)
                results[action_id] = (
                    "set_trap", {"card_id": cid, "hand_idx": i})

        return results


class ToggleResolver(LegalActionResolver):
    """Resolver for toggling monster position."""

    def resolve(env: GameEnv, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Resolve monsters in field slots that can be toggled."""
        gs = env.engine.game_state
        if gs.player_info[player.id].has_toggled:
            return {}

        my_monsters = get_cards_typed(gs, player.id, CardType.MONSTER)
        results = {}
        for m in my_monsters:
            s = env.get_card_slot_idx(player.id, m)
            action_id = ActionCodec.encode("toggle", toggle=s)
            results[action_id] = ("toggle", {"card_id": m.id, "slot": s})

        return results


class CombineResolver(LegalActionResolver):
    """Resolver for merging monsters."""

    def resolve(env: GameEnv, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Resolve pairs of field slots containing mergeable monsters."""
        gs = env.engine.game_state
        mergeable_groups = gs.get_mergeable_groups(player.id)
        results = {}

        for group in mergeable_groups.values():
            if len(group) >= 2:
                for i in range(len(group)):
                    for j in range(i + 1, len(group)):
                        m1, m2 = group[i], group[j]
                        s1 = env.get_card_slot_idx(player.id, m1)
                        s2 = env.get_card_slot_idx(player.id, m2)
                        # TODO: handle this later, no 5 stars yet
                        if m1.star >= 4:
                            continue
                        aid1 = ActionCodec.encode(
                            "combine", slot_1=s1, slot_2=s2)
                        results[aid1] = (
                            "combine", {"card1_id": m1.id, "card2_id": m2.id, "slots": (s1, s2)})
                        aid2 = ActionCodec.encode(
                            "combine", slot_1=s2, slot_2=s1)
                        results[aid2] = (
                            "combine", {"card1_id": m2.id, "card2_id": m1.id, "slots": (s2, s1)})

        return results


class EndTurnResolver(LegalActionResolver):
    """Resolver for ending turn."""

    def resolve(env: GameEnv, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Resolve the end turn action."""
        return {0: ("end_turn", {})}


NormalResolvers = {
    SummonResolver,
    AttackResolver,
    CastSpellResolver,
    SetTrapResolver,
    ToggleResolver,
    CombineResolver,
    EndTurnResolver
}

TrapStageResolvers = (
    TrapActivateResolver,
    EndTurnResolver
)
