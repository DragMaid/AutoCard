import logging
from core.cards.monster_card import CardMode
from core.cards.card import CardType
from core.logic.turn_manager import TurnManager
from core.data.game_state import GameState
from typing import Tuple
from core.config import Config

logger = logging.getLogger(__name__)


class RuleEngine:
    """Handles game rule logic, validation of player actions, and turn-based state updates."""

    def __init__(self, game_state: GameState, turn_manager: TurnManager) -> None:
        """Initializes the RuleEngine with the current game state and turn manager.

        Args:
            game_state (GameState): The current state of the game.
            turn_manager (TurnManager): The manager responsible for handling turn transitions.
        """
        self.turn_manager = turn_manager
        self.game_state = game_state

    def can_draw(self, player_id: str) -> bool:
        """Validates if a player is allowed to draw a card from their deck.

        Args:
            player_id (str): The ID of the player attempting to draw.

        Returns:
            bool: True if the action is valid, False otherwise.
        """
        current_player = self.turn_manager.get_current_player()
        hand_size = len(
            self.game_state.player_info[player_id].held_cards.card_ids)

        if current_player.id != player_id:
            logger.warning(
                "Draw denied",
                extra={
                    "reason": "Not player's turn yet",
                    "playerID": player_id,
                    "currentID": current_player.id
                }
            )
            return False

        if hand_size >= Config.MAX_HAND_CARDS:
            logger.warning(
                "Draw denied",
                extra={
                    "reason": "Player hand is already full",
                    "playerID": player_id,
                    "handCount": f"{hand_size} / {Config.MAX_HAND_CARDS}"
                }
            )
            return False

        return True

    def can_activate(
        self,
        player_id: str,
        trap_id: str
    ) -> bool:
        """Validates if a player is allowed to activate a trap card.

        Args:
            player_id (str): The ID of the player attempting the activation.
            trap_id (str): The ID of the trap card being activated.

        Returns:
            bool: True if the activation is valid, False otherwise.
        """
        trapper = self.turn_manager.get_trapper()
        card = self.game_state.get_card_by_id(trap_id)

        if not trapper or trapper.id != player_id:
            logger.warning(
                "Activation denied",
                extra={
                    "reason": "Not trapper's turn",
                    "playerID": player_id,
                    "cardName": card.name
                }
            )
            return False

        if trap_id not in list(self.game_state.triggerable_traps.keys()):
            logger.warning(
                "Activation denied",
                extra={
                    "reason": "Card not currently triggerable",
                    "cardName": card.name
                }
            )
            return False

        if card.owner_id != player_id:
            logger.warning(
                "Activation denied",
                extra={
                    "reason": "Card does not belong to player",
                    "playerID": player_id,
                    "cardName": card.name
                }
            )
            return False

        logger.debug(
            "Activation allowed",
            extra={
                "playerID": player_id,
                "cardName": card.name
            }
        )
        return True

    def can_summon(
        self,
        player_id: str,
        card_id: str,
        pos: Tuple[int, int]
    ) -> bool:
        """Validates if a player is allowed to summon a card to the specified field position.

        Args:
            player_id (str): The ID of the player attempting to summon.
            card_id (str): The ID of the card being summoned.
            pos (Tuple[int, int]): The target position on the field (row, column).

        Returns:
            bool: True if the summon action is valid, False otherwise.
        """
        current_player = self.turn_manager.get_current_player()
        card = self.game_state.get_card_by_id(card_id)

        if not card:
            logger.warning(
                "Summon denied",
                extra={
                    "reason": "Provided card ID does not exist",
                    "cardID": card_id
                }
            )
            return False

        # Check if it's player's turn
        if current_player.id != player_id:
            logger.warning(
                "Summon denied",
                extra={
                    "reason": "Not player's turn",
                    "playerID": player_id,
                    "cardName": card.name
                }
            )
            return False

        # Check if card is in hand
        if card_id not in self.game_state.get_player_held_card_ids(player_id):
            logger.warning(
                "Summon denied",
                extra={
                    "reason": "Card not in hand",
                    "playerID": player_id,
                    "cardName": card.name
                }
            )
            return False

        # Check summon type restrictions
        if card.card_type == CardType.MONSTER:
            if self.game_state.player_info[player_id].has_summoned_monster:
                logger.warning(
                    "Summon denied",
                    extra={
                        "reason": "Already summoned monster this turn",
                        "playerID": player_id,
                        "cardName": card.name
                    }
                )
                return False
        elif card.card_type == CardType.TRAP:
            if self.game_state.player_info[player_id].has_summoned_trap:
                logger.warning(
                    "Summon denied",
                    extra={
                        "reason": "Already summoned trap this turn",
                        "playerID": player_id,
                        "cardName": card.name
                    }
                )
                return False
        else:
            logger.warning(
                "Invalid card type for summon action",
                extra={
                    "cardName": card.name,
                    "cardType": card.card_type
                }
            )
            return False

        # Check position validity
        if pos is None:
            logger.warning(
                "Summon denied",
                extra={
                    "reason": "No slot specified",
                    "playerID": player_id,
                    "cardName": card.name,
                    "position": pos
                }
            )
            return False

        card_matrix = self.game_state.field_matrix
        ownership_matrix = self.game_state.field_matrix_ownership
        row, col = pos
        if not (0 <= row < len(card_matrix) and 0 <= col < len(card_matrix[0])):
            logger.warning(
                "Summon denied",
                extra={
                    "reason": "Position out of bounds",
                    "playerID": player_id,
                    "cardName": card.name,
                    "position": pos
                }
            )
            return False

        if card_matrix[row][col] is not None:
            existing_id = card_matrix[row][col]
            existing = self.game_state.get_card_by_id(existing_id)
            logger.warning(
                "Summon denied",
                extra={
                    "reason": "Position occupied",
                    "playerID": player_id,
                    "cardName": card.name,
                    "position": pos,
                    "existingCard": existing.name if existing else existing_id
                }
            )
            return False

        slot_owner_id = ownership_matrix[row][col]
        if slot_owner_id != player_id:
            logger.warning(
                "Summon denied",
                extra={
                    "reason": "Slot isn't owned by player",
                    "playerID": player_id,
                    "ownerID": slot_owner_id,
                    "position": pos,
                }
            )
            return False

        # Check max cards on field
        empty_count = len(self.game_state.get_empty_slots(player_id))
        if empty_count <= 0:
            logger.warning(
                "Summon denied",
                extra={
                    "reason": "Field full",
                    "playerID": player_id,
                    "cardName": card.name,
                    "remaining": empty_count
                }
            )
            return False

        logger.debug(
            "Summon allowed",
            extra={
                "playerID": player_id,
                "cardName": card.name,
                "position": pos
            }
        )
        return True

    def can_change_mode(self, player_id: str, card_id: str) -> bool:
        """Validates if a player is allowed to change the mode of a card on the field.

        Args:
            player_id (str): The ID of the player attempting to change the mode.
            card_id (str): The ID of the card being changed.

        Returns:
            bool: True if the mode change is valid, False otherwise.
        """
        current_player = self.turn_manager.get_current_player()

        if current_player.id != player_id:
            logger.warning(
                "Mode change denied",
                extra={
                    "reason": "Not player's turn",
                    "playerID": player_id
                }
            )
            return False

        if card_id not in self.game_state.get_player_field_cards(player_id):
            logger.warning(
                "Mode change denied",
                extra={
                    "reason": "Card not on field",
                    "playerID": player_id,
                    "cardID": card_id
                }
            )
            return False

        return True

    def can_attack(
        self,
        attacker_id: str,
        defender_id: str,
        card_id: str,
        target_id: str,
        target_is_player: bool = False
    ) -> bool:
        """Validates if an attack action is permitted.

        Args:
            attacker_id (str): The ID of the player initiating the attack.
            defender_id (str): The ID of the player being attacked.
            card_id (str): The ID of the card being used to attack.
            target_id (str): The ID of the target card or player.
            target_is_player (bool, optional): Whether the target is a player. Defaults to False.

        Returns:
            bool: True if the attack action is valid, False otherwise.
        """
        current_player = self.turn_manager.get_current_player()
        card = self.game_state.get_card_by_id(card_id)

        if not card:
            logger.warning(
                "Summon denied",
                extra={
                    "reason": "Provided card ID does not exist",
                    "cardID": card_id
                }
            )
            return False

        # Cannot attack on first turn
        if self.turn_manager.turn_state.turn_count == 1:
            logger.warning(
                "Attack denied",
                extra={
                    "reason": "Cannot attack on turn 1",
                    "attackerID": attacker_id,
                    "cardName": card.name
                }
            )
            return False

        # Must be attacker's turn
        if current_player.id != attacker_id:
            logger.warning(
                "Attack denied",
                extra={
                    "reason": "Not attacker's turn",
                    "attackerID": attacker_id,
                    "currentID": current_player.id
                }
            )
            return False

        # Card must belong to attacker
        if card.owner_id != attacker_id:
            logger.warning(
                "Attack denied",
                extra={
                    "reason": "Card belongs to another player",
                    "attackerID": attacker_id,
                    "cardName": card.name,
                    "ownerID": card.owner_id
                }
            )
            return False

        # Card must be in attack position
        if card.mode != CardMode.ATTACK:
            logger.warning(
                "Attack denied",
                extra={
                    "reason": "Card not in attack mode",
                    "attackerID": attacker_id,
                    "cardName": card.name,
                    "mode": card.mode
                }
            )
            return False

        # Card cannot have already attacked
        if card.has_attacked:
            logger.warning(
                "Attack denied",
                extra={
                    "reason": "Already attacked this turn",
                    "attackerID": attacker_id,
                    "cardName": card.name
                }
            )
            return False

        # If attacking a monster
        if not target_is_player:
            target = self.game_state.get_card_by_id(target_id)

            if not target:
                return False

            if target.card_type != CardType.MONSTER:
                logger.warning(
                    "Attack denied",
                    extra={
                        "reason": "Cannot attack trap card",
                        "cardName": card.name,
                        "targetName": target.name
                    }
                )
                return False

            if target.owner_id != defender_id:
                logger.warning(
                    "Attack denied",
                    extra={
                        "reason": "Target belongs to different defender",
                        "attackerID": attacker_id,
                        "targetName": target.name,
                        "defenderID": defender_id
                    }
                )
                return False
            logger.debug(
                "Attack allowed",
                extra={
                    "attackerID": attacker_id,
                    "cardName": card.name,
                    "targetName": target.name
                }
            )
            return True

        # If direct attack to player
        if target_is_player:
            # Check if defender has any monsters
            defender_cards = self.game_state.get_player_field_cards(
                defender_id)
            for def_card in defender_cards:
                if def_card.card_type == CardType.MONSTER:
                    logger.warning(
                        "Direct attack denied",
                        extra={
                            "reason": "Defender has monsters on field",
                            "attackerID": attacker_id,
                            "defenderID": defender_id
                        }
                    )
                    return False

            logger.debug(
                "Direct attack allowed",
                extra={
                    "attackerID": attacker_id,
                    "defenderID": defender_id,
                    "cardName": card.name
                }
            )
            return True

        logger.warning(
            "Attack denied",
            extra={
                "reason": "Invalid target",
                "attackerID": attacker_id
            }
        )
        return False

    def can_toggle(self, player_id: str, card_id: str) -> bool:
        """Validates if a player is allowed to toggle the state of a card.

        Args:
            player_id (str): The ID of the player attempting the action.
            card_id (str): The ID of the card being toggled.

        Returns:
            bool: True if the toggle is valid, False otherwise.
        """
        current_player = self.turn_manager.get_current_player()
        card = self.game_state.get_card_by_id(card_id)

        if not card:
            logger.warning(
                "Summon denied",
                extra={
                    "reason": "Provided card ID does not exist",
                    "cardID": card_id
                }
            )
            return False

        if current_player.id != player_id:
            logger.warning(
                "Toggle denied",
                extra={
                    "reason": "Not player's turn",
                    "playerID": player_id,
                    "cardName": card.name
                }
            )
            return False

        if card.owner_id != player_id:
            logger.warning(
                "Toggle denied",
                extra={
                    "reason": "Card belongs to another player",
                    "playerID": player_id,
                    "cardName": card.name,
                    "ownerID": card.owner_id
                }
            )
            return False

        if self.game_state.player_info[player_id].has_toggled:
            logger.warning(
                "Toggle denied",
                extra={
                    "reason": "Already toggled this turn",
                    "playerID": player_id,
                    "cardName": card.name
                }
            )
            return False

        logger.debug(
            "Toggle allowed",
            extra={
                "playerID": player_id,
                "cardName": card.name
            }
        )
        return True

    def can_upgrade(self, player_id: str, own_card_id: str, target_card_id: str) -> bool:
        """Validates if a player is allowed to upgrade a monster card.

        Args:
            player_id (str): The ID of the player initiating the upgrade.
            own_card_id (str): The ID of the player's card to be used for the upgrade.
            target_card_id (str): The ID of the target monster card.

        Returns:
            bool: True if the upgrade is valid, False otherwise.
        """
        current_player = self.turn_manager.get_current_player()
        own_card = self.game_state.get_card_by_id(own_card_id)
        target_card = self.game_state.get_card_by_id(target_card_id)

        if not own_card or not target_card:
            logger.warning(
                "Upgrade denied",
                extra={
                    "reason": "Either owned card or target card could not be found",
                    "playerID": player_id,
                    "ownCard": f"{own_card_id}: {own_card}",
                    "targetCard": f"{target_card_id}: {target_card}"
                }
            )
            return False

        if current_player.id != player_id:
            logger.warning(
                "Upgrade denied",
                extra={
                    "reason": "Not player's turn",
                    "playerID": player_id,
                    "currentID": current_player.id
                }
            )
            return False

        if own_card.card_type != CardType.MONSTER \
                or target_card.card_type != CardType.MONSTER:
            logger.warning(
                "Upgrade denied",
                extra={
                    "reason": "Cards are not monsters",
                    "playerID": player_id,
                    "card1Type": own_card.card_type,
                    "card2Type": target_card.card_type
                }
            )
            return False

        if own_card.star != target_card.star:
            logger.warning(
                "Upgrade denied",
                extra={
                    "reason": "Level mismatch",
                    "playerID": player_id,
                    "ownCard": own_card.name,
                    "targetCard": target_card.name,
                    "ownLevel": own_card.star,
                    "targetLevel": target_card.star
                }
            )
            return False

        if own_card.owner_id != player_id or target_card.owner_id != player_id:
            logger.warning(
                "Upgrade denied",
                extra={
                    "reason": "Cards don't belong to player",
                    "playerID": player_id,
                    "ownOwner": own_card.owner_id,
                    "targetOwner": target_card.owner_id
                }
            )
            return False

        if own_card.card_type != target_card.card_type:
            logger.warning(
                "Upgrade denied",
                extra={
                    "reason": "Type mismatch",
                    "playerID": player_id,
                    "ownCard": own_card.name,
                    "targetCard": target_card.name,
                    "ownType": own_card.card_type,
                    "targetType": target_card.card_type
                }
            )
            return False

        if own_card_id == target_card_id:
            logger.warning(
                "Upgrade denied",
                extra={
                    "reason": "Same card instance",
                    "playerID": player_id
                }
            )
            return False

        logger.debug(
            "Upgrade allowed",
            extra={
                "playerID": player_id,
                "ownCard": own_card.name,
                "targetCard": target_card.name,
                "type": own_card.monster_type,
                "oldLevel": own_card.star,
                "newLevel": own_card.star + 1
            }
        )
        return True
