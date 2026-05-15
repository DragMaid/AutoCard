from __future__ import annotations

import numpy as np
from functools import lru_cache
from core.cards.trap_card import TrapCard, TrapAbility, ActivateCondition
from core.cards.spell_card import SpellCard, SpellAbility
from core.cards.monster_card import MonsterCard, MonsterType, CardMode
from core.config import Config
from typing import TYPE_CHECKING, List, Any, Type, Optional
from core.cards.card import CardType
from core.data.player import Player
from core.data.game_state import LogicCard, GameState

if TYPE_CHECKING:
    from .environment import GameEnv


def one_hot(index: int, size: int) -> np.ndarray:
    vec = np.zeros(size, dtype=np.float32)
    if 0 <= index < size:
        vec[index] = 1.0
    return vec


def normalize(x: float, max_value: float) -> float:
    return float(x) / max_value if max_value else 0.0


def enum_index(enum_cls: Type, value: Any) -> int:
    try:
        return list(enum_cls).index(value)
    except ValueError:
        return -1


def encode_effects(
    abilities: List[Any],
    values: Optional[List[float]],
    durations: Optional[List[int]],
    enum_cls: Type,
    value_norm: float = Config.VALUE_NORM,
    duration_norm: float = Config.DURATION_NORM,
) -> np.ndarray:
    enum_size = len(enum_cls)
    max_effects = Config.MAX_EFFECTS

    # Each effect: one-hot(ability) + value + duration + effect_type
    out = np.zeros(
        (max_effects, enum_size + 3),
        dtype=np.float32,
    )

    for i in range(min(len(abilities), max_effects)):
        ability = abilities[i]

        has_value = values is not None and i < len(values)
        has_duration = durations is not None and i < len(durations)

        value = values[i] if has_value else 0.0
        duration = durations[i] if has_duration else 0.0

        # Determine effect type: 1 scalar, 2 trigger-only, 3 hybrid
        if not has_value and not has_duration:
            effect_type = 2
        elif has_value or has_duration:
            effect_type = 1
        # This kinda do nothing, just for future references
        else:
            effect_type = 3

        a_idx = enum_index(enum_cls, ability)
        if a_idx != -1:
            out[i, :enum_size] = one_hot(a_idx, enum_size)

        # Output a 2D dimension
        out[i, enum_size + 0] = normalize(value, value_norm)
        out[i, enum_size + 1] = normalize(duration, duration_norm)
        out[i, enum_size + 2] = effect_type

    return out.flatten()


def encode_monster_specific(card: Optional[MonsterCard]) -> np.ndarray:
    """Encodes features specific to monster cards."""
    dim = len(MonsterType) + len(CardMode) + 4
    if card is None:
        return np.zeros(dim, dtype=np.float32)

    return np.concatenate([
        one_hot(enum_index(MonsterType, card.monster_type), len(MonsterType)),
        one_hot(enum_index(CardMode, card.mode), len(CardMode)),
        np.array([
            normalize(card.attack, Config.MAX_ATTACK),
            normalize(card.defend, Config.MAX_DEFEND),
            normalize(card.star, Config.MAX_STAR),
            float(card.has_attacked),
        ], dtype=np.float32)
    ])


def encode_spell_specific(card: Optional[SpellCard]) -> np.ndarray:
    """Encodes features specific to spell cards."""
    dim = Config.MAX_EFFECTS * (len(SpellAbility) + 3)
    if card is None:
        return np.zeros(dim, dtype=np.float32)

    return encode_effects(
        card.abilities,
        card.effectiveness,
        card.duration,
        SpellAbility,
    )


def encode_trap_specific(card: Optional[TrapCard], hide: bool = False) -> np.ndarray:
    """Encodes features specific to trap cards."""
    dim = Config.MAX_EFFECTS * (len(TrapAbility) + 3) + \
        len(ActivateCondition) + 2

    # If there is not card or the card is still in hidden phase
    # and it also belongs to the opponent
    if card is None:
        return np.zeros(dim, dtype=np.float32)

    if hide:
        # Hide all information except whether card was triggered
        encoded = np.zeros(dim, dtype=np.float32)
        encoded[-2] = float(card.is_triggered)
        encoded[-1] = float(card.triggerable)
        return encoded

    return np.concatenate([
        encode_effects(
            card.abilities,
            card.effectiveness,
            card.duration,
            TrapAbility,
        ),
        one_hot(enum_index(ActivateCondition,
                card.activation), len(ActivateCondition)),
        np.array([
            float(card.is_triggered),
            float(card.triggerable),
        ], dtype=np.float32)
    ])


@lru_cache(maxsize=1)
def get_max_specific_dim() -> int:
    """Calculates the maximum dimension of card-type specific features."""
    return max(
        len(encode_monster_specific(None)),
        len(encode_spell_specific(None)),
        len(encode_trap_specific(None))
    )


@lru_cache(maxsize=1)
def get_common_card_dim() -> int:
    """Calculates the dimension of common card features."""
    return 1 + len(CardType) + 3


