from core.player import Player
from typing import Tuple, List, Dict, Any


class LegalActionResolver:
    def resolve(self, env, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        raise NotImplementedError


class TrapActivateResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        """Resolve triggerable traps based on the current state."""
        gs = env.engine.game_state

        triggerable_slots = []
        for trap_id in gs.triggerable_traps:
            card = gs.get_card_by_id(trap_id)
            if card.owner_id == player.id:
                slot = env._get_card_slot_idx(player.id, card)
                if slot != -1:
                    triggerable_slots.append(slot)

        if not triggerable_slots:
            return [], {}

        return ["activate_trap"], {"activate_trap": {"traps": triggerable_slots}}


class SummonResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        """Resolve summonable monsters from hand slots."""
        gs = env.engine.game_state
        card_ids = gs.player_info[player.id]["held_cards"].cards

        # Resolver logic for summonable monsters
        summonable_hand_slots = []
        for i, cid in enumerate(card_ids):
            card = gs.get_card_by_id(cid)
            if card and card.ctype == "monster":
                summonable_hand_slots.append(i)

        if summonable_hand_slots \
                and not gs.player_info[player.id].get("has_summoned_monster", False) \
                and gs.has_slot_available(player.id):
            return ["summon"], {"summon": {"monsters": summonable_hand_slots}}
        return [], {}


class AttackResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        """Resolve monsters in field slots that can attack."""
        gs = env.engine.game_state
        tm = env.engine.turn_manager
        opp_id = gs.get_opponent_id(player.id)

        # Get attackers that are in attack mode and haven't attacked yet
        my_attackers = [c for c in gs.get_player_cards(player.id)
                        if c.ctype == "monster"
                        and c.mode == "attack"
                        and not c.has_attack]

        opp_monsters = gs.get_cards_typed(opp_id, "monster")

        if my_attackers and tm.turn_count > 1:
            attacker_slots = [env._get_card_slot_idx(
                player.id, c) for c in my_attackers]
            target_slots = [env._get_card_slot_idx(
                opp_id, c) for c in opp_monsters]

            # If no monsters, direct attack is target 10
            if not target_slots:
                target_slots = [10]

            # Filter out -1 slots (shouldn't happen but safe)
            attacker_slots = [s for s in attacker_slots if s != -1]
            target_slots = [s for s in target_slots if s != -1]

            if attacker_slots:
                return ["attack"], {
                    "attack": {
                        "attackers": attacker_slots,
                        "targets": target_slots,
                    }
                }
        return [], {}


class CastSpellResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        """Resolve castable spells and their target field slots."""
        gs = env.engine.game_state
        card_ids = gs.player_info[player.id]["held_cards"].cards

        castable_hand_slots = []
        for i, cid in enumerate(card_ids):
            card = gs.get_card_by_id(cid)
            if card and card.ctype == "spell":
                castable_hand_slots.append(i)

        if not castable_hand_slots:
            return [], {}

        spell_targets: Dict[int, List[int]] = {}
        my_monsters = gs.get_cards_typed(player.id, "monster")
        opp_id = gs.get_opponent_id(player.id)
        opp_traps = gs.get_cards_typed(opp_id, "trap")

        for hand_idx in castable_hand_slots:
            card = gs.get_card_by_id(card_ids[hand_idx])
            ability = card.ability
            valid_target_vals: List[int] = []  # 0=None, 1-10=Own, 11-20=Opp

            if ability in ("buff_attack", "buff_defense"):
                for m in my_monsters:
                    s = env._get_card_slot_idx(player.id, m)
                    if s != -1:
                        valid_target_vals.append(1 + s)

            elif ability == "destroy_trap":
                for t in opp_traps:
                    s = env._get_card_slot_idx(opp_id, t)
                    if s != -1:
                        valid_target_vals.append(11 + s)
            else:
                # Spells with no target
                valid_target_vals = [0]

            if valid_target_vals:
                spell_targets[hand_idx] = valid_target_vals

        if spell_targets:
            return ["cast_spell"], {"cast_spell": {"spells": list(spell_targets.keys()), "targets": spell_targets}}
        return [], {}


class SetTrapResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        """Resolve settable traps from hand slots."""
        gs = env.engine.game_state
        card_ids = gs.player_info[player.id]["held_cards"].cards

        trappable_hand_slots = []
        for i, cid in enumerate(card_ids):
            card = gs.get_card_by_id(cid)
            if card and card.ctype == "trap":
                trappable_hand_slots.append(i)

        if trappable_hand_slots \
                and not gs.player_info[player.id].get("has_summoned_trap", False) \
                and gs.has_slot_available(player.id):
            return ["set_trap"], {"set_trap": {"traps": trappable_hand_slots}}
        return [], {}


class ToggleResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        """Resolve monsters in field slots that can be toggled."""
        gs = env.engine.game_state
        my_monsters = gs.get_cards_typed(player.id, "monster")

        if not my_monsters or gs.player_info[player.id].get("has_toggled", False):
            return [], {}

        toggle_slots = []
        for m in my_monsters:
            s = env._get_card_slot_idx(player.id, m)
            if s != -1:
                toggle_slots.append(s)

        if toggle_slots:
            return ["toggle"], {"toggle": {"toggles": toggle_slots}}
        return [], {}


class CombineResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        """Resolve pairs of field slots containing mergeable monsters."""
        gs = env.engine.game_state
        mergeable_groups = gs.get_mergeable_groups(player.id)
        combine_pairs: List[Tuple[int, int]] = []

        for group in mergeable_groups.values():
            if len(group) >= 2:
                for i in range(len(group)):
                    for j in range(i + 1, len(group)):
                        s1 = env._get_card_slot_idx(player.id, group[i])
                        s2 = env._get_card_slot_idx(player.id, group[j])
                        if s1 != -1 and s2 != -1:
                            combine_pairs.append((s1, s2))

        if combine_pairs:
            return ["combine"], {"combine": {"pairs": combine_pairs}}
        return [], {}


class EndTurnResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        return ["end_turn"], {"end_turn": {}}
