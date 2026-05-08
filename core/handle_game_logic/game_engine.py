from datetime import datetime
from typing import Tuple, List, Any
from core.cards.trap_card import ActivateCondition
from core.factory.draw_system import DrawSystem
from core.player import Player
from core.factory.monster_factory import MonsterFactory
from core.factory.spell_factory import SpellFactory
from core.factory.trap_factory import TrapFactory
from core.game_info.game_state import GameState
from core.handle_game_logic.rule_engine import RuleEngine
from core.handle_game_logic.turn_manager import TurnManager
from core.game_info.effect_tracker import EffectTracker, EffectType
from core.game_info.events import EventLogger, AttackEvent, TrapTriggerEvent, ToggleEvent, SpellActiveEvent, MergeEvent
from core.utils import disable_print, setup_logger


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

        self.players = players

        self.monster_factory = MonsterFactory()
        self.monster_factory.build()

        self.spell_factory = SpellFactory()
        self.spell_factory.build()

        self.trap_factory = TrapFactory()
        self.trap_factory.build()

        self.start_hand_count = 5
        self.socket_io = socket_io

        # --- Control verbosity ---
        if not verbose:
            disable_print()

        log_path = None
        if log_to_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H-%M-%S")
            log_path = f"logs/game_run_{timestamp}.log"
        self.logger = setup_logger(log_path=log_path, console=True)

        # Action counter for tracking
        self.action_counter = 0

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
            "action_counter": self.action_counter,
            "start_hand_count": self.start_hand_count,
            "turn_manager": self.turn_manager.serialize()
        }

    def deserialize(self, content):
        self.effect_tracker.deserialize(content["effect_tracker"])
        self.event_logger.deserialize(content["event_logger"])
        self.game_state.deserialize(content["game_state"])
        self.action_counter = content["action_counter"]
        self.start_hand_count = content["start_hand_count"]
        self.turn_manager.deserialize(content["turn_manager"])
        self.players = self.game_state.players

    def reset(self):
        self.effect_tracker.clear_all_effects(self.game_state)
        self.event_logger.clear_events()
        self.game_state.reset()
        self.action_counter = 0
        for player in self.players:
            player.reset()

    def _log_action(self, action_type: str, player_id: str, details: dict, success: bool):
        """Central logging method for all game actions"""
        self.action_counter += 1
        status = "SUCCESS" if success else "FAILED"
        log_msg = f"[Action #{self.action_counter}] [{
            status}] {action_type} by {player_id}"

        # Add relevant details
        detail_parts = []
        for key, value in details.items():
            detail_parts.append(f"{key}={value}")

        if detail_parts:
            log_msg += f" | {', '.join(detail_parts)}"

        if success:
            print(log_msg)
        else:
            print(f"❌ {log_msg}")

    def start_game(self):
        print("="*60)
        print("GAME STARTED")
        print("="*60)
        self.give_init_cards(self.start_hand_count)

    def give_init_cards(self, number: int):
        for player in self.players:
            for _ in range(number):
                self.draw_card(player.id, check=False)

    # DEBUG FUNCTION
    def draw_specific_card(self, player_id: str, name: str, ctype: str):
        if ctype == "monster":
            card = self.monster_factory.load(player_id, name)
        elif ctype == "trap":
            card = self.trap_factory.load(player_id, name)
        elif ctype == "spell":
            card = self.spell_factory.load(player_id, name)
        else:
            return
        self.game_state.entity_lookup[card.id] = card
        self.game_state.player_info[player_id]["held_cards"].add(card.id)
        print(f"[DEBUG] {player_id} received specific card: {name}")

    def draw_card(self, player_id: str, check=True):
        """Player draws a card if allowed"""
        can_draw = not check or self.rule_engine.can_draw(player_id)

        if can_draw:
            card = self.draw_system.rate_card_draw(player_id)
            if card:
                self.game_state.entity_lookup[card.id] = card
                self.game_state.player_info[player_id]["held_cards"].add(
                    card.id)
                self._log_action("DRAW", player_id, {
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
            self.check_toggle_trap(card_id)
            self._log_action("TOGGLE", owner_id, {
                "card": card.name,
                "position": card.pos_in_matrix,
                "from": old_mode,
                "to": new_mode
            }, True)
            self.synchronize()
            return True

        self._log_action("TOGGLE", owner_id, {
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

            self._log_action("SUMMON", player_id, {
                "card": card.name,
                "type": card.ctype,
                "target_cell": cell,
                "reason": ", ".join(reasons) if reasons else "Rule check failed"
            }, False)
            return False

        if cell is None:
            cell = self.game_state.get_random_empty_slot(player_id)
            if cell is None:
                self._log_action("SUMMON", player_id, {
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

        self._log_action("SUMMON", player_id, details, True)

        # TODO: fix this and leave the activation to the other first
        # TODO: add an indicator for the target also
        # self.check_summon_trap(card_id)

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

            self._log_action("ATTACK", attacker_id, {
                "attacker_card": card.name,
                "target": target_name,
                "reason": ", ".join(reasons) if reasons else "Rule check failed"
            }, False)
            return False

        # TODO: this was a shitty way to do it, please fix this
        # Check for trap triggers before resolving battle
        # if self.check_attack_trap(card_id, defender_id):
            # target_card = self.game_state.get_card_by_id(target_id)
            # self._log_action("ATTACK", attacker_id, {
                # "attacker_card": card.name,
                # "target": target_card.name if target_card else target_id,
                # "result": "Negated/Reflected by trap"
            # }, True)
            # self.synchronize()
            # return True

        self.resolve_battle(attacker_id, defender_id,
                            card_id, target_id, target_is_player)
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

            self._log_action("ATTACK", attacker_id, battle_details, True)
        else:  # direct attack to player
            target_player = self.game_state.players_lookup[target_id]
            damage = card.atk
            target_player.life_points = max(
                target_player.life_points - damage, 0)
            self._log_action("ATTACK", attacker_id, {
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

            self._log_action("UPGRADE", player_id, {
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
            self._log_action("UPGRADE", player_id, {
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

            self._log_action("UPGRADE", player_id, {
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

    def cast_spell(self, spell_id: str, target_id: Any = None):
        """Cast a spell card immediately"""
        spell = self.game_state.get_card_by_id(spell_id)
        if not spell or spell.ctype != "spell":
            self._log_action("CAST_SPELL", None, {
                "reason": "Not a spell card"
            }, False)
            return False

        current_player = self.turn_manager.get_current_player()

        if spell.owner_id != current_player.id:
            self._log_action("CAST_SPELL", spell.owner_id, {
                "spell": spell.name,
                "reason": f"Not your turn (current: {current_player.name})"
            }, False)
            return False

        # TODO: this is way too hard coded
        if spell.ability not in ("draw_two_cards", "call_of_brave") and target_id:
            target_card = self.game_state.get_card_by_id(target_id)
            if target_card and target_card.ctype == "monster" and spell.owner_id != target_card.owner_id:
                self._log_action("CAST_SPELL", spell.owner_id, {
                    "spell": spell.name,
                    "target": target_card.name,
                    "reason": "Cannot target enemy monsters with buff spells"
                }, False)
                return False

            if target_card and target_card.ctype == "trap" and spell.owner_id == target_card.owner_id:
                self._log_action("CAST_SPELL", spell.owner_id, {
                    "spell": spell.name,
                    "target": target_card.name,
                    "reason": "Cannot destroy your own trap"
                }, False)
                return False

        details = {"spell": spell.name, "ability": spell.ability}

        # Resolve spell based on ability
        if spell.ability == "draw_two_cards":
            self.draw_card(spell.owner_id, check=False)
            self.draw_card(spell.owner_id, check=False)
            details["effect"] = "Drew 2 cards"

        elif spell.ability == "buff_attack":
            self.effect_tracker.add_effect(
                EffectType.BUFF, target_id, "atk", spell.value, spell.duration, self.game_state)
            target_card = self.game_state.get_card_by_id(target_id)
            details["target"] = target_card.name if target_card else target_id
            details["effect"] = f"+{spell.value} ATK for {spell.duration} turns"

        elif spell.ability == "buff_defense":
            self.effect_tracker.add_effect(
                EffectType.BUFF, target_id, "defend", spell.value, spell.duration, self.game_state)
            target_card = self.game_state.get_card_by_id(target_id)
            details["target"] = target_card.name if target_card else target_id
            details["effect"] = f"+{spell.value} DEF for {spell.duration} turns"

        elif spell.ability == "destroy_trap":
            if target_id:
                target_card = self.game_state.get_card_by_id(target_id)
                if target_card and target_card.ctype == "trap":
                    self.move_card_to_graveyard(target_id)
                    details["target"] = target_card.name
                    details["effect"] = "Trap destroyed"
                else:
                    details["reason"] = f"Invalid trap target - {target_id}"
                    self._log_action(
                        "CAST_SPELL", spell.owner_id, details, False)
                    return False

        elif spell.ability == "summon_monster_from_hand":
            self.game_state.player_info[spell.owner_id]['has_summoned_monster'] = False
            details["effect"] = "Extra summon enabled"

        # Move spell to graveyard after use
        self.event_logger.add_event(SpellActiveEvent(
            spell_id=spell.id, target_id=target_id))
        self.game_state.player_info[spell.owner_id]["held_cards"].remove(
            spell_id)
        self.game_state.player_info[spell.owner_id]["graveyard_cards"].add(
            spell_id)

        self._log_action("CAST_SPELL", spell.owner_id, details, True)
        self.synchronize()
        return True

    def set_trap(self, trap_id: str, position: Tuple[int, int] | None, check=True):
        """Set a trap card face-down on the field"""
        trap = self.game_state.get_card_by_id(trap_id)
        if not trap or trap.ctype != "trap":
            return False

        can_set = self.rule_engine.can_summon(
            trap.owner_id, trap_id, self.game_state.field_matrix, position) or not check

        if not can_set:
            self._log_action("SET_TRAP", trap.owner_id, {
                "trap": trap.name,
                "position": position,
                "reason": "Cannot set trap (already set one or no space)"
            }, False)
            return False

        if position is None:
            position = self.game_state.get_random_empty_slot(trap.owner_id)
            if position is None:
                self._log_action("SET_TRAP", trap.owner_id, {
                    "trap": trap.name,
                    "reason": "No empty slots available"
                }, False)
                return False

        # Place trap face-down
        self.game_state.player_info[trap.owner_id]["held_cards"].remove(
            trap_id)
        self.game_state.modify_field("add", trap, position)
        self.game_state.player_info[trap.owner_id]["has_summoned_trap"] = True
        trap.is_placed = True
        trap.is_face_down = True
        trap.pos_in_matrix = position

        self._log_action("SET_TRAP", trap.owner_id, {
            "trap": trap.name,
            "ability": trap.ability,
            "position": position,
            "state": "face-down"
        }, True)
        self.synchronize()
        return True

    def resolve_trap(self, trap_id: str, attacker_id: str):
        """Resolve a trap card when triggered"""
        trap = self.game_state.get_card_by_id(trap_id)
        attacker = self.game_state.get_card_by_id(attacker_id)

        if not trap or trap.ctype != "trap" or not attacker:
            return False

        print(f"  🪤 TRAP ACTIVATED: {trap.name} (Owner: {trap.owner_id})")
        print(f"     Trigger: {attacker.name} (Owner: {attacker.owner_id})")

        result = False
        effect_desc = ""

        # TODO: sometime the debuff trigger first then the one time use which is a waste
        if trap.ability == "debuff_enemy_atk":
            self.effect_tracker.add_effect(
                EffectType.DEBUFF, attacker_id, "atk", trap.value, trap.duration, self.game_state)
            trap.reveal()
            self.event_logger.add_event(TrapTriggerEvent(trap_id, attacker_id))
            self.move_card_to_graveyard(trap_id)
            effect_desc = f"{
                attacker.name} ATK -{trap.value} for {trap.duration} turns"

        elif trap.ability == "debuff_enemy_def":
            self.effect_tracker.add_effect(
                EffectType.DEBUFF, attacker_id, "defend", trap.value, trap.duration, self.game_state)
            trap.reveal()
            self.event_logger.add_event(TrapTriggerEvent(trap_id, attacker_id))
            self.move_card_to_graveyard(trap_id)
            effect_desc = f"{
                attacker.name} DEF -{trap.value} for {trap.duration} turns"

        elif trap.ability == "dodge_attack":
            attacker.has_attack = True
            self.move_card_to_graveyard(trap_id)
            effect_desc = "Attack negated"
            result = True
            trap.reveal()
            self.event_logger.add_event(TrapTriggerEvent(trap_id, attacker_id))

        elif trap.ability == "reflect_attack":
            self.move_card_to_graveyard(attacker_id)
            self.move_card_to_graveyard(trap_id)
            trap.reveal()
            self.event_logger.add_event(TrapTriggerEvent(trap_id, attacker_id))
            effect_desc = "Attack reflected, attacker destroyed"
            result = True

        print(f"Effect: {effect_desc}")
        return result

    def check_trap(self, condition: ActivateCondition, **kwargs):
        """Identify traps triggerable by a toggle, add them to triggerable_traps"""
        condition_map = {
            ActivateCondition.TOGGLE: self.rule_engine.get_toggle_traps,
            ActivateCondition.ATTACK: self.rule_engine.get_attack_traps,
            ActivateCondition.SUMMON: self.rule_engine.get_toggle_traps
        }
        triggerable = condition_map[condition](**kwargs)
        return triggerable

        # TODO: fix this later
        # for trap_id, target_id, context in triggerable:
            # self.game_state.triggerable_traps[trap_id] = context
            # self.event_logger.add_event(
                # TrapTriggerEvent(trap_id, target_id))

        # return len(triggerable) > 0

    def get_triggerable_traps(self) -> list:
        """Return list of trap IDs that are currently triggerable."""
        return list(self.game_state.triggerable_traps.keys())

    def has_triggerable_traps(self) -> bool:
        """Check if there are any triggerable traps waiting for activation."""
        return len(self.game_state.triggerable_traps) > 0

    # TODO: this function jjust doesnt get used at all
    # def activate_trap(self, trap_id: str) -> bool:
        # """Activate a specific trap that is marked as triggerable.

        # Args:
            # trap_id: ID of the trap to activate

        # Returns:
            # True if trap was successfully activated, False otherwise
        # """
        # if trap_id not in self.game_state.triggerable_traps:
            # self.logger.warning(
                # f"[TRAP] Attempted to activate non-triggerable trap {trap_id}")
            # return False

        # trap = self.game_state.get_card_by_id(trap_id)
        # if not trap or trap.ctype != "trap":
            # self.logger.warning(f"[TRAP] Trap {trap_id} not found or invalid")
            # return False

        # context = self.game_state.triggerable_traps[trap_id]
        # self.game_state.activated_traps.add(trap_id)

        # # Resolve the trap's effect based on its ability
        # trigger_type = context.get("trigger_type")

        # if trigger_type == "attack":
            # attacker_id = context.get("attacker_id")
            # result = self.resolve_trap(trap_id, attacker_id)
        # elif trigger_type == "toggle":
            # toggled_card_id = context.get("toggled_card_id")
            # # Apply toggle trap effect
            # result = self._resolve_toggle_trap(trap_id, toggled_card_id)
        # elif trigger_type == "summon":
            # summoned_card_id = context.get("summoned_card_id")
            # # Apply summon trap effect
            # result = self._resolve_summon_trap(trap_id, summoned_card_id)
        # else:
            # result = False

        # # Remove from triggerable list
        # del self.game_state.triggerable_traps[trap_id]

        # self.logger.info(
            # f"[TRAP] Trap {trap.name} activated (result: {result})")
        # self.synchronize()
        # return result

    def skip_triggerable_traps(self) -> bool:
        """Skip all remaining triggerable traps and clear the list."""
        if not self.game_state.triggerable_traps:
            return False

        # Reset traps to face-down if they weren't activated
        non_activated = [tid for tid in self.game_state.triggerable_traps.keys()
                         if tid not in self.game_state.activated_traps]

        for trap_id in non_activated:
            trap = self.game_state.get_card_by_id(trap_id)
            if trap:
                trap.is_face_down = True  # Flip back to face-down

        # Clear triggerable traps and activated traps for this phase
        self.game_state.triggerable_traps.clear()
        self.game_state.activated_traps.clear()

        self.logger.info(f"[TRAP] Skipped {len(
            non_activated)} triggerable traps")
        self.synchronize()
        return True

    def _resolve_toggle_trap(self, trap_id: str, toggled_card_id: str) -> bool:
        """Resolve a trap triggered by toggle."""
        trap = self.game_state.get_card_by_id(trap_id)
        toggled_card = self.game_state.get_card_by_id(toggled_card_id)

        if not trap or not toggled_card:
            return False

        if trap.ability == "debuff_defend_toggle":
            self.effect_tracker.add_effect(
                EffectType.DEBUFF, toggled_card_id, "defend", trap.value, trap.duration, self.game_state
            )
            self.move_card_to_graveyard(trap_id)
            self.logger.info(f"[TRAP] {trap.name} debuffed {
                             toggled_card.name} DEF")
            return True

        return False

    def _resolve_summon_trap(self, trap_id: str, summoned_card_id: str) -> bool:
        """Resolve a trap triggered by summon."""
        trap = self.game_state.get_card_by_id(trap_id)
        summoned_card = self.game_state.get_card_by_id(summoned_card_id)

        if not trap or not summoned_card:
            return False

        if trap.ability == "debuff_summon":
            self.effect_tracker.add_effect(
                EffectType.DEBUFF, summoned_card_id, "atk", trap.value, trap.duration, self.game_state
            )
            self.effect_tracker.add_effect(
                EffectType.DEBUFF, summoned_card_id, "defend", trap.value, trap.duration, self.game_state
            )
            self.move_card_to_graveyard(trap_id)
            self.logger.info(f"[TRAP] {trap.name} debuffed {
                             summoned_card.name}")
            return True

        return False

    def update_effects(self):
        """Update all active effects (call at end of each turn)"""
        self.effect_tracker.update_round(self.game_state)

    def end_turn(self):
        """End current player's turn"""
        current_player = self.turn_manager.get_current_player()

        for card in self.game_state.get_player_cards(current_player.id):
            if card.ctype == "monster":
                card.has_attack = False

        self.turn_manager.end_turn()
        next_player = self.turn_manager.get_current_player()

        self.draw_card(next_player.id)
        self.synchronize()
