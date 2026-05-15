import random
import logging
from pathlib import Path
from core.data.game_state import GameState, LogicCard
from typing import List, Optional
from core.cards.card import CardType
from logging.handlers import RotatingFileHandler

from core.cards.monster_card import MonsterType, MonsterCard
from core.factory.monster_factory import MonsterFactory


class DictFormatter(logging.Formatter):
    """Custom logging formatter that includes extra fields from the log record."""

    def format(self, record):
        base = super().format(record)

        extras = {
            k: v for k, v in record.__dict__.items()
            if k not in logging.LogRecord(
                None, None, "", 0, "", (), None
            ).__dict__
        }

        if extras:
            extra_str = " | " + " ".join(f"{k}={v}" for k, v in extras.items())
            return base + extra_str

        return base


def setup_logging(file: Optional[str] = None, debug: bool = False) -> None:
    """Configures logging for the application.

    Args:
        file: Optional path to a log file.
        debug: If True, sets log level to DEBUG.
    """
    level = logging.DEBUG if debug else logging.INFO

    formatter = DictFormatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    root = logging.getLogger()
    root.setLevel(level)

    root.handlers.clear()

    # Console output
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)

    logging.captureWarnings(True)

    # File output
    if file is not None:
        Path(file).parent.mkdir(exist_ok=True, parents=True)
        file_handler = RotatingFileHandler(file, maxBytes=5_000_000)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    root.addHandler(console)


def load_by_type_and_level(
    factory: MonsterFactory,
    player_id: str,
    monster_type: MonsterType,
    star: int
) -> Optional[MonsterCard]:
    """Specific loader for monsters filtering by type and level.

    Args:
        factory: The monster factory to use.
        player_id: The ID of the owner player.
        monster_type: The type of monster to filter by.
        star: The star level of the monster to filter by.

    Returns:
        A loaded MonsterCard instance, or None if not found.
    """
    candidates = [
        name for name, info in factory.get_cards().items()
        if info.get("monster_type") == monster_type
        and info.get("star") == star
    ]

    if not candidates:
        return None

    selected_name = random.choice(candidates)
    return factory.load(player_id, name=selected_name)


def get_cards_typed(
    game_state: GameState,
    player_id: str,
    card_type: CardType
) -> List[LogicCard]:
    """Get list of field cards that belong in same card_type."""
    cards = game_state.get_player_field_cards(player_id)
    return [c for c in cards if c.card_type == card_type]
