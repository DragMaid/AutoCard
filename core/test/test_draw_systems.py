# tests/test_draw_system.py
from collections import Counter
from typing import Counter as TypingCounter

import pytest

from core.cards.card import CardType
from core.factory.draw_system import DrawSystem


@pytest.fixture(scope="module")
def draw_system() -> DrawSystem:
    """Fixture for shared DrawSystem instance.

    Returns:
        A DrawSystem instance.
    """
    return DrawSystem()


@pytest.fixture
def player_id() -> str:
    """Fixture for dummy player ID.

    Returns:
        A test player ID.
    """
    return "test_player"


def test_draw_returns_card(draw_system: DrawSystem, player_id: str) -> None:
    """Verifies draw() returns a valid card.

    Args:
        draw_system: The shared DrawSystem instance.
        player_id: The ID of the player drawing the card.
    """
    draws = 500
    failures = []

    for i in range(draws):
        card = draw_system.draw(player_id)

        if card is None:
            failures.append(i)

    assert not failures, (
        f"{len(failures)}/{draws} draws returned None. "
        f"Failed indices: {failures[:10]}"
    )


def test_card_type_distribution(draw_system: DrawSystem) -> None:
    """Verifies weighted card category distribution.

    Args:
        draw_system: The shared DrawSystem instance.
    """
    iterations = 10_000
    counts: TypingCounter[CardType] = Counter()

    for _ in range(iterations):
        category = draw_system._weighted_choice(
            draw_system.CARD_TYPE_WEIGHTS
        )
        counts[category] += 1

    monster_ratio = counts[CardType.MONSTER] / iterations
    spell_ratio = counts[CardType.SPELL] / iterations
    trap_ratio = counts[CardType.TRAP] / iterations

    assert 0.45 <= monster_ratio <= 0.55
    assert 0.25 <= spell_ratio <= 0.35
    assert 0.15 <= trap_ratio <= 0.25


def test_monster_level_distribution(draw_system: DrawSystem) -> None:
    """Verifies monster level weights match expectations.

    Args:
        draw_system: The shared DrawSystem instance.
    """
    iterations = 20_000
    counts: TypingCounter[int] = Counter()

    table = draw_system.DRAW_TABLES[CardType.MONSTER]

    for _ in range(iterations):
        level = draw_system._weighted_choice(table)
        counts[level] += 1

    level_1_ratio = counts[1] / iterations
    level_2_ratio = counts[2] / iterations
    level_3_ratio = counts[3] / iterations
    level_4_ratio = counts[4] / iterations

    assert 0.68 <= level_1_ratio <= 0.80
    assert 0.15 <= level_2_ratio <= 0.25
    assert 0.03 <= level_3_ratio <= 0.07
    assert 0.00 <= level_4_ratio <= 0.03


def test_draw_returns_expected_card_types(
    draw_system: DrawSystem,
    player_id: str,
) -> None:
    """Verifies returned cards have valid CardType.

    Args:
        draw_system: The shared DrawSystem instance.
        player_id: The ID of the player drawing the card.
    """
    valid_types = {
        CardType.MONSTER,
        CardType.SPELL,
        CardType.TRAP,
    }

    for _ in range(500):
        card = draw_system.draw(player_id)

        assert card is not None
        assert hasattr(card, "card_type")
        assert card.card_type in valid_types


def test_weighted_choice_rejects_empty_table(
    draw_system: DrawSystem,
) -> None:
    """Verifies empty weighted tables raise ValueError.

    Args:
        draw_system: The shared DrawSystem instance.
    """
    with pytest.raises(ValueError):
        draw_system._weighted_choice({})


def test_weighted_choice_falls_back_on_invalid_weights(
    draw_system: DrawSystem,
) -> None:
    """Verifies invalid weights do not crash selection.

    Args:
        draw_system: The shared DrawSystem instance.
    """
    table = {
        "a": "invalid",
        "b": None,
        "c": -100,
    }

    result = draw_system._weighted_choice(table)

    assert result in table
