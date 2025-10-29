from pathlib import Path
from core.cards.spell_card import SpellCard
from core.factory.card_registry import CardRegistry  # the shared registry


class SpellFactory:
    DATA_FILE = Path("./assets/data/spellInfo.json")

    def build(self):
        CardRegistry.build_from_file(
            card_type="spell",
            path=self.DATA_FILE,
            CardClass=SpellCard
        )

    def load(self, owner_id: str, name: str | None = None):
        return CardRegistry.create("spell", owner_id=owner_id, name=name)

    def get_cards(self):
        return CardRegistry.list_cards("spell")
