import random
import logging
from core.factory.monster_factory import MonsterFactory
from core.factory.spell_factory import SpellFactory
from core.factory.trap_factory import TrapFactory

logger = logging.getLogger(__name__)


class DrawSystem:
    def __init__(self):
        # Weighted probabilities for each card category
        self.generic_draw = {
            'monster': 50,
            'spell': 25,
            'trap': 25
        }

        # Initialize factories
        self.monster_factory = MonsterFactory()
        self.monster_factory.build()
        self.spell_factory = SpellFactory()
        self.spell_factory.build()
        self.trap_factory = TrapFactory()
        self.trap_factory.build()

        # Weighted tables for specific cards (or monster levels)
        self.draw_table = {
            "monster": {
                1: 99,  # Level 1 monsters are common
                2: 1,
                3: 0.001  # tiny but not zero
            },
            "spell": {
                "Mystical Space Typhoon": 10,
                "Call of the Brave": 15,
                "Maniac War": 25,
                "Aura Shield": 25,
                "Reinforcement": 20
            },
            "trap": {
                "Shattered Guard": 25,
                "Crippling Curse": 25,
                "Phantom Dodge": 20,
                "Mirror Strike": 10,
                "Weaken Summon": 15
            }
        }

    # -------------------------------
    # Utility: Weighted random choice
    # -------------------------------
    def rate(self, table: dict):
        """
        Weighted random choice from a dictionary {key: weight}.
        Uses total weight normalization. Falls back to uniform random
        if weights are invalid or zero.
        """
        if not table:
            raise ValueError("Empty table passed to rate().")

        keys, weights = zip(*table.items())
        try:
            weights = [float(w) if float(w) > 0 else 0 for w in weights]
        except Exception as e:
            logger.warning(f"Invalid weights in table: {e}")
            weights = [1] * len(keys)

        total = sum(weights)
        if total <= 0:
            logger.warning(
                "All weights are zero or invalid, falling back to uniform choice.")
            return random.choice(keys)

        return random.choices(keys, weights=weights, k=1)[0]

    # -------------------------------
    # Core: Draw a single card
    # -------------------------------
    def rate_card_draw(self, player_id: str):
        card_type = self.rate(self.generic_draw)
        card_key = self.rate(self.draw_table[card_type])
        card = None

        try:
            if card_type == 'monster':
                monster_type = random.choice(
                    ["Scholar", "Conqueror", "Forest Monster",
                        "Demon", "Forest Guard"]
                )
                card = self.monster_factory.load_by_type_and_level(
                    player_id, monster_type, card_key)
                if not card:
                    logger.warning(f"Missing monster L{card_key} for {
                                   monster_type}, using fallback.")
                    fallback_key = random.choice(
                        list(self.monster_factory.get_cards().keys()))
                    card = self.monster_factory.load(player_id, fallback_key)

            elif card_type == 'spell':
                card = self.spell_factory.load(player_id, card_key)

            elif card_type == 'trap':
                card = self.trap_factory.load(player_id, card_key)

        except Exception as e:
            logger.exception(f"Error drawing {card_type} ({card_key}): {e}")

        if not card:
            logger.error(f"Failed to load {card_type} '{
                         card_key}' even after fallback.")
        return card

    # -------------------------------
    # Debug / diagnostic
    # -------------------------------
    def check_draw_issues(self, player_id: str, attempts=1000):
        """
        Perform multiple draws to detect any cards that fail to load.
        """
        failures = []
        for _ in range(attempts):
            card_type = self.rate(self.generic_draw)
            card_key = self.rate(self.draw_table[card_type])

            card = None
            try:
                if card_type == 'monster':
                    monster_type = random.choice(
                        ["Scholar", "Conqueror", "Forest Monster",
                            "Demon", "Forest Guard"]
                    )
                    card = self.monster_factory.load_by_type_and_level(
                        player_id, monster_type, card_key)
                    if not card:
                        for fallback_key in self.monster_factory.get_cards().keys():
                            card = self.monster_factory.load(
                                player_id, fallback_key)
                            if card:
                                break
                elif card_type == "spell":
                    card = self.spell_factory.load(player_id, card_key)
                elif card_type == "trap":
                    card = self.trap_factory.load(player_id, card_key)

            except Exception as e:
                logger.exception(f"Exception while drawing {
                                 card_type} ({card_key}): {e}")

            if not card:
                failures.append((card_type, card_key))

        if failures:
            logger.warning(f"Found {len(failures)} problematic draws:")
            for f in failures:
                logger.warning(f" - Failed to draw {f[0]} card '{f[1]}'")
        else:
            logger.info(f"No draw issues found after {attempts} attempts.")
