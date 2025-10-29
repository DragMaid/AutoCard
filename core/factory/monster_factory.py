import random
from pathlib import Path
from core.cards.monster_card import MonsterCard
from core.factory.card_registry import CardRegistry


class MonsterFactory:
    DATA_FILE = Path("./assets/data/monsterInfo.json")

    def build(self):
        CardRegistry.build_from_file(
            card_type="monster",
            path=self.DATA_FILE,
            CardClass=MonsterCard,
            type_field="type"
        )

    def load(self, owner_id: str, name: str | None = None):
        return CardRegistry.create("monster", owner_id=owner_id, name=name)

    def load_by_type_and_level(self, player_id: str, monster_type: str, level_star: int):
        # Filter by type and level
        candidates = [
            name for name, info in CardRegistry._registry["monster"].items()
            if info.get("type") == monster_type and info.get("level_star") == level_star
        ]
        if not candidates:
            return None
        selected_name = random.choice(candidates)
        return self.load(player_id, name=selected_name)

    def get_cards(self):
        return CardRegistry.list_cards("monster")
