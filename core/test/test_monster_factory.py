from core.cards.monster_card import MonsterCard
from core.factory.monster_factory import MonsterFactory
from core.data.player import Player
from core.utils import load_by_type_and_level


def test_monster_factory_build_and_load() -> None:
    """Tests building and loading monsters via MonsterFactory."""
    factory = MonsterFactory()
    factory.build()  # load JSON

    # Check that cards are indexed
    cards = factory.get_cards()
    assert cards is not None
    assert len(cards) > 0

    # Create a dummy player
    player = Player(player_index=0, name="Tester")

    # Load a specific monster
    sample_name = list(cards.keys())[0]
    monster = factory.load(player.id, name=sample_name)
    assert isinstance(monster, MonsterCard)
    assert monster.owner_id == player.id

    # Load a random monster
    random_monster = factory.load(player.id)
    assert isinstance(random_monster, MonsterCard)

    # Load by type and level
    sample_info = list(cards.values())[0]
    monster_type = sample_info["monster_type"]
    level = sample_info["star"]
    m = load_by_type_and_level(factory, player.id, monster_type, level)
    assert isinstance(m, MonsterCard)
    assert m.star == level
    assert m.monster_type.value == monster_type.upper().replace(" ", "_")
