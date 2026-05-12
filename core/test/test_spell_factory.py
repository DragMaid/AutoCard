from core.cards.spell_card import SpellCard
from core.factory.spell_factory import SpellFactory
from core.data.player import Player


def test_spell_factory():
    factory = SpellFactory()
    factory.build()

    cards = factory.get_cards()
    assert cards is not None
    assert len(cards) > 0

    player = Player(0, "Tester")

    # Load a specific spell
    sample_name = list(cards.keys())[0]
    spell = factory.load(player.id, name=sample_name)
    assert isinstance(spell, SpellCard)
    assert spell.owner_id == player.id

    # Load random spell
    random_spell = factory.load(player.id)
    assert isinstance(random_spell, SpellCard)
