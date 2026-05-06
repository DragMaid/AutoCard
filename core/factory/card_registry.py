from pathlib import Path
import random


class CardRegistry:
    """
    Unified card registry for monsters, spells, and traps.
    Supports flat arrays or nested dicts in JSON.
    """
    _registry = {}

    @classmethod
    def build_from_file(cls, card_type: str, path: Path, CardClass, type_field=None):
        """
        Load cards from JSON into registry.

        card_type: 'monster', 'spell', or 'trap'
        path: Path to JSON file
        CardClass: class to instantiate cards
        type_field: optional field to store category type (for monsters)
        """
        if not path.exists():
            raise FileNotFoundError(f"{path} not found")

        import json
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        cls._registry[card_type] = {}

        if isinstance(data, dict):
            # Nested dict (monsters)
            for category, cards in data.items():
                for card_info in cards:
                    if card_info.get("texture"):
                        if type_field:
                            card_info[type_field] = category
                        card_info["_image_path"] = Path(
                            "./assets" + card_info["texture"])
                        cls._registry[card_type][card_info["name"]] = card_info
        elif isinstance(data, list):
            # Flat array (spells, traps)
            for card_info in data:
                if card_info.get("texture"):
                    card_info["_image_path"] = Path(
                        "./assets" + card_info["texture"])
                    cls._registry[card_type][card_info["name"]] = card_info
        else:
            raise ValueError("Unsupported JSON format")

    @classmethod
    def create(cls, card_type: str, owner_id: str, name: str | None = None):
        """Return a card instance for a player, optionally by name."""
        if card_type not in cls._registry:
            raise RuntimeError(f"Card type {card_type} not built yet")
        if not cls._registry[card_type]:
            return None

        if name:
            prototype = cls._registry[card_type].get(name)
            if not prototype:
                return None
        else:
            prototype = random.choice(list(cls._registry[card_type].values()))

        # Dynamically create card instance
        from core.cards.monster_card import MonsterCard
        from core.cards.spell_card import SpellCard
        from core.cards.trap_card import TrapCard

        CardClass = {
            "monster": MonsterCard,
            "spell": SpellCard,
            "trap": TrapCard
        }[card_type]

        # Monster specific fields
        kwargs = {
            "name": prototype["name"],
            "description": prototype.get("description", ""),
            "owner_id": owner_id,
            "image_path": prototype.get("_image_path")
        }

        if card_type == "monster":
            kwargs.update({
                "atk": prototype.get("attack_points", 0),
                "defend": prototype.get("defense_points", 0),
                "level_star": prototype.get("level_star", 1),
                "type": prototype.get("type", "Unknown")
            })
        else:
            # Spell/Trap fields
            kwargs.update({
                "ability": prototype.get("ability", ""),
                "value": prototype.get("value", None),
                "duration": prototype.get("duration", None)
            })

        return CardClass(**kwargs)

    @classmethod
    def list_cards(cls, card_type: str):
        return cls._registry.get(card_type, {})
