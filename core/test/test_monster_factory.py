from core.cards.monster_card import MonsterCard
from core.factory.monster_factory import MonsterFactory
from core.player import Player


def test_monster_factory_build_and_load():
    factory = MonsterFactory()
    factory.build()  # load JSON

    # Check that cards are indexed
    cards = factory.get_cards()
    assert cards is not None
    assert len(cards) > 0

    # Create a dummy player
    player = Player(0, "Tester")

    # Load a specific monster
    sample_name = list(cards.keys())[0]
    monster = factory.load(player, name=sample_name)
    assert isinstance(monster, MonsterCard)
    assert monster.owner == player

    # Load a random monster
    random_monster = factory.load(player)
    assert isinstance(random_monster, MonsterCard)

    # Load by type and level
    monster_type = list(cards.values())[0]["type"]
    level = list(cards.values())[0]["level_star"]
    m = factory.load_by_type_and_level(player, monster_type, level)
    assert isinstance(m, MonsterCard)
    assert m.level_star == level
    assert m.type == monster_type
