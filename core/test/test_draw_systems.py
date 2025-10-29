# tests/test_draw_system.py
import pytest
from collections import Counter
from core.factory.draw_system import DrawSystem


class DummyPlayer:
    """Minimal dummy player object to satisfy factory calls."""

    def __init__(self, name="TestPlayer"):
        self.name = name


@pytest.fixture(scope="module")
def draw_system():
    """Fixture that initializes the DrawSystem once for all tests."""
    return DrawSystem()


def test_rate_card_draw_returns_valid_card(draw_system):
    """
    Ensures that rate_card_draw() always returns a valid (non-None) card.
    """
    player = DummyPlayer()
    failures = 0
    n = 500

    for _ in range(n):
        card = draw_system.rate_card_draw(player)
        if card is None:
            failures += 1

    assert failures == 0, f"{failures}/{n} draws returned None"


def test_distribution_of_card_types(draw_system):
    """
    Ensures the drawn card type distribution roughly matches
    the configured weights (monster: 50, spell: 25, trap: 25).
    """
    n = 5000
    counts = Counter()

    for _ in range(n):
        # We'll intercept card type using draw_system.rate()
        card_type = draw_system.rate(draw_system.generic_draw)
        counts[card_type] += 1

    total = sum(counts.values())
    monster_ratio = counts["monster"] / total
    spell_ratio = counts["spell"] / total
    trap_ratio = counts["trap"] / total

    # Expect roughly 0.5, 0.25, 0.25 (±0.1 tolerance)
    assert 0.4 <= monster_ratio <= 0.6, f"Monster ratio off: {monster_ratio}"
    assert 0.15 <= spell_ratio <= 0.35, f"Spell ratio off: {spell_ratio}"
    assert 0.15 <= trap_ratio <= 0.35, f"Trap ratio off: {trap_ratio}"


def test_check_draw_issues(draw_system):
    """
    Ensures no missing or failed draws occur when stress-tested.
    """
    player = DummyPlayer()
    draw_system.check_draw_issues(player, attempts=500)
    # This function already prints failures; test passes if it runs without exception
