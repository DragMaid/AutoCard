from __future__ import annotations
from core.config import config

import numpy as np
from functools import lru_cache

from typing import TYPE_CHECKING, List, Any, Type
from core.cards.card import CardType
from core.cards.monster_card import MonsterType, CardMode
from core.cards.spell_card import SpellAbility
from core.cards.trap_card import TrapAbility, ActivateCondition
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


def encode_card(card: LogicCard | None, player_id: str) -> np.ndarray:
    """
    Fully structured per-card encoding.
    """
    dim = get_card_feature_dim()
    if card is None:
        return np.zeros(dim, dtype=np.float32)

    features = []

    # Existence bit
    features.append(np.array([1.0], dtype=np.float32))

    # Card Type
    features.append(
        one_hot(enum_index(CardType, card.card_type), len(CardType)))

    # Status bits
    features.append(
        np.array(
            [
                float(card.is_face_down),
                float(card.owner_id != player_id),
                float(card.is_placed),
            ],
            dtype=np.float32,
        )
    )

    # Monster specific features
    if card.card_type == CardType.MONSTER:
        features.append(
            one_hot(enum_index(MonsterType, card.monster_type), len(MonsterType)))
        features.append(
            one_hot(enum_index(CardMode, card.mode), len(CardMode)))

        features.append(
            np.array(
                [
                    normalize(card.attack, config.MAX_ATTACK),
                    normalize(card.defend, config.MAX_DEFEND),
                    normalize(card.star, config.MAX_STAR),
                    float(card.has_attacked),
                ],
                dtype=np.float32,
            )
        )
    else:
        features.append(np.zeros(len(MonsterType), dtype=np.float32))
        features.append(np.zeros(len(CardMode), dtype=np.float32))
        features.append(np.zeros(4, dtype=np.float32))

    # Spell specific features
    if card.card_type == CardType.SPELL:
        features.append(
            encode_effects(
                card.abilities,
                card.effectiveness,
                card.duration,
                SpellAbility,
            )
        )
    else:
        features.append(
            np.zeros(config.MAX_EFFECTS * (len(SpellAbility) + 3), dtype=np.float32))

    # Trap specific features
    if card.card_type == CardType.TRAP:
        features.append(
            encode_effects(
                card.abilities,
                card.effectiveness,
                card.duration,
                TrapAbility,
            )
        )

        features.append(one_hot(enum_index(ActivateCondition,
                        card.activation), len(ActivateCondition)))

        features.append(
            np.array(
                [
                    float(card.is_triggered),
                    float(card.triggerable),
                ],
                dtype=np.float32,
            )
        )
    else:
        features.append(
            np.zeros(config.MAX_EFFECTS * (len(TrapAbility) + 3), dtype=np.float32))
        features.append(np.zeros(len(ActivateCondition), dtype=np.float32))
        features.append(np.zeros(2, dtype=np.float32))

    return np.concatenate(features, axis=0)


# TODO: LogicCard is a Union of MonsterCard, SpellCard, TrapCard
# Each have a different attribute size hence making the encoded
# have mismatched size when inserting into the DQN
@lru_cache(maxsize=1)
def get_card_feature_dim() -> int:
    # Use a dummy card to determine the dimension
    dummy = LogicCard(
        name="dummy",
        description="",
        card_type=CardType.MONSTER,
        owner_id="p1"
    )
    return len(encode_card(dummy, "p1"))


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


# TODO: implement attention pooling
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
                    board_encoded[idx *
                                  card_dim: (idx + 1) * card_dim] = encoded
            idx += 1

    return board_encoded


def encode_state(env: GameEnv, player_id: str) -> np.ndarray:
    """
    Encodes the entire game state from the perspective of a player.
    """
    gs = env.engine.game_state
    opponent_id = gs.get_opponent_id(player_id)

    player = gs.players_lookup[player_id]
    opponent = gs.players_lookup[opponent_id]

    features = [
        encode_player_features(gs, player),
        encode_player_features(gs, opponent),
        encode_hand(gs, player_id),
        encode_board(gs, player_id),
    ]

    return np.concatenate(features, axis=0)
