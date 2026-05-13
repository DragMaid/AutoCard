import json
import random
from pathlib import Path
from typing import Optional, List
from core.cards.monster_card import MonsterCard
from core.factory.base_factory import BaseFactory
from core.factory.card_registry import CardRegistry
from core.cards.card import CardType
from core.config import config


class MonsterFactory(BaseFactory):
    DATA_FILE = Path("./assets/data/monsterInfo.json")

    def __init__(self):
        self._cards = {}
        CardRegistry.register(CardType.MONSTER, self)

    def build(self):
        """Load monster cards from JSON (nested format)."""
        if not self.DATA_FILE.exists():
            raise FileNotFoundError(f"{self.DATA_FILE} not found")

        with open(self.DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError(
                "Unsupported JSON format for monsters (expected dict)")

        for category, cards in data.items():
            for card_info in cards:
                enum_name = category.upper().replace(" ", "_")
                card_info["monster_type"] = enum_name
                card_info["star"] = card_info.get("star", 1)
                image_path = str(config.ASSET_DIR / card_info["texture"].lstrip("/"))
                card_info["_image_path"] = image_path
                self._cards[card_info["name"]] = card_info

    def load(self, owner_id: str, name: Optional[str] = None) -> MonsterCard:
        """Create a MonsterCard instance."""
        if not self._cards:
            return None

        if name:
            prototype = self._cards.get(name)
            if not prototype:
                return None
        else:
            prototype = random.choice(list(self._cards.values()))

        return MonsterCard(
            name=prototype["name"],
            description=prototype.get("description", ""),
            owner_id=owner_id,
            image_path=prototype.get("_image_path"),
            monster_type=prototype["monster_type"],
            attack=prototype.get("attack", 0),
            defend=prototype.get("defend", 0),
            star=prototype.get("star", 1)
        )

    def get_cards(self) -> List[MonsterCard]:
        return self._cards
