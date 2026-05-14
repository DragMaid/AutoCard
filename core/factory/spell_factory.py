import json
import random
from pathlib import Path
from typing import Optional, Dict, Any
from core.cards.spell_card import SpellCard
from core.factory.base_factory import BaseFactory
from core.factory.card_registry import CardRegistry
from core.cards.card import CardType
from core.config import config


class SpellFactory(BaseFactory):
    DATA_FILE = Path("./assets/data/spellInfo.json")

    def __init__(self) -> None:
        self._cards: Dict[str, Dict[str, Any]] = {}
        CardRegistry.register(CardType.SPELL, self)

    def build(self) -> None:
        """Loads spell cards from JSON (flat array)."""
        if not self.DATA_FILE.exists():
            raise FileNotFoundError(f"{self.DATA_FILE} not found")

        with open(self.DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError(
                "Unsupported JSON format for spells (expected list)")

        for card_info in data:
            image_path = str(config.ASSET_DIR / card_info["texture"].lstrip('/'))
            card_info["_image_path"] = image_path
            self._cards[card_info["name"]] = card_info

    def load(self, owner_id: str, name: Optional[str] = None) -> SpellCard:
        """Creates a SpellCard instance.

        Args:
            owner_id (str): The ID of the owner.
            name (Optional[str]): The name of the spell.

        Returns:
            SpellCard: A new SpellCard instance.

        Raises:
            ValueError: If spell not found.
        """
        if not self._cards:
            raise ValueError("Factory not built.")

        if name:
            prototype = self._cards.get(name)
            if not prototype:
                raise ValueError(f"Spell '{name}' not found.")
        else:
            prototype = random.choice(list(self._cards.values()))

        return SpellCard(
            name=prototype["name"],
            description=prototype.get("description", ""),
            owner_id=owner_id,
            image_path=prototype.get("_image_path"),
            abilities=prototype.get("abilities", []),
            effectiveness=prototype.get("effectiveness"),
            duration=prototype.get("duration")
        )

    def get_cards(self) -> Dict[str, Dict[str, Any]]:
        """Returns the spell cards dictionary.

        Returns:
            Dict[str, Dict[str, Any]]: A dictionary of spell card data.
        """
        return self._cards
