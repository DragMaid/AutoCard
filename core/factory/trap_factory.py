import json
import random
from pathlib import Path
from typing import Optional, List

from core.cards.trap_card import TrapCard
from core.factory.base_factory import BaseFactory
from core.factory.card_registry import CardRegistry
from core.cards.card import CardType
from core.config import config


class TrapFactory(BaseFactory):
    """Factory class for creating TrapCard instances from data files."""

    DATA_FILE = Path("./assets/data/trapInfo.json")

    def __init__(self) -> None:
        """Initializes the TrapFactory and registers it with the CardRegistry."""
        self._cards: dict = {}
        CardRegistry.register(CardType.TRAP, self)

    def build(self) -> None:
        """Loads trap cards from the JSON data file."""
        if not self.DATA_FILE.exists():
            raise FileNotFoundError(f"{self.DATA_FILE} not found")

        with open(self.DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError("Unsupported JSON format for traps (expected list)")

        for card_info in data:
            image_path = str(config.ASSET_DIR / card_info["texture"].lstrip("/"))
            card_info["_image_path"] = image_path
            self._cards[card_info["name"]] = card_info

    def load(self, owner_id: str, name: Optional[str] = None) -> Optional[TrapCard]:
        """Creates a TrapCard instance.

        Args:
            owner_id (str): The ID of the owner of the card.
            name (Optional[str]): The name of the specific trap to create. If None,
                picks a random trap.

        Returns:
            Optional[TrapCard]: The instantiated TrapCard, or None if creation failed.
        """
        if not self._cards:
            return None

        if name:
            prototype = self._cards.get(name)
            if not prototype:
                return None
        else:
            prototype = random.choice(list(self._cards.values()))

        return TrapCard(
            name=prototype["name"],
            description=prototype.get("description", ""),
            owner_id=owner_id,
            image_path=prototype.get("_image_path"),
            abilities=prototype.get("abilities", []),
            activation=prototype.get("activation"),
            effectiveness=prototype.get("value"),
            duration=prototype.get("duration")
        )

    def get_cards(self) -> List[TrapCard]:
        """Returns the list of loaded trap prototypes.

        Returns:
            List[TrapCard]: The list of available trap card definitions.
        """
        return self._cards
