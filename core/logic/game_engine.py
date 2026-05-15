import logging
from typing import Tuple, List, Optional
from core.cards.card import CardType
from core.cards.monster_card import MonsterCard
from core.cards.trap_card import ActivateCondition
from core.factory.draw_system import DrawSystem
from core.data.player import Player
from core.data.game_state import GameState, ModifyMode, AttackEntry
from core.logic.rule_engine import RuleEngine
from core.logic.turn_manager import TurnManager
from core.data.effects import EffectTracker
from core.data.events import EventLogger, ToggleEvent
from core.logic.trap_engine import TrapEngine
from core.logic.spell_engine import SpellEngine
from .battle_engine import BattleEngine
from .summon_engine import SummonEngine
from .upgrade_engine import UpgradeEngine
from .utils import log_action, is_local_turn

logger = logging.getLogger(__name__)


class GameEngine:
    """The main orchestrator for game logic, integrating various specialized engines."""

    def __init__(self, players: List[Player], socket_io=None) -> None:
        """Initializes the GameEngine.

        Args:
            players (List[Player]): The list of players in the game.
            socket_io: Socket interface for synchronization.
        """
        self.game_state = GameState(players=players)
        self.game_state.reset()

        self.effect_tracker = EffectTracker()
        self.turn_manager = TurnManager(self.game_state, self.effect_tracker)
        self.rule_engine = RuleEngine(self.game_state, self.turn_manager)
        self.draw_system = DrawSystem()
        self.event_logger = EventLogger()

        # Modular Engines
        self.trap_engine = TrapEngine(self)
        self.spell_engine = SpellEngine(self)
        self.battle_engine = BattleEngine(self)
        self.summon_engine = SummonEngine(self)
        self.upgrade_engine = UpgradeEngine(self)

        self.start_hand_count = 5
        self.socket_io = socket_io

    def synchronize(self) -> None:
        """Synchronizes game state across the network."""
        if self.socket_io:
            try:
                data = self.serialize()
                self.socket_io.emit("synchronize", data)
            except Exception as e:
                logger.error(e)
                raise

    def serialize(self) -> dict:
        """Serializes the current game state.

        Returns:
            dict: A dictionary representation of the game engine state.
        """
        serialized = {}
        serialized["game_state"] = self.game_state.serialize()
        serialized["effect_tracker"] = self.effect_tracker.serialize()
        serialized["event_logger"] = self.event_logger.serialize()
        serialized["turn_manager"] = self.turn_manager.serialize()
        return serialized

    def deserialize(self, serialized: dict) -> None:
        """Deserializes game state from a dictionary.

        Args:
            serialized (dict): The dictionary representation to restore.
        """
        self.game_state.deserialize(serialized["game_state"])
        self.effect_tracker.deserialize(serialized["effect_tracker"])
        self.event_logger.deserialize(serialized["event_logger"])
        self.turn_manager.deserialize(serialized["turn_manager"])

    def reset(self) -> None:
        """Resets the game state and trackers."""
        self.effect_tracker.clear_all_effects(self.game_state)
        self.event_logger.clear_events()
        self.game_state.reset()

    def start_game(self) -> None:
        """Starts the game by dealing initial cards."""
        self.give_init_cards(self.start_hand_count)

    def give_init_cards(self, number: int) -> None:
        """Gives initial cards to all players.

        Args:
            number (int): Number of cards to draw.
        """
        for player in self.game_state.players:
            for _ in range(number):
                self.draw_card(player.id, check=False)

    def draw_card(self, player_id: str, check: bool = True) -> bool:
        """Player draws a card if allowed by rules.

        Args:
            player_id (str): ID of the drawing player.
            check (bool): Whether to enforce rule checks.

        Returns:
            bool: True if card was drawn, False otherwise.
        """
        can_draw = not check or self.rule_engine.can_draw(player_id)

        if can_draw:
            card = self.draw_system.draw(player_id)
            if card:
                card.is_opponent = self.game_state.players_lookup[player_id].is_opponent
                self.game_state.entity_lookup[card.id] = card
                self.game_state.player_info[player_id].held_cards.add(
                    card.id)
                log_action("DRAW", player_id, {
                    "card": card.name,
                    "type": card.card_type.value,
                    "hand_size": len(self.game_state.player_info[player_id].held_cards.card_ids)
                }, True)
                self.synchronize()
                return True

        return False

    def toggle_card(self, card_id: str) -> bool:
        """Toggles a monster's position (Attack/Defense).

        Args:
            card_id (str): ID of the card to toggle.

        Returns:
            bool: True if successful, False otherwise.
        """
        card = self.game_state.get_card_by_id(card_id)
        if not card or card.card_type != CardType.MONSTER:
            return False

        owner_id = card.owner_id
        if self.rule_engine.can_toggle(owner_id, card_id):
            old_mode = card.mode
            new_mode = card.switch_position()
            self.event_logger.add_event(
                ToggleEvent(card_id=card.id, mode=new_mode))
            self.game_state.player_info[owner_id].has_toggled = True

            if self.trap_engine.check_traps(
                condition=ActivateCondition.TOGGLE,
                target_id=card_id
            ):
                self.turn_manager.toggle_trap_stage(state=True)

            log_action("TOGGLE", owner_id, {
                "card": card.name,
                "position": card.pos_in_matrix,
                "from": old_mode.value,
                "to": new_mode.value
            }, True)

            self.synchronize()
            return True

        log_action("TOGGLE", owner_id, {
            "card": card.name,
            "reason": "Already toggled this turn or rule violation"
        }, False)
        return False

    def summon_card(
        self,
        player_id: str,
        card_id: str,
        cell: Optional[Tuple[int, int]],
        check: bool = True
    ) -> bool:
        """Delegates summoning logic to SummonEngine."""
        success = self.summon_engine.summon_card(
            player_id, card_id, cell, check)
        if success:
            self.synchronize()
        return success

    def attack(self, attack: AttackEntry) -> bool:
        """Initiates an attack sequence.

        Args:
            attacker_id (str): ID of the attacker.
            defender_id (str): ID of the defender.
            card_id (str): ID of the attacking card.
            target_id (str): ID of the target.
            target_is_player (bool): True if targeting the player directly.

        Returns:
            bool: True if attack sequence started, False if invalid.
        """
        can_attack = self.rule_engine.can_attack(
            attack.attacker_id,
            attack.defender_id,
            attack.card_id,
            attack.target_id,
            attack.target_is_player
        )

        if not can_attack:
            return False

        # Check for trap triggers
        if not self.trap_engine.check_traps(
            condition=ActivateCondition.ATTACK,
            target_id=attack.card_id,
        ):
            self.battle_engine.resolve_battle(attack)
        else:
            self.turn_manager.toggle_trap_stage(state=True)
            self.game_state.attack_queue.append(attack)

        self.synchronize()
        return True

    def move_card_to_graveyard(self, card_id: str) -> None:
        """Moves a card from the field or hand to the graveyard.

        Args:
            card_id (str): ID of the card to move.
        """
        card = self.game_state.get_card_by_id(card_id)
        assert card is not None

        if card.pos_in_matrix:
            self.game_state.modify_field(
                ModifyMode.REMOVE, card, card.pos_in_matrix)

        self.game_state.player_info[card.owner_id].graveyard_cards.add(
            card_id)
        logger.debug(
            "Card moved to graveyard",
            extra={
                "card_name": card.name,
                "owner_id": card.owner_id,
                "card_id": card_id
            }
        )

    def toggle_trap_activation(self, trap_id: str, activated: bool = False) -> None:
        """Toggles player's intent to activate a triggerable trap.

        Args:
            trap_id (str): ID of the trap card.
            activated (bool): Whether the trap is to be activated.
        """
        owner_id = self.game_state.get_card_by_id(trap_id).owner_id
        if self.rule_engine.can_activate(owner_id, trap_id):
            if activated:
                self.game_state.activated_traps.append(trap_id)
            else:
                self.game_state.activated_traps.remove(trap_id)

    def resolve_battle(self, attack: AttackEntry) -> None:
        """Delegates battle resolution to BattleEngine."""
        self.battle_engine.resolve_battle(attack)

    def upgrade_monster(self, player_id: str, own_card_id: str, target_card_id: str) -> bool:
        """Delegates upgrade logic to UpgradeEngine."""
        success = self.upgrade_engine.upgrade_monster(
            player_id, own_card_id, target_card_id)
        if success:
            self.synchronize()
        return success

    def set_trap(self, trap_id: str, position: Optional[Tuple[int, int]], check: bool = True) -> bool:
        """Delegates trap setting to TrapEngine."""
        success = self.trap_engine.set_trap(trap_id, position, check)
        if success:
            self.synchronize()
        return success

    def cast_spell(self, spell_id: str, target_id: Optional[str] = None) -> bool:
        """Delegates spell casting to SpellEngine."""
        success = self.spell_engine.cast_spell(spell_id, target_id)
        if success:
            self.synchronize()
        return success

    def end_turn(self) -> None:
        """Ends the current turn and handles phase transitions."""
        if self.turn_manager.is_trap_stage():
            cancel_resolve = self.trap_engine.resolve_traps()
            if not cancel_resolve:
                for attack in self.game_state.attack_queue:
                    self.resolve_battle(attack)
            self.game_state.attack_queue.clear()
            self.turn_manager.toggle_trap_stage(state=False)
        else:
            current_player = self.turn_manager.get_current_player()
            for card in self.game_state.get_player_field_cards(current_player.id):
                if isinstance(card, MonsterCard):
                    card.has_attacked = False

            self.turn_manager.end_turn()
            next_player = self.turn_manager.get_current_player()
            self.draw_card(next_player.id)

        self.synchronize()

    def is_local_turn(self) -> bool:
        """Checks if it's the local player's turn.

        Returns:
            bool: True if it is the local player's turn, False otherwise.
        """
        return is_local_turn(self.turn_manager, self.game_state.players)
