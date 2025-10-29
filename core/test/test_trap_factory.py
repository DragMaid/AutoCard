from core.cards.trap_card import TrapCard
from core.factory.trap_factory import TrapFactory
from core.player import Player


def test_trap_factory():
    factory = TrapFactory()
    factory.build()

    cards = factory.get_cards()
    assert cards is not None
    assert len(cards) > 0

    player = Player(0, "Tester")

    # Load a specific trap
    sample_name = list(cards.keys())[0]
    trap = factory.load(player, name=sample_name)
    assert isinstance(trap, TrapCard)
    assert trap.owner == player

    # Load random trap
    random_trap = factory.load(player)
    assert isinstance(random_trap, TrapCard)
