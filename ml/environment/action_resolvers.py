from core.data.player import Player
from typing import Tuple, List, Dict, Any
from .action_codec import ActionCodec
from core.cards.card import CardType
from core.cards.monster_card import CardMode


class LegalActionResolver:
    def resolve(self, env, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        raise NotImplementedError


class TrapActivateResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Resolve triggerable traps based on the current state."""
        gs = env.engine.game_state
        results = {}

        for trap_id in gs.triggerable_traps.keys():
            card = gs.get_card_by_id(trap_id)
            if card.owner_id == player.id and card.id not in gs.activated_traps:
                slot = env._get_card_slot_idx(player.id, card)
                action_id = ActionCodec.encode("activate_trap", trap=slot)
                results[action_id] = (
                    "activate_trap", {"card_id": trap_id, "slot": slot})

        return results


class SummonResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Resolve summonable monsters from hand slots."""
        gs = env.engine.game_state
        card_ids = gs.player_info[player.id]["held_cards"].cards

        results = {}
        if gs.player_info[player.id].get("has_summoned_monster", False) or \
                not gs.has_slot_available(player.id):
            return {}

        # TODO: since when were there 11 cards in hand ?
        print("The length of the card in hands are", len(card_ids))
        for i, cid in enumerate(card_ids):
            card = gs.get_card_by_id(cid)
            if card and card.card_type == CardType.MONSTER:
                action_id = ActionCodec.encode("summon", monster=i)
                results[action_id] = (
                    "summon", {"card_id": cid, "hand_idx": i})

        return results


class AttackResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Resolve monsters in field slots that can attack."""
        gs = env.engine.game_state
        tm = env.engine.turn_manager
        opp_id = gs.get_opponent_id(player.id)

        # Get attackers that are in attack mode and haven't attacked yet
        my_attackers = [c for c in gs.get_player_cards(player.id)
                        if c.card_type == CardType.MONSTER
                        and c.mode == CardMode.ATTACK
                        and not c.has_attack]

        if not my_attackers or tm.turn_count <= 1:
            return {}

        opp_monsters = gs.get_cards_typed(opp_id, CardType.MONSTER)
        results = {}

        for attacker in my_attackers:
            attacker_slot = env._get_card_slot_idx(player.id, attacker)

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
                    target_slot = env._get_card_slot_idx(opp_id, target)
                    action_id = ActionCodec.encode(
                        "attack", attacker=attacker_slot, target=target_slot)
                    results[action_id] = ("attack", {
                        "attacker_id": attacker.id,
                        "target_id": target.id,
                        "target_is_player": False
                    })
        return results


class CastSpellResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Resolve castable spells and their target field slots."""
        gs = env.engine.game_state
        card_ids = gs.player_info[player.id]["held_cards"].cards
        opp_id = gs.get_opponent_id(player.id)

        results = {}
        for i, cid in enumerate(card_ids):
            card = gs.get_card_by_id(cid)
            if not card or card.card_type != CardType.SPELL:
                continue

            ability = card.ability
            # (target_val, target_id, is_player)
            valid_targets: List[Tuple[int, Any, bool]] = []

            if ability in ("buff_attack", "buff_defense"):
                my_monsters = gs.get_cards_typed(player.id, "monster")
                for m in my_monsters:
                    s = env._get_card_slot_idx(player.id, m)
                    valid_targets.append((1 + s, m.id, False))

            elif ability == "destroy_trap":
                opp_traps = gs.get_cards_typed(opp_id, "trap")
                for t in opp_traps:
                    s = env._get_card_slot_idx(opp_id, t)
                    valid_targets.append((11 + s, t.id, False))
            else:
                # Spells with no target
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
    def resolve(self, env, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Resolve settable traps from hand slots."""
        gs = env.engine.game_state
        card_ids = gs.player_info[player.id]["held_cards"].cards

        if gs.player_info[player.id].get("has_summoned_trap", False) or not gs.has_slot_available(player.id):
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
    def resolve(self, env, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Resolve monsters in field slots that can be toggled."""
        gs = env.engine.game_state
        if gs.player_info[player.id].get("has_toggled", False):
            return {}

        my_monsters = gs.get_cards_typed(player.id, CardType.MONSTER)
        results = {}
        for m in my_monsters:
            s = env._get_card_slot_idx(player.id, m)
            action_id = ActionCodec.encode("toggle", toggle=s)
            results[action_id] = ("toggle", {"card_id": m.id, "slot": s})

        return results


class CombineResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        """Resolve pairs of field slots containing mergeable monsters."""
        gs = env.engine.game_state
        mergeable_groups = gs.get_mergeable_groups(player.id)
        results = {}

        for group in mergeable_groups.values():
            if len(group) >= 2:
                for i in range(len(group)):
                    for j in range(i + 1, len(group)):
                        m1, m2 = group[i], group[j]
                        s1 = env._get_card_slot_idx(player.id, m1)
                        s2 = env._get_card_slot_idx(player.id, m2)
                        # Both orderings for completeness
                        # TODO: is this really the way to go ?
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
    def resolve(self, env, player: Player) -> Dict[int, Tuple[str, Dict[str, Any]]]:
        return {0: ("end_turn", {})}
