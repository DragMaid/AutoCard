import numpy as np
from typing import Any, List
from core.config import config
from .utils import card_type_to_int, ability_to_float


def encode_player_features(player: Any) -> np.ndarray:
    """Encodes basic player features.

    Args:
        player: The player object to encode.

    Returns:
        A 1D numpy array containing normalized life points.
    """
    return np.array([player.life_points / player.max_life_points], dtype=np.float32)


def encode_hand(env: Any, player: Any) -> np.ndarray:
    """Encodes the cards in a player's hand.

    Args:
        env: The game environment.
        player: The player whose hand to encode.

    Returns:
        A 1D numpy array containing encoded hand card features.
    """
    gs = env.engine.game_state
    hand_card_ids = gs.player_info[player.id].held_cards.card_ids
    max_hand = config.MAX_HAND_CARDS
    card_features = config.CARD_FEATURES
    max_stats = env.reward_calculator.max_stats

    hand_encoded = np.zeros(max_hand * card_features, dtype=np.float32)
    for i, card_id in enumerate(hand_card_ids[:max_hand]):
        card = gs.get_card_by_id(card_id)
        if not card:
            continue
        base = i * card_features
        hand_encoded[base + 0] = card_type_to_int(card)
        hand_encoded[base + 1] = getattr(card, "attack", 0) / max_stats
        hand_encoded[base + 2] = getattr(card, "defend", 0) / max_stats
        # Reserved for owner flag in hand (always 0)
        hand_encoded[base + 3] = 0
        hand_encoded[base + 4] = ability_to_float(card)
        hand_encoded[base + 5] = 1 if card.is_face_down else 0
    return hand_encoded


def encode_board(env: Any, player: Any) -> np.ndarray:
    """Encodes the state of the game board.

    Args:
        env: The game environment.
        player: The player whose perspective to use for board ownership.

    Returns:
        A 1D numpy array containing encoded board features.
    """
    gs = env.engine.game_state
    board = gs.field_matrix
    card_features = config.CARD_FEATURES
    max_stats = env.reward_calculator.max_stats

    board_encoded: List[float] = []
    for row in board:
        for card_id in row:
            if card_id:
                card = gs.get_card_by_id(card_id)
                owner_flag = 0 if card.owner_id == player.id else 1
                board_encoded.extend([
                    card_type_to_int(card),
                    getattr(card, "attack", 0) / max_stats,
                    getattr(card, "defend", 0) / max_stats,
                    owner_flag,
                    ability_to_float(card),
                    1 if card.is_face_down else 0,
                ])
            else:
                board_encoded.extend([0.0] * card_features)
    return np.array(board_encoded, dtype=np.float32)
