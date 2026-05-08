from datetime import datetime
from typing import Tuple, List
from core.cards.trap_card import ActivateCondition
from core.factory.draw_system import DrawSystem
from core.player import Player
from core.factory.monster_factory import MonsterFactory
from core.factory.spell_factory import SpellFactory
from core.factory.trap_factory import TrapFactory
from core.game_info.game_state import GameState
from core.handle_game_logic.rule_engine import RuleEngine
from core.handle_game_logic.turn_manager import TurnManager
from core.game_info.effect_tracker import EffectTracker
from core.game_info.events import EventLogger, AttackEvent, ToggleEvent, MergeEvent
from core.utils import disable_print, setup_logger
from core.handle_game_logic.trap_engine import TrapEngine
from core.handle_game_logic.spell_engine import SpellEngine
from .utils import log_action


class GameEngine:
    def __init__(self,
                 players: List[Player],
                 verbose: bool = True,
                 log_to_file: bool = False,
                 socket_io=None):
        self.game_state = GameState(players)
        self.effect_tracker = EffectTracker()
        self.turn_manager = TurnManager(self.game_state, self.effect_tracker)
        self.rule_engine = RuleEngine(self.game_state, self.turn_manager)
        self.draw_system = DrawSystem()
        self.event_logger = EventLogger()

        self.trap_engine = TrapEngine(self)
        self.spell_engine = SpellEngine(self)

        self.players = players

        self.monster_factory = MonsterFactory()
        self.monster_factory.build()

        self.spell_factory = SpellFactory()
        self.spell_factory.build()

        self.trap_factory = TrapFactory()
        self.trap_factory.build()

        self.start_hand_count = 5
        self.socket_io = socket_io

        # Control verbosity
        if not verbose:
            disable_print()

        log_path = None
        if log_to_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H-%M-%S")
            log_path = f"logs/game_run_{timestamp}.log"
        self.logger = setup_logger(log_path=log_path, console=True)

    def synchronize(self):
        if self.socket_io:
            try:
                data = self.serialize()
                self.socket_io.emit("synchronize", data)
            except Exception as e:
                self.logger.error(e)
                self.logger.debug(data)
                raise

    def serialize(self):
        return {
            "effect_tracker": self.effect_tracker.serialize(),
            "event_logger": self.event_logger.serialize(),
            "game_state": self.game_state.serialize(),
            "start_hand_count": self.start_hand_count,
            "turn_manager": self.turn_manager.serialize()
        }

    def deserialize(self, content):
        self.effect_tracker.deserialize(content["effect_tracker"])
        self.event_logger.deserialize(content["event_logger"])
        self.game_state.deserialize(content["game_state"])
        self.start_hand_count = content["start_hand_count"]
        self.turn_manager.deserialize(content["turn_manager"])
        self.players = self.game_state.players

    def reset(self):
        self.effect_tracker.clear_all_effects(self.game_state)
        self.event_logger.clear_events()
        self.game_state.reset()
        for player in self.players:
            player.reset()

    def start_game(self):
        self.give_init_cards(self.start_hand_count)

    def give_init_cards(self, number: int):
        for player in self.players:
            for _ in range(number):
                self.draw_card(player.id, check=False)

    def draw_card(self, player_id: str, check=True):
        """Player draws a card if allowed"""
        can_draw = not check or self.rule_engine.can_draw(player_id)

        if can_draw:
            card = self.draw_system.rate_card_draw(player_id)
            if card:
                self.game_state.entity_lookup[card.id] = card
                self.game_state.player_info[player_id]["held_cards"].add(
                    card.id)
                log_action("DRAW", player_id, {
                    "card": card.name,
                    "type": card.ctype,
                    "hand_size": len(self.game_state.player_info[player_id]["held_cards"])
                }, True)
                self.synchronize()
                return True

        return False

    def toggle_card(self, card_id: str):
        card = self.game_state.get_card_by_id(card_id)
        if not card:
            return False

        owner_id = card.owner_id
        can_toggle = self.rule_engine.can_toggle(
            owner_id, card_id) and card.ctype == "monster"

        if can_toggle:
            old_mode = card.mode
            new_mode = card.switch_position()
            self.event_logger.add_event(
                ToggleEvent(card_id=card.id, mode=new_mode))
            self.game_state.player_info[owner_id]["has_toggled"] = True

            # TODO: allow the usage of this
            # TODO: this was a shitty way to do it, please fix this
            # TODO: the thing is to make it shows only for correct user
            if self.trap_engine.check_traps(ActivateCondition.TOGGLE, toggled_card_id=card_id):
                self.turn_manager.toggle_trap_stage(state=True)

            log_action("TOGGLE", owner_id, {
                "card": card.name,
                "position": card.pos_in_matrix,
                "from": old_mode,
                "to": new_mode
            }, True)

            self.synchronize()
            return True

        log_action("TOGGLE", owner_id, {
            "card": card.name,
            "reason": "Already toggled this turn or invalid card type"
        }, False)
        return False

    def summon_card(self,
                    player_id: str,
                    card_id: str,
                    cell: Tuple[int, int] | None,
                    check=True):
        """Player summons a card from hand if allowed"""
        can_summon = self.rule_engine.can_summon(
            player_id, card_id, self.game_state.field_matrix, cell) or not check

        card = self.game_state.get_card_by_id(card_id)
        if not card:
            return False

        if not can_summon:
            reasons = []
            if card.ctype == "monster":
                if self.game_state.player_info[player_id]["has_summoned_monster"]:
                    reasons.append("Already summoned monster this turn")
                if card_id not in self.game_state.player_info[player_id]["held_cards"].cards:
                    reasons.append("Card not in hand")

            log_action("SUMMON", player_id, {
                "card": card.name,
                "type": card.ctype,
                "target_cell": cell,
                "reason": ", ".join(reasons) if reasons else "Rule check failed"
            }, False)
            return False

        if cell is None:
            cell = self.game_state.get_random_empty_slot(player_id)
            if cell is None:
                log_action("SUMMON", player_id, {
                    "card": card.name,
                    "reason": "No empty slots available"
                }, False)
                return False

        self.game_state.player_info[player_id]["held_cards"].remove(card_id)
        if card.ctype == "monster":
            self.game_state.player_info[player_id]["has_summoned_monster"] = True
        elif card.ctype == "trap":
            self.game_state.player_info[player_id]["has_summoned_trap"] = True

        self.game_state.modify_field("add", card, cell)
        card.is_placed = True
        card.pos_in_matrix = cell

        details = {
            "card": card.name,
            "type": card.ctype,
            "position": cell
        }
        if card.ctype == "monster":
            details.update({
                "atk": card.atk,
                "def": card.defend,
                "level": card.level_star
            })

        log_action("SUMMON", player_id, details, True)

        # TODO: fix this and leave the activation to the other first
        # TODO: the summon one is easy, the toggle one is easy, but the attack one is hard
        # TODO: add an indicator for the target also
        # self.check_summon_trap(card_id)
        if self.trap_engine.check_traps(ActivateCondition.SUMMON, summoned_card_id=card_id):
            self.turn_manager.toggle_trap_stage(state=True)

        self.synchronize()
        return True

    def attack(self,
               attacker_id: str,
               defender_id: str,
               card_id: str,
               target_id: str,
               target_is_player: bool = False
               ):
        can_attack = self.rule_engine.can_attack(
            attacker_id, defender_id, card_id, target_id, target_is_player)

        card = self.game_state.get_card_by_id(card_id)

        if not can_attack:
            reasons = []
            if card.has_attack:
                reasons.append("Already attacked this turn")
            if not card.is_placed:
                reasons.append("Card not on field")
            if card.owner_id != attacker_id:
                reasons.append("Not your card")
            if card.mode != "attack":
                reasons.append("Cards cannot attack in defend mode")

            target_name = target_id
            if target_is_player:
                target_name = f"Player {target_id}"
            else:
                target_card = self.game_state.get_card_by_id(target_id)
                if target_card:
                    target_name = target_card.name

            log_action("ATTACK", attacker_id, {
                "attacker_card": card.name,
                "target": target_name,
                "reason": ", ".join(reasons) if reasons else "Rule check failed"
            }, False)
            return False

        # TODO: this was a shitty way to do it, please fix this
        # TODO: move the _log_action to utils
        # Check for trap triggers before resolving battle
        # if self.check_attack_trap(card_id, defender_id):
            # target_card = self.game_state.get_card_by_id(target_id)
            # log_action("ATTACK", attacker_id, {
            # "attacker_card": card.name,
            # "target": target_card.name if target_card else target_id,
            # "result": "Negated/Reflected by trap"
            # }, True)
            # self.synchronize()
            # return True

        # if no trap trigger then process it internally else let the opponent do it
        if not self.trap_engine.check_traps(
            ActivateCondition.ATTACK,
            attacker_id=card_id,  # the one doing attacking is this one
            defender_id=defender_id
        ):
            self.resolve_battle(
                attacker_id=attacker_id,
                defender_id=defender_id,
                card_id=card_id,
                target_id=target_id,
                target_is_player=target_is_player
            )
        else:
            self.turn_manager.toggle_trap_stage(state=True)
            self.game_state.attack_queue.append({
                "attacker_id": attacker_id,
                "defender_id": defender_id,
                "card_id": card_id,
                "target_id": target_id,
                "target_is_player": target_is_player
            })

        # TODO: just let the other person resolve the attack
        # TODO: what we can do is just put this a queue thats waiting to be executed after trap resolve is done
        self.synchronize()
        return True

    def move_card_to_graveyard(self, card_id: str):
        card = self.game_state.get_card_by_id(card_id)
        if not card:
            return
        self.game_state.modify_field("remove", card, card.pos_in_matrix)
        self.game_state.player_info[card.owner_id]["graveyard_cards"].add(
            card_id)
        print(f"  → {card.name} moved to {card.owner_id}'s graveyard")

    def resolve_battle(self,
                       attacker_id: str,
                       defender_id: str,
                       card_id: str,
                       target_id: str,
                       target_is_player: bool = False
                       ):
        """Resolve a battle between a card and a target (card or player)"""
        card = self.game_state.get_card_by_id(card_id)
        if not card:
            return

        # The attack event is triggered here
        self.event_logger.add_event(AttackEvent(
            card_id=card.id, target_id=target_id, target_is_player=target_is_player))

        if not target_is_player:
            target = self.game_state.get_card_by_id(target_id)
            if not target:
                return
            defender = self.game_state.players_lookup[defender_id]
            attacker = self.game_state.players_lookup[attacker_id]

            battle_details = {
                "attacker_card": f"{card.name} (ATK:{card.atk})",
                "target_card": f"{target.name} ({'ATK' if target.mode == 'attack' else 'DEF'}:{target.atk if target.mode == 'attack' else target.defend})"
            }

            if target.mode == 'attack':
                if card.atk > target.atk:
                    damage = abs(card.atk - target.atk)
                    defender.life_points = max(
                        defender.life_points - damage, 0)
                    self.move_card_to_graveyard(target_id)
                    battle_details["result"] = f"Target destroyed, {
                        defender.name} -{damage}LP"
                elif card.atk < target.atk:
                    damage = abs(target.atk - card.atk)
                    attacker.life_points = max(
                        attacker.life_points - damage, 0)
                    self.move_card_to_graveyard(card_id)
                    battle_details["result"] = f"Attacker destroyed, {
                        attacker.name} -{damage}LP"
                else:
                    self.move_card_to_graveyard(card_id)
                    self.move_card_to_graveyard(target_id)
                    battle_details["result"] = "Both destroyed (tie)"
            else:  # defense position
                if card.atk > target.defend:
                    self.move_card_to_graveyard(target_id)
                    battle_details["result"] = "Target destroyed (defense pierced)"
                elif card.atk < target.defend:
                    damage = abs(target.defend - card.atk)
                    attacker.life_points = max(
                        attacker.life_points - damage, 0)
                    battle_details["result"] = f"Attack got reflected, {
                        attacker.name} -{damage}LP"
                else:
                    battle_details["result"] = "Attack tied defense (no effect)"

            log_action("ATTACK", attacker_id, battle_details, True)
        else:  # direct attack to player
            target_player = self.game_state.players_lookup[target_id]
            damage = card.atk
            target_player.life_points = max(
                target_player.life_points - damage, 0)
            log_action("ATTACK", attacker_id, {
                "attacker_card": f"{card.name} (ATK:{card.atk})",
                "target": f"Player {target_player.name}",
                "damage": damage,
                "target_remaining_LP": target_player.life_points
            }, True)

        card.has_attack = True

    def upgrade_monster(self,
                        player_id: str,
                        own_card_id: str,
                        target_card_id: str):
        """Upgrade monsters of the same type to a higher level"""
        can_upgrade = self.rule_engine.can_upgrade(
            player_id, own_card_id, target_card_id)

        own_card = self.game_state.get_card_by_id(own_card_id)
        target_card = self.game_state.get_card_by_id(target_card_id)

        if not can_upgrade:
            reasons = []
            if own_card.type != target_card.type:
                reasons.append(f"Type mismatch: {own_card.type} vs {
                               target_card.type}")
            if own_card.level_star != target_card.level_star:
                reasons.append(f"Level mismatch: {own_card.level_star} vs {
                               target_card.level_star}")
            if own_card.owner_id != player_id or target_card.owner_id != player_id:
                reasons.append("Not your cards")

            log_action("UPGRADE", player_id, {
                "card1": f"{own_card.name} (Lv{own_card.level_star})",
                "card2": f"{target_card.name} (Lv{target_card.level_star})",
                "reason": ", ".join(reasons) if reasons else "Rule check failed"
            }, False)
            return False

        upgrade_position = target_card.pos_in_matrix
        old_level = own_card.level_star
        new_level = old_level + 1

        # Remove the base monsters from the field and move them to graveyard
        self.move_card_to_graveyard(own_card_id)
        self.move_card_to_graveyard(target_card_id)

        # Create the upgraded monster
        upgraded_monster = self.monster_factory.load_by_type_and_level(
            player_id, own_card.type, new_level)

        if upgraded_monster is None:
            log_action("UPGRADE", player_id, {
                "type": own_card.type,
                "from_level": old_level,
                "to_level": new_level,
                "reason": f"No monster of type {own_card.type} at level {new_level}"
            }, False)
            return False

        # Place the upgraded monster on the field
        self.game_state.entity_lookup[upgraded_monster.id] = upgraded_monster
        if upgrade_position:
            self.game_state.modify_field(
                "add", upgraded_monster, upgrade_position)
            upgraded_monster.is_placed = True
            upgraded_monster.pos_in_matrix = upgrade_position

            log_action("UPGRADE", player_id, {
                "from": f"{own_card.name} + {target_card.name}",
                "to": f"{upgraded_monster.name} (Lv{new_level})",
                "position": upgrade_position,
                "stats": f"ATK:{upgraded_monster.atk}/DEF:{upgraded_monster.defend}"
            }, True)

            self.event_logger.add_event(MergeEvent(
                card_id=own_card_id,
                target_id=target_card_id,
                result_card_id=upgraded_monster.id
            ))
            self.synchronize()
            return True

        return False

    def set_trap(self, trap_id: str, position: Tuple[int, int] | None, check=True) -> bool:
        success = self.trap_engine.set_trap(trap_id, position, check)
        if success:
            self.synchronize()
        return success

    # TODO: normalize the dependency logging thing later
    def cast_spell(self, spell_id: str, target_id: str | None = None) -> bool:
        success = self.spell_engine.cast_spell(spell_id, target_id)
        if success:
            self.synchronize()
        return success

    def update_effects(self):
        """Update all active effects (call at end of each turn)"""
        self.effect_tracker.update_round(self.game_state)

    # TODO: refactor the rest after, each would have its own manager instance
    # TODO: should remove all the print for logging module instead
    def end_turn(self):
        """End current player's turn"""
        # TODO: must also allow the user to pass only when its their trap turn
        # TODO: the problem is this one where its re-writing everything
        if not self.is_local_turn():
            return

        if self.turn_manager.is_trap_stage():
            # only let the player activating traps end the turn
            # TODO: add an automatic timeout
            self.trap_engine.resolve_traps()
            for attack in self.game_state.attack_queue:
                self.resolve_battle(**attack)
            self.turn_manager.toggle_trap_stage(state=False)
        else:
            current_player = self.turn_manager.get_current_player()

            for card in self.game_state.get_player_cards(current_player.id):
                if card.ctype == "monster":
                    card.has_attack = False

            self.turn_manager.end_turn()
            next_player = self.turn_manager.get_current_player()

            self.draw_card(next_player.id)

        self.synchronize()

    # This take trap into account, does not contribute for real turn
    def is_local_turn(self) -> bool:
        trapper = self.turn_manager.get_trapper()
        current = self.turn_manager.get_current_player()
        for p in self.players:
            if not p.is_opponent:
                local = p
                break

        if trapper:
            return trapper.id == local.id

        return current.id == local.id
