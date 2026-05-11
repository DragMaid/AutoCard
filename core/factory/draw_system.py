import random
from core.factory.monster_factory import MonsterFactory
from core.factory.spell_factory import SpellFactory
from core.factory.trap_factory import TrapFactory
from core.utils import get_logger

logger = get_logger(__name__)


class DrawSystem:
    def __init__(self):
        # Weighted probabilities for each card category
        self.generic_draw = {
            'monster': 50,
            'spell': 30,
            'trap': 20
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
                1: 74,   # Level 1 monsters are common
                2: 20,   # Level 2 are uncommon
                3: 5,    # Level 3 are rare
                4: 1     # Level 4 are very rare
            },
            "spell": {
                "Mystical Space Typhoon": 15,
                "Call of the Brave": 10,
                "Maniac War": 15,
                "Aura Shield": 15,
                "Reinforcement": 45  # Increased reinforcement draw rate
            },
            "trap": {
                "Shattered Guard": 20,
                "Crippling Curse": 20,
                "Phantom Dodge": 20,
                "Mirror Strike": 20,
                "Weaken Summon": 20
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
        except (ValueError, TypeError) as e:
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
        """
        Draws a card based on weighted probabilities.
        """
        card_type = self.rate(self.generic_draw)
        card_key = self.rate(self.draw_table[card_type])
        card = None

        try:
            if card_type == 'monster':
                # Dynamically get available monster types from factory
                all_monsters = self.monster_factory.get_cards()
                monster_types = list(set(
                    info.get("type") for info in all_monsters.values()
                    if info.get("type")
                ))

                if not monster_types:
                    logger.error("No monster types found in factory!")
                    return None

                monster_type = random.choice(monster_types)
                card = self.monster_factory.load_by_type_and_level(
                    player_id, monster_type, card_key)

                if not card:
                    # If specific level/type combo fails, try any monster of that level
                    logger.debug(f"Level {card_key} {
                                 monster_type} not found, trying any level {card_key} monster")
                    candidates = [
                        name for name, info in all_monsters.items()
                        if info.get("level_star") == card_key
                    ]
                    if candidates:
                        card = self.monster_factory.load(
                            player_id, random.choice(candidates))
                    else:
                        # Absolute fallback: draw any monster
                        card = self.monster_factory.load(player_id)

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
            card = self.rate_card_draw(player_id)
            if not card:
                # We need to know what failed, but rate_card_draw logs it.
                # For this diagnostic, we'll re-run a simplified check if needed
                # or just track null returns.
                failures.append("Unknown")

        if failures:
            logger.warning(f"Found {len(failures)} problematic draws out of {
                           attempts} attempts.")
        else:
            logger.info(f"No draw issues found after {attempts} attempts.")
