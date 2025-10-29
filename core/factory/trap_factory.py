from core.cards.trap_card import TrapCard
from pathlib import Path
from core.factory.card_registry import CardRegistry


class TrapFactory:
    DATA_FILE = Path("./assets/data/trapInfo.json")

    def build(self):
        CardRegistry.build_from_file(
            card_type="trap",
            path=self.DATA_FILE,
            CardClass=TrapCard
        )

    def load(self, owner_id: str, name: str | None = None):
        return CardRegistry.create("trap", owner_id=owner_id, name=name)

    def get_cards(self):
        return CardRegistry.list_cards("trap")
