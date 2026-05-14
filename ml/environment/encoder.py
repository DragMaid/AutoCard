from __future__ import annotations

import numpy as np
from functools import lru_cache
from core.cards.trap_card import TrapCard, TrapAbility, ActivateCondition
from core.cards.spell_card import SpellCard, SpellAbility
from core.cards.monster_card import MonsterCard, MonsterType, CardMode
from core.config import config
from typing import TYPE_CHECKING, List, Any, Type
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
    values: List[float] | None,
    durations: List[int] | None,
    enum_cls: Type,
    value_norm: float = config.VALUE_NORM,
    duration_norm: float = config.DURATION_NORM,
) -> np.ndarray:
    enum_size = len(enum_cls)
    max_effects = config.MAX_EFFECTS

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
        else:
            effect_type = 3

        a_idx = enum_index(enum_cls, ability)
        if a_idx != -1:
            out[i, :enum_size] = one_hot(a_idx, enum_size)

        out[i, enum_size + 0] = normalize(value, value_norm)
        out[i, enum_size + 1] = normalize(duration, duration_norm)
        out[i, enum_size + 2] = effect_type

    return out.flatten()


def encode_monster_specific(card: MonsterCard | None) -> np.ndarray:
    """Encodes features specific to monster cards."""
    dim = len(MonsterType) + len(CardMode) + 4
    if card is None:
        return np.zeros(dim, dtype=np.float32)

    return np.concatenate([
        one_hot(enum_index(MonsterType, card.monster_type), len(MonsterType)),
        one_hot(enum_index(CardMode, card.mode), len(CardMode)),
        np.array([
            normalize(card.attack, config.MAX_ATTACK),
            normalize(card.defend, config.MAX_DEFEND),
            normalize(card.star, config.MAX_STAR),
            float(card.has_attacked),
        ], dtype=np.float32)
    ])


def encode_spell_specific(card: SpellCard | None) -> np.ndarray:
    """Encodes features specific to spell cards."""
    dim = config.MAX_EFFECTS * (len(SpellAbility) + 3)
    if card is None:
        return np.zeros(dim, dtype=np.float32)

    return encode_effects(
        card.abilities,
        card.effectiveness,
        card.duration,
        SpellAbility,
    )


def encode_trap_specific(card: TrapCard | None) -> np.ndarray:
    """Encodes features specific to trap cards."""
    dim = config.MAX_EFFECTS * (len(TrapAbility) + 3) + \
        len(ActivateCondition) + 2
    if card is None:
        return np.zeros(dim, dtype=np.float32)

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


def encode_card(card: LogicCard | None, player_id: str) -> np.ndarray:
    """
    Fully structured per-card encoding with shared padded specific section.
    """
    total_dim = get_card_feature_dim()
    if card is None:
        return np.zeros(total_dim, dtype=np.float32)

    # 1. Common features (Existence, Type, Status)
    common = np.concatenate([
        np.array([1.0], dtype=np.float32),  # Existence bit
        one_hot(enum_index(CardType, card.card_type), len(CardType)),
        np.array([
            float(card.is_face_down),
            float(card.owner_id != player_id),
            float(card.is_placed),
        ], dtype=np.float32)
    ])

    # 2. Specific features based on card type
    if isinstance(card, MonsterCard):
        specific = encode_monster_specific(card)
    elif isinstance(card, SpellCard):
        specific = encode_spell_specific(card)
    elif isinstance(card, TrapCard):
        specific = encode_trap_specific(card)
    else:
        specific = np.array([], dtype=np.float32)

    # 3. Pad specific section to maximum dimension
    max_spec = get_max_specific_dim()
    padded_specific = np.zeros(max_spec, dtype=np.float32)
    padded_specific[:len(specific)] = specific

    return np.concatenate([common, padded_specific])


@lru_cache(maxsize=1)
def get_card_feature_dim() -> int:
    """Calculates the total dimension of a single encoded card."""
    # 1 (existence) + len(CardType) + 3 (status) + max_specific
    common_dim = 1 + len(CardType) + 3
    return common_dim + get_max_specific_dim()


def encode_player_features(gs: GameState, player: Player) -> np.ndarray:
    pinfo = gs.player_info[player.id]
    hand_card_ids = pinfo.held_cards.card_ids
    return np.array([
        normalize(player.life_points, config.MAX_LIFE_POINTS),
        normalize(len(hand_card_ids), config.MAX_HAND_CARDS),
        float(pinfo.has_summoned_trap),
        float(pinfo.has_summoned_monster),
    ], dtype=np.float32)


def encode_hand(gs: GameState, player_id: str) -> np.ndarray:
    hand_card_ids = gs.player_info[player_id].held_cards.card_ids
    card_dim = get_card_feature_dim()
    hand_encoded = np.zeros(config.MAX_HAND_CARDS * card_dim, dtype=np.float32)

    for i, card_id in enumerate(hand_card_ids[:config.MAX_HAND_CARDS]):
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
        config.ROWS * config.COLS * card_dim, dtype=np.float32)

    idx = 0
    for row in board:
        for card_id in row:
            if card_id:
                card = gs.get_card_by_id(card_id)
                if card:
                    encoded = encode_card(card, player_id)
                    board_encoded[idx * card_dim: (idx + 1) * card_dim] = encoded
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
        config.MAX_HAND_CARDS * card_dim,
        dtype=np.float32
    )

    for i in range(config.MAX_HAND_CARDS):
        if i >= len(hand_card_ids):
            break

        card = gs.get_card_by_id(hand_card_ids[i])
        if card is None:
            continue

        encoded = encode_card(card, player_id)

        start = i * card_dim
        hand_encoded[start:start + card_dim] = encoded

    board_encoded = np.zeros(
        config.ROWS * config.COLS * card_dim,
        dtype=np.float32
    )

    idx = 0
    for r in range(config.ROWS):
        for c in range(config.COLS):
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
