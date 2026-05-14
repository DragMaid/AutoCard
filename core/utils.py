import random
import logging
from core.cards.monster_card import MonsterType, MonsterCard
from core.factory.base_factory import BaseFactory
from typing import Optional
from logging.handlers import RotatingFileHandler


def setup_logging(file: Optional[str] = None, debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    root = logging.getLogger()
    root.setLevel(level)

    root.handlers.clear()

    # Console output
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)

    # File output
    if file is not None:
        file_handler = RotatingFileHandler(
            "game.log",
            maxBytes=5_000_000,
            backupCount=3
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    root.addHandler(console)


def load_by_type_and_level(
    factory: BaseFactory,
    player_id: str,
    monster_type: MonsterType,
    star: int
) -> Optional[MonsterCard]:
    """Specific loader for monsters filtering by type and level."""
    candidates = [
        name for name, info in factory.get_cards().items()
        if info.get("monster_type") == monster_type
        and info.get("star") == star
    ]

    if not candidates:
        return None

    selected_name = random.choice(candidates)
    return factory.load(player_id, name=selected_name)
