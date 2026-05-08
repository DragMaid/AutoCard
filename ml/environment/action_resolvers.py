from core.player import Player
from typing import Tuple, List, Dict, Any


class LegalActionResolver:
    def resolve(self, env, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        raise NotImplementedError


class SummonResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        gs = env.engine.game_state
        card_ids = gs.player_info[player.id]["held_cards"].cards
        summonable = [i for i, cid in enumerate(
            card_ids) if gs.get_card_by_id(cid).ctype == "monster"]
        if summonable \
                and not gs.player_info[player.id].get("has_summoned_monster", False) \
                and gs.has_slot_available(player.id):
            return ["summon"], {"summon": {"monsters": summonable}}
        return [], {}


class AttackResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        gs = env.engine.game_state
        tm = env.engine.turn_manager
        opp_id = gs.get_opponent_id(player.id)
        my_monsters = [c for c in gs.get_player_cards(player.id)
                       if c.ctype == "monster"
                       and c.mode == "attack"
                       and not c.has_attack]
        opp_monsters = [c for c in gs.get_player_cards(
            opp_id) if c.ctype == "monster"]
        if my_monsters and tm.turn_count > 1:
            attack_info = {
                "attack": {
                    "attackers": list(range(len(my_monsters))),
                    "targets": list(range(len(opp_monsters))) if opp_monsters else [-1],
                }
            }
            return ["attack"], attack_info
        return [], {}


class CastSpellResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        gs = env.engine.game_state
        card_ids = gs.player_info[player.id]["held_cards"].cards
        castable = [i for i, cid in enumerate(
            card_ids) if gs.get_card_by_id(cid).ctype == "spell"]
        if not castable:
            return [], {}
        spell_targets: Dict[int, List[int]] = {}
        my_monsters = gs.get_cards_typed(player.id, "monster")

        for spell_idx in castable:
            card = gs.get_card_by_id(card_ids[spell_idx])
            ability = card.ability
            valid_targets: List[int] = []

            if ability in ("buff_attack", "buff_defense"):
                valid_targets = list(range(len(my_monsters)))

            elif ability == "destroy_trap":
                opp_id = gs.get_opponent_id(player.id)
                opp_traps = [c for c in gs.get_cards_typed(opp_id, "trap")]
                valid_targets = list(range(len(opp_traps)))

            else:
                valid_targets = []

            spell_targets[spell_idx] = valid_targets

        to_remove = []
        for key, value in spell_targets.items():
            if len(value) <= 0:
                to_remove.append(key)

        for key in to_remove:
            spell_targets.pop(key)
            castable.remove(key)

        if castable and spell_targets:
            return ["cast_spell"], {"cast_spell": {"spells": castable, "targets": spell_targets}}
        return [], {}


class SetTrapResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        gs = env.engine.game_state
        card_ids = gs.player_info[player.id]["held_cards"].cards
        traps = [i for i, cid in enumerate(
            card_ids) if gs.get_card_by_id(cid).ctype == "trap"]
        if traps \
                and not gs.player_info[player.id].get("has_summoned_trap", False) \
                and gs.has_slot_available(player.id):
            return ["set_trap"], {"set_trap": {"traps": traps}}
        return [], {}


class ToggleResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        gs = env.engine.game_state
        my_monsters = [c for c in gs.get_player_cards(
            player.id) if c.ctype == "monster"]
        toggles = list(range(len(my_monsters)))
        if toggles \
                and not gs.player_info[player.id].get("has_toggled", False):
            return ["toggle"], {"toggle": {"toggles": toggles}}
        return [], {}


class CombineResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        mergeable_groups = env.engine.game_state.get_mergeable_groups(player.id)
        combine_pairs: List[Tuple[str, str]] = []
        for group in mergeable_groups.values():
            if len(group) >= 2:
                for i in range(len(group)):
                    for j in range(i + 1, len(group)):
                        combine_pairs.append((group[i].id, group[j].id))
        if combine_pairs:
            return ["combine"], {"combine": {"pairs": combine_pairs}}
        return [], {}


class EndTurnResolver(LegalActionResolver):
    def resolve(self, env, player: Player) -> Tuple[List[str], Dict[str, Any]]:
        return ["end_turn"], {"end_turn": {}}
