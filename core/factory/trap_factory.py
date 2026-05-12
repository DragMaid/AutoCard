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
    DATA_FILE = Path("./assets/data/trapInfo.json")

    def __init__(self):
        self._cards = {}
        CardRegistry.register(CardType.TRAP, self)

    def build(self):
        """Load trap cards from JSON (flat array)."""
        if not self.DATA_FILE.exists():
            raise FileNotFoundError(f"{self.DATA_FILE} not found")

        with open(self.DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError("Unsupported JSON format for traps (expected list)")

        for card_info in data:
            image_path = config.ASSET_DIR / card_info["texture"]
            card_info["_image_path"] = image_path
            self._cards[card_info["name"]] = card_info

    def load(self, owner_id: str, name: Optional[str] = None) -> Optional[TrapCard]:
        """Create a TrapCard instance."""
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
            image_path=str(prototype.get("_image_path")),
            ability=prototype.get("ability", []),
            activation=prototype.get("activation"),
            effectiveness=prototype.get("value"),
            duration=prototype.get("duration")
        )

    def get_cards(self) -> List[TrapCard]:
        return self._cards
