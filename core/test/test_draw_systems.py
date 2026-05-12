# tests/test_draw_system.py
from collections import Counter

import pytest

from core.cards.card import CardType
from core.factory.draw_system import DrawSystem


@pytest.fixture(scope="module")
def draw_system() -> DrawSystem:
    """
    Shared DrawSystem instance for all tests.
    """
    return DrawSystem()


@pytest.fixture
def player_id() -> str:
    """
    Dummy player ID used for card creation.
    """
    return "test_player"


def test_draw_returns_card(draw_system: DrawSystem, player_id: str):
    """
    Ensures draw() always returns a valid card.
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


def test_card_type_distribution(draw_system: DrawSystem):
    """
    Ensures weighted category distribution is approximately correct.
    """
    iterations = 10_000
    counts = Counter()

    for _ in range(iterations):
        category = draw_system._weighted_choice(
            draw_system.CARD_TYPE_WEIGHTS
        )
        counts[category] += 1

    monster_ratio = counts[CardType.MONSTER] / iterations
    spell_ratio = counts[CardType.SPELL] / iterations
    trap_ratio = counts[CardType.TRAP] / iterations

    # Expected:
    # monster = 0.50
    # spell   = 0.30
    # trap    = 0.20

    assert 0.45 <= monster_ratio <= 0.55
    assert 0.25 <= spell_ratio <= 0.35
    assert 0.15 <= trap_ratio <= 0.25


def test_monster_level_distribution(draw_system: DrawSystem):
    """
    Ensures monster level weights roughly match expectations.
    """
    iterations = 20_000
    counts = Counter()

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
):
    """
    Ensures returned cards have valid CardType values.
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
):
    """
    Ensures empty weighted tables raise ValueError.
    """
    with pytest.raises(ValueError):
        draw_system._weighted_choice({})


def test_weighted_choice_falls_back_on_invalid_weights(
    draw_system: DrawSystem,
):
    """
    Ensures invalid weights do not crash selection.
    """
    table = {
        "a": "invalid",
        "b": None,
        "c": -100,
    }

    result = draw_system._weighted_choice(table)

    assert result in table
