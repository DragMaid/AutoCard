from core.utils import get_logger
from core.handle_game_logic.turn_manager import TurnManager
from core.cards.trap_card import ActivateCondition
from core.game_info.game_state import GameState
from typing import Tuple, List


class RuleEngine:
    def __init__(self, game_state: GameState, turn_manager: TurnManager):
        self.turn_manager = turn_manager
        self.game_state = game_state
        self.max_hand_cards = 10
        self.max_stats = 9999

        self.logger = get_logger()
        self.logger.info("RuleEngine initialized")

    def can_draw(self, player_id: str) -> bool:
        """Check if player can draw a card."""
        current_player = self.turn_manager.get_current_player()
        hand_size = len(
            self.game_state.player_info[player_id]["held_cards"].cards)

        # Validation checks
        if current_player.id != player_id:
            self.logger.debug(f"[RULE] {player_id} cannot draw: Not their turn (current: {
                              current_player.id})")
            return False

        if hand_size >= self.max_hand_cards:
            self.logger.debug(f"[RULE] {player_id} cannot draw: Hand full ({
                              hand_size}/{self.max_hand_cards})")
            return False

        return True

    def can_activate(self,
                     player_id: str,
                     trap_id: str) -> bool:
        trapper = self.turn_manager.get_trapper()
        card = self.game_state.get_card_by_id(trap_id)

        if trapper.id != player_id:
            self.logger.debug(f"[RULE] {player_id} cannot activate {
                              card.name} since its not their trap turn")
            return False

        if trap_id not in list(self.game_state.triggerable_traps.keys()):
            self.logger.debug(f"[RULE] {player_id} cannot activate {
                              card.name}: card not currently triggerable")
            return False

        if card.owner_id != player_id:
            self.logger.debug(f"[RULE] {player_id} cannot activate {
                              card.name}: card not does not belong to the player")
            return False

        self.logger.debug(f"[RULE] ✓ {player_id} can activate {card.name}")
        return True

    def can_summon(self,
                   player_id: str,
                   card_id: str,
                   matrix: List[List[None | str]],
                   pos: Tuple[int, int]) -> bool:
        """Check if player can summon a card."""
        current_player = self.turn_manager.get_current_player()
        card = self.game_state.get_card_by_id(card_id)

        if not card:
            return False

        # Check if it's player's turn
        if current_player.id != player_id:
            self.logger.debug(f"[RULE] {player_id} cannot summon {
                              card.name}: Not their turn (current: {current_player.id})")
            return False

        # Check if card is in hand
        if card_id not in self.game_state.player_info[player_id]["held_cards"].cards:
            self.logger.debug(f"[RULE] {player_id} cannot summon {
                              card.name}: Card not in hand")
            return False

        # Check summon type restrictions
        if card.ctype == "monster":
            if self.game_state.player_info[player_id]["has_summoned_monster"]:
                self.logger.debug(f"[RULE] {player_id} cannot summon {
                                  card.name}: Already summoned monster this turn")
                return False
        elif card.ctype == "trap":
            if self.game_state.player_info[player_id]["has_summoned_trap"]:
                self.logger.debug(f"[RULE] {player_id} cannot summon {
                                  card.name}: Already summoned trap this turn")
                return False
        else:
            self.logger.warning(f"[RULE] Unknown card type for {
                                card.name}: {card.ctype}")
            return False

        # Check position validity
        if pos is None:
            # Pos of None is handled by caller wrapper
            return False

        row, col = pos
        if not (0 <= row < len(matrix) and 0 <= col < len(matrix[0])):
            self.logger.debug(f"[RULE] {player_id} cannot summon {
                              card.name}: Position {pos} out of bounds")
            return False

        if matrix[row][col] is not None:
            existing_id = matrix[row][col]
            existing = self.game_state.get_card_by_id(existing_id)
            self.logger.debug(f"[RULE] {player_id} cannot summon {
                              card.name}: Position {pos} occupied by {existing.name if existing else existing_id}")
            return False

        # Check max cards on field
        player_card_count = len(
            self.game_state._player_cards.get(player_id, []))
        if player_card_count >= 10:
            self.logger.debug(f"[RULE] {player_id} cannot summon {
                              card.name}: Field full ({player_card_count}/10)")
            return False

        self.logger.debug(f"[RULE] ✓ {player_id} can summon {
                          card.name} at {pos}")
        return True

    def can_change_mode(self, player_id: str, card_id: str) -> bool:
        """Check if player can change card mode."""
        current_player = self.turn_manager.get_current_player()

        if current_player.id != player_id:
            self.logger.debug(
                f"[RULE] {player_id} cannot change mode: Not their turn")
            return False

        if card_id not in self.game_state._player_cards.get(player_id, []):
            self.logger.debug(f"[RULE] {player_id} cannot change mode for {
                              card_id}: Card not in field")
            return False

        return True

    def can_attack(self,
                   attacker_id: str,
                   defender_id: str,
                   card_id: str,
                   target_id: str,
                   target_is_player: bool = False) -> bool:
        """Check if an attack is valid."""
        current_player = self.turn_manager.get_current_player()
        card = self.game_state.get_card_by_id(card_id)

        # If no source card
        if not card:
            return False

        # Cannot attack on first turn
        if self.turn_manager.turn_count == 1:
            self.logger.debug(f"[RULE] {attacker_id} cannot attack with {
                              card.name}: Cannot attack on turn 1")
            return False

        # Must be attacker's turn
        if current_player.id != attacker_id:
            self.logger.debug(f"[RULE] {
                              attacker_id} cannot attack: Not their turn (current: {current_player.id})")
            return False

        # Card must belong to attacker
        if card.owner_id != attacker_id:
            self.logger.debug(f"[RULE] {attacker_id} cannot attack with {
                              card.name}: Card belongs to {card.owner_id}")
            return False

        # Card must be in attack position
        if card.mode != "attack":
            self.logger.debug(f"[RULE] {attacker_id} cannot attack with {
                              card.name}: Card in {card.mode} mode")
            return False

        # Card cannot have already attacked
        if card.has_attack:
            self.logger.debug(f"[RULE] {attacker_id} cannot attack with {
                              card.name}: Already attacked this turn")
            return False

        # If attacking a monster
        if not target_is_player:
            target = self.game_state.get_card_by_id(target_id)

            if not target:
                return False

            if target.ctype != "monster":
                self.logger.debug(
                    f"[RULE] {card.name} cannot attack a trap card {target.name}")
                return False

            if target.owner_id != defender_id:
                self.logger.debug(f"[RULE] {attacker_id} cannot attack {
                                  target.name}: Target belongs to {target.owner_id}, not defender {defender_id}")
                return False
            self.logger.debug(f"[RULE] ✓ {attacker_id} can attack {
                              target.name} with {card.name}")
            return True

        # If direct attack to player
        if target_is_player:
            # Check if defender has any monsters
            defender_cards = self.game_state.get_player_cards(defender_id)
            for def_card in defender_cards:
                if def_card.ctype == "monster":
                    self.logger.debug(f"[RULE] {attacker_id} cannot direct attack: {
                                      defender_id} has monsters on field")
                    return False

            self.logger.debug(f"[RULE] ✓ {attacker_id} can direct attack {
                              defender_id} with {card.name}")
            return True

        self.logger.debug(
            f"[RULE] {attacker_id} cannot attack: Invalid target")
        return False

    def can_toggle(self, player_id: str, card_id: str) -> bool:
        """Check if player can toggle card position."""
        current_player = self.turn_manager.get_current_player()
        card = self.game_state.get_card_by_id(card_id)

        if not card:
            return False

        if current_player.id != player_id:
            self.logger.debug(f"[RULE] {player_id} cannot toggle {
                              card.name}: Not their turn")
            return False

        if card.owner_id != player_id:
            self.logger.debug(f"[RULE] {player_id} cannot toggle {
                              card.name}: Card belongs to {card.owner_id}")
            return False

        if self.game_state.player_info[player_id]["has_toggled"]:
            self.logger.debug(f"[RULE] {player_id} cannot toggle {
                              card.name}: Already toggled this turn")
            return False

        self.logger.debug(f"[RULE] ✓ {player_id} can toggle {card.name}")
        return True

    def can_upgrade(self, player_id: str, own_card_id: str, target_card_id: str) -> bool:
        """Check if player can upgrade monsters of given type to target level."""
        current_player = self.turn_manager.get_current_player()
        own_card = self.game_state.get_card_by_id(own_card_id)
        target_card = self.game_state.get_card_by_id(target_card_id)

        if not own_card or not target_card:
            return False

        if current_player.id != player_id:
            self.logger.debug(f"[RULE] {
                              player_id} cannot upgrade: Not their turn (current: {current_player.id})")
            return False

        if own_card.ctype != 'monster' or target_card.ctype != 'monster':
            self.logger.debug(f"[RULE] {player_id} cannot upgrade: Cards are not monsters ({
                              own_card.ctype}, {target_card.ctype})")
            return False

        if own_card.level_star != target_card.level_star:
            self.logger.debug(f"[RULE] {player_id} cannot upgrade {own_card.name} + {target_card.name}: "
                              f"Level mismatch (Lv{own_card.level_star} vs Lv{target_card.level_star})")
            return False

        if own_card.owner_id != player_id or target_card.owner_id != player_id:
            owners = f"{own_card.owner_id}, {target_card.owner_id}"
            self.logger.debug(f"[RULE] {
                              player_id} cannot upgrade: Cards don't belong to player (owners: {owners})")
            return False

        if own_card.type != target_card.type:
            self.logger.debug(f"[RULE] {player_id} cannot upgrade {own_card.name} + {target_card.name}: "
                              f"Type mismatch ({own_card.type} vs {target_card.type})")
            return False

        if own_card_id == target_card_id:
            self.logger.debug(
                f"[RULE] {player_id} cannot upgrade: Same card instance")
            return False

        self.logger.debug(f"[RULE] ✓ {player_id} can upgrade {own_card.name} + {target_card.name} "
                          f"(Type: {own_card.type}, Lv{own_card.level_star} → Lv{own_card.level_star + 1})")
        return True

    def next_turn(self):
        """Advance to next turn and reset turn-based flags."""
        # Reset toggles for all players at the start of a new turn
        self.has_toggled = {
            player: False for player in self.turn_manager.players}

        self.logger.info("[RULE] Turn advanced, flags reset")
        self.turn_manager.end_turn()

    def validate_game_rules(self) -> List[str]:
        """Validate overall game rules and return any violations found."""
        violations = []

        # Check each player's state
        for player in self.game_state.players:
            info = self.game_state.player_info[player]

            # Check hand size
            hand_size = len(info["held_cards"].cards)
            if hand_size > self.max_hand_cards:
                violations.append(f"{player.name} has {
                                  hand_size} cards in hand (max: {self.max_hand_cards})")

            # Check field card count
            field_count = len(self.game_state.get_player_cards(player))
            if field_count > 10:
                violations.append(f"{player.name} has {
                                  field_count} cards on field (max: 10)")

            # Validate card positions
            for card in self.game_state.get_player_cards(player):
                if card.pos_in_matrix is None:
                    violations.append(
                        f"{card.name} on field but pos_in_matrix is None")
                else:
                    row, col = card.pos_in_matrix
                    field_card = self.game_state.field_matrix[row][col]
                    if field_card != card:
                        violations.append(f"{card.name} position mismatch: reports {
                                          card.pos_in_matrix} but field has {field_card.name if field_card else 'None'}")

        if violations:
            self.logger.warning("[RULE] Game rule violations detected:")
            for violation in violations:
                self.logger.warning(f"  - {violation}")

        return violations

    def get_attack_traps(self, attacker_id: str, defender_id: str) -> List[Tuple[str, dict]]:
        """Identify traps that can be triggered by an attack.

        Returns list of (trap_id, context_dict) tuples where context includes:
        - trigger_type: 'attack'
        - attacker_id: the attacking card's owner
        - target_id: the defending card/player
        """
        defender_cards = self.game_state.get_player_cards(defender_id)
        triggerable = []

        for card in defender_cards:
            # Bypass if the trap is already triggered or card is not a trap
            if card.ctype != "trap" or card.is_trigger:
                continue

            # Traps that trigger on attack
            if card.ability in ["debuff_enemy_atk", "debuff_enemy_def", "dodge_attack", "reflect_attack"]:
                triggerable.append(
                    (card.id, attacker_id, ActivateCondition.ATTACK))

        return triggerable

    def get_summon_traps(self, summoned_card_id: str) -> List[Tuple[str, dict]]:
        """Identify traps that can be triggered by a card summon.

        Returns list of (trap_id, context_dict) tuples where context includes:
        - trigger_type: 'summon'
        - summoned_card_id: the card that was summoned
        """
        summoned_card = self.game_state.get_card_by_id(summoned_card_id)
        if not summoned_card or summoned_card.ctype != "monster":
            return []

        triggerable = []
        opponents_ids = [
            pid for pid in self.game_state.player_info.keys()
            if pid != summoned_card.owner_id
        ]

        for opponent_id in opponents_ids:
            opponent_cards = self.game_state.get_player_cards(opponent_id)
            for card in opponent_cards:
                if card.ctype != "trap" or card.is_trigger:
                    continue

                # Traps that trigger on summon
                if card.ability == "debuff_summon":
                    triggerable.append(
                        (card.id, summoned_card_id, ActivateCondition.SUMMON))

        return triggerable

    def get_toggle_traps(self, toggled_card_id: str) -> List[Tuple[str, dict]]:
        """Identify traps that can be triggered by a card toggle.

        Returns list of (trap_id, context_dict) tuples where context includes:
        - trigger_type: 'toggle'
        - toggled_card_id: the card that was toggled
        """
        toggled_card = self.game_state.get_card_by_id(toggled_card_id)
        if not toggled_card or toggled_card.ctype != "monster":
            return []

        # Only trigger if toggled to defense mode
        if toggled_card.mode != "defense":
            return []

        triggerable = []
        opponents_ids = [
            pid for pid in self.game_state.player_info.keys()
            if pid != toggled_card.owner_id
        ]

        for opponent_id in opponents_ids:
            opponent_cards = self.game_state.get_player_cards(opponent_id)
            for card in opponent_cards:
                if card.ctype != "trap" or card.is_trigger:
                    continue

                # Traps that trigger on toggle to defense
                if card.ability == "debuff_defend_toggle":
                    triggerable.append(
                        (card.id, toggled_card_id, ActivateCondition.TOGGLE))

        return triggerable
