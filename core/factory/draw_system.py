import logging
import random
from typing import Any, Dict
from core.factory.card_registry import CardRegistry
from core.factory.monster_factory import MonsterFactory
from core.factory.spell_factory import SpellFactory
from core.factory.trap_factory import TrapFactory
from core.cards.card import CardType

logger = logging.getLogger(__name__)


class DrawSystem:
    """
    Handles weighted card draws for monsters, spells, and traps.
    """

    CARD_TYPE_WEIGHTS: Dict[str, int] = {
        CardType.MONSTER: 50,
        CardType.SPELL: 30,
        CardType.TRAP: 20,
    }

    DRAW_TABLES: Dict[str, Dict[Any, int]] = {
        CardType.MONSTER: {
            1: 74,
            2: 20,
            3: 5,
            4: 1,
        },
        CardType.SPELL: {
            "Mystical Space Typhoon": 15,
            "Call of the Brave": 10,
            "Maniac War": 15,
            "Aura Shield": 15,
            "Reinforcement": 45,
        },
        CardType.TRAP: {
            "Shattered Guard": 20,
            "Crippling Curse": 20,
            "Phantom Dodge": 20,
            "Mirror Strike": 20,
            "Weaken Summon": 20,
        },
    }

    def __init__(self):
        self.monster_factory = MonsterFactory()
        self.spell_factory = SpellFactory()
        self.trap_factory = TrapFactory()

        self.monster_factory.build()
        self.spell_factory.build()
        self.trap_factory.build()

    def draw(self, player_id: str):
        """
        Draw a card using weighted probabilities.
        """
        category = self._weighted_choice(self.CARD_TYPE_WEIGHTS)
        selection = self._weighted_choice(self.DRAW_TABLES[category])

        try:
            if category == CardType.MONSTER:
                return self._draw_monster(player_id, level=selection)

            return self._draw_named_card(
                player_id=player_id,
                category=category,
                card_name=selection,
            )

        except Exception:
            logger.exception(
                "Failed to draw card",
                extra={
                    "category": category,
                    "selection": selection,
                    "player_id": player_id,
                },
            )
            return None

    def _draw_named_card(
        self,
        player_id: str,
        category: CardType,
        card_name: str,
    ):
        """
        Draw a spell or trap card by name.
        """
        card = CardRegistry.create(category, player_id, card_name)

        if card is None:
            logger.error(
                "Failed to create card",
                extra={
                    "category": category,
                    "card_name": card_name,
                },
            )

        return card

    def _draw_monster(
        self,
        player_id: str,
        level: int,
    ):
        """
        Draw a monster matching the requested level.
        """
        factory = CardRegistry.get_factory(CardType.MONSTER)

        all_monsters = factory.get_cards()

        candidates = [
            name
            for name, info in all_monsters.items()
            if info.get("star") == level
        ]

        if not candidates:
            logger.warning(
                "No monsters found for level",
                extra={"level": level},
            )

            return factory.load(player_id)

        monster_name = random.choice(candidates)

        card = factory.load(player_id, monster_name)

        if card is None:
            logger.error(
                "Failed to load monster",
                extra={
                    "monster_name": monster_name,
                    "level": level,
                },
            )

        return card

    @staticmethod
    def _weighted_choice(table: Dict[Any, Any]) -> Any:
        """
        Select a weighted random item from a mapping.
        """
        if not table:
            raise ValueError("Weighted table cannot be empty.")

        normalized = {}

        for key, weight in table.items():
            try:
                normalized[key] = max(float(weight), 0)
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid weight encountered",
                    extra={
                        "key": key,
                        "weight": weight,
                    },
                )
                normalized[key] = 0

        total_weight = sum(normalized.values())

        if total_weight <= 0:
            logger.warning(
                "All weights invalid or zero. Falling back to uniform random.")
            return random.choice(list(table.keys()))

        return random.choices(
            population=list(normalized.keys()),
            weights=list(normalized.values()),
            k=1,
        )[0]