def encode_card_common(card: LogicCard, player_id: str) -> np.ndarray:
    common = np.concatenate([
        np.array([1.0], dtype=np.float32),  # Existence bit
        one_hot(enum_index(CardType, card.card_type), len(CardType)),
        np.array([
            float(card.is_face_down),
            float(card.owner_id != player_id),
            float(card.is_placed),
        ], dtype=np.float32)
    ])
    return common


def encode_card(card: Optional[LogicCard], player_id: str) -> np.ndarray:
    """
    Fully structured per-card encoding with shared padded specific section.
    """
    total_dim = get_card_feature_dim()
    if card is None:
        return np.zeros(total_dim, dtype=np.float32)

    common = encode_card_common(card, player_id)

    # Only show trap card info if its triggered or the person owns it
    is_opponent = card.owner_id != player_id
    hidden = getattr(card, "is_triggered", False) or not is_opponent
    type_to_encoder = {
        CardType.MONSTER: encode_monster_specific,
        CardType.TRAP: lambda c: encode_trap_specific(c, hide=hidden),
        CardType.SPELL: encode_spell_specific
    }

    encoded = type_to_encoder[card.card_type](card)

    # Pad specific section to maximum dimension
    max_spec = get_max_specific_dim()
    padded_specific = np.zeros(max_spec, dtype=np.float32)
    padded_specific[:len(encoded)] = encoded

    return np.concatenate([common, padded_specific])


@lru_cache(maxsize=1)
def get_card_feature_dim() -> int:
    """Calculates the total dimension of a single encoded card."""
    return get_common_card_dim() + get_max_specific_dim()


PLAYER_FEATURE_EXTRACTORS = [
    lambda gs, p: normalize(p.life_points, Config.MAX_LIFE_POINTS),
    lambda gs, p: normalize(
        len(gs.player_info[p.id].held_cards.card_ids), Config.MAX_HAND_CARDS),
    lambda gs, p: float(gs.player_info[p.id].has_summoned_trap),
    lambda gs, p: float(gs.player_info[p.id].has_summoned_monster),
]


@lru_cache(maxsize=1)
def get_player_feature_dim() -> int:
    return len(PLAYER_FEATURE_EXTRACTORS)


def encode_player_features(gs: GameState, player: Player) -> np.ndarray:
    return np.array([f(gs, player) for f in PLAYER_FEATURE_EXTRACTORS], dtype=np.float32)


def encode_hand(gs: GameState, player_id: str) -> np.ndarray:
    hand_card_ids = gs.player_info[player_id].held_cards.card_ids
    card_dim = get_card_feature_dim()
    hand_encoded = np.zeros(Config.MAX_HAND_CARDS * card_dim, dtype=np.float32)

    for i, card_id in enumerate(hand_card_ids[:Config.MAX_HAND_CARDS]):
        card = gs.get_card_by_id(card_id)
        if card:
            encoded = encode_card(card, player_id)
            hand_encoded[i * card_dim: (i + 1) * card_dim] = encoded

    return hand_encoded


def encode_board(gs: GameState, player_id: str) -> np.ndarray:
    board = gs.field_matrix
    card_dim = get_card_feature_dim()
    # Matrix is ROWS x COLS
    board_encoded = np.zeros(
        Config.ROWS * Config.COLS * card_dim, dtype=np.float32)

    idx = 0
    for row in board:
        for card_id in row:
            if card_id:
                card = gs.get_card_by_id(card_id)
                if card:
                    encoded = encode_card(card, player_id)
                    board_encoded[idx *
                                  card_dim: (idx + 1) * card_dim] = encoded
            idx += 1

    return board_encoded


def encode_state(env: GameEnv, player_id: str) -> np.ndarray:
    """
    Encodes the full game state in a format compatible with GameStateEncoder.
    Layout MUST match:
    [player_feats | hand_cards | board_cards]
    """

    gs = env.engine.game_state

    player = gs.players_lookup[player_id]
    opponent_id = gs.get_opponent_id(player_id)
    opponent = gs.players_lookup[opponent_id]

    player_feats = np.concatenate([
        encode_player_features(gs, player),
        encode_player_features(gs, opponent),
    ], axis=0)

    hand_card_ids = gs.player_info[player_id].held_cards.card_ids
    card_dim = get_card_feature_dim()

    hand_encoded = np.zeros(
        Config.MAX_HAND_CARDS * card_dim,
        dtype=np.float32
    )

    for i in range(Config.MAX_HAND_CARDS):
        if i >= len(hand_card_ids):
            break

        card = gs.get_card_by_id(hand_card_ids[i])
        if card is None:
            continue

        encoded = encode_card(card, player_id)

        start = i * card_dim
        hand_encoded[start:start + card_dim] = encoded

    board_encoded = np.zeros(
        Config.ROWS * Config.COLS * card_dim,
        dtype=np.float32
    )

    idx = 0
    for r in range(Config.ROWS):
        for c in range(Config.COLS):
            card_id = gs.field_matrix[r][c]

            if card_id:
                card = gs.get_card_by_id(card_id)
                if card:
                    encoded = encode_card(card, player_id)
                    start = idx * card_dim
                    board_encoded[start:start + card_dim] = encoded

            idx += 1

    return np.concatenate([
        player_feats,
        hand_encoded,
        board_encoded
    ], axis=0)
